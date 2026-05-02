"""
Telegram to LinkedIn Newsletter: production weekly runner.

Combines fetch + generate + notify in a single atomic workflow:
  1. Fetch last N days of messages from a Telegram supergroup into Google Sheets
  2. Filter and rank using category-aware scoring
  3. Generate LinkedIn-ready post via Claude API
  4. Create Gmail draft for human review
  5. Send Telegram self-notification on success
  6. Log run status to a Run Log tab in the same Google Sheet
  7. Send dual failure notifications (Telegram + email) on error
"""

import os
import sys
import json
import base64
import asyncio
import traceback
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetForumTopicsRequest

import gspread
from google.oauth2.service_account import Credentials as ServiceCreds
from google.oauth2.credentials import Credentials as UserCreds
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from anthropic import Anthropic

load_dotenv()

# =============================================================================
# Configuration
# =============================================================================

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
SESSION_STRING = os.getenv("TELEGRAM_SESSION_STRING", "")
GROUP_NAME = os.getenv("GROUP_NAME", "Your Group Name Here")

SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
RECIPIENT = os.getenv("GMAIL_RECIPIENT")
CONTACT_FOR_GROUP_ACCESS = os.getenv("CONTACT_FOR_GROUP_ACCESS", "Group Admin on Telegram")

DAYS_BACK = 7
FETCH_BUFFER_DAYS = 8  # fetch slightly more than we generate from
RUN_LOG_TAB = "Run Log"
DATA_TAB = "Sheet1"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]

# =============================================================================
# Topic prioritization (CUSTOMIZE FOR YOUR COMMUNITY)
# =============================================================================
# Tier 1 topics are always included if available. These should be the topics
# whose content drives the audience action you want (e.g., job opportunities,
# announcements, networking).
#
# Tier 2 topics are filler if Tier 1 is light. These should be topics that
# generate engagement but are not your primary call-to-action drivers.

TIER_1_TOPICS = {
    # Replace these with your actual Telegram topic names
    "Jobs and Referrals",
    "Official Announcements",
    "Networking and Meet-ups",
    "Business Proposals",
    "Startups and Entrepreneurs",
}

TIER_2_TOPICS_FALLBACK = {
    # Replace these with your actual Telegram topic names
    "Mentorship",
    "Technology",
    "Finance and Investing",
    "Travel",
    "Education",
    "General Discussion",
    "Social",
}


# =============================================================================
# Google Sheets helpers
# =============================================================================

def get_sheets_client():
    """Return an authenticated gspread client.

    Supports two modes:
      - Local: reads from service_account.json file
      - Production: reads from SERVICE_ACCOUNT_JSON env var (GitHub Actions)
    """
    if os.path.exists("service_account.json"):
        creds = ServiceCreds.from_service_account_file(
            "service_account.json", scopes=SHEETS_SCOPES
        )
    else:
        sa_json = os.getenv("SERVICE_ACCOUNT_JSON")
        if not sa_json:
            raise RuntimeError(
                "No service_account.json file or SERVICE_ACCOUNT_JSON env var found"
            )
        creds = ServiceCreds.from_service_account_info(
            json.loads(sa_json), scopes=SHEETS_SCOPES
        )
    return gspread.authorize(creds)


def get_or_create_run_log_tab(spreadsheet):
    """Ensure the Run Log tab exists with proper headers."""
    try:
        return spreadsheet.worksheet(RUN_LOG_TAB)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=RUN_LOG_TAB, rows=1000, cols=10)
        ws.append_row([
            "Timestamp",
            "Status",
            "Step",
            "Messages Fetched",
            "Messages Selected",
            "Newsletter Length",
            "Duration (s)",
            "Error",
        ])
        return ws


def log_run(spreadsheet, status, step, messages_fetched=0, messages_selected=0,
            newsletter_length=0, duration=0, error=""):
    """Append a run record to the Run Log tab."""
    try:
        log = get_or_create_run_log_tab(spreadsheet)
        log.append_row([
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            status,
            step,
            messages_fetched,
            messages_selected,
            newsletter_length,
            round(duration, 1),
            error[:500] if error else "",
        ], value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"Warning: failed to write run log: {e}")


# =============================================================================
# Telegram helpers
# =============================================================================

