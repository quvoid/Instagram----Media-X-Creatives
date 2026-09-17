# CREATOR_DB.md — the permanent creator store

**Read this before answering any question about creators, regions, campaigns, or brand
collaborators.** The answer is almost always a query against `creator_intelligence.db`,
not a new scrape.

```
creator_intelligence.db      <- single SQLite file, repo root, no server
core/creator_db.py           <- schema, writes, query API, CLI
core/regional_engine.py      <- harvest / audit / deliver / backfill
core/discovery_sources.py    <- region, category and campaign definitions
core/profile_auditor.py      <- the exact follower-count ladder
```

---

## 1. Why it exists

Discovery used to build a throwaway list per client. Kolkata produced 170 creators and each
Enamor state barely 90 — not because the market is that small, but because:

1. **Location and hashtag reads only took the first page.** One Kolkata place gives 61 authors
   on page 0 and **176 distinct authors by page 2**, and Instagram still reports
   `more_available: true`. The great majority of every place was being left on the table.
2. **Residence was judged on bio keywords.** Every genuine Kolkata creator who doesn't type
   "Kolkata" in their bio was discarded. That is a huge false-negative class.
3. **Nothing accumulated.** Each client started from zero, and the work was stranded in
   one-off `.xlsx` files.

Point 3 was the expensive one: the first backfill pulled **9,193 distinct handles** out of
rosters and workbooks already sitting in this repo.

---

## 2. The three-step loop

| Step | Cost | What it does |
|---|---|---|
| `harvest` | cheap, wide | Pages locations and hashtags, walks the chaining graph, sweeps YouTube. No per-creator requests. Writes leads + evidence. |
| `audit` | expensive, narrow | Resolves **exact** follower counts for pending leads, most-corroborated first, within a budget. Fully resumable. |
| `deliver` | free | A query over everything ever harvested, exported as a workbook. |

Harvest wide once, audit continuously, deliver per client. **A client brief is a filter, not a
new scrape.**

---

## 3. Schema

### `creators` — one row per Instagram handle
| Column | Meaning |
|---|---|
| `handle` (PK) | lowercase, no `@` |
| `pk` | Instagram numeric id |
| `followers` | integer count |
| `followers_precision` | **`exact`** \| `rounded` \| `unresolved` — **always filter on `exact` for anything client-facing** |
| `followers_source` | which rung of the ladder produced it |
| `resolved_at` | UTC ISO. Counts drift by the minute; a count without this is not a fact |
| `tier` | `Mega (1M+)` / `Macro (500K-1M)` / `Mid-Tier (100K-500K)` / `Micro (10K-100K)` / `Nano (<10K)` |
| `ig_category` | Instagram's own category ("Digital creator") |
| `category` | our plain-text label ("Food & Culinary") |
| `email`, `phone` | structured business contacts where exposed, else bio-scraped |
| `city_name` | Instagram's own city field (business accounts only) |
| `is_verified`, `is_private`, `media_count`, `following_count` | |
| `branded_content_ready` | eligible for paid-partnership / branded-content tooling |
| `engagement_rate_pct`, `avg_plays` | only when the feed endpoint was reachable |
| `audit_status` | `VALID` / `BELOW_GATE (n)` / `404_NOT_FOUND` / `PENDING_AUDIT` / `BORDERLINE_ROUNDED_NEEDS_EXACT` |
| `review_flag` | `region_review_needed` / `below_gate` / `gone` / `unresolved`, else empty |

### `observations` — append-only provenance
`(handle, source, detail, region, observed_at)`, source ∈ `chaining · llm · topsearch · geo ·
hashtag · hub · directory · youtube · manual`.
**Corroboration = `COUNT(DISTINCT source)`.** Ranking the audit queue by it turned a pipeline
that mostly logged SKIPPED into 5 verified creators from 5 audits.

### `geo_evidence` — residence proof, not a bio guess
`(handle, region, place_pk, place_name, post_taken_at, like_count)`.
**`COUNT(DISTINCT place_pk)` in a region is the residence signal.** One place is a visit; two or
more separate real Instagram locations is evidence they operate there. This is what satisfies
"must actually live in Kolkata".

### `campaign_evidence` — participation proof
`(handle, campaign, evidence_type, evidence_ref, post_taken_at, post_code, like_count)`,
`evidence_type` ∈ `hashtag · location`.
A row exists only if a post of theirs falls **inside the campaign's date window**, checked
against Instagram's own `taken_at`. Campaigns are defined in `discovery_sources.CAMPAIGNS` —
`durga_puja_2025` is 2025-09-18 → 2025-10-10 (Mahalaya through a week past Vijaya Dashami),
covering both the hashtags and the big pandals as locations.

