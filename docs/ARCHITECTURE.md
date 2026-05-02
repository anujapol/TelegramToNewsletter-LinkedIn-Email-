# Architecture

This document explains the system design, the key trade-offs, and why each component was chosen.

## High-level flow

```
┌─────────────────────────────┐
│  Telegram Supergroup         │
│  (with topics/threads)       │
└──────────────┬──────────────┘
               │
               │ Telethon (user account, MTProto API)
               ▼
┌─────────────────────────────┐
│  fetch_telegram_messages()   │
│  - reads last 8 days         │
│  - dedupes against sheet     │
│  - extracts topic, sender,   │
│    content, reactions, etc.  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Google Sheets (Sheet1)      │
│  10 columns × N rows         │
│  Audit trail + data layer    │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  filter_recent_messages()    │
│  - last 7 days               │
│  - drops trivial content     │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  select_top_posts()          │
│  - tier 1 + tier 2 buckets   │
│  - score = reactions×3       │
│          + replies×5         │
│          + length_bonus      │
│  - dedupe near-identical     │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Claude API (Anthropic)      │
│  build_prompt() + invoke     │
│  Returns LinkedIn post text  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Gmail Draft                 │
│  Subject + body              │
│  Human reviews + posts       │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Telegram self-notification  │
│  + Run Log row               │
│  + Email failure alerts      │
└─────────────────────────────┘
```

## The three decisions that mattered most

### Decision 1: Google Sheets as the data layer

A real database (SQLite, Postgres) would give you cleaner queries, indexes, transactions, and proper schema enforcement. So why Sheets?

**Three reasons:**

1. **Free human-browsable UI during iteration.** When you are tuning what gets captured (topic mapping, sender extraction, reaction counting), being able to glance at a sheet and spot weirdness is faster than running ad-hoc SQL queries. Most projects live in this iteration phase longer than expected.

2. **Zero infrastructure overhead.** No connection strings, no migrations, no backup strategy, no provisioning. The sheet exists and works. For a once-weekly automation, the operational simplicity wins.

3. **Free tier covers more scale than this project will ever need.** Sheets caps at 10 million cells. With 10 columns per message, that is ~1 million messages of capacity. At 3,000 messages per week, that is 6 years of data. This is not a constraint that will bite.

**Where this decision is wrong:**

- If the data layer needs to be queried by other systems (e.g., a dashboard, a search interface)
- If you need to do complex analytics over historical data
- If multiple processes write concurrently (Sheets API has rate limits)
- If you grow past ~50,000 rows (browser becomes sluggish, though API stays fine)

**Migration path:** SQLite first (just swap the read/write functions, keep everything else identical), Postgres later if you outgrow SQLite.

### Decision 2: Category-aware ranking, not pure engagement

The naive approach: rank all posts by `reactions + replies` and take the top N. This fails for community newsletters.

**Why it fails:**

A funny meme reliably gets more reactions than a job referral. If your newsletter goal is "drive engagement back to the group," the meme winning means the newsletter becomes entertainment-focused and loses its action-driving edge. People stop opening the Telegram app because the LinkedIn post already gave them what they came for (a laugh).

**The fix:**

Two-tier classification by topic:

```python
TIER_1_TOPICS = {
    # Always include if available - these drive your CTA
    "Jobs and Referrals",
    "Official Announcements",
    "Networking and Meet-ups",
    "Business Proposals",
    "Startups and Entrepreneurs",
}

TIER_2_TOPICS_FALLBACK = {
    # Filler if Tier 1 is light - these add variety and warmth
    "Mentorship",
    "Technology",
    "Finance and Investing",
    "Travel",
    "Education",
    "General Discussion",
    "Social",
}
```

Within each tier, score by `reactions * 3 + replies * 5 + min(content_length / 100, 5)`. Take 7 from Tier 1; if Tier 1 yields fewer than 7, top up from Tier 2.

**Why those weights:**

- Replies are weighted higher than reactions because they signal deeper engagement (someone took the time to write something, not just tap an emoji)
- The length bonus is capped at 5 so a 2,000-character rant cannot beat a 200-character gem with 5 reactions
- The 3:5 ratio for reactions:replies came from inspecting real data; tune for your community

**Where this decision is wrong:**

If your community is purely entertainment or social (e.g., a fandom group), engagement IS the goal and pure scoring is fine.

### Decision 3: Human in the loop, never auto-post

The system creates a Gmail draft. It does not post to LinkedIn automatically.

**Why not auto-post:**

