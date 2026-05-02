# Telegram to LinkedIn/Email Newsletter Automation

> A weekly automation that pulls discussions from a Telegram supergroup, identifies high-engagement posts using a category-aware ranking system, generates a LinkedIn-ready post via Claude, and delivers it as a Gmail draft for human review.

Built to solve a specific problem: active Telegram communities generate valuable discussions, but most of that signal stays buried in the group. This automation surfaces the week's most relevant conversations as scroll-stopping LinkedIn content designed to drive new and lapsed members back to the group.

---

## What it does

```
Telegram supergroup (with topics)
        │
        ▼
Telethon fetcher (Python)  ──► deduplicates against existing rows
        │
        ▼
Google Sheets (data layer)  ──► one row per message, full audit trail
        │
        ▼
Category-aware ranker (Python)  ──► tier-1 priority topics + tier-2 fallback
        │
        ▼
Claude API (newsletter generator)  ──► LinkedIn-formatted post with teasers
        │
        ▼
Gmail draft  ──► you review, copy, paste to LinkedIn
        │
        ▼
Run Log + Telegram self-notification + email alerts on failure
```

Runs weekly via GitHub Actions cron. Zero infrastructure to maintain. All secrets stored in GitHub Actions Secrets, never in code.

---

## Top 3 architectural decisions

These are the calls that mattered most. Skip if you just want to deploy.

### 1. Google Sheets as the data layer (not a real database)

**Decision:** Use Google Sheets as the message store, with one row per Telegram message and a separate "Run Log" tab for operational history.

**Why:** For a weekly newsletter at this scale (a few thousand messages per week max), Sheets gives you a free human-browsable UI to inspect what was captured during iteration. A real database would be technically cleaner but adds operational overhead (provisioning, backups, connection strings) for zero functional benefit at this scale.

**Trade-offs:** Browser becomes sluggish around 100K rows, but the API stays fast much longer. If you grow past 50K rows you have an obvious migration trigger to SQLite or Postgres. Until then, do not pre-optimize.

**When this decision is wrong:** If you need to query historical data in complex ways, run analytics, or share the data layer with other systems. Then move to a real database.

### 2. Category-aware ranking, not pure engagement

**Decision:** Classify every message into priority tiers based on its topic, then select top posts within tiers rather than ranking globally by reactions.

**Why:** Pure engagement ranking is a trap for community newsletters. A funny meme with 20 reactions will always beat a job referral with 2 reactions, but the job referral is the content that drives the audience action you actually want (people opening Telegram). The newsletter goal is not "show what is popular," it is "show what is valuable enough to drive engagement back to the group."

**How:** Tier 1 (always include if available) covers job referrals, official announcements, networking opportunities, business proposals. Tier 2 (filler if Tier 1 is light) covers everything else. Within each tier, score by `reactions * 3 + replies * 5 + content_length_bonus`.

**When this decision is wrong:** If your community is purely entertainment-focused and engagement IS the goal. Then revert to pure engagement scoring.

### 3. Claude as the writer, you as the editor

**Decision:** Generate a Gmail draft, never auto-post. Always require a human in the loop before content goes public.

**Why:** Three reasons. First, LLM outputs occasionally embarrass. A weird hallucination in a public LinkedIn post damages trust in ways that take months to recover. Second, posting to LinkedIn programmatically requires LinkedIn API access that is not easy to get for personal accounts. Third, the act of reviewing the draft is when you spot prompt-tuning opportunities; full automation would mean you stop noticing the slow drift in quality.

**Trade-offs:** Requires 5 minutes of your time every Monday to review and post. Cost of not having that 5 minutes: occasional public embarrassment.

**When this decision is wrong:** If you genuinely need 100% automated posting (e.g., for very high frequency content). Then add a content-safety classifier between generation and posting, and accept that occasional bad outputs will go live.

---

## Cost structure

Total monthly cost: **under $2 USD** for typical use.

