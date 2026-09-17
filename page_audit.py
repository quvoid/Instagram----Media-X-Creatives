"""
================================================================================
PAGE MOMENTUM AUDIT
================================================================================
For every page in page_audit_input.txt: pull the latest posts and reels, and
judge CURRENT MOMENTUM rather than historical follower count.

Data sources (all live, all through the user's session):
  users/{pk}/info                      exact follower count
  PolarisProfilePostsQuery             likes, comments, post dates, pinned flag
  PolarisProfileReelsTabContentQuery   exact play counts per reel

Two things this is careful about, because the output goes to a founder:

  HIDDEN COUNTS. A page with "hide like count" turned on returns like_count = 3
  on every post - a placeholder, not a real number. The flag is
  like_and_view_counts_disabled. Those pages report "Hidden by page" for likes
  and engagement rate; the number 3 is never printed as a metric. View counts
  are still exact on those pages, which is why the verdict leans on views.

  PINNED POSTS. Pinned posts sit at the top of a grid and are usually old top
  performers - one page had a 57-week-old pinned reel with 16.9M views. They are
  excluded from every momentum metric and counted separately.

Output: Page_Momentum_Audit.xlsx - one tab per group, in the supplied order,
plain text, no colours, no emojis.

  python page_audit.py                 # full run, resumable
  python page_audit.py --limit 20      # try a slice first
  python page_audit.py --excel-only    # rebuild the workbook from the cache
================================================================================
"""

import sys, os, re, json, time, statistics
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from curl_cffi import requests as cffi

from core.profile_auditor import (
    COOKIES, WEB_UA, ANDROID_UA, IG_APP_ID, is_throttled, now_iso, format_followers,
)

INPUT_FILE = os.path.join(BASE_DIR, "page_audit_input.txt")
CACHE_FILE = os.path.join(BASE_DIR, "page_audit_cache.json")   # shared across lists
EXCEL_FILE = os.path.join(BASE_DIR, "deliverables", "Page_Momentum_Audit.xlsx")

POSTS_DOC_ID = "38154989454116081"   # PolarisProfilePostsQuery
REELS_DOC_ID = "37945290971781723"   # PolarisProfileReelsTabContentQuery

SAMPLE_SIZE = 12

# ---- verdict thresholds (printed into the workbook so they can be challenged) --
ACTIVE_DAYS = 21           # must have posted within this many days
FLOOR_REACH_RATIO = 0.02   # absolute floor: median views vs followers
FLOOR_CONSISTENCY = 0.25   # absolute floor: median / average views

METHODOLOGY = (
    "Latest {n} posts and reels per page, pinned posts excluded. Two stages. "
    "Stage 1, absolute floors that rule a page out at any size: must have posted within "
    "{d} days, Reach Ratio at or above {r}, Consistency at or above {c}. "
    "Stage 2, peer comparison within the page's own tab: Momentum Score = "
    "60 percent Reach Ratio percentile + 20 percent Consistency percentile + "
    "20 percent Comments-per-view percentile. Invest means the page clears every floor "
    "and scores at or above the median for its tab. "
    "Peer comparison is used because reach and engagement fall structurally as follower "
    "count rises - an 11.9M-follower page reaching 528K views has a Reach Ratio of 0.04 "
    "while a 60K-follower city page doing 90K views has 1.5, and a single fixed bar would "
    "mark every large page a failure."
).format(n=SAMPLE_SIZE, d=ACTIVE_DAYS, r=FLOOR_REACH_RATIO, c=FLOOR_CONSISTENCY)


# ==============================================================================
# INPUT
# ==============================================================================
def load_tabs() -> List[Dict[str, Any]]:
    tabs, cur = [], None
    for line in open(INPUT_FILE, encoding="utf-8"):
        s = line.strip()
        if not s or (s.startswith("#") and not s.startswith("## ")):
            continue
        if s.startswith("## "):
            cur = {"name": s[3:].strip(), "handles": []}
            tabs.append(cur)
            continue
        if cur is not None:
            cur["handles"].append(s.lower())
    return tabs


# ==============================================================================
# HTTP
# ==============================================================================
def _session():
    return cffi.Session(impersonate="chrome120")


