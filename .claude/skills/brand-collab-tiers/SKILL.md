---
name: brand-collab-tiers
description: For a brand's Instagram account, list every creator who collaborated with it in the last 1 or 2 years and sort them into four tiers by paid-partnership toggle and boosted ad spend. Use whenever the user gives a brand name or brand Instagram URL and asks who it worked with, its collaborators, partnerships, creator tiers, paid vs organic collabs, or competitor creator analysis.
---

# Brand collaborator 4-tier scan

## How to handle a plain-English request

1. Confirm `.env` exists (see CLAUDE.md Step 0). This tool also needs
   Playwright's browser: `python -m playwright install chromium` once.
2. Get the brand's Instagram URL. If the user gave a name only, resolve it
   to `https://www.instagram.com/<handle>/` - ask if you are not sure which
   account is the official one.
3. Window: default 2 years. "last year" = `--years 1`, "6 months" = `--days 180`.
4. Tell them the timing: 2-4 s per candidate post, plus a profile lookup per
   new creator. A brand with 300 tagged posts is roughly 20-30 min.
5. Run:
   ```bash
   python brand_collab_tiers.py --url https://www.instagram.com/cred_club/ --brand CRED --years 2 --output deliverables/CRED_Collab_Tiers.xlsx
   ```
   For brands with a long tagged grid add `--max-scrolls 30` so the scan
   reaches the full window (the grid is newest-first).
6. Several brands = run once per brand, one workbook each. Do not merge
   brands into one sheet unless asked.

## How to explain the tiers (say this to the user)

Every collab post is scored on two independent signals:

- **Toggle** - did the creator switch on Instagram's "Paid partnership
  with ..." label? That is the creator declaring a paid deal.
- **Boosted** - does the engagement shape look like ad money? Ad spend buys
  views from strangers who do not like, so views balloon while the like
  rate collapses. Boosted if any of: 1M+ views with like rate under 0.35%;
  views over 5x the creator's followers with ER under 1%; 500K+ views
  with like rate under 0.5%; 50K+ likes; #ad / #collab caption with
  100K+ views or 5K+ likes.

| Tier | Toggle | Boosted | Meaning |
|---|---|---|---|
| 1 | ON | Yes | Declared deal and the brand put ad money behind it. Highest-conviction creators. |
| 2 | ON | No | Declared deal, ran organically. Confirmed relationship, smaller budget. |
| 3 | OFF | Yes | Not declared but numbers say paid distribution. Undisclosed deal, barter run as ad, or whitelisting. Check manually. |
| 4 | OFF | No | Organic mention, UGC, fan post, sister-account tag. Noise. |

Creator size band is separate, on exact followers: Nano <10K, Micro 10-50K,
Mid 50-100K, Macro 100K-1M, Mega 1M+.

## Caveats to state

- The boost rules are heuristics; a genuinely viral organic reel can land
  in Tier 3.
- A sister brand tagging its parent appears as a collaborator. If one
  account dominates the list, flag it.
- Views not exposed by Instagram are written as 0, never estimated.
- Follower counts carry `followers_precision`; only `exact` is a number
  you can quote.

## Before sending

No emoji cells, one workbook per brand in `deliverables/`, window dates
shown in the summary tab header.
