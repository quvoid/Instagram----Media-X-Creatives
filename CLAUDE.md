# Instagram Media X Creatives - agent instructions

You are working inside an influencer-marketing toolkit. The person using you
is usually NOT a developer. They will describe what they want in plain
English or paste a list. Your job is to pick the right tool, run it, and hand
back a workbook plus a short plain-English summary. Do not ask them to run
commands themselves; run them.

## Step 0 - every session: check the Instagram session

Before running anything that touches Instagram, check that `.env` exists in
the repo root and has `IG_SESSIONID`, `IG_CSRFTOKEN`, `IG_DS_USER_ID`.

- If `.env` is missing or a value is blank: stop and tell the user to run
  `python setup.py` in a terminal. It walks them through copying four cookies
  from their browser. Do NOT ask them to paste cookie values into this chat,
  and NEVER write cookie values into any file other than `.env`.
- If a run fails with HTTP 401/403 or "session not configured", the cookies
  expired: same instruction, `python setup.py` again.

## Step 1 - route the request to a skill

| The user says something like | Skill to load |
|---|---|
| "find / give me creators from Kolkata / Punjab / Chennai ...", "creators who did Durga Puja", "how many creators do we have", "creators above 50k with email", a client brief naming a city | `.claude/skills/region-creator-discovery/SKILL.md` |
| pastes a list of Instagram pages / URLs, "invest or don't invest", "which of these pages are worth it", "average views on these pages", "momentum audit" | `.claude/skills/page-momentum-audit/SKILL.md` |
| gives a BRAND's Instagram URL or name, "who did X collaborate with", "collaborators in the last year / 2 years", "tiers", "paid partnerships for brand X" | `.claude/skills/brand-collab-tiers/SKILL.md` |

Read the skill file fully before running. Each one has the exact commands,
the input format, how long it takes, and how to explain the result.

If the request fits none of these, say so and list the three things this
repo can do.

## Rules that never bend

- Follower counts are exact or reported as unresolved. Never round, never guess.
- Never invent a metric. Views not exposed = 0 and say so.
- Throttling (HTTP 429, `feedback_required`) is not "account missing". Pause and say it was throttled.
- Zero emojis and zero colour fills in any workbook cell.
- Read questions ("give me", "how many", "which") query `creator_intelligence.db` first. Only harvest / audit / deepscan touch Instagram.
- Every long run saves progress incrementally and is resumable; if it stops, rerun the same command.
- Never accept terms, log in, or click consent on any site on the user's behalf.
- `creator_intelligence.db` holds creators' emails and phone numbers. Never commit it or send it anywhere.

## Delivering to a non-technical user

- Put every workbook in `deliverables/` and give them the path.
- Explain the result in 3-6 plain sentences: what was checked, how many rows, what the verdict columns mean.
- Say how long a run will take before starting it (each skill lists timings) and give a status line every few minutes on long runs.
