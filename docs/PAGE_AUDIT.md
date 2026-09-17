# Page Momentum Audit

Paste the prompt at the bottom into any IDE agent (Claude Code, Cursor, Windsurf, Copilot)
opened on this repo. Everything needed is already committed to the working tree.

---

## What this task is

Audit ~424 Instagram pages listed in `page_audit_input.txt` and judge **current momentum**,
not historical follower count. Output is a single Excel file for a founder:
`Page_Momentum_Audit.xlsx`.

## Files that matter

| File | Role |
|---|---|
| `page_audit.py` | The whole pipeline. Fetch, metrics, verdicts, Excel. |
| `page_audit_input.txt` | The 618 page URLs grouped under `## Tab Name` headers. Order and duplicates are intentional — **do not reorder or dedupe**. |
| `page_audit_cache.json` | Progress cache. Saved after every page. Safe to stop and resume. |
| `Page_Momentum_Audit.xlsx` | The deliverable. |
| `Page_Momentum_Audit_v1_BUGGY_BACKUP.xlsx` | Earlier output with known-bad view/engagement columns. Reference only, do not send. |
| `core/profile_auditor.py` | Holds the Instagram session cookies and the throttle detector. |

## Commands

```bash
python page_audit.py                    # full run, resumable, skips cached pages
python page_audit.py --pause 1.0        # faster (1s between requests instead of 2s)
python page_audit.py --limit 20         # test on a slice
python page_audit.py --excel-only       # rebuild the workbook from cache, no fetching
python page_audit.py --excel-only --per-tab   # also emit one sheet per tab
```

A full run is **424 pages, ~4 requests each**. At `--pause 1.0` expect roughly 45–60 minutes;
at the default 2.0s, roughly 90 minutes.

## How the data is obtained

Instagram's normal REST API (`/api/v1/feed/user/...`) is **hard-throttled** on this session —
it returns `400 {"message":"feedback_required","is_spam":true}`. That is a rate limit, not a
missing account.

The pipeline instead replays the same GraphQL calls the Instagram website makes:

| Need | Source |
|---|---|
| numeric pk + `fb_dtsg`/`lsd` tokens | profile HTML |
| exact follower count | `GET /api/v1/users/{pk}/info/` |
| likes, comments, post dates, pinned flag | `PolarisProfilePostsQuery`, doc_id `38154989454116081` |
| exact reel view counts | `PolarisProfileReelsTabContentQuery`, doc_id `37945290971781723` |

**If Instagram rotates a doc_id and the run starts failing:** open a profile in a browser with
devtools Network open, filter for `graphql/query`, find the request whose
`fb_api_req_friendly_name` matches, and copy the new `doc_id` into the constants at the top of
`page_audit.py`.

## Rules this deliverable must keep

1. **No emojis, no colours anywhere in the workbook.** It goes to a founder.
2. **Never print a hidden like count.** Pages with `like_and_view_counts_disabled: true` return
   `like_count = 3` as a placeholder. Those cells must read `Hidden by page`. Roughly 70% of the
   meme pages do this. Views stay exact on those pages, which is why verdicts lean on views.
3. **Exclude pinned posts** from every metric. They are old trophies — one page had a
   57-week-old pinned reel with 16.9M views.
4. **Follower counts are exact and live**, never the rounded "12M" Instagram displays.
5. **Keep the tab grouping** from `page_audit_input.txt`. The consolidated sheet carries it in
   the `Tab` column.

## The bug that was fixed (do not reintroduce)

The posts feed and the reels feed **do not return the same posts**. The original code averaged
likes from one and views from the other.

Worst case: `janjgirplace` — 12 recent posts with 261–57,310 likes, while its reels feed
returned three months-old virals at 1.7M–7.5M views sharing no post codes. That produced a
reported 1.14M "average views" and a **45.5% engagement rate**.

Second issue: engagement measured against followers is wrong for these pages, because their
reach runs 3x–47x their follower count. One page came out at **69.4%**.

