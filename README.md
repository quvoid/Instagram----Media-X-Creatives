# Instagram Media X Creatives

Free influencer-marketing tools that run through your own Instagram login. No paid APIs.

It does three things:

1. **Find creators from a city** - "give me Kolkata food creators above 20K with email". Exact follower counts, proof they live there, 90-day brand partnerships, content category.
2. **Invest / Don't Invest on a list of pages** - paste any list of Instagram pages and get a verdict per page with the metrics behind it.
3. **Who a brand worked with** - give a brand's Instagram URL and get every collaborator from the last 1-2 years sorted into 4 tiers (paid + boosted, paid, undisclosed boosted, organic).

## Quick start (no coding needed)

**1. Install** - once. You need Python 3.10+ installed ([python.org](https://www.python.org/downloads/), tick "Add to PATH").

```bash
git clone git@github.com:quvoid/Instagram----Media-X-Creatives.git
cd Instagram----Media-X-Creatives
pip install -r requirements.txt
```

**2. Connect your Instagram** - once. This asks you for four cookies from your browser and checks they work. It tells you exactly where to click.

```bash
python setup.py
```

Your login is saved only to a local `.env` file that git ignores. It never leaves your machine except to talk to instagram.com. If Instagram logs you out, run `python setup.py` again.

**3. Open the folder in Claude Code** (or Cursor / any agent IDE) and just say what you want:

- "find kolkata food creators above 20k followers with email"
- "audit these pages for invest / don't invest" - then paste your list, headings and all
- "who did CRED collaborate with in the last 2 years, in tiers"
- "how many creators do we have for chennai"

The agent reads `CLAUDE.md` and the skills in `.claude/skills/`, picks the right tool, tells you how long it will take, runs it, and puts the workbook in `deliverables/`. If `.env` is missing it will tell you to run `python setup.py` first.

Everything below is for people who want to run the scripts directly.

---

## Layout

```
setup.py                     first-run wizard: cookies -> .env, session check, browser install
CLAUDE.md                    what an agent does with a plain-English request
core/session.py              cookies from .env (the only place credentials come from)
core/profile_auditor.py      exact follower-count ladder, throttle detection, 10K gate
core/discovery_sources.py    region/category/campaign definitions + all free harvesters
core/creator_db.py           SQLite store (creator_intelligence.db): schema, queries, NL ask, xlsx export
core/regional_engine.py      harvest -> audit -> deepscan -> deliver pipeline, resumable
core/creator_deep_scan.py    90-day post walk: partnerships, views, medians, contacts, category
core/creator_language_id.py  Bengali speech check via faster-whisper (video deleted after use)
core/llm_discovery.py        ask ChatGPT / duck.ai / Perplexity for creators, resolve names via IG search
core/kolkata_engine.py       legacy Kolkata-specific engine (kept for clean_cell + hub crawl)
page_audit.py                Invest / Don't Invest momentum audit
brand_collab_tiers.py        brand URL -> collaborators in window -> 4 tiers -> workbook
scripts/run_kolkata_deep.py  one-shot: harvest -> audit -> deepscan -> export
scripts/status.py            progress of a running pipeline
docs/CREATOR_DB.md           schema, SQL recipes, worked client briefs
docs/PAGE_AUDIT.md           metrics and verdict logic in full
.claude/skills/              one skill per tool: region-creator-discovery, page-momentum-audit, brand-collab-tiers
```

## 1. Region-wise creator discovery

```bash
python core/regional_engine.py harvest --region kolkata --pages 6      # cheap, wide: geo, hashtag, chaining, topsearch, youtube, llm, directories
python core/regional_engine.py audit   --region kolkata --limit 400    # exact follower count, 10K gate, ranked by geo evidence
python core/regional_engine.py deepscan --region kolkata               # 90-day partnerships, views, emails, category
python core/regional_engine.py deliver --region kolkata --residence 2 --min 10000 --xlsx deliverables/kolkata.xlsx
python core/creator_db.py ask "kolkata food creators above 50k with email"
```

Or the whole thing: `python scripts/run_kolkata_deep.py --region kolkata`.

How verification works, in order:
- **Follower count** is exact, from `users/{pk}/info` (Android UA) or the rendered DOM `span[title]`. Never the rounded `og:description`. Every row carries `followers_precision` (exact / rounded / unresolved).
- **Residence** = posts geotagged at 2+ distinct physical locations inside the region (`geo_evidence`). Bio keywords are the weakest signal and never decide membership on their own.
- **Discovery sources**, ranked by yield: `discover/chaining` (seeded only from geo-backed accounts), LLM citations, free directory pages, topsearch grid, location sections, hashtag sections. Each hit adds to a corroboration score that orders the audit queue but never decides region membership.
- **Partnerships (90 days)**: paid-partnership toggle > tagged/co-author brand accounts > partner hashtags (#ad, #collab, #gifted...).
- **Metrics** are medians, views come from the reels feed joined to posts on shortcode, hidden likes are reported as "Hidden by page" not guessed.
- **Campaign evidence** (e.g. Durga Puja 2025) is verified per creator by a post inside the date window - hashtag recent tabs are newest-first and cannot reach last year.
- Throttling is per-endpoint: a 429 or `feedback_required` is recorded as throttled, never as "account missing".

Regions and categories live in `core/discovery_sources.py`; add a region there and every source picks it up.

## 2. Page momentum audit (Invest / Don't Invest)

Input file: tab names on `##` lines, one handle or URL per line (see `page_audit_input.txt`).

```bash
python page_audit.py --input page_audit_input.txt --output deliverables/Page_Momentum_Audit.xlsx
python page_audit.py --excel-only            # rebuild the workbook from cache without re-scraping
python page_audit.py --per-tab               # one sheet per tab instead of one consolidated sheet
```

Per page: last 12 non-pinned posts via Instagram's own web GraphQL queries (posts + reels, joined on shortcode), then:
- median views, median likes, median comments, posts per week, days since last post
- reach = median views / followers; engagement per view = (median likes + comments) / median views
- **Floors** (fail any = Don't Invest): posted within 21 days, reach >= 2%, consistency >= 0.25
- **Peer score** for pages that pass: 60% reach + 20% consistency + 20% comments-per-view, percentile-ranked inside the same tab
- **Invest** = above the tab median. So the verdict is relative to the page's own peer group, not a fixed threshold.

Every metric used is written into the workbook next to the verdict. No colours, no emojis.

## 3. Brand collaborator 4-tier scan

```bash
python brand_collab_tiers.py --url https://www.instagram.com/cred_club/ --brand CRED --years 2
python brand_collab_tiers.py --url https://www.instagram.com/britanniaindustries/ --years 1 --max-scrolls 30 --output deliverables/britannia_tiers.xlsx
```

What it does: opens the brand's **Tagged** grid and **Reels** grid in a logged-in Playwright session, collects every post/reel URL, opens each one, keeps only posts inside the window (`--years` or `--days`) that have an author other than the brand (tagged creator, co-author, or the post's own author), and reads the paid-partnership label, likes, comments, views and date. Each creator's follower count is resolved exactly (`followers_precision` is written to the row). Nothing is estimated: if Instagram does not expose views for a post the row says 0, not a guess.

### The four tiers

Two independent signals per post:

- **Toggle** - did the creator switch on Instagram's "Paid partnership with ..." label? That is the creator publicly declaring a commercial deal.
- **Boosted** - does the engagement shape look like paid distribution rather than organic reach? Any one of: 1M+ views with a like rate under 0.35%; views over 5x the creator's followers with ER under 1%; 500K+ views with like rate under 0.5%; 50K+ likes; or an #ad / #collab / #sponsored caption with 100K+ views or 5K+ likes.

| Tier | Toggle | Boosted | Meaning for a media buyer |
|---|---|---|---|
| **Tier 1** | ON | Yes | Declared paid deal *and* the brand put ad money behind it. The brand's highest-conviction creators - the ones it paid twice. |
| **Tier 2** | ON | No | Declared paid deal, left to run organically. Confirmed commercial relationship, smaller budget. |
| **Tier 3** | OFF | Yes | No declaration but the numbers say paid distribution. Usually an undisclosed deal, a barter run as an ad, or brand-side whitelisting. Worth checking manually. |
| **Tier 4** | OFF | No | Organic mention, UGC, fan post or a sister-account cross-tag. Noise for partnership analysis. |

The workbook has three tabs: executive summary (post and creator counts per tier, top creators), a per-creator sheet with the creator's size band (Nano / Micro / Mid / Macro / Mega on exact followers), and a per-post master sorted by tier then views with the boost reason and every metric used.

Caveats: a sister brand tagging its parent shows up as a "collaborator" - check any single account that dominates the list. The tagged grid is newest-first, so raise `--max-scrolls` for brands with many tagged posts or the window will not be reached.

## Rules that apply everywhere
- Never fabricate or round a follower count.
- Never write an emoji into a tier string, category or Excel cell (`clean_cell`).
- Save progress incrementally; every command is resumable.
- The tool never accepts terms or logs in on its own.
- `creator_intelligence.db` contains personal contact data and stays local.