def fetch_profile(handle: str) -> Dict[str, Any]:
    """Profile HTML gives the numeric pk and the GraphQL tokens in one request."""
    out = {"pk": None, "fb_dtsg": None, "lsd": None, "http": None, "exists": None}
    try:
        r = _session().get(f"https://www.instagram.com/{handle}/",
                           headers={"User-Agent": WEB_UA,
                                    "accept-language": "en-US,en;q=0.9"},
                           cookies=COOKIES, timeout=25)
        out["http"] = r.status_code
        if is_throttled(r):
            out["exists"] = None
            out["throttled"] = True
            return out
        if r.status_code != 200:
            out["exists"] = False
            return out
        html = r.text
        m = re.search(r'"profilePage_(\d+)"', html) or re.search(r'"user_id":"(\d+)"', html)
        out["pk"] = m.group(1) if m else None
        d = re.search(r'"dtsg":\{"token":"([^"]+)"', html) or re.search(r'"fb_dtsg":"([^"]+)"', html)
        out["fb_dtsg"] = d.group(1) if d else None
        l = re.search(r'"LSD",\[\],\{"token":"([^"]+)"', html) or re.search(r'"lsd":"([^"]+)"', html)
        out["lsd"] = l.group(1) if l else None
        out["exists"] = out["pk"] is not None
    except Exception as e:
        out["error"] = f"{type(e).__name__}"
    return out


def fetch_followers(pk: str) -> Dict[str, Any]:
    out = {"followers": None, "precision": "unresolved", "is_verified": None,
           "is_private": None, "category": "", "media_count": None}
    try:
        r = _session().get(f"https://www.instagram.com/api/v1/users/{pk}/info/",
                           headers={"User-Agent": ANDROID_UA, "x-ig-app-id": IG_APP_ID,
                                    "x-csrftoken": COOKIES["csrftoken"],
                                    "referer": "https://www.instagram.com/"},
                           cookies=COOKIES, timeout=25)
        if is_throttled(r) or r.status_code != 200:
            out["throttled"] = is_throttled(r)
            return out
        u = (r.json() or {}).get("user", {})
        if u.get("follower_count") is not None:
            out["followers"] = int(u["follower_count"])
            out["precision"] = "exact"
        out["is_verified"] = u.get("is_verified")
        out["is_private"] = u.get("is_private")
        out["category"] = u.get("category") or ""
        out["media_count"] = u.get("media_count")
    except Exception:
        pass
    return out


def _graphql(handle: str, friendly_name: str, doc_id: str, variables: Dict[str, Any],
             tokens: Dict[str, Any], referer_suffix: str = ""):
    body = {"av": COOKIES["ds_user_id"], "__d": "www", "__user": "0", "__a": "1",
            "__comet_req": "7", "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": friendly_name, "server_timestamps": "true",
            "doc_id": doc_id, "variables": json.dumps(variables, separators=(",", ":"))}
    if tokens.get("fb_dtsg"):
        body["fb_dtsg"] = tokens["fb_dtsg"]
    if tokens.get("lsd"):
        body["lsd"] = tokens["lsd"]
    headers = {"User-Agent": WEB_UA,
               "content-type": "application/x-www-form-urlencoded",
               "x-csrftoken": COOKIES["csrftoken"], "x-ig-app-id": IG_APP_ID,
               "x-fb-friendly-name": friendly_name, "x-asbd-id": "359341",
               "origin": "https://www.instagram.com",
               "referer": f"https://www.instagram.com/{handle}/{referer_suffix}",
               "accept": "*/*", "accept-language": "en-US,en;q=0.9"}
    if tokens.get("lsd"):
        headers["x-fb-lsd"] = tokens["lsd"]
    return _session().post("https://www.instagram.com/graphql/query",
                           headers=headers, cookies=COOKIES, data=body, timeout=30)


def fetch_posts(handle: str, tokens: Dict[str, Any]) -> Dict[str, Any]:
    """Likes, comments, dates and the pinned flag."""
    out = {"status": "failed", "posts": []}
    variables = {
        "data": {"count": SAMPLE_SIZE, "include_reel_media_seen_timestamp": True,
                 "include_relationship_info": True, "latest_besties_reel_media": True,
                 "latest_reel_media": True},
        "username": handle,
        "__relay_internal__pv__PolarisMultiCaptionCarouselEnabledrelayprovider": True,
        "__relay_internal__pv__PolarisShortDramaEnabledrelayprovider": False,
        "__relay_internal__pv__PolarisReelsRecoDebugOverlayEnabledrelayprovider": False,
    }
    try:
        r = _graphql(handle, "PolarisProfilePostsQuery", POSTS_DOC_ID, variables, tokens)
        if is_throttled(r):
            out["status"] = "throttled"
            return out
        if r.status_code != 200:
            out["status"] = f"http_{r.status_code}"
            return out
        edges = (((r.json().get("data") or {})
                  .get("xdt_api__v1__feed__user_timeline_graphql_connection") or {})
                 .get("edges") or [])
        for e in edges:
            n = e.get("node", {})
            out["posts"].append({
                "code": n.get("code"),
                "media_type": n.get("media_type"),
                "like_count": n.get("like_count"),
                "comment_count": n.get("comment_count"),
                "taken_at": n.get("taken_at"),
                "pinned": bool(n.get("timeline_pinned_user_ids")),
                "counts_hidden": bool(n.get("like_and_view_counts_disabled")),
                "is_paid_partnership": bool(n.get("is_paid_partnership")),
            })
        out["status"] = "ok"
    except Exception as e:
        out["status"] = f"{type(e).__name__}"
    return out


