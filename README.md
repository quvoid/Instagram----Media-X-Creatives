# Instagram Media X Creatives

Two free, session-cookie-based Instagram tools for influencer marketing:

1. **Region-wise creator discovery** - find, verify and deep-scan creators who actually live in a city (Kolkata, Punjab, Hyderabad, Chennai, Mumbai, Delhi, Bangalore), with exact follower counts, emails, 90-day brand partnerships and content category.
2. **Page momentum audit (Invest / Don't Invest)** - given a list of Instagram pages, sample their last 12 posts and rank them on current momentum.

No paid APIs. Everything runs through your own logged-in Instagram session.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # fill in from a logged-in browser: DevTools -> Application -> Cookies -> instagram.com
```

`.env` is git-ignored. A `sessionid` is a login - never commit it. If it leaks, log out of all sessions in Instagram settings.

## Layout

```
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
scripts/run_kolkata_deep.py  one-shot: harvest -> audit -> deepscan -> export
scripts/status.py            progress of a running pipeline
docs/CREATOR_DB.md           schema, SQL recipes, worked client briefs
docs/PAGE_AUDIT.md           metrics and verdict logic in full
.claude/skills/              agent skill for Claude Code / any IDE agent
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

## Rules that apply everywhere
- Never fabricate or round a follower count.
- Never write an emoji into a tier string, category or Excel cell (`clean_cell`).
- Save progress incrementally; every command is resumable.
- The tool never accepts terms or logs in on its own.
- `creator_intelligence.db` contains personal contact data and stays local.
