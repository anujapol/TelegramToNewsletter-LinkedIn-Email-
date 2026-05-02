# Prompt Tuning Guide

The newsletter quality depends almost entirely on the prompt sent to Claude. This guide walks through how to tune it for your community.

## Where the prompt lives

`run_weekly.py` → `build_prompt()` function (around line 280).

## The structure of a good prompt

The included prompt has 6 sections, each doing specific work:

```
1. ROLE AND GOAL          ← who is the LLM pretending to be, what is the goal
2. INPUT DATA             ← the actual posts, formatted consistently
3. OPENING HOOK rules     ← how to open the post
4. STRUCTURE rules        ← how to lay out the body
5. FORMATTING rules       ← character-level formatting
6. TONE AND VOICE         ← style guidelines
7. LENGTH AND CONSTRAINTS ← hard limits
8. OUTPUT INSTRUCTIONS    ← what NOT to include
```

Removing any section degrades quality. Adding more sections rarely helps.

## How to tune effectively

### Iterate on real outputs, not on imagined ones

The fastest tuning loop:

1. Run `python run_weekly.py` locally
2. Read the actual generated post
3. Identify ONE specific thing to change
4. Update the prompt with explicit instructions for that one thing
5. Re-run
6. Read the new output
7. Repeat

Do not change five things at once. You will not know which change helped.

### Use positive AND negative examples

The included prompt has examples like:

```
Examples that work:
* "While you were heads down at work this week, your network was busy."

Examples that DO NOT work:
* "This week was amazing!" (generic)
* "Hello fellow alumni!" (filler)
```

Negative examples are powerful. The LLM learns boundaries faster from "do not do this" than from "do this."

### Be specific about formatting

Vague: "Use bullets"
Specific: "Use the Unicode triangle character (U+25B8) at the start of each bullet"

Vague: "Keep it short"
Specific: "1400 to 1600 characters total including hashtags"

Vague: "Sound professional"
Specific: "Punchy, declarative, professional but warm. No em dashes (use commas, periods, colons). No filler phrases."

## Common adjustments

### "Newsletter feels too formal"

Add to TONE section:
```
- Conversational, like you are talking to a friend who happens to be in the network
- Contractions are fine ("you're" not "you are")
- Occasional informal phrases work ("dropping a tip", "worth a peek")
```

### "Newsletter feels too casual / not professional enough"

Add to TONE section:
```
- Maintain professional register throughout
- No contractions
- No emoji except the bullet character
- No exclamation points
```

### "Hooks are not catchy enough"

Make the OPENING HOOK section more aggressive:

```
OPENING HOOK (make this 30% of your effort):
- Must create FOMO or curiosity gap
- Use one of these patterns:
  * "While you were [common boring activity], [community] was [doing something interesting]"
  * "[Specific number] conversations from this week that [aspirational outcome]"
  * "The [community name] had [a specific descriptor]. Here's what happened."
- AVOID: greetings, generalizations, "this week was..."
```

### "Includes names of people"

Strengthen the generalize-references rule:

```
PRIVACY RULES (strict):
- NEVER include any person's name, even partial names or initials
- NEVER include company names mentioned in posts unless they are public knowledge (e.g., FAANG companies, well-known startups)
- Use role-based references: "an alum", "a senior leader", "a recent grad", "a community member"
- If a post mentions specific people doing specific things, abstract it: "Someone in the group is hiring for a Director role" not "Jane Doe is hiring"
```

### "Posts feel disconnected, no narrative"

Add a TRANSITION rule between bullets:

```
NARRATIVE FLOW:
- Order bullets so they tell a mini-story arc
- Lead with the most actionable (jobs, opportunities)
- Middle section: networking and growth
- End with lighter or aspirational items
- The transition line before CTA should reference the thread of the post
```

### "Newsletter is too long / too short"

Hard-set the character count:

```
LENGTH: Exactly 1400 to 1600 characters. Do not exceed 1600. Do not write less than 1400. If you cannot fit all 7 bullets within budget, reduce to 5 or 6 bullets but keep the structure.
```

### "Hashtags are generic"

Be specific about hashtag selection:

```
HASHTAG RULES:
- 4 to 6 hashtags total
- 2 must be brand hashtags: #YourCommunityName #AlumniNetwork
- 2 to 4 must be DERIVED FROM THIS WEEK'S CONTENT (e.g., if jobs dominated: #Hiring #Careers; if AI dominated: #ArtificialIntelligence #TechLeadership)
- Do not reuse the same generic set every week
```

### "Tone shifts mid-post"

Add a CONSISTENCY rule:

```
CONSISTENCY:
- Whatever tone is established in the opening hook must persist through every bullet and the closing
- Do not drift from punchy to flowery within the same post
- The transition line and CTA should match the energy of the bullets
```

## When to add examples to the prompt

If you keep getting outputs that miss the mark on a specific dimension after 3+ tuning attempts, add a full example to the prompt:

```
EXAMPLE OF DESIRED OUTPUT (do not copy content, only structure and tone):

While you were heads down this week, your network was hiring, building, and meeting up.

Seven conversations worth your attention:

▸ Hiring now: Director-level role at a FAANG company, 14+ years exp, immediate start. [link]
... (full example post)
...
#YourCommunity #AlumniNetwork #JobReferrals #StartupLife
```

This is heavyweight, only do it if other tactics fail.

## Cost considerations

Each prompt run costs ~$0.10-0.30 with Claude. Aggressive prompt tuning over 50 iterations is still under $15 total. Do not optimize for cost during the tuning phase. Spend the API calls.

After the prompt is locked, costs drop to ~$0.40 to $1.20/month for once-weekly runs.

## When to stop tuning

You are done tuning when:

1. **Three consecutive weekly runs produce posts you would post without editing.** Not "with one tweak", actually as-is.
2. **The community responds positively** to the LinkedIn posts (likes, comments, new Telegram joins).
3. **You stop noticing things to fix** when you read the draft.

Do not chase perfection. The newsletter is meant to be a regular, reliable signal, not a literary masterpiece.

## Switching to a different LLM provider

The architecture is provider-agnostic. To swap from Anthropic to OpenAI:

1. Replace `anthropic` in `requirements.txt` with `openai`
2. Replace the import: `from anthropic import Anthropic` → `from openai import OpenAI`
3. Replace `generate_newsletter()`:

```python
def generate_newsletter(posts, week_label):
    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = build_prompt(posts, week_label)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
    )
    return response.choices[0].message.content.strip()
```

4. Update env var name and GitHub Secret accordingly

The prompt itself usually does NOT need changes when switching providers. If output quality drops, the prompt just needs slight adjustment for the new provider's quirks.
