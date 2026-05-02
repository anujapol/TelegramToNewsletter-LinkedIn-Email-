# Troubleshooting

Common failure modes and how to fix them. Organized by where the problem manifests.

## Local development issues

### "ImportError: cannot import name 'GetForumTopicsRequest'"

The Telethon API moved this class between minor versions. The repo uses `from telethon.tl.functions.messages import GetForumTopicsRequest`. If you see this error, your Telethon is older than 1.43.

Fix: `pip install --upgrade telethon`

### "Group 'X' not found in dialogs"

The script could not find your group. Causes:

1. **Name mismatch.** Telegram group names are exact. Spaces, capitalization, special characters all matter. Check the actual name shown at the top of your Telegram group, copy verbatim.
2. **You are not a member of that group.** The script authenticates as your user account, so it can only see groups you are in.
3. **Cached session is stale.** Delete `local_session.session` and re-authenticate.

### "Please enter the code you received"

This is normal on first run. Telegram sends a login code to your Telegram app (NOT SMS). Check your Telegram chats for a message from the official Telegram account, type the code in the prompt.

### "Two-factor verification password"

If you have 2FA enabled on Telegram, this is your "cloud password" (the one you set up under Settings → Privacy and Security → Two-Step Verification). It is NOT your phone unlock or your SMS code.

### "spreadsheet.WorksheetNotFound: 'Sheet1'"

Your Google Sheet's first tab is named differently. Check the tab name at the bottom of the sheet. Either rename it to "Sheet1" or change `DATA_TAB` in `run_weekly.py` to match.

### "PermissionError: 403 Forbidden" on Sheets API

The service account does not have access to your sheet. Fix:
1. Open your sheet, click Share
2. Paste the service account email (ends with `.iam.gserviceaccount.com`)
3. Set to Editor
4. Uncheck "Notify people"
5. Click Share
6. Confirm "share anyway"

### "OAuth consent: Access blocked: This app's request is invalid"

Your OAuth app is misconfigured. Common causes:
1. App not configured in OAuth consent screen
2. Your email not added as test user
3. Sensitive scopes not added

Fix: go through OAuth Consent Screen wizard fully, add yourself as test user under Audience tab.

### "redirect_uri_mismatch"

Your OAuth client is configured for the wrong type. The script expects "Desktop app" type. If you created "Web application" by mistake, recreate as Desktop app.

### Browser does not open during OAuth flow

The flow uses `flow.run_local_server(port=0)` which expects a browser. If you are running in a headless environment, this fails.

For local dev, this should work. If it does not:
- Check firewall is not blocking localhost
- Manually open the URL printed in console

### Gmail draft created but not visible

Wait 30 seconds and refresh Gmail. Drafts can take a moment to sync.

If still missing, check:
1. You are looking in the right Gmail account (the one that authenticated)
2. The "Drafts" folder, not "Inbox"
3. The script printed "Draft created" without errors

---

## GitHub Actions issues

### Workflow does not appear in Actions tab

Ensure `.github/workflows/weekly.yml` is on the `main` branch. GitHub Actions only reads workflow files from the default branch.

### Workflow fails on first run with "secrets.X not found"

