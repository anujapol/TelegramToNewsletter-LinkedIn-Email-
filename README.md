# Telegram to LinkedIn/Email Newsletter Automation

> An autonomous weekly pipeline that turns active Telegram community discussions into scroll-stopping LinkedIn content, delivered as a Gmail draft for human review. Built to surface the signal buried in busy group chats and convert it into measurable community growth.

---

## From Buried Signal to Community Growth

Active Telegram communities generate thousands of valuable messages per week, jobs, referrals, announcements, business proposals, but **over 90% of that signal stays trapped in the group, invisible to members not actively scrolling**. Meanwhile, parallel community surfaces like LinkedIn alumni groups (often 5x to 10x larger than the Telegram core) sit idle because nobody has the time to manually curate weekly recaps.

This project closes that gap with a **fully automated, $1/month pipeline** that runs every Monday morning. It pulls the week's discussions, applies category-aware ranking to surface what actually drives community action (jobs, networking, announcements over memes), and produces a publication-ready LinkedIn post in under 90 seconds of compute time. The output lands in your Gmail drafts for a 5-minute human review, then ships to LinkedIn to drive new and lapsed members back to the Telegram group.

**Outcome:** A repeatable weekly content engine that converts community activity into community growth, with zero infrastructure to maintain, full operational visibility, and built-in safety guardrails.

---

## The Problem 

Most active Telegram communities suffer from the same three failures:

| Problem | Impact |
|---|---|
| **Signal buried in volume.** A 1,500-member group can produce 2,000+ messages per week across 10+ topic threads. The most valuable posts (a Director-level job referral, an alumni meetup announcement, a startup partnership proposal) compete with hundreds of casual chats. | Members miss high-value opportunities. A job posting that should reach 20 to 50 prospective applicants in an active community might reach only 5 to 10 people if it lands during a busy thread. |
| **Audience fragmentation across surfaces.** A community typically exists on Telegram (the active core) and LinkedIn (the larger but passive ring). The two rarely cross-pollinate. | LinkedIn alumni groups with 6,000+ members generate near-zero engagement because the content surfaced there is not relevant or fresh. Telegram membership stagnates because new prospects do not see what they would be joining. |
| **Manual curation is unsustainable.** A weekly digest done by hand takes 60 to 90 minutes: scrolling threads, picking winners, writing teasers, formatting. Volunteers burn out within 4 to 6 weeks. | Communities that tried newsletters quit after a few editions. The signal stays trapped, and the audience continues to disengage. |

Combined effect: **a 6,000-member community with a 1,500-member active core typically converts only 5 to 8 new active members per quarter** organically, despite ample inbound interest.

---

## The Solution

A weekly automation that runs entirely without intervention except a 5-minute human review:

1. **Fetches** the past 7 days of messages from a Telegram supergroup, including topic threads, sender info, reactions, and replies
2. **Stores** every message in a Google Sheet that doubles as data layer and audit trail
3. **Ranks** posts using category-aware logic (job referrals always beat memes, even if memes get more reactions)
4. **Generates** a LinkedIn-ready post via Claude API, designed to create curiosity gaps that drive readers back to Telegram
5. **Delivers** the output as a Gmail draft for human review (catches LLM oddities before they go public)
6. **Logs** every run with status, errors, and metrics to a dedicated tab in the same Google Sheet
7. **Notifies** you on success (Telegram self-message) and on failure (dual Telegram + email alerts)

**Key result:** What used to take 90 minutes of manual work now takes 5 minutes of review. Posts are consistent in quality and tone. The LinkedIn group becomes a credible funnel for Telegram membership growth.

---

## System Architecture

```
┌─────────────────────────────┐
│  Telegram Supergroup        │
│  (with topic threads)       │
└──────────────┬──────────────┘
               │ Telethon (MTProto API)
               ▼
┌─────────────────────────────┐
│  Telegram Fetcher           │
│  - last 7 days              │
│  - dedupes vs sheet         │
│  - extracts engagement      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Google Sheets              │
│  Sheet1 = message archive   │
│  Run Log = ops history      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Category-Aware Ranker      │
│  Tier 1: jobs, announcements│
│  Tier 2: filler             │
│  Score = R×3 + Re×5 + L     │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Claude API                 │
│  Newsletter generator with  │
│  tuned LinkedIn prompt      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Gmail Draft                │
│  Human review → LinkedIn    │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Notifications              │
│  Success: Telegram message  │
│  Failure: Telegram + Email  │
└─────────────────────────────┘
```

### Tools that get automated end to end

| Stage | Tool | What gets automated |
|---|---|---|
| **Discovery** | Telegram (Telethon) | Authenticate, fetch all topics, extract messages with engagement metrics |
| **Storage** | Google Sheets | Append-only message archive, dedupe by message ID, audit log of every run |
| **Selection** | Python ranker | Category classification, tier-aware scoring, near-duplicate removal |
| **Generation** | Claude API | LinkedIn-format post with hook, bullets, CTA, hashtags |
| **Delivery** | Gmail API | Draft creation in user's Drafts folder |
| **Monitoring** | Telegram Saved Messages + Gmail | Success pings, failure alerts on 2 channels |
| **Scheduling** | GitHub Actions | Cron-driven weekly trigger, no server needed |
| **Secrets** | GitHub Actions Secrets | Encrypted at rest, redacted from logs, only available during runs |

