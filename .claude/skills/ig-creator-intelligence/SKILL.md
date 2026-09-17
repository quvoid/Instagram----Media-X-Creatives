---
name: ig-creator-intelligence
description: Find, verify, tier and rank Instagram creators for a region, category, festival or client brief, and judge pages on current momentum. Use this whenever the user asks for creators from a city or state (Kolkata, Punjab, Hyderabad, Chennai, Mumbai, Delhi, Bangalore), creators who took part in a campaign like Durga Puja, a creator list for a client (Britannia, Enamor, Visa), how many creators we already have, a query over the creator database, a page audit with Invest / Don't Invest calls, average views or engagement on a list of pages, or asks a chatbot-style question like "who are the top creators in X". Trigger even when the user just pastes a list of Instagram URLs and asks for metrics.
---

# Instagram creator intelligence

Two capabilities, one permanent store.

- **Discovery** — find and verify creators for any region / category /
  campaign, accumulating into `creator_intelligence.db` so a client brief is
  a *query*, not a new scrape.
- **Page momentum audit** — given a list of pages, measure current
  traction (exact views, likes, comments, dates on the latest posts) and give
  an Invest / Don't Invest call ranked against peers.

Full references: `docs/CREATOR_DB.md` and `docs/PAGE_AUDIT.md`. Read the
one you need before running anything.

## Rules that never bend

- **Exact follower counts only.** `core/profile_auditor.resolve_profile()`
  returns `followers_precision` of `exact` / `rounded` / `unresolved`; only
  `exact` ships. `og:description` is rounded above ~10K — never read it.
- **Never invent a number.** Unresolved is reported as unresolved.
- **Throttling is not absence.** `429` or `feedback_required` means stop and
  say so. `is_throttled()` detects both shapes.
- **Zero emojis, zero colour fills** in any workbook. `clean_cell()` on every cell.
- **Residence is evidence, not a bio keyword** — `geo_evidence` rows from
  real places the creator posted at. Two or more distinct places in a region
  is the residence signal.
- **A campaign claim needs a post inside the date window** with the
  campaign hashtag or venue. Never infer participation from a bio.
- **Read queries never scrape.** "give me / how many / which" go to the
  database. Only `harvest` / `audit` / `backfill` touch Instagram.

## Query the store first

```bash
python core/creator_db.py stats
python core/creator_db.py ask "kolkata food creators above 50k with email"
python core/creator_db.py query --region punjab --category fashion --min 10000 --residence 2 --xlsx out.xlsx
python core/creator_db.py sql "SELECT ..."
python run.py "give me hyderabad creators above 100k"
```

The NL parser understands region, tier, ranges (`50k-200k`, `above 50k`),
category, campaign, `with email`, `verified`, `living in` (→ residence ≥ 2),
`youtube`, and `collaborators of @brand`.

Regions: kolkata · punjab · hyderabad · chennai · mumbai · delhi · bangalore
Categories: food · fashion · beauty · comedy · travel · lifestyle · fitness · dance · cinema · festive
Campaigns: durga_puja_2025 · durga_puja_2026 · diwali_2025
Add more in `core/discovery_sources.py` (`REGIONS`, `CATEGORIES`, `CAMPAIGNS`).

## Discovery — harvest → audit → deliver

Split by cost. Harvest is cheap and wide and writes leads as `PENDING_AUDIT`
with `followers = 0`. Audit is expensive and resolves exact counts,
most-corroborated first, resumable. Deliver is a query.

```bash
python core/regional_engine.py harvest --region punjab --pages 6
python core/regional_engine.py audit   --region punjab --limit 400 --min-post-likes 300
python core/regional_engine.py deliver --region punjab --residence 2 --min 10000 --xlsx Enamor_Punjab.xlsx
```

`--min-post-likes` is a free size filter: on a Kolkata sweep 75% of
geo-harvested handles had a best post under 30 likes (civilians who tagged
the city). Filtering on it took the audit hit-rate from 8% to 100%.

**Festival brief** (e.g. Britannia — Kolkata residents who did Durga Puja 2025):

```bash
python core/regional_engine.py harvest --region kolkata --campaign durga_puja_2025 --pages 6
python core/regional_engine.py audit   --region kolkata --has-campaign durga_puja_2025 --verify-campaign durga_puja_2025
python core/regional_engine.py deliver --region kolkata --campaign durga_puja_2025 --residence 2 --min 10000 --xlsx Britannia.xlsx
```