You missed adding a secret. Go to Settings → Secrets and variables → Actions, verify all 11 secrets are present:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION_STRING`
- `GOOGLE_SHEET_ID`
- `GROUP_NAME`
- `ANTHROPIC_API_KEY`
- `GMAIL_RECIPIENT`
- `CONTACT_FOR_GROUP_ACCESS`
- `SERVICE_ACCOUNT_JSON`
- `GMAIL_CREDENTIALS_JSON`
- `GMAIL_TOKEN_JSON`

### "TELEGRAM_SESSION_STRING is invalid"

Your session string is corrupted, was from a different account, or was truncated when copied to GitHub Secrets.

Fix: regenerate via the bootstrap script in [SETUP.md](SETUP.md) Phase 8.1, replace the secret.

### Workflow runs successfully but no Gmail draft appears

Check:
1. Gmail OAuth still valid (token expires in Testing mode every 7 days, see Decision below)
2. Recipient email is correct in `GMAIL_RECIPIENT` secret
3. Look in the right Gmail account (the one that authenticated, not your other account)

### "RefreshError: Token has been expired or revoked"

Gmail OAuth refresh token has died. This is the most common issue if you stayed in "Testing" mode.

Fix permanently:
1. Cloud Console → OAuth consent screen → Publish app
2. Delete `gmail_token.json` locally
3. Run `python run_weekly.py` locally to regenerate token
4. Update `GMAIL_TOKEN_JSON` secret with new token contents
5. Manually trigger workflow to verify

### Anthropic returns 429 (rate limit)

You hit a rate limit. For weekly runs this is rare but can happen if you tested heavily.

Fix: wait 1 minute, retry. If persistent, check Anthropic Console for quota limits and upgrade tier if needed.

### Anthropic returns 401 (unauthorized)

API key is invalid or revoked. Generate a new one at https://console.anthropic.com/settings/keys, update `ANTHROPIC_API_KEY` secret.

### Cron does not fire on schedule

GitHub Actions cron is "best effort" and can be delayed by up to ~30 minutes during high load. This is normal.

If it skips entirely:
1. Repo must have had activity in the last 60 days (commits, PRs). Inactive repos have their schedules disabled. Push a trivial commit to wake it up.
2. Workflow file must be on default branch
3. Workflow must not be disabled (check Actions → workflow → ... menu)

---

## Output quality issues

### Newsletter mentions specific people by name

The prompt explicitly says not to, but LLMs occasionally slip. Strengthen the rule. See [PROMPT_TUNING.md](PROMPT_TUNING.md) → "Includes names of people".

### Newsletter is too long / too short

Adjust the LENGTH section in `build_prompt()`. Be specific: "Exactly 1400 to 1600 characters. Do not exceed."

### All bullets sound the same

Vary the category labels in the prompt. Force diversity:

```
BULLET CATEGORIES (use a mix, do not repeat):
Tier 1 categories: Hiring now, Just dropped, On the table, Heads up, Closing soon
Tier 2 categories: Worth a read, Quick win, Off the beaten path, In demand, Conversation starter
```

### Hooks are weak / boring

See [PROMPT_TUNING.md](PROMPT_TUNING.md) → "Hooks are not catchy enough"

### Newsletter ignores some posts that should be included

Ranking is based on engagement metrics (reactions + replies). If something important got no engagement, it will not be selected.

Options:
1. Lower the threshold by adjusting `target_count` (default 7) higher
2. Add a "must-include" override list in `select_top_posts()`
3. Tune the scoring weights to bias differently

---

## Data quality issues

### Topic column shows "General" for everything

The script could not extract topic info. Causes:

1. **Group is not a forum/topic-based supergroup.** The fallback to "General" is correct.
2. **GetForumTopicsRequest failed silently.** Add print statements in `fetch_telegram_messages()` to debug.
3. **Topic IDs are not matching message reply_to fields.** Telegram sometimes uses unexpected reply structures. Inspect a few messages manually with `print(msg.stringify())`.

### Sender column shows "Unknown" frequently

`msg.sender` is None for some messages (forwarded, anonymous, system). The fallback to "Unknown" is correct behavior.

### Reactions column is always 0

1. **No reactions on messages this week.** Check a known-reacted message in your group.
2. **`msg.reactions` field is None.** Some message types do not support reactions.
3. **Reactions are stored differently in your Telegram region.** Inspect with `print(msg.reactions)` to see the structure.

### Reply Count is always 0

This is mostly correct. In topic-based supergroups, "replies" within a topic are sibling messages, not threaded replies. Telegram's `msg.replies.replies` only counts true threaded replies.

For ranking purposes, weight reactions more heavily (already done) and accept that reply count is mostly noise.

### Duplicate rows in the sheet

The fetcher dedupes against existing Message IDs. If duplicates appear:

1. Check Column A is "Message ID" (the dedup key)
2. Check that existing IDs are stored as strings, not numbers (gspread sometimes coerces)
3. Manually delete dupes; the issue should not recur

---

## Security incidents

### "I accidentally committed a secret"

Treat the secret as compromised, regardless of how briefly it was exposed.

1. **Immediately rotate the secret:**
   - Anthropic key: revoke and regenerate at https://console.anthropic.com/settings/keys
   - Telegram session: Telegram → Settings → Devices → revoke session, regenerate via bootstrap script
   - Google service account: Cloud Console → IAM → service accounts → keys → delete and recreate
   - Gmail OAuth: Cloud Console → Credentials → delete OAuth client → recreate
2. **Update GitHub Secrets** with the new values
3. **Force-push to remove from history:**
   ```bash
   git rebase -i [commit-before-leak]
   # remove the offending commit
   git push --force
   ```
4. **Or, if the repo is brand new:** delete repo entirely, recreate, push clean code
5. **Verify the leak is gone:** `git log -p | grep -i 'sk-ant'` should return nothing

### "Someone says they have my session string"

Same response as above. Revoke and rotate.

### "I am seeing API usage I did not initiate"

Possible compromise. Rotate the affected API key immediately. Check Anthropic Console for usage spikes. Consider enabling 2FA on all related accounts (Anthropic, Google, GitHub).

---

## Recovery scenarios

### "I lost my laptop, need to rebuild from scratch"

The cloud workflow continues running fine. To rebuild local dev:

1. New machine, install Python and Git
2. Clone your repo
3. Create venv, install requirements
4. Recreate `.env` (you have the values in GitHub Secrets, but secrets are write-only, so you would need to remember them or rotate)
5. Re-download `service_account.json` and `gmail_credentials.json` from Cloud Console
6. Re-run OAuth flow to regenerate `gmail_token.json`
7. Re-authenticate Telegram (will create new `local_session.session`)

The cloud workflow keeps running throughout this rebuild.

### "My GitHub Actions secrets got deleted"

Recreate them from your local `.env` and JSON files. Keep a secure offline backup of these files (encrypted USB, password manager) so this scenario is not catastrophic.

### "The Run Log shows 10 consecutive failures, what now?"

1. Read the latest error in the Run Log
2. Look up the error in this troubleshooting doc
3. If specific to a credential: rotate it
4. If specific to a code change: check recent commits for a regression
5. If specific to an external service: check status pages for Anthropic, Google, GitHub
6. Manually trigger the workflow once you think it is fixed
7. If it succeeds, normal cron resumes

---

## Getting help

If you hit something not covered here:

1. Read the full GitHub Actions run log, including stack traces
2. Check the Run Log tab in your sheet for context
3. Check Anthropic, Google, GitHub status pages for outages
4. Open an issue on this repo with: error message, run log link, what you tried

The system is intentionally simple. Most failures are credential-related and resolved by rotating the affected credential.