### Features

- **Topic-aware extraction.** Handles forum-style supergroups with multiple topic threads, mapping each message to its correct topic
- **Engagement scoring with content priors.** Reactions, replies, and content length combine into a single rankable score, weighted by category priority
- **Near-duplicate dedup.** When users cross-post (e.g., a job referral posted in both Jobs and AI topics), the system picks one and skips the rest
- **Category fallback logic.** If priority topics had a quiet week, fillers from secondary topics keep the newsletter publishable rather than thin
- **Human-in-the-loop by design.** The system creates a draft, never auto-posts, preventing LLM oddities from going public
- **Dual notification channels.** Telegram messages and email alerts mean a failure in one channel never leaves you blind
- **Run Log for full observability.** Every run, success or failure, gets a timestamped row with metrics (messages fetched, length generated, duration, error)
- **Customizable prompt.** The LLM prompt is intentionally exposed in source code, designed to be tuned per community

---

## Architectural Decisions

The three calls that mattered most. These are the "why this and not that" decisions worth carrying into similar projects.

### 1. Google Sheets as the data layer (not a real database)

**Decision:** Use Google Sheets as the message store, with one row per message and a separate Run Log tab for ops history.

**Why this works for this project:**
- Free human-browsable UI during iteration. Inspecting a sheet is faster than running ad-hoc SQL when tuning topic mapping or sender extraction
- Zero infrastructure overhead. No connection strings, no migrations, no provisioning, no backup strategy
- Free tier covers 6+ years of data at typical community scale (10 million cells = ~1M messages)

**Where this would be wrong:**
- If multiple processes write concurrently (Sheets API has rate limits)
- If you need complex analytics queries over historical data
- If you grow past ~50,000 rows (browser becomes sluggish, though API stays fine)

**Migration path:** SQLite first (just swap read/write functions), Postgres only if you outgrow SQLite.

### 2. Category-aware ranking, not pure engagement

**Decision:** Classify every message into priority tiers based on its topic, then rank within tiers rather than globally by reactions.

**Why pure engagement ranking fails:** A funny meme reliably beats a job referral on raw reactions. If your goal is "drive engagement back to the group," the meme winning means the newsletter becomes entertainment-focused and loses its action-driving edge. People stop clicking through to Telegram because the LinkedIn post already gave them what they came for.

**Implementation:** Tier 1 (job referrals, announcements, networking, business proposals) always included if available. Tier 2 (everything else) used as filler when Tier 1 is light. Scoring: `reactions * 3 + replies * 5 + min(content_length / 100, 5)`.

**Where this would be wrong:** If your community is purely entertainment or social (e.g., a fandom group), engagement IS the goal and pure scoring is fine.

### 3. Human in the loop, never auto-post

**Decision:** Generate a Gmail draft. Never auto-post to LinkedIn.

**Why:**
- LLM outputs occasionally embarrass. A weird hallucination on a public LinkedIn post damages trust in ways that take months to recover
- LinkedIn API access for personal accounts is not viable; unofficial tooling violates ToS
- The act of reviewing the draft is when you spot prompt-tuning opportunities. Full automation cuts off this feedback loop

**The cost:** 5 minutes every Monday to read and post. For weekly cadence, this is a feature, not a bug.

**Where this would be wrong:** Very high frequency content (multiple posts per day) where the human bottleneck breaks. Then add a content-safety classifier between generation and posting.

---

## Technical Stack

| Layer | Technology | Why this choice |
|---|---|---|
| **Language** | Python 3.12 | Mature ecosystem for Telegram clients and Google APIs |
| **Telegram client** | Telethon 1.43+ | User-account auth (sees full history). Telegram bots cannot read messages they were not present for |
| **Data layer** | Google Sheets via gspread | Zero ops, free, human-browsable during iteration |
| **LLM** | Anthropic Claude (Opus model) | Strong nuanced writing for newsletter copy, predictable pricing |
| **Email** | Gmail API via google-api-python-client | Native draft creation in user's Drafts folder |
| **Auth: Sheets** | Google Cloud service account | Headless, no user interaction, scoped to specific sheets |
| **Auth: Gmail** | OAuth 2.0 (Desktop app type) | Required for sending/drafting on user's behalf |
| **Auth: Telegram** | Telethon string session | Portable across environments, stored as a single secret |
| **Scheduler** | GitHub Actions cron | Free for this volume, no server, built-in secrets management |
| **Secrets** | GitHub Actions Secrets | Encrypted with libsodium sealed boxes, auto-redacted from logs |
| **Observability** | Run Log tab in Google Sheet | Single source of operational truth, no separate logging service |

### Cost structure