async def fetch_telegram_messages(spreadsheet):
    """Pull recent messages from the supergroup into the data tab.

    Deduplicates against existing message IDs so it can be run repeatedly
    without creating duplicate rows.
    """
    print("Connecting to Telegram...")

    if SESSION_STRING:
        client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    else:
        client = TelegramClient("local_session", API_ID, API_HASH)

    await client.start()
    print("Telegram connected.")

    target = None
    async for dialog in client.iter_dialogs():
        if dialog.name == GROUP_NAME:
            target = dialog.entity
            break

    if not target:
        await client.disconnect()
        raise RuntimeError(f"Group '{GROUP_NAME}' not found in dialogs")

    group_username = getattr(target, "username", None) or f"c/{target.id}"

    # Fetch forum topics if this is a topic-based supergroup
    topics_map = {}
    if getattr(target, "forum", False):
        result = await client(
            GetForumTopicsRequest(
                peer=target,
                offset_date=None,
                offset_id=0,
                offset_topic=0,
                limit=100,
            )
        )
        for topic in result.topics:
            if hasattr(topic, "id") and hasattr(topic, "title"):
                topics_map[topic.id] = topic.title

    sheet = spreadsheet.worksheet(DATA_TAB)
    existing_ids = set(sheet.col_values(1)[1:])  # skip header row

    cutoff = datetime.now(timezone.utc) - timedelta(days=FETCH_BUFFER_DAYS)
    new_rows = []

    async for msg in client.iter_messages(target):
        if msg.date < cutoff:
            break
        if str(msg.id) in existing_ids:
            continue

        # Identify which topic the message belongs to
        topic_id = None
        if msg.reply_to and getattr(msg.reply_to, "forum_topic", False):
            topic_id = msg.reply_to.reply_to_top_id or msg.reply_to.reply_to_msg_id
        topic_name = topics_map.get(topic_id, "General")

        sender = ""
        if msg.sender:
            sender = (
                getattr(msg.sender, "first_name", "")
                or getattr(msg.sender, "title", "")
                or "Unknown"
            )
            last = getattr(msg.sender, "last_name", "")
            if last:
                sender = f"{sender} {last}".strip()

        timestamp = msg.date.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        content = (msg.message or "").replace("\n", " ").strip()

        reply_count = msg.replies.replies if msg.replies else 0
        reactions = (
            sum(r.count for r in msg.reactions.results)
            if msg.reactions and msg.reactions.results
            else 0
        )

        has_media = bool(msg.media)
        week = msg.date.astimezone(timezone.utc).strftime("%Y-W%V")
        link = f"https://t.me/{group_username}/{msg.id}" if group_username else ""

        new_rows.append([
            str(msg.id),
            topic_name,
            sender,
            timestamp,
            content,
            reply_count,
            reactions,
            "TRUE" if has_media else "FALSE",
            week,
            link,
        ])

    if new_rows:
        sheet.append_rows(new_rows, value_input_option="USER_ENTERED")

    print(f"Fetched {len(new_rows)} new messages.")
    await client.disconnect()
    return len(new_rows)


async def send_telegram_self_notification(message_text):
    """Send a message to your own Telegram Saved Messages."""
    if SESSION_STRING:
        client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    else:
        client = TelegramClient("local_session", API_ID, API_HASH)

    await client.start()
    me = await client.get_me()
    await client.send_message(me, message_text)
    await client.disconnect()


# =============================================================================
# Newsletter generation
# =============================================================================

