---
name: page-momentum-audit
description: Judge a list of Instagram pages on their current momentum and give each an Invest / Don't Invest call with the exact metrics used (median views, likes, comments, posts per week, reach, engagement per view). Use whenever the user pastes a list of Instagram handles or URLs - with or without tab/group headings - and asks which are worth investing in, wants average views or engagement on them, says "audit these pages", or asks for a momentum / traction check.
---

# Page momentum audit (Invest / Don't Invest)

Full method: `docs/PAGE_AUDIT.md`. Read it before the first run.

## How to handle a plain-English request

The user will usually paste a list straight into chat, often with headings
("Community Pages", "Food Pages", ...). That is the input.

1. Confirm `.env` exists (see CLAUDE.md Step 0).
2. Write the list to a text file in the repo root, in this format:

   ```
   ## Group name exactly as the user wrote it
   handle_or_url
   handle_or_url

   ## Next group
   ...
   ```
   Keep the user's grouping and order. If they gave no headings, use one
   heading `## Pages`. Accept handles, `@handles` or full URLs.
3. Tell them the timing: about 10 s per page (a 600-page list is 1.5-2 h).
   Pages already in `page_audit_cache.json` are reused, not re-fetched.
4. Run:
   ```bash
   python page_audit.py --input mylist.txt --output MyList_Momentum_Audit.xlsx
   ```
   Output lands in `deliverables/`. If the run stops (sleep, throttle),
   rerun the same command; it resumes from the cache.
   `--excel-only` rebuilds the workbook from cache without scraping.
   `--per-tab` gives one sheet per group instead of one consolidated sheet.
5. Give a short status line every few minutes on long lists.

## How to explain the verdict (say this to the user, in this order)

- We looked at each page's last 12 posts that are not pinned.
- Numbers are medians, so one viral post cannot flatter a page.
- Stage 1 - three floors. Fail any one = Don't Invest:
  posted in the last 21 days; median views at least 2% of followers;
  median views at least 25% of average views (consistency).
- Stage 2 - pages that pass are scored against the other pages in the same
  group: 60% reach (views / followers), 20% consistency, 20% comments per
  view. Invest = above the group's median score.
- So Invest is relative to the page's peers, not a fixed bar. That is
  deliberate: reach falls with size, and a fixed bar marks every big page
  a failure.
- Every metric used is in the workbook next to the verdict so it can be
  challenged.

## Things that look like bugs but are not

- "Hidden by page" in the likes column: the page turned off like counts.
- Engagement Per View of 5-20% on a small page can be genuine.
- Posts With Matched View Data below 12: posts and reels are different
  feeds; only the overlap has views.

## Before sending

No emoji cells, no colour fills, every row has the group name in the Tab
column, and no row was silently dropped - private / not found / throttled
pages stay in with a reason.