def _walk(obj, found):
    if isinstance(obj, dict):
        if obj.get("code") and ("play_count" in obj or "like_count" in obj):
            found.append(obj)
        for v in obj.values():
            _walk(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, found)


def fetch_reels(handle: str, pk: str, tokens: Dict[str, Any]) -> Dict[str, Any]:
    """Exact play counts. Still available on pages that hide their like counts."""
    out = {"status": "failed", "reels": []}
    variables = {"data": {"include_feed_video": True, "page_size": SAMPLE_SIZE,
                          "target_user_id": str(pk)},
                 "user_id": str(pk),
                 "__relay_internal__pv__PolarisShortDramaEnabledrelayprovider": False}
    try:
        r = _graphql(handle, "PolarisProfileReelsTabContentQuery", REELS_DOC_ID,
                     variables, tokens, referer_suffix="reels/")
        if is_throttled(r):
            out["status"] = "throttled"
            return out
        if r.status_code != 200:
            out["status"] = f"http_{r.status_code}"
            return out
        found, seen = [], set()
        _walk(r.json(), found)
        for n in found:
            c = n.get("code")
            if not c or c in seen:
                continue
            seen.add(c)
            out["reels"].append({
                "code": c,
                "play_count": n.get("play_count"),
                "like_count": n.get("like_count"),
                "comment_count": n.get("comment_count"),
                "counts_hidden": bool(n.get("like_and_view_counts_disabled")),
            })
        out["status"] = "ok"
    except Exception as e:
        out["status"] = f"{type(e).__name__}"
    return out