def filter_recent_messages(rows):
    """Keep messages from the last N days with non-trivial content."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    filtered = []
    for row in rows:
        try:
            ts_str = row.get("Timestamp", "")
            if not ts_str:
                continue
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            if ts < cutoff:
                continue
            content = (row.get("Content") or "").strip()
            if not content or len(content) < 20:
                # Skip very short messages and media-only posts
                continue
            filtered.append(row)
        except Exception:
            continue
    return filtered


def score_message(row):
    """Compute engagement score: reactions weighted, replies weighted higher,
    plus a small bonus for content length (caps at 5)."""
    try:
        reactions = int(row.get("Reactions") or 0)
    except (ValueError, TypeError):
        reactions = 0
    try:
        replies = int(row.get("Reply Count") or 0)
    except (ValueError, TypeError):
        replies = 0
    content = row.get("Content") or ""
    length_bonus = min(len(content) / 100, 5)
    return reactions * 3 + replies * 5 + length_bonus


def select_top_posts(messages, target_count=7):
    """Select top posts using category-aware scoring.

    Tier 1 topics (priority categories) are pulled first.
    Tier 2 topics are used as filler if Tier 1 yields fewer than target_count.
    Also deduplicates near-identical cross-posts from the same sender.
    """
    tier_1 = [m for m in messages if m.get("Topic") in TIER_1_TOPICS]
    tier_2 = [m for m in messages if m.get("Topic") in TIER_2_TOPICS_FALLBACK]

    tier_1_sorted = sorted(tier_1, key=score_message, reverse=True)
    tier_2_sorted = sorted(tier_2, key=score_message, reverse=True)

    seen_signatures = set()
    deduped_t1 = []
    for m in tier_1_sorted:
        sig = (m.get("Sender", ""), (m.get("Content") or "")[:80])
        if sig in seen_signatures:
            continue
        seen_signatures.add(sig)
        deduped_t1.append(m)

    deduped_t2 = []
    for m in tier_2_sorted:
        sig = (m.get("Sender", ""), (m.get("Content") or "")[:80])
        if sig in seen_signatures:
            continue
        seen_signatures.add(sig)
        deduped_t2.append(m)

    selected = deduped_t1[:target_count]
    if len(selected) < target_count:
        needed = target_count - len(selected)
        selected.extend(deduped_t2[:needed])
    return selected


def build_prompt(posts, week_label):
    """Build the LLM prompt for newsletter generation.

    Customize this function to match your community's tone and goals.
    See docs/PROMPT_TUNING.md for guidance.
    """
    posts_text = ""
    for i, p in enumerate(posts, 1):
        posts_text += f"\n[Post {i}]\n"
        posts_text += f"Topic: {p.get('Topic')}\n"
        posts_text += f"Content: {p.get('Content')}\n"
        posts_text += f"Reactions: {p.get('Reactions', 0)} | Replies: {p.get('Reply Count', 0)}\n"
        posts_text += f"Link: {p.get('Message Link')}\n"

    prompt = f"""You are writing a LinkedIn post that summarizes the week's most interesting discussions from a private Telegram community group. The goal is to drive engagement back to the Telegram group by teasing what is happening there.

WEEK: {week_label}

POSTS FROM TELEGRAM THIS WEEK:
{posts_text}

WRITING REQUIREMENTS:

OPENING HOOK (most important):
- First line must stop the scroll
- Single line, under 100 characters, ends with curiosity
- Examples: "While you were heads down at work this week, your network was busy."

VISUAL STRUCTURE (critical for LinkedIn):
- Hook line, blank line, framing line, blank line
- 6 to 7 bullets each on its own line, separated by blank lines for breathing room
- Soft transition line before CTA
- CTA: "Not in the Telegram group yet? Contact {CONTACT_FOR_GROUP_ACCESS} to get added."
- Blank line, hashtags

BULLET FORMATTING:
- Use the Unicode triangle character (U+25B8) at the start of each bullet
- Each bullet is one tight line, max 2 lines
- Format: "[Category]: [the hook] [link]"
- Categories vary: Hiring now, On the table, Heads up, In demand, Worth a read, Just dropped, Quick win

TONE AND VOICE:
- Punchy, declarative, professional but warm
- Each line earns its place
- No em dashes (use commas, periods, colons)
- No filler phrases
- Generalize, never name individuals (say "an alum" or "a senior leader" not real names)
- Active voice
- Specific over vague

LENGTH: 1400 to 1600 characters total including hashtags

HASHTAGS: 4 to 6, mix of brand and topical

