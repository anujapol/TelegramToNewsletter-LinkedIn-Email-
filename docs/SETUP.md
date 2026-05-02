# Setup Guide

End-to-end walkthrough from zero to a deployed weekly automation.

**Total time: 2 to 3 hours** for someone comfortable with command-line basics. First-timers should plan a half day.

## Phase 0: Prerequisites

Before starting, you need:

- **Telegram account** that is already a member of the target group
- **GitHub account** (free)
- **Google account** with access to Google Cloud Console
- **Anthropic Console account** with billing enabled (~$2/month expected)
- **Local machine** with Python 3.10+ and Git installed
- **Comfort with PowerShell or Terminal**

If you do not have Python installed:
- Windows: download from https://python.org, **check "Add to PATH"** during install
- Mac: `brew install python` or download from python.org
- Linux: `apt install python3-venv python3-pip` or equivalent

If you do not have Git installed:
- Windows: https://git-scm.com/download/win
- Mac: `brew install git`
- Linux: `apt install git` or equivalent

---

## Phase 1: Clone and prepare locally

### 1.1 Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_FORK.git
cd YOUR_FORK
```

Or if you are starting fresh, fork this template first via GitHub UI then clone your fork.

### 1.2 Create virtual environment and install dependencies

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activation script:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Type Y, press Enter, retry activation.

**Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

You should see `(venv)` at the start of your prompt after activation.

### 1.3 Create your .env file

```bash
cp .env.example .env
```

Edit `.env` in your favorite editor. We will fill in values as we go.

---

## Phase 2: Telegram API credentials

### 2.1 Get your API ID and hash

1. Go to https://my.telegram.org
2. Log in with your phone number (the one tied to your Telegram account)
3. Enter the login code Telegram sends you (in-app, not SMS)
4. Click "API development tools"
5. Fill the form:
   - App title: anything (e.g., "My Newsletter")
   - Short name: anything alphanumeric
   - URL: leave blank or use `http://localhost`
   - Platform: Desktop
   - Description: anything
6. Click Create application
7. Copy `api_id` and `api_hash`

### 2.2 Add to .env

```
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_actual_hash
TELEGRAM_PHONE=+1XXXXXXXXXX
```

Phone must include country code, no spaces or dashes.

### 2.3 Set the group name

Find the exact display name of your Telegram supergroup. Open Telegram, click the group, copy the name as shown at the top.

```
GROUP_NAME=Your Exact Group Name
```

The match is case-sensitive and exact.

---

## Phase 3: Google Cloud setup

### 3.1 Create a Google Cloud project

1. Go to https://console.cloud.google.com
2. Click the project dropdown at top, click "New Project"
3. Name: "Newsletter Automation" or similar
4. Click Create

### 3.2 Enable the required APIs

In the search bar at the top, find and enable each:
- **Google Sheets API** → click Enable
- **Google Drive API** → click Enable
- **Gmail API** → click Enable

### 3.3 Create a service account (for Sheets access)

1. Navigation: APIs & Services → Credentials
2. Click "Create Credentials" → "Service Account"
3. Name: `sheets-writer` or similar
4. Click "Create and Continue", skip the optional steps, click "Done"
5. Click on the service account you just created
6. Go to "Keys" tab
7. Click "Add Key" → "Create new key" → JSON
8. A JSON file downloads. Save it as `service_account.json` in your project folder.
9. Open the JSON, find `client_email` (looks like `sheets-writer@your-project.iam.gserviceaccount.com`). Copy this email.

### 3.4 Create OAuth credentials (for Gmail draft)

1. In Cloud Console, search for "OAuth consent screen" (under APIs & Services)
2. If prompted, click "Get Started" or follow the wizard:
   - App name: "Newsletter Automation"
   - User support email: your email
   - Audience: External
   - Developer contact: your email
   - Agree to policies, click Continue/Create
3. Go to "Audience" tab, scroll to "Test users", click "Add users", add your own email, save
4. Go to "Credentials" tab
5. Click "Create Credentials" → "OAuth client ID"
6. Application type: Desktop app
7. Name: anything
8. Click Create
9. Download the JSON file, save as `gmail_credentials.json` in your project folder

---

## Phase 4: Create the Google Sheet