# ==============================================================================
# METRICS
# ==============================================================================
def compute(handle: str, prof: Dict[str, Any], foll: Dict[str, Any],
            posts: Dict[str, Any], reels: Dict[str, Any]) -> Dict[str, Any]:
    r: Dict[str, Any] = {
        "handle": handle,
        "profile_url": f"https://www.instagram.com/{handle}/",
        "checked_at": now_iso(),
        "status": "OK",
        "followers": foll.get("followers"),
        "followers_precision": foll.get("precision"),
        "is_verified": foll.get("is_verified"),
        "is_private": foll.get("is_private"),
        "ig_category": foll.get("category"),
        "posts_analysed": 0, "reels_analysed": 0, "pinned_excluded": 0,
        "avg_views": None, "median_views": None,
        "avg_likes": None, "avg_comments": None,
        "engagement_rate_pct": None, "reach_ratio": None, "consistency": None,
        "days_since_last_post": None, "posts_per_week": None,
        "likes_hidden": False, "verdict": "Pending", "verdict_reason": "",
        "verdict_basis": "", "comment_rate_pct": None, "momentum_score": None,
        "peer_reach_percentile": None, "disqualifiers": [],
        "median_likes": None, "median_comments": None,
        "engagement_per_view_pct": None, "posts_with_views": 0,
        "posts_with_visible_likes": 0,
    }

    if prof.get("throttled") or foll.get("throttled"):
        r["status"] = "THROTTLED - not measured"
        r["verdict"] = "Not assessed"
        r["verdict_reason"] = "Instagram rate limit reached; page not measured"
        return r
    if prof.get("exists") is False:
        r["status"] = "NOT FOUND"
        r["verdict"] = "Not assessed"
        r["verdict_reason"] = "Page not found or renamed"
        return r
    if foll.get("followers") is None:
        r["status"] = "FOLLOWERS UNRESOLVED"
        r["verdict"] = "Not assessed"
        r["verdict_reason"] = "Could not resolve follower count"
        return r
    if foll.get("is_private"):
        r["status"] = "PRIVATE"
        r["verdict"] = "Not assessed"
        r["verdict_reason"] = "Private account"
        return r

    all_posts = posts.get("posts", [])
    pinned = [p for p in all_posts if p["pinned"]]
    live_posts = [p for p in all_posts if not p["pinned"]]
    r["pinned_excluded"] = len(pinned)

    if not live_posts:
        r["status"] = "NO RECENT POSTS"
        r["verdict_reason"] = "No recent non-pinned posts available"
        return r

    # ---- join posts to reels ON THE POST CODE --------------------------------
    # The posts tab and the reels tab do NOT return the same set. One page's
    # posts tab held 12 recent posts (261 to 57,310 likes) while its reels tab
    # returned three year-old virals at 1.6M to 7.5M plays, sharing no codes at
    # all. Averaging views from one set and likes from the other describes two
    # different time periods and produced a 45% engagement rate. So every metric
    # below is computed from the SAME posts: recent, non-pinned, and present in
    # both responses wherever views are involved.
    reel_by_code = {x["code"]: x for x in reels.get("reels", []) if x.get("code")}
    matched = [(p, reel_by_code[p["code"]]) for p in live_posts if p["code"] in reel_by_code]

    r["posts_analysed"] = len(live_posts)
    r["reels_analysed"] = len(reel_by_code)
    r["posts_with_views"] = len(matched)

    # ---- views: only from posts that are in BOTH responses -------------------
    views = [rl["play_count"] for _, rl in matched if rl.get("play_count")]
    if views:
        r["avg_views"] = round(statistics.mean(views))
        r["median_views"] = round(statistics.median(views))
        r["reach_ratio"] = round(r["median_views"] / r["followers"], 3)
        r["consistency"] = round(r["median_views"] / r["avg_views"], 3) if r["avg_views"] else None

    # ---- likes and comments: same recent, non-pinned posts -------------------
    hidden = [p for p in live_posts if p["counts_hidden"]]
    r["likes_hidden"] = bool(hidden) and len(hidden) >= max(1, len(live_posts) // 2)

    visible = [p for p in live_posts if not p["counts_hidden"]]
    r["posts_with_visible_likes"] = len(visible)
    if visible:
        likes = [p["like_count"] for p in visible if p.get("like_count") is not None]
        if likes:
            r["avg_likes"] = round(statistics.mean(likes))
            r["median_likes"] = round(statistics.median(likes))
    comments = [p["comment_count"] for p in live_posts if p.get("comment_count") is not None]
    if comments:
        r["avg_comments"] = round(statistics.mean(comments))
        r["median_comments"] = round(statistics.median(comments))

    # ---- engagement -----------------------------------------------------------
    # Two denominators, because they answer different questions.
    #
    # Per view is the honest one for these pages: their reach routinely runs
    # several times their follower count, so dividing engagement by followers
    # overstates it badly - one page came out at 69% that way. Medians are used
    # so a single viral post cannot carry the figure.
    if r.get("median_likes") is not None and not r["likes_hidden"]:
        eng_med = (r["median_likes"] or 0) + (r["median_comments"] or 0)
        r["engagement_rate_pct"] = round(eng_med / r["followers"] * 100, 3)
        if r.get("median_views"):
            r["engagement_per_view_pct"] = round(eng_med / r["median_views"] * 100, 3)
    elif r["likes_hidden"] and r.get("median_comments") is not None and r.get("median_views"):
        # Likes hidden: comments are still real, so report what can be stood behind.
        r["engagement_per_view_pct"] = round(
            r["median_comments"] / r["median_views"] * 100, 3)

    # ---- recency and cadence -------------------------------------------------
    stamps = [p["taken_at"] for p in live_posts if p.get("taken_at")]
    if stamps:
        newest, oldest = max(stamps), min(stamps)
        now = datetime.now(timezone.utc).timestamp()
        r["days_since_last_post"] = round((now - newest) / 86400, 1)
        span_days = max((newest - oldest) / 86400, 0.1)
        r["posts_per_week"] = round(len(stamps) / span_days * 7, 1)

    # ---- comment rate: the engagement signal that survives hidden likes ------
    if r.get("median_comments") is not None and r.get("median_views"):
        r["comment_rate_pct"] = round(r["median_comments"] / r["median_views"] * 100, 4)

    # ---- hard disqualifiers (absolute, tier independent) ---------------------
    # Only things that make a page unusable regardless of size.
    dq = []
    if r["days_since_last_post"] is None:
        dq.append("no post dates available")
    elif r["days_since_last_post"] > ACTIVE_DAYS:
        dq.append(f"inactive, last post {r['days_since_last_post']} days ago")
    if r["reach_ratio"] is None:
        if r.get("reels_analysed") and not r.get("posts_with_views"):
            dq.append("reels tab returned only older posts; no view data for recent posts")
        else:
            dq.append("no reel view data for recent posts")
    elif r["reach_ratio"] < FLOOR_REACH_RATIO:
        dq.append(f"reach floor missed, median views only {r['reach_ratio']}x followers")
    if r["consistency"] is not None and r["consistency"] < FLOOR_CONSISTENCY:
        dq.append(f"one viral post carrying the average, consistency {r['consistency']}")

    r["disqualifiers"] = dq

    basis = []
    if r["days_since_last_post"] is not None:
        basis.append(f"last post {r['days_since_last_post']}d ago")
    if r["reach_ratio"] is not None:
        basis.append(f"reach ratio {r['reach_ratio']}")
    if r["consistency"] is not None:
        basis.append(f"consistency {r['consistency']}")
    if r["engagement_per_view_pct"] is not None:
        basis.append(f"engagement per view {r['engagement_per_view_pct']}%")
    if r["engagement_rate_pct"] is not None:
        basis.append(f"engagement vs followers {r['engagement_rate_pct']}%")
    elif r["likes_hidden"]:
        basis.append("likes hidden by page, judged on views and comments")
    basis.append(f"{r.get('posts_with_views', 0)} posts with matched view data")
    if r.get("comment_rate_pct") is not None:
        basis.append(f"comments per view {r['comment_rate_pct']}%")
    r["verdict_basis"] = "; ".join(basis)

    # The verdict itself is assigned later, peer-relative within each tab.
    r["verdict"] = "Pending"
    r["verdict_reason"] = ""
    return r


# ==============================================================================
# VERDICTS - peer relative, because reach and engagement fall as pages get bigger
# ==============================================================================
# An 11.9M-follower meme page reaching 528K views has a reach ratio of 0.04; a
# 60K-follower city page doing 90K views has 1.5. A single fixed bar marks every
# large page a failure, which is not a useful answer. So each page is judged
# against the other pages in ITS OWN tab, on top of absolute floors that catch
# pages nobody should buy at any size.
def assign_verdicts(cache: Dict[str, Any], tabs: List[Dict[str, Any]]) -> None:
    for tab in tabs:
        peers = []
        for h in set(tab["handles"]):
            rec = cache.get(h)
            if not rec or rec.get("status") != "OK":
                continue
            if rec.get("reach_ratio") is None:
                continue
            peers.append(rec)

        if not peers:
            continue

        def pct_rank(values: List[float], v: float) -> float:
            if not values:
                return 0.0
            below = sum(1 for x in values if x < v)
            return round(below / len(values), 3)

        reaches = [p["reach_ratio"] for p in peers]
        consists = [p["consistency"] for p in peers if p.get("consistency") is not None]
        crates = [p["comment_rate_pct"] for p in peers if p.get("comment_rate_pct") is not None]

        for rec in peers:
            r_rank = pct_rank(reaches, rec["reach_ratio"])
            c_rank = (pct_rank(consists, rec["consistency"])
                      if rec.get("consistency") is not None else 0.5)
            e_rank = (pct_rank(crates, rec["comment_rate_pct"])
                      if rec.get("comment_rate_pct") is not None else 0.5)
            score = round(0.60 * r_rank + 0.20 * c_rank + 0.20 * e_rank, 3)
            rec["peer_reach_percentile"] = r_rank
            rec["momentum_score"] = score
            rec["peer_group"] = tab["name"]
            rec["peer_group_size"] = len(peers)

        scored = sorted(peers, key=lambda x: -x["momentum_score"])
        median_score = statistics.median([p["momentum_score"] for p in scored])

        for rec in peers:
            if rec.get("disqualifiers"):
                rec["verdict"] = "Don't Invest"
                rec["verdict_reason"] = "; ".join(rec["disqualifiers"])
            elif rec["momentum_score"] >= max(median_score, 0.5):
                rec["verdict"] = "Invest"
                rec["verdict_reason"] = (
                    f"Active and consistent; recent reach in the top "
                    f"{round((1 - rec['peer_reach_percentile']) * 100)}% of "
                    f"{rec['peer_group_size']} pages in this tab")
            else:
                rec["verdict"] = "Don't Invest"
                rec["verdict_reason"] = (
                    f"Recent traction below the median for this tab "
                    f"(momentum score {rec['momentum_score']} vs median "
                    f"{round(median_score, 3)})")

    # Anything never scored keeps an honest non-answer.
    for h, rec in cache.items():
        if rec.get("verdict") in (None, "Pending"):
            if rec.get("disqualifiers"):
                rec["verdict"] = "Don't Invest"
                rec["verdict_reason"] = "; ".join(rec["disqualifiers"])
            elif rec.get("status") != "OK":
                rec["verdict"] = "Not assessed"
                rec["verdict_reason"] = rec.get("verdict_reason") or rec.get("status", "")
            else:
                rec["verdict"] = "Not assessed"
                rec["verdict_reason"] = "Insufficient recent data to judge momentum"


# ==============================================================================
# RUN
# ==============================================================================
def load_cache() -> Dict[str, Any]:
    if os.path.exists(CACHE_FILE):
        try:
            return json.load(open(CACHE_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache: Dict[str, Any]) -> None:
    tmp = CACHE_FILE + ".tmp"
    json.dump(cache, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.replace(tmp, CACHE_FILE)


def run(limit: Optional[int] = None, pause: float = 2.0, redo_throttled: bool = True):
    tabs = load_tabs()
    handles = []
    for t in tabs:
        for h in t["handles"]:
            if h not in handles:
                handles.append(h)

    cache = load_cache()
    todo = []
    for h in handles:
        c = cache.get(h)
        if c is None:
            todo.append(h)
        elif redo_throttled and "THROTTLED" in str(c.get("status", "")):
            todo.append(h)
    if limit:
        todo = todo[:limit]

    print("=" * 78)
    print(f"PAGE MOMENTUM AUDIT   {len(handles)} unique pages, {len(todo)} to fetch")
    print(f"                      {len(cache)} already cached")
    print("=" * 78)

    throttle_streak = 0
    for i, h in enumerate(todo, 1):
        prof = fetch_profile(h)
        time.sleep(pause)

        foll = {"followers": None, "precision": "unresolved"}
        posts = {"status": "skipped", "posts": []}
        reels = {"status": "skipped", "reels": []}

        if prof.get("pk"):
            foll = fetch_followers(prof["pk"])
            time.sleep(pause)
            posts = fetch_posts(h, prof)
            time.sleep(pause)
            reels = fetch_reels(h, prof["pk"], prof)
            time.sleep(pause)

        rec = compute(h, prof, foll, posts, reels)
        rec["_raw_posts_status"] = posts.get("status")
        rec["_raw_reels_status"] = reels.get("status")
        # Keep the raw rows. Recomputing a metric should never cost another scrape.
        rec["_raw_posts"] = posts.get("posts", [])
        rec["_raw_reels"] = reels.get("reels", [])
        cache[h] = rec
        save_cache(cache)

        if "THROTTLED" in rec["status"] or posts.get("status") == "throttled":
            throttle_streak += 1
        else:
            throttle_streak = 0

        fl = f"{rec['followers']:,}" if rec.get("followers") else "-"
        av = f"{rec['avg_views']:,}" if rec.get("avg_views") else "-"
        er = rec.get("engagement_rate_pct")
        ers = f"{er}%" if er is not None else ("hidden" if rec.get("likes_hidden") else "-")
        print(f"[{i}/{len(todo)}] {h:32s} f={fl:>12s} views={av:>11s} er={ers:>8s} "
              f"-> {rec['verdict']}")

        if throttle_streak >= 5:
            print("\n[STOP] Five consecutive throttled pages. Instagram is rate limiting.")
            print("       Progress is saved. Re-run the same command later to continue;")
            print("       cached pages are skipped and throttled ones are retried.")
            break

    print(f"\n[CACHE] {len(cache)} pages measured -> {CACHE_FILE}")
    return cache


# ==============================================================================
# EXCEL
# ==============================================================================
def build_excel(cache: Dict[str, Any], per_tab: bool = False) -> str:
    import openpyxl
    from openpyxl.styles import Font, Alignment
    from openpyxl.utils import get_column_letter

    tabs = load_tabs()
    # Verdicts are derived, not collected, so they are computed fresh here and not
    # written back. That also makes --excel-only safe to run while a fetch is still
    # going: it never touches the cache file the running fetch is appending to.
    assign_verdicts(cache, tabs)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    headers = [
        "S.No", "Tab", "Page Handle", "Profile URL", "Followers", "Posts Analysed",
        "Pinned Excluded", "Average Views", "Median Views", "Average Likes",
        "Average Comments", "Engagement Rate %", "Reach Ratio (Median Views / Followers)",
        "Consistency (Median / Average Views)", "Engagement Per View %",
        "Comments Per View %", "Posts With Matched View Data",
        "Days Since Last Post", "Posts Per Week", "Momentum Score (0-1)",
        "Reach Percentile In Tab", "Recommendation", "Reason",
        "Metrics Behind The Call", "Data Notes", "Checked At (UTC)",
    ]

    bold = Font(bold=True)

    def sheet_name(name: str, used: set) -> str:
        base = re.sub(r'[\\/*?:\[\]]', '', name)[:31]
        n, out = 1, base
        while out in used:
            suffix = f" {n}"
            out = base[:31 - len(suffix)] + suffix
            n += 1
        used.add(out)
        return out

    def row_values(idx: int, tab_name: str, h: str) -> List[Any]:
        rec = cache.get(h)
        if rec is None:
            rec = {"handle": h, "status": "NOT MEASURED", "verdict": "Not assessed",
                   "verdict_reason": "Not fetched yet",
                   "profile_url": f"https://www.instagram.com/{h}/"}
        notes = []
        if rec.get("likes_hidden"):
            notes.append("Page hides its like count; engagement rate vs followers not "
                         "computable, call based on views")
        if rec.get("pinned_excluded"):
            notes.append(f"{rec['pinned_excluded']} pinned post(s) excluded")
        if rec.get("status") not in ("OK", None):
            notes.append(rec.get("status"))
        if rec.get("followers_precision") == "exact":
            notes.append("Follower count exact, read live")
        return [
            idx, tab_name, h, rec.get("profile_url", f"https://www.instagram.com/{h}/"),
            rec.get("followers"), rec.get("posts_analysed"),
            rec.get("pinned_excluded"), rec.get("avg_views"), rec.get("median_views"),
            rec.get("avg_likes") if not rec.get("likes_hidden") else "Hidden by page",
            rec.get("avg_comments"),
            rec.get("engagement_rate_pct") if rec.get("engagement_rate_pct") is not None
            else ("Hidden by page" if rec.get("likes_hidden") else None),
            rec.get("reach_ratio"), rec.get("consistency"),
            rec.get("engagement_per_view_pct"), rec.get("comment_rate_pct"),
            rec.get("posts_with_views"),
            rec.get("days_since_last_post"), rec.get("posts_per_week"),
            rec.get("momentum_score"), rec.get("peer_reach_percentile"),
            rec.get("verdict"), rec.get("verdict_reason"), rec.get("verdict_basis"),
            "; ".join(n for n in notes if n), rec.get("checked_at"),
        ]

    widths = [6, 24, 30, 42, 13, 14, 15, 14, 14, 14, 16, 17, 30, 30, 19, 18, 22,
              17, 14, 18, 20, 16, 58, 58, 58, 21]

    def write_sheet(ws, rows: List[List[Any]]) -> None:
        for c, htxt in enumerate(headers, 1):
            cell = ws.cell(1, c, htxt)
            cell.font = bold
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for ri, vals in enumerate(rows, 2):
            for c, v in enumerate(vals, 1):
                ws.cell(ri, c, v).alignment = Alignment(vertical="center")
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "D2"
        ws.auto_filter.ref = (f"A1:{get_column_letter(len(headers))}"
                              f"{max(len(rows) + 1, 2)}")

    # ---- the consolidated sheet: every page, tab name carried as a column -----
    # Row order follows the supplied tab order exactly, so the original grouping
    # is preserved. A page listed in several tabs appears once per tab, which is
    # why the row count is higher than the number of distinct pages.
    all_rows: List[List[Any]] = []
    n = 0
    for tab in tabs:
        for h in tab["handles"]:
            n += 1
            all_rows.append(row_values(n, tab["name"], h))
    write_sheet(wb.create_sheet("All Creators"), all_rows)

    # ---- per-tab sheets, only when asked for ---------------------------------
    if per_tab:
        used: set = set()
        for tab in tabs:
            rows = [row_values(i, tab["name"], h)
                    for i, h in enumerate(tab["handles"], 1)]
            write_sheet(wb.create_sheet(sheet_name(tab["name"], used)), rows)

    # ---- methodology tab -----------------------------------------------------
    ws = wb.create_sheet("Method And Definitions")
    ws.cell(1, 1, "Field").font = bold
    ws.cell(1, 2, "Definition").font = bold
    rows = [
        ("Purpose", "Assess current momentum of each page, not historical follower count."),
        ("Sample", f"Latest {SAMPLE_SIZE} posts and up to {SAMPLE_SIZE} reels per page, read live."),
        ("Followers", "Exact, read live from Instagram at the time in Checked At. Not estimated."),
        ("Average Views", "Mean play count across the page's recent non-pinned reels. Exact counts."),
        ("Median Views", "Middle value of those view counts. Less distorted by one viral reel."),
        ("Average Likes", "Mean likes across recent non-pinned posts, where the page shows likes."),
        ("Average Comments", "Mean comments across recent non-pinned posts."),
        ("Engagement Rate %", "(Average Likes + Average Comments) / Followers x 100. "
                              "Blank where the page hides its like count."),
        ("Reach Ratio", "Median Views / Followers. Above 1.0 means the page reliably "
                        "reaches beyond its own follower base."),
        ("Consistency", "Median Views / Average Views. Near 1.0 means steady performance. "
                        "A low value means a single viral post is carrying the average."),
        ("Days Since Last Post", "Recency of the most recent non-pinned post."),
        ("Posts Per Week", "Posting cadence across the sampled window."),
        ("Pinned Excluded", "Pinned posts are excluded from every metric. They sit at the top "
                            "of a grid and are usually old top performers - one page had a "
                            "57-week-old pinned reel with 16.9M views, which would badly "
                            "distort a momentum read."),
        ("Hidden by page", "The page has 'hide like count' enabled. Instagram returns a "
                           "placeholder instead of the real number, so likes and engagement "
                           "rate are reported as hidden rather than guessed. View counts are "
                           "still exact on these pages, so the recommendation uses views."),
        ("Comments Per View %", "Average comments / median views x 100. Used as the "
                                "engagement signal for pages that hide their like count, "
                                "since view counts stay exact on those pages."),
        ("Momentum Score", "0 to 1. Blend of the page's percentile rank within its own tab: "
                           "60 percent Reach Ratio, 20 percent Consistency, "
                           "20 percent Comments Per View."),
        ("Reach Percentile In Tab", "Share of pages in the same tab with a lower Reach Ratio. "
                                    "0.90 means it out-reaches 90 percent of its peers."),
        ("Recommendation", METHODOLOGY),
        ("Not assessed", "Page was private, not found, or could not be measured. "
                         "No recommendation is given rather than an assumed one."),
    ]
    for i, (k, v) in enumerate(rows, 2):
        ws.cell(i, 1, k).alignment = Alignment(vertical="top")
        ws.cell(i, 2, v).alignment = Alignment(vertical="top", wrap_text=True)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 115

    # ---- summary tab ---------------------------------------------------------
    ws = wb.create_sheet("Summary")
    for c, htxt in enumerate(["Tab", "Rows", "Invest", "Don't Invest",
                              "Not Assessed", "Likes Hidden"], 1):
        ws.cell(1, c, htxt).font = bold
    r = 2
    for tab in tabs:
        inv = dont = na = hid = 0
        for h in tab["handles"]:
            rec = cache.get(h) or {}
            v = rec.get("verdict", "Not assessed")
            if v == "Invest":
                inv += 1
            elif v == "Don't Invest":
                dont += 1
            else:
                na += 1
            if rec.get("likes_hidden"):
                hid += 1
        for c, v in enumerate([tab["name"], len(tab["handles"]), inv, dont, na, hid], 1):
            ws.cell(r, c, v)
        r += 1
    ws.column_dimensions["A"].width = 28
    for col in "BCDEF":
        ws.column_dimensions[col].width = 15

    try:
        wb.save(EXCEL_FILE)
        out = EXCEL_FILE
    except PermissionError:
        out = EXCEL_FILE.replace(".xlsx", f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        wb.save(out)
    print(f"[EXCEL] {out}")
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    # A different list gets its own input and its own workbook, but shares the
    # cache - a page already audited for one list is reused, not re-fetched.
    if "--input" in args:
        INPUT_FILE = os.path.join(BASE_DIR, args[args.index("--input") + 1])
    if "--output" in args:
        _o = args[args.index("--output") + 1]
        # bare filename -> deliverables/, a path is used as given
        EXCEL_FILE = _o if os.sep in _o or "/" in _o else os.path.join(BASE_DIR, "deliverables", _o)
    if "--excel-only" in args:
        build_excel(load_cache(), per_tab="--per-tab" in args)
        sys.exit(0)
    lim = None
    if "--limit" in args:
        lim = int(args[args.index("--limit") + 1])
    pause = 2.0
    if "--pause" in args:
        pause = float(args[args.index("--pause") + 1])
    c = run(limit=lim, pause=pause)
    build_excel(c, per_tab="--per-tab" in args)