**The fix, now in `compute()`:**
- join posts to reels **on the post code**; only use posts present in both for anything
  involving views
- new column `Posts With Matched View Data` shows how many posts backed each row
- new column `Engagement Per View %` — engagement ÷ views, the correct measure for reels.
  Sane range is 1–4%
- all metrics use **medians**, not means, so one viral post cannot carry a page
- a page whose reels feed returns only older posts is disqualified with that stated as the
  reason, rather than given a fabricated reach ratio
- raw per-post rows are now cached (`_raw_posts`, `_raw_reels`) so future metric changes
  recompute in seconds instead of re-scraping

**Sanity check after any run** — the right test is NOT "engagement rate above 10%". Once the
join is correct, a genuinely strong creator whose reels reach 2-3x their follower count can
legitimately show 16-21% engagement against followers. `thecurlypoet` does: 829,533 followers,
2,386,800 median views, 168,408 median likes — 20.5% against followers but a sane 7.1% per view,
with 9 of 9 posts matched.

Check these instead:
- `Engagement Per View %` should sit roughly in the 1-12% band. The median across all pages is
  1.25%. Anything above about 25% means the join is broken again.
- `Posts With Matched View Data` should be greater than 0 for any page reporting views. A page
  with views but 0 matched posts is the old bug returning.

## Verdict logic

**Stage 1 — hard floors, fail any one and it is Don't Invest**
- posted within 21 days
- median reel views at least 2% of follower count
- median views at least 25% of average views (not a one-hit wonder)

**Stage 2 — ranked against pages in the same tab**
- 60% reach percentile (median views ÷ followers)
- 20% consistency percentile
- 20% comments-per-view percentile
- Invest = clears every floor and scores at or above its tab's median

Peer comparison is essential: reach and engagement fall structurally as follower count rises.
An 11.9M-follower page at 528K views has a reach ratio of 0.04; a 60K city page at 90K views
has 1.5. A single fixed bar marked every large page a failure.

## Known state

- Session belongs to `@schwarzdontfollow` (`ds_user_id 25113411270`), cookies in
  `core/profile_auditor.py`.
- **Security debt:** that live `sessionid` is in plaintext across 12+ files including
  `AGENTS.md`, and a commit containing it is already pushed to GitHub. Rotating the session in
  Instagram's settings invalidates it but **will break this pipeline until the new cookies are
  pasted in**. Moving them to a git-ignored `.env` is the proper fix and has not been done.

---

## PROMPT TO PASTE INTO THE NEXT IDE

```
Read docs/PAGE_AUDIT.md in this repo first, then continue the page momentum audit.

Current state: page_audit.py has the fixed metrics (posts joined to reels on post code,
engagement per view, medians). A full run may be partially complete — check
page_audit_cache.json for how many of the 424 pages are done.

Do this:
1. Run `python page_audit.py --pause 1.0` to finish any remaining pages. It is resumable
   and skips whatever is already cached. Report progress and ETA as it goes.
2. When it completes, run `python page_audit.py --excel-only` to build
   Page_Momentum_Audit.xlsx — one consolidated "All Creators" sheet, 618 rows, with the
   tab name in column B.
3. Before handing it over, verify:
   - zero emoji characters and zero colour fills in any cell
   - Engagement Per View % sits in the 1-12% band (median ~1.25%); anything above 25%
     means the posts/reels join is broken again. Do NOT flag high engagement-vs-followers
     as a bug on its own - see the sanity-check section in the handoff.
   - Posts With Matched View Data is greater than 0 for every page reporting views
   - pages that hide likes read "Hidden by page", never the number 3
   - row count is 618 and the tab order matches page_audit_input.txt
4. Tell me the Invest / Don't Invest / Not assessed counts and anything that looks wrong.

Rules: no emojis, no colours, exact follower counts only, never invent a number. If
Instagram starts returning feedback_required or 429, stop and tell me rather than
retrying in a loop.
```