Output ONLY the LinkedIn post text. No preamble, no markdown fences. Preserve all blank lines."""
    return prompt


def generate_newsletter(posts, week_label):
    """Call Claude API to generate the LinkedIn post."""
    client = Anthropic(api_key=ANTHROPIC_KEY)
    prompt = build_prompt(posts, week_label)
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# =============================================================================
# Gmail helpers
# =============================================================================

def get_gmail_service():
    """Authenticate and return a Gmail API service client.

    Supports two modes:
      - Local: reads/writes gmail_token.json on disk
      - Production: writes JSON env vars to disk at startup, uses normal flow
    """
    creds = None
    token_path = "gmail_token.json"

    # In CI: write env JSON to disk before normal auth flow
    if os.getenv("GMAIL_TOKEN_JSON") and not os.path.exists(token_path):
        with open(token_path, "w") as f:
            f.write(os.getenv("GMAIL_TOKEN_JSON"))

    if os.getenv("GMAIL_CREDENTIALS_JSON") and not os.path.exists("gmail_credentials.json"):
        with open("gmail_credentials.json", "w") as f:
            f.write(os.getenv("GMAIL_CREDENTIALS_JSON"))

    if os.path.exists(token_path):
        creds = UserCreds.from_authorized_user_file(token_path, GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "w") as f:
                f.write(creds.to_json())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "gmail_credentials.json", GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
            with open(token_path, "w") as f:
                f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def create_gmail_draft(service, subject, body, recipient):
    """Create a Gmail draft (does not send)."""
    message = MIMEText(body)
    message["to"] = recipient
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()


def send_gmail_alert(service, subject, body, recipient):
    """Send (not draft) a notification email - used for failure alerts."""
    message = MIMEText(body)
    message["to"] = recipient
    message["from"] = recipient
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()


# =============================================================================
# Main orchestration
# =============================================================================

async def run():
    started_at = datetime.now(timezone.utc)
    sheets_client = get_sheets_client()
    spreadsheet = sheets_client.open_by_key(SHEET_ID)
    current_step = "init"

    try:
        # Step 1: Fetch
        current_step = "fetch_telegram"
        print(f"\n=== Step 1: Fetching Telegram messages ===")
        fetched_count = await fetch_telegram_messages(spreadsheet)

        # Step 2: Read sheet for newsletter generation
        current_step = "read_sheet"
        print(f"\n=== Step 2: Reading sheet for selection ===")
        sheet = spreadsheet.worksheet(DATA_TAB)
        all_rows = sheet.get_all_records()
        recent = filter_recent_messages(all_rows)
        print(f"Recent messages: {len(recent)}")

        if not recent:
            raise RuntimeError("No recent messages to summarize")

        # Step 3: Select top posts
        current_step = "select_posts"
        print(f"\n=== Step 3: Selecting top posts ===")
        selected = select_top_posts(recent, target_count=7)
        print(f"Selected {len(selected)} posts")

        # Step 4: Generate newsletter
        current_step = "generate_newsletter"
        print(f"\n=== Step 4: Generating newsletter via Claude ===")
        week_label = datetime.now().strftime("Week of %B %d, %Y")
        newsletter = generate_newsletter(selected, week_label)
        print(f"Generated {len(newsletter)} character newsletter")

        # Step 5: Create Gmail draft
        current_step = "create_draft"
        print(f"\n=== Step 5: Creating Gmail draft ===")
        gmail_service = get_gmail_service()
        subject = f"Telegram Weekly Digest: {week_label}"
        create_gmail_draft(gmail_service, subject, newsletter, RECIPIENT)
        print(f"Draft created in {RECIPIENT}")

        # Step 6: Telegram self-notification
        current_step = "telegram_notify"
        print(f"\n=== Step 6: Sending Telegram notification ===")
        notification_text = (
            f"Newsletter generated successfully\n\n"
            f"Week: {week_label}\n"
            f"Messages fetched: {fetched_count}\n"
            f"Posts selected: {len(selected)}\n"
            f"Newsletter length: {len(newsletter)} chars\n\n"
            f"Check your Gmail drafts for: {subject}"
        )
        await send_telegram_self_notification(notification_text)
        print("Telegram notification sent.")

        # Log success
        duration = (datetime.now(timezone.utc) - started_at).total_seconds()
        log_run(
            spreadsheet,
            status="SUCCESS",
            step="complete",
            messages_fetched=fetched_count,
            messages_selected=len(selected),
            newsletter_length=len(newsletter),
            duration=duration,
        )
        print(f"\n=== DONE in {duration:.1f}s ===")

    except Exception as e:
        duration = (datetime.now(timezone.utc) - started_at).total_seconds()
        error_text = f"{type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}"
        print(f"\n=== FAILED at step '{current_step}' ===")
        print(error_text)

        # Log failure
        log_run(
            spreadsheet,
            status="FAILURE",
            step=current_step,
            duration=duration,
            error=error_text,
        )

        # Notify via Telegram
        try:
            failure_msg = (
                f"Newsletter run FAILED\n\n"
                f"Step: {current_step}\n"
                f"Error: {type(e).__name__}: {str(e)[:200]}\n\n"
                f"Check Run Log in the sheet for full traceback."
            )
            await send_telegram_self_notification(failure_msg)
        except Exception as notify_err:
            print(f"Could not send Telegram alert: {notify_err}")

        # Notify via email
        try:
            gmail_service = get_gmail_service()
            send_gmail_alert(
                gmail_service,
                subject=f"Newsletter FAILED at {current_step}",
                body=f"The weekly newsletter run failed.\n\nStep: {current_step}\n\n{error_text}",
                recipient=RECIPIENT,
            )
        except Exception as notify_err:
            print(f"Could not send email alert: {notify_err}")

        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