1. Go to https://sheets.google.com
2. Create a new blank sheet, name it (e.g., "Telegram Messages")
3. In row 1, add these column headers across A1 to J1:
   ```
   Message ID | Topic | Sender | Timestamp | Content | Reply Count | Reactions | Has Media | Week | Message Link
   ```
4. Click Share, paste the service account email from Phase 3.3
5. Set permission to Editor
6. **Uncheck "Notify people"** (service accounts cannot receive email)
7. Click Share. Confirm "share anyway" if prompted.
8. Copy the sheet ID from the URL: `https://docs.google.com/spreadsheets/d/THIS_PART_HERE/edit`

### 4.1 Add to .env

```
GOOGLE_SHEET_ID=your_sheet_id_here
```

---

## Phase 5: Anthropic API key

1. Go to https://console.anthropic.com
2. Sign up if you have not, add a payment method (you can set a low spending limit)
3. Go to https://console.anthropic.com/settings/keys
4. Click "Create Key"
5. Name: "newsletter-automation"
6. Copy the key starting with `sk-ant-api03-...`

### 5.1 Add to .env

```
ANTHROPIC_API_KEY=sk-ant-api03-your-key
```

### 5.2 Other .env values

```
GMAIL_RECIPIENT=your-email@gmail.com
CONTACT_FOR_GROUP_ACCESS=Group Admin Name on Telegram
```

`CONTACT_FOR_GROUP_ACCESS` is whatever instruction makes sense for how new readers should reach the group admin (e.g., "Jane Doe on Telegram", "DM @groupadmin", etc.).

---

## Phase 6: Customize topic priorities

Open `run_weekly.py`. Find these sections (around line 60):

```python
TIER_1_TOPICS = {
    "Jobs and Referrals",
    "Official Announcements",
    "Networking and Meet-ups",
    "Business Proposals",
    "Startups and Entrepreneurs",
}

TIER_2_TOPICS_FALLBACK = {
    "Mentorship",
    "Technology",
    ...
}
```

Replace these with the **exact topic names** as they appear in your Telegram group. Topic names are case-sensitive.

To see the exact topic names, the easiest way is to run the fetcher once and look at the Topic column in your sheet. If you do not match exactly, posts from those topics get classified as "General" (Tier 2) instead of Tier 1.

---

## Phase 7: First local run

With venv active and `.env` filled in:

```bash
python run_weekly.py
```

### What happens on first run

1. **Telegram authentication prompt:** Enter the code Telegram sends to your app
2. **2FA prompt** if you have it enabled
3. A `local_session.session` file is created (cached auth)
4. **Browser opens for Gmail OAuth:** click Advanced → "Go to (unsafe)" → grant permissions
5. A `gmail_token.json` file is created
6. Script proceeds through 6 steps
7. You should see:
   - A Gmail draft in your Drafts folder titled "Telegram Weekly Digest..."
   - A Telegram message in your Saved Messages
   - A new "Run Log" tab in your Google Sheet
   - Console output ending with `=== DONE ===`

### If something fails

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Common causes:
- Topic name mismatch (run anyway, just check Topic column)
- 2FA password missing
- OAuth consent screen not configured
- Service account not shared on the sheet

---

## Phase 8: Migration to GitHub Actions (production)

Once local runs work, deploy to production.

### 8.1 Generate Telegram session string

Create a one-time bootstrap script:

```bash
cat > generate_session.py << 'EOF'
import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
load_dotenv()
API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print(client.session.save())
EOF
python generate_session.py
```

Copy the long string output. **Do not save it to a file or commit it.** Delete the script:

```bash
rm generate_session.py
```

### 8.2 Make the OAuth app "Published" (critical)

By default, OAuth apps in "Testing" mode rotate refresh tokens every 7 days. Production needs them to last forever.

1. Cloud Console → OAuth consent screen (or "Audience" in newer UI)
2. Click "Publish app"
3. Confirm
4. Status changes to "In production"
5. Verification is NOT required for personal use (just yourself)

After publishing, regenerate your local token:

```bash
rm gmail_token.json
python run_weekly.py
```

The browser flow opens again. After completing it, you have a long-lived token in `gmail_token.json`.