### `cross_platform` — the same person elsewhere
`(handle, platform, profile_url, display_name, reach, reach_precision)`.
YouTube subscriber counts are **rounded** (`261K`) — that is all YouTube renders. Never present
them as exact.

### `brand_collabs` — feeds from the existing competitor-collaborator scan
`(handle, brand, post_url, is_paid_partnership, tier, post_taken_at)`. This is where the Visa
strategy lives: the competitor's collaborator list becomes a permanent, queryable pool.

### `regions`
The region config actually used for a run, stored as JSON for reproducibility.

---

## 4. Answering a brief

### Natural language
```bash
python core/creator_db.py ask "kolkata food creators above 50k who did durga pujo 2025 with email"
python core/creator_db.py ask "top 100 punjab fashion creators living in punjab"
```
The parser handles region, tier, ranges (`50k-200k`, `above 50k`), category, campaign,
`with email`, `verified`, `lives in` (→ residence ≥ 2), `youtube`, and `collaborators of @brand`.

### Structured
```bash
python core/creator_db.py query --region kolkata --category food --min 10000 \
       --campaign durga_puja_2025 --residence 2 --has-email --xlsx out.xlsx
```

### Raw SQL — the escape hatch for anything the flags don't cover
```bash
python core/creator_db.py sql "SELECT handle, followers FROM creators WHERE ..."
python core/creator_db.py stats
python core/creator_db.py schema
```

---

## 4b. Asking a chatbot (`core/llm_discovery.py`)

Queries ChatGPT / duck.ai / Perplexity / Gemini through a real browser and turns their answers
into audited creators.

**A browser is required, not a nicety.** duck.ai returns `HTTP 418 ERR_CHALLENGE` to a plain HTTP
client because its `x-vqd-hash-1` header is obfuscated JavaScript that must be executed; ChatGPT
needs a logged-in session. A browser does both for free — the challenge runs natively and a
persistent profile keeps the login.

**The important part is that nothing an LLM says is trusted.** Chatbots mostly answer with
*names*, and the handles they do state are often invented. So:

1. pull both `@handles` and person names out of the answer;
2. resolve every name through Instagram's own topsearch — measured:
   `"Soham Sinha"` → **@kolkatadelites** (605,822 followers, verified),
   `"Bong Eats"` → **@bongeats**, `"Tannistha Rupayan"` → **@themasala_trails**;
3. write everything as `PENDING_AUDIT` with source `llm`;
4. the audit resolves the exact count and decides. A hallucinated handle simply comes back
   `404_NOT_FOUND` — tested with an invented `@indrani_eats`, while the name behind it resolved
   to a real account.

**An LLM never contributes a follower number, only a name to go and check.**

One-time setup, done by you — the tool will not log in or accept terms on its own:
```bash
python core/llm_discovery.py login chatgpt     # real window opens, you log in
python core/llm_discovery.py login duckai      # you click Continue once
```
The profile persists under `llm_profiles/<provider>` and is reused headless afterwards.
`--accept-terms` lets a run click a consent dialog itself, if you'd rather.

```bash
python core/llm_discovery.py ask duckai  --region kolkata --categories food
python core/llm_discovery.py ask chatgpt --region punjab --categories fashion
python core/llm_discovery.py resolve "Soham Sinha" "Bong Eats" --region kolkata
python core/regional_engine.py audit --region kolkata --sources-min 2 --limit 200
```

`--sources-min 2` is the natural follow-up: a handle that a chatbot named *and* Instagram's own
graph corroborates is about as good as a lead gets.

Raw answers are kept in `llm_discovery_answers.json` so a claim can always be traced back to the
prompt and provider that produced it.

---

## 5. Worked client briefs

**Britannia — creators who live in Kolkata and did Durga Puja last year**
```bash
python core/regional_engine.py harvest --region kolkata --campaign durga_puja_2025 --pages 6
python core/regional_engine.py audit   --region kolkata --limit 400
python core/regional_engine.py deliver --region kolkata --campaign durga_puja_2025 \
       --residence 2 --min 10000 --xlsx Britannia_Kolkata_Pujo.xlsx \
       --brief "Kolkata-resident creators with verified Durga Puja 2025 participation"
```

**Enamor — four regions**
```bash
for r in punjab hyderabad chennai mumbai; do
  python core/regional_engine.py harvest --region $r --pages 6
  python core/regional_engine.py audit   --region $r --limit 400
  python core/regional_engine.py deliver --region $r --residence 2 --min 10000 \
         --xlsx Enamor_${r}.xlsx
done
```