| Service | Cost | Notes |
|---|---|---|
| GitHub Actions | $0 | ~5 min/week × 4 weeks = 20 min/month, well under 2,000 min free tier |
| Google Sheets API | $0 | Free, no billing required |
| Google Drive API | $0 | Free, no billing required |
| Gmail API | $0 | Free for personal use |
| Telegram API | $0 | Free for user accounts |
| Anthropic API (Claude) | $0.40 to $1.20 | ~$0.10–$0.30 per weekly run depending on message volume |
| **Total** | **~$1/month** | |

Set up an Anthropic spending alert at $5/month to catch runaway behavior.

---

## What you need before deploying

- A Telegram account that is a member of the target group
- A GitHub account (free tier)
- A Google account with access to Google Cloud Console
- An Anthropic Console account with billing enabled
- About 2–3 hours of focused setup time
- Comfort with command-line basics (PowerShell or Terminal)

---

## Quick start

Full setup walkthrough in [docs/SETUP.md](docs/SETUP.md). High level:

1. **Get API credentials**
   - Telegram: get `api_id` and `api_hash` from https://my.telegram.org
   - Anthropic: create API key at https://console.anthropic.com
   - Google Cloud: create project, enable Sheets/Drive/Gmail APIs

2. **Set up Google services**
   - Create a Google Sheet, share with a service account
   - Create OAuth credentials for Gmail draft access

3. **Configure local environment**
   - Clone this repo
   - Create `.env` from `.env.example`
   - Generate Telegram session string (see [docs/SETUP.md](docs/SETUP.md))

4. **Test locally**
   - Run `python run_weekly.py`
   - Verify Gmail draft, Telegram notification, and Run Log row

5. **Deploy to GitHub Actions**
   - Push code to your private repo
   - Add all secrets to GitHub Actions Secrets
   - The cron schedule in `.github/workflows/weekly.yml` triggers automatically

---

## Repository structure

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
├── LICENSE
├── README.md                    # This file
├── requirements.txt             # Python dependencies
└── run_weekly.py                # Main script (fetch + generate + notify)
```

---

## Customization

This is a template. To adapt for your own community:

- **Group and topics:** edit `GROUP_NAME` in `.env`. Update `TIER_1_TOPICS` and `TIER_2_TOPICS_FALLBACK` in `run_weekly.py` to match your group's topic names.
- **Newsletter tone:** edit the `build_prompt` function in `run_weekly.py`. See [docs/PROMPT_TUNING.md](docs/PROMPT_TUNING.md).
- **Schedule:** edit the cron expression in `.github/workflows/weekly.yml`. Default is Mondays at 16:00 UTC (~9 AM Pacific).
- **Output destination:** the script creates a Gmail draft by default. To send to Slack, Discord, or directly post somewhere, replace the `create_gmail_draft` call with your preferred destination.

---

## Security notes

This system handles sensitive credentials:

- **Telegram session string** authenticates as your personal account, treat it like a password
- **Anthropic API key** is billed to your account
- **Google service account JSON** has Editor access to your sheet
- **Gmail OAuth token** can read and send mail from your account

All of these belong in **GitHub Actions Secrets** for production, never in code or in the repo. The included `.gitignore` excludes all credential files. Do not bypass it.

If a secret is compromised, rotate immediately. See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for the response checklist.

---

## Limitations and known issues

- **Private Telegram group links** open the Telegram app, not the web client. Acceptable since recipients are typically already group members.
- **Gmail OAuth in "Testing" mode** rotates refresh tokens every 7 days. The setup guide walks you through publishing to fix this.
- **Reactions vs replies in topic-based supergroups:** Telegram's `msg.replies.replies` field is meaningful for channels but not for topics within supergroups. The ranking weighs reactions more heavily as a result.
- **Single group only:** the script handles one supergroup at a time. To monitor multiple groups, parameterize the workflow.
- **English-only prompt tuning:** the included newsletter prompt is tuned for English. Adapt as needed.

---

## Contributing

This is shared as a template, not an actively maintained product. If you adapt it for your community and find improvements worth contributing back, open a pull request.

If you build something interesting on top of this, I would love to hear about it.

---

## License

MIT. See [LICENSE](LICENSE).

Built with [Telethon](https://github.com/LonamiWebs/Telethon), [gspread](https://github.com/burnash/gspread), and the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python).