1. **LLM outputs occasionally embarrass.** A weird hallucination or tone misfire on a public LinkedIn post damages trust in ways that take months to recover. The cost of a single bad post is much higher than the convenience of full automation.

2. **LinkedIn API access for personal accounts is hard.** LinkedIn's posting API is designed for company pages and partner integrations. For personal accounts, you would need to use unofficial tooling that violates ToS and can get your account flagged.

3. **The act of reviewing tunes the prompt over time.** Every time you read the draft and think "this could be better," that is a signal to update `build_prompt()`. Full automation cuts off this feedback loop. You stop noticing slow drift.

**The cost:**

5 minutes every Monday to read the draft, edit if needed, and paste to LinkedIn. For a weekly cadence, this is fine. For higher frequencies, the math changes.

**Where this decision is wrong:**

For very high frequency content (multiple posts per day), the human bottleneck breaks. In that case, add a content-safety classifier between generation and posting, and accept that occasional bad outputs will go live.

## Component choices and why

### Telethon over a Telegram bot

**Telegram bots can only see messages in groups where they are explicitly added as admins, and they cannot read historical messages they were not present for.**

Telethon authenticates as a user account, which means it sees everything the user sees, including history. For monitoring an existing community, this is the only viable option.

The trade-off: a user account session is more sensitive than a bot token. Treat the session string like a password.

### Claude over other LLMs

Two reasons:

1. **Quality of nuanced writing.** Newsletter copy needs to balance information density, tone, and curiosity hooks. Claude tends to handle this kind of soft-skill writing more reliably than alternatives, in my experience.

2. **Pricing predictability.** A weekly run costs $0.10 to $0.30. For a personal automation, this is rounding error.

The architecture is LLM-agnostic. To swap providers, change the `generate_newsletter()` function. Everything else is unchanged.

### GitHub Actions over a VM or PaaS

**Compute volume:** ~5 minutes per week × 4 weeks = 20 minutes/month. Free tier is 2,000 minutes/month. This is not a constraint.

**Operational simplicity:** No server to maintain or patch. No SSH keys, no firewall rules, no OS upgrades.

**Built-in secrets management:** Encrypted at rest, redacted from logs, only accessible during workflow runs.

**Forces version control discipline.** The deployment IS the repo, so you cannot have stale code on a server while the repo says something else.

### Gmail draft over direct send

The `create_gmail_draft` API call lands the post in your Drafts folder. This is intentional and aligns with Decision 3.

If you want to make this fully autonomous later, swap `create_gmail_draft` for `send_gmail_alert` and the post goes out without review. Not recommended.

## Failure modes and resilience

The system has three notification channels that fail somewhat independently:

1. **Run Log in Google Sheets** - written via service account, separate from Gmail OAuth
2. **Telegram self-message** - written via Telethon, separate from both Sheets and Gmail
3. **Email alert** - written via Gmail API, dependent on OAuth refresh tokens

If Gmail is down, you still get the Telegram message. If Telegram is rate-limiting, you still get the email. If both notification paths fail, the Run Log still has the failure recorded for next time you check.

The orchestrator wraps everything in a single try/except so any failure logs to all available channels before exiting non-zero. GitHub Actions then marks the run as failed, which is visible in the Actions tab.

## Scaling considerations

This architecture handles **one Telegram supergroup, one LinkedIn destination, weekly cadence**. To scale beyond:

**Multiple groups:** parameterize the workflow. Run it once per group, with a config file mapping groups to recipients.

**Higher frequency:** the cron schedule is the only change. Watch Anthropic costs (roughly linear with frequency).

**Multiple destinations:** factor out the "create draft" step into a strategy pattern. Add destinations like Slack, Discord, X, or direct LinkedIn posting (if you have API access).

**Different content selection logic:** the `select_top_posts` function is the only place rankings happen. Override it with whatever logic fits your community.

## What is NOT in the architecture

Things that would be over-engineering at this scale:

- **A real database.** See Decision 1.
- **A queue system.** Single-threaded sequential execution is fine for once-weekly runs.
- **Caching.** Each run is independent, no benefit.
- **A web dashboard.** Run Log tab in Sheets is the dashboard.
- **Multi-region failover.** Running in one GitHub region is fine.
- **Comprehensive metrics.** Run Log gives you what you need.
- **Unit tests.** Manual testing during prompt iteration is more useful than unit tests for this kind of generative system.

If your use case grows beyond template scope, these become worth adding. Until then, do not pre-engineer.