A **past** campaign cannot be swept from the hashtag `recent` tab — it is
newest-first and would need thousands of pages to reach last year.
`--verify-campaign` reads each gated creator's own media instead. It needs
the feed endpoint, which Instagram throttles first; it reports
unavailability rather than guessing.

**Deep research on verified creators** — 90 days of their own posts:

```bash
python core/regional_engine.py deepscan   --region kolkata --limit 400 --days 90
python core/regional_engine.py deepexport --region kolkata --xlsx Kolkata_Creators_Deep_Research.xlsx
python core/creator_deep_scan.py one @handle
```

Per creator it walks back 90 days (pinned posts excluded so an old trophy
cannot end the walk), and records: every partnership post and the brand
behind it (paid toggle, sponsor tag, co-author, #ad hashtag, or a tagged
business account — tagged accounts are resolved once and cached, a tagged
friend is not a partnership), median likes / comments / exact reel views,
engagement per view, posting cadence, content category scored over every
caption, and the email (business email, else bio). Measured on one Kolkata
food creator: 53 posts, 45 distinct brands in 90 days, 0 with the paid
toggle on. `scripts/run_kolkata_deep.py` chains harvest → audit → deepscan
→ export for a whole region, resumable.

**Competitor's collaborators** (Visa strategy) — already scanned, now a query:
`deliver --brand <competitor> --min 10000`, or `--exclude-brand` for who the
competitor has *not* used.

**Fresh clone:** `python core/regional_engine.py backfill` once — it pulls
every roster and workbook already in the repo into the store (recovered
9,193 handles the first time).

### Source ranking (measured)

1. `discover/chaining` — Instagram's own similar-accounts graph. ~80 per
   seed, category-coherent. Best source by far. Seed it with a pk resolved
   from the live profile; a wrong pk returns confident nonsense.
2. Chatbot answers (`core/llm_discovery.py`) — strong on established names,
   blind to emerging. **They give names; stated handles are often invented.**
   Resolve names through Instagram search, let the audit decide.
3. Free vendor directory pages (modash etc.) — handles only, never their
   follower estimates.
4. Topsearch grid, geo sections (only physical-presence proof), hashtag
   sections, legacy hub crawl.

Hub seed lists rot — 9 of the original 16 were dead. `seed_health_check()`
runs first.

## Page momentum audit

Input: a text file of handles under `## Tab Name` headers. Output: one
consolidated sheet, tab carried as a column, no emojis, no colours.

```bash
python page_audit.py --input mylist.txt --output MyList.xlsx --pause 1.0
python page_audit.py --input mylist.txt --output MyList.xlsx --excel-only   # rebuild from cache
```

Uses the web app's own GraphQL queries (`PolarisProfilePostsQuery`,
`PolarisProfileReelsTabContentQuery`), which work while the REST feed is
throttled. ~10 s per new page; cache is shared across lists.

**Verdict:** Stage 1 floors (posted ≤ 21 days, median views ≥ 2% of
followers, median ≥ 25% of average views) then Stage 2 peer ranking within
the tab (60% reach, 20% consistency, 20% comments-per-view); Invest = clears
floors and ≥ tab median. Peer-relative because reach and engagement fall
structurally with size — a fixed bar marked every large page a failure.

**Do not reintroduce these bugs:**
- posts feed and reels feed return *different* posts — join on post code,
  use only the intersection for anything involving views
- engagement vs followers overstates badly when reach ≫ followers — report
  **Engagement Per View %** too; sane band 1–12%, median ~1.25%
- pinned posts are old trophies — exclude
- hidden likes come back as `3` — print "Hidden by page"

Before sending: 0 emoji cells, 0 fills, Engagement Per View under 25%
everywhere, `Posts With Matched View Data` > 0 on every row with views.

## Chatbot discovery

```bash
python core/llm_discovery.py login duckai      # once — you click Continue
python core/llm_discovery.py login chatgpt     # once — you log in
python core/llm_discovery.py ask duckai --region kolkata --categories food
python core/llm_discovery.py resolve "Soham Sinha" "Bong Eats" --region kolkata
```

A browser is required: duck.ai returns `418 ERR_CHALLENGE` to plain HTTP,
ChatGPT needs a login. The tool never accepts terms or logs in by itself —
`login` opens a real window for the user; `--accept-terms` is an explicit
opt-in. Everything it finds lands as `PENDING_AUDIT` with source `llm`.

## Handing over

- A handful of rows → answer in chat. Hundreds → workbook.
- State the read timestamp with any count; counts drift by the minute.
- Say what was *not* assessed and why (private, not found, throttled)
  rather than dropping the rows.