**Visa — a competitor's collaborators, plus who the competitor has *not* used**
```bash
python core/regional_engine.py deliver --brand <competitor> --min 10000 --xlsx Visa_Pool.xlsx
python core/regional_engine.py deliver --category fintech --exclude-brand <competitor> --min 10000
```

---

## 6. SQL recipes

```sql
-- Strongest Kolkata residents: several distinct places, several sources, exact count
SELECT c.handle, c.name, c.followers, c.tier, c.email,
       (SELECT COUNT(DISTINCT g.place_pk) FROM geo_evidence g
          WHERE g.handle=c.handle AND g.region='kolkata') AS places,
       (SELECT COUNT(DISTINCT o.source) FROM observations o
          WHERE o.handle=c.handle) AS srcs
FROM creators c
WHERE c.followers_precision='exact' AND c.followers>=10000
  AND (c.review_flag IS NULL OR c.review_flag='')
HAVING places>=2 AND srcs>=2
ORDER BY c.followers DESC;

-- Durga Puja 2025 participants with the actual post as proof
SELECT c.handle, c.followers, e.evidence_type, e.evidence_ref,
       datetime(e.post_taken_at,'unixepoch') AS posted,
       'https://www.instagram.com/p/' || e.post_code || '/' AS post_url
FROM campaign_evidence e JOIN creators c ON c.handle=e.handle
WHERE e.campaign='durga_puja_2025' AND c.followers_precision='exact'
ORDER BY c.followers DESC;

-- Creators strong on Instagram AND YouTube
SELECT c.handle, c.followers AS ig, x.reach AS yt, x.profile_url
FROM creators c JOIN cross_platform x ON x.handle=c.handle
WHERE x.platform='youtube' AND c.followers_precision='exact' AND c.followers>=10000
ORDER BY (c.followers + COALESCE(x.reach,0)) DESC;

-- Audit queue: what to spend the next budget on
SELECT c.handle,
       (SELECT COUNT(DISTINCT o.source) FROM observations o WHERE o.handle=c.handle) AS srcs,
       (SELECT COUNT(DISTINCT g.place_pk) FROM geo_evidence g WHERE g.handle=c.handle) AS places
FROM creators c WHERE c.audit_status='PENDING_AUDIT'
ORDER BY srcs DESC, places DESC LIMIT 50;

-- What a region actually contains, by tier
SELECT c.tier, COUNT(*) n FROM creators c
WHERE c.followers_precision='exact'
  AND EXISTS (SELECT 1 FROM observations o WHERE o.handle=c.handle AND o.region='kolkata')
GROUP BY c.tier ORDER BY n DESC;
```

---

## 7. Rules

1. **Never present a `rounded` or `unresolved` count to a client.** `query_creators()` defaults
   to `require_exact=True`; `--allow-rounded` is for internal triage only.
2. **Never write a follower count from a third-party source into `creators.followers`.** Vendor
   directory numbers, YouTube subscriber counts and LLM answers are leads and annotations.
   They live in `cross_platform` or nowhere.
3. **A `PENDING_AUDIT` row is a lead, not a creator.** It carries `followers = 0` and
   `precision = 'unresolved'` on purpose.
4. **Residence is `geo_evidence`, not a bio keyword.** Bio matching stays as a weak secondary
   signal only.
5. **A campaign claim needs a `campaign_evidence` row**, which means a real post inside the
   window. Never infer participation from a bio or a hashtag in a caption outside the dates.
6. **Zero emojis in any workbook cell.** Everything exported goes through
   `kolkata_engine.clean_cell()`.
7. **A throttled response is not a missing account.** See AGENTS.md §1b.

---

## 8. Extending it

* **New region** — add an entry to `discovery_sources.REGIONS` (`place_queries`,
  `authenticity_keywords`, `search_tokens`, `language_hints`). Every source picks it up.
* **New category** — add to `discovery_sources.CATEGORIES` (`search_terms`, `hashtags`,
  `bio_keywords`). Extends the topsearch grid, hashtag sweep, YouTube grid and LLM prompts at once.
* **New campaign** — add to `discovery_sources.CAMPAIGNS` with `start`, `end`, `hashtags` and
  `place_queries`. The date window is enforced automatically.
* **New source** — write a harvester returning `{"status", "users"|"observations"}`, add a weight
  in `discovery_sources.SOURCE_WEIGHTS`, and call `creator_db.add_candidate_only()`.