### 8.3 Push code to a private GitHub repo

**Critical:** Verify `.gitignore` is excluding secrets BEFORE first commit.

```bash
git status
```

The output should NOT list any of: `.env`, `service_account.json`, `gmail_credentials.json`, `gmail_token.json`, `*.session`. If any appear, do not commit. Verify your `.gitignore`.

If clean:

```bash
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 8.4 Add GitHub Actions secrets

In your repo: Settings → Secrets and variables → Actions → "New repository secret"

Add each:

| Secret Name | Value |
|---|---|
| `TELEGRAM_API_ID` | from .env |
| `TELEGRAM_API_HASH` | from .env |
| `TELEGRAM_SESSION_STRING` | from Phase 8.1 |
| `GROUP_NAME` | from .env |
| `GOOGLE_SHEET_ID` | from .env |
| `ANTHROPIC_API_KEY` | from .env |
| `GMAIL_RECIPIENT` | from .env |
| `CONTACT_FOR_GROUP_ACCESS` | from .env |
| `SERVICE_ACCOUNT_JSON` | entire contents of service_account.json |
| `GMAIL_CREDENTIALS_JSON` | entire contents of gmail_credentials.json |
| `GMAIL_TOKEN_JSON` | entire contents of gmail_token.json |

For JSON values: open the file, select all, copy, paste the entire content (including outer braces) into the secret value field.

### 8.5 Adjust the cron schedule

Open `.github/workflows/weekly.yml`. Default schedule is `0 16 * * 1` (Mondays at 16:00 UTC, ~9 AM Pacific).

Use https://crontab.guru/ to design your schedule. Examples:
- `0 14 * * 1` - Mondays at 14:00 UTC (~9 AM Eastern)
- `0 9 * * 0` - Sundays at 9:00 UTC (~5 AM Eastern Sunday morning, ready for Monday)
- `0 13 * * 5` - Fridays at 13:00 UTC

Commit and push the change.

### 8.6 Trigger a manual test run

1. Go to repo → Actions tab
2. Click "Weekly Newsletter" in the left sidebar
3. Click "Run workflow" button (right side)
4. Leave branch as main, click "Run workflow"
5. Refresh the page, click into the new run
6. Watch live logs

If green check: deployment is live. The cron will fire on schedule from now on.
If red X: open the failed step, read the error, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## Phase 9: Weekly operations

After deployment, your weekly routine:

1. **Cron fires** Monday morning (or whatever you scheduled)
2. **Telegram notification** lands in your Saved Messages within ~5 minutes
3. **Open Gmail** → Drafts folder → find the weekly digest draft
4. **Review** the LinkedIn post text in the body
5. **Edit** if needed (typos, tone tweaks)
6. **Copy and paste** into your LinkedIn destination
7. **Delete** the Gmail draft after posting

If the run fails, you get a Telegram notification AND an email. Check the Run Log tab in your sheet for the full error.

---

## Phase 10: Tuning over time

The newsletter quality will need adjustment over the first few runs. See [PROMPT_TUNING.md](PROMPT_TUNING.md) for guidance.

The fastest tuning loop:
1. Edit `build_prompt()` in `run_weekly.py` locally
2. Test with `python run_weekly.py`
3. Read the new draft
4. Iterate
5. Once happy, commit and push - next scheduled run uses the new prompt

---

## Common pitfalls

- **Topic names with special characters** (commas, slashes) need to match exactly. Look at your sheet's Topic column to see what was actually fetched.
- **Test users in OAuth consent screen** must include yourself, otherwise OAuth fails.
- **OneDrive-synced project folders** sometimes lock files mid-write. Move out of OneDrive if you hit weird "file in use" errors.
- **Notepad on Windows** can save `.env` as `.env.txt`. Verify with `dir` and rename if needed.
- **GitHub Secrets cannot be viewed after entry.** If you lose track of a value, regenerate it.

---

## Rollback

If something goes wrong post-deployment, disable the workflow:

1. Repo → Actions tab
2. Click "Weekly Newsletter"
3. Click "..." menu → "Disable workflow"

Cron stops firing. Re-enable when ready.

To fully roll back, delete the GitHub Actions secrets. The workflow will fail loudly but cause no damage.