| Service | Monthly Cost | Notes |
|---|---|---|
| GitHub Actions | $0 | ~5 min/week × 4 weeks well under 2,000 min free tier |
| Google APIs (Sheets + Drive + Gmail) | $0 | Free for personal use, no billing required |
| Telegram API | $0 | Free for user accounts |
| Anthropic API (Claude) | $0.40 to $1.20 | $0.10 to $0.30 per weekly run depending on volume |
| **Total** | **~$1/month** | |

Set an Anthropic spending alert at $5/month to catch runaway behavior.

---

## Repository Structure

```
.
├── .github/
│   └── workflows/
│       └── weekly.yml           # Cron schedule and CI workflow
├── docs/
│   ├── SETUP.md                 # Full deployment walkthrough
│   ├── ARCHITECTURE.md          # System design and trade-offs
│   ├── PROMPT_TUNING.md         # How to adjust the LLM newsletter style
│   └── TROUBLESHOOTING.md       # Common failure modes and fixes
├── .env.example                 # Template env file with placeholders
├── .gitignore                   # Excludes secrets and venv
├── LICENSE                      # MIT
├── README.md                    # This file
├── requirements.txt             # Python dependencies
└── run_weekly.py                # Main script (fetch + generate + notify)
```

---

## Prerequisites

Before deploying, ensure you have:

- **A Telegram account** that is already a member of the target group
- **A GitHub account** (free tier works fine)
- **A Google account** with access to Google Cloud Console
- **An Anthropic Console account** with billing enabled (~$2/month expected)
- **Python 3.10+** installed locally
- **Git** installed locally
- **2 to 3 hours** of focused setup time

---

## Quick Start Guide

Full walkthrough in [docs/SETUP.md](docs/SETUP.md). High level:

### 1. Get API credentials

- Telegram: get `api_id` and `api_hash` from https://my.telegram.org
- Anthropic: create API key at https://console.anthropic.com/settings/keys
- Google Cloud: create project, enable Sheets / Drive / Gmail APIs

### 2. Set up Google services

- Create a Google Sheet, share with a service account
- Create OAuth credentials for Gmail draft access
- **Publish your OAuth app** (otherwise refresh tokens expire weekly)

### 3. Configure local environment

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_FORK.git
cd YOUR_FORK
python -m venv venv
source venv/bin/activate    # Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your real values
```

### 4. Test locally

```bash
python run_weekly.py
```

Verify a Gmail draft was created, a Telegram self-notification arrived, and a Run Log row appears in your sheet.

### 5. Deploy to GitHub Actions

- Generate a Telegram session string (one-time bootstrap)
- Push code to your private GitHub repo
- Add all 11 secrets to GitHub Actions Secrets
- Manually trigger the workflow once to verify
- Cron then fires weekly on schedule

### 6. Tune the prompt over the first 2 to 3 weekly runs

See [docs/PROMPT_TUNING.md](docs/PROMPT_TUNING.md). Most tuning involves tone, length, and bullet category labels.

---

## Customization

This is a template. To adapt for your community:

- **Group and topics:** edit `GROUP_NAME` in `.env`. Update `TIER_1_TOPICS` and `TIER_2_TOPICS_FALLBACK` in `run_weekly.py` to match your group's actual topic names
- **Newsletter tone:** edit the `build_prompt` function in `run_weekly.py`. See [docs/PROMPT_TUNING.md](docs/PROMPT_TUNING.md)
- **Schedule:** edit the cron expression in `.github/workflows/weekly.yml`. Default is Mondays at 16:00 UTC (~9 AM Pacific)
- **Output destination:** the script creates a Gmail draft by default. To send to Slack, Discord, or another destination, replace the `create_gmail_draft` call

---

## Security Notes

This system handles sensitive credentials:

- **Telegram session string** authenticates as your personal account, treat like a password
- **Anthropic API key** is billed to your account
- **Google service account JSON** has Editor access to your sheet
- **Gmail OAuth token** can read and send mail from your account

All credentials belong in **GitHub Actions Secrets** for production, never in code. The included `.gitignore` excludes all credential files. Do not bypass it.

If a secret is compromised, rotate immediately. See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for the response checklist.

---

## Limitations and Known Issues

- **Private Telegram group links** open the Telegram app, not the web client. Acceptable since recipients are typically already group members
- **Gmail OAuth in "Testing" mode** rotates refresh tokens every 7 days. The setup guide walks you through publishing to fix this
- **Reactions vs replies in topic supergroups:** Telegram's `msg.replies.replies` is meaningful for channels but not for topics within supergroups. The ranking weighs reactions more heavily as a result
- **Single group only:** the script handles one supergroup at a time. To monitor multiple groups, parameterize the workflow
- **English-only prompt:** the included prompt is tuned for English. Adapt as needed for other languages

---

## Contributing

This is shared as a template, not an actively maintained product. If you adapt it for your community and find improvements worth contributing back, open a pull request.

If you build something interesting on top of this, I would love to hear about it.

---

## License

MIT. See [LICENSE](LICENSE).

Built with [Telethon](https://github.com/LonamiWebs/Telethon), [gspread](https://github.com/burnash/gspread), and the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python).
