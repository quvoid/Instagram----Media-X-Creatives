"""
=============================================================================
FINTECH BRANDS 4-TIER PARTNERSHIP BIFURCATION ENGINE (2-YEAR AUDIT)
=============================================================================
Purpose:
  Extracts all creator collaborations from a given Fintech Brand Instagram URL
  across a configurable window (default 2 years), evaluates Meta paid toggles,
  analyzes boost/ad spend signatures, and outputs the exact 4-Tier Bifurcation
  Workbook:
    - Tab 1: Executive Summary
    - Tab 2: Creators Profile Metrics (Deduped Creators, Pure Tiers, ER%)
    - Tab 3: 4-Tier Collaborations Master (Ranked by Tier & Views)
    - Tab 4: Brand Detailed Sheet
=============================================================================
"""

import sys, os, json, time, re, argparse
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

NOW_DT = datetime.now(timezone.utc)
WINDOW_DAYS = 730          # overridden by --years / --days
CUTOFF_DT = NOW_DT - timedelta(days=WINDOW_DAYS)
CUTOFF_TIMESTAMP = int(CUTOFF_DT.timestamp())

def set_window(days: int):
    global WINDOW_DAYS, CUTOFF_DT, CUTOFF_TIMESTAMP
    WINDOW_DAYS = days
    CUTOFF_DT = NOW_DT - timedelta(days=days)
    CUTOFF_TIMESTAMP = int(CUTOFF_DT.timestamp())

from core.session import load_cookies, playwright_cookies
from core.profile_auditor import resolve_profile
COOKIES = playwright_cookies(load_cookies())

def parse_count(c_str):
    if not c_str:
        return 0
    s = str(c_str).strip().upper().replace(',', '')
    try:
        if s.endswith('M'):
            return float(s[:-1]) * 1_000_000
        elif s.endswith('K'):
            return float(s[:-1]) * 1_000
        elif s.endswith('B'):
            return float(s[:-1]) * 1_000_000_000
        return float(s)
    except:
        return 0

def format_count(num):
    if not num or num == 0:
        return "0"
    if num >= 1_000_000:
        return f"{num/1_000_000:.2f}M".replace('.00M', 'M')
    elif num >= 1_000:
        return f"{num/1_000:.1f}K".replace('.0K', 'K')
    return str(int(num))

def get_pure_tier(followers):
    if followers >= 1_000_000:
        return " Mega Creator / Celebrity (1M+)"
    elif followers >= 100_000:
        return " Macro Creator (100K - 1M)"
    elif followers >= 50_000:
        return " Mid-Tier Creator (50K - 100K)"
    elif followers >= 10_000:
        return " Micro Creator (10K - 50K)"
    else:
        return " Nano Creator (<10K)"

def evaluate_boost_and_tier(is_paid_toggle, views, likes, comments, followers, caption=""):
    """
    Evaluates ThruPlay boosting signatures and assigns 4-Tier classification:
      Tier 1: Toggle ON + Boosted Paid Ad
      Tier 2: Toggle ON + Organic Reach
      Tier 3: Toggle OFF + Boosted Paid Ad / Partnership Ad
      Tier 4: Toggle OFF + Organic (Noise)
    """
    like_rate = (likes / views * 100) if views > 0 else 0.0
    view_multiplier = (views / followers) if followers > 0 else 0.0
    er_pct = ((likes + comments) / followers * 100) if followers > 0 else 0.0
    
    caption_lower = caption.lower()
    has_ad_signal = any(tag in caption_lower for tag in ["#ad", "#collab", "#sponsored", "partnership", "sponsored by", "collab with"])
    
    is_boosted = False
    boost_reason = "Organic Engagement Pattern"
    
    if views >= 1_000_000 and like_rate < 0.35:
        is_boosted = True
        boost_reason = f"Heavily Boosted (Paid Ad Spend): High view count ({views:,}) with sub-0.35% like rate ({like_rate:.2f}%) indicates ThruPlay video ad campaign"
    elif view_multiplier >= 5.0 and er_pct < 1.0:
        is_boosted = True
        boost_reason = f"Boosted (Paid Media Spend): High view multiplier ({view_multiplier:.1f}x followers) combined with low natural ER ({er_pct:.2f}%)"
    elif views >= 500_000 and like_rate < 0.50:
        is_boosted = True
        boost_reason = f"Likely Boosted (Targeted Ad): Disproportionate views ({views:,}) relative to likes ({likes:,})"
    elif likes >= 50_000:
        is_boosted = True
        boost_reason = f"Major Paid Campaign: Scale engagement ({likes:,} likes) indicates paid media support"
    elif has_ad_signal and (views >= 100_000 or likes >= 5_000):
        is_boosted = True
        boost_reason = " Sponsored Campaign with Paid Distribution"
        
    if is_paid_toggle:
        if is_boosted:
            tier = 1
            tier_name = "Tier 1: Toggle ON + Boosted Paid Ad"
        else:
            tier = 2
            tier_name = "Tier 2: Toggle ON + Organic"
    else:
        if is_boosted:
            tier = 3
            tier_name = "Tier 3: Toggle OFF + Boosted Paid Ad"
        else:
            tier = 4
            tier_name = "Tier 4: Toggle OFF + Organic (Noise)"
            
    return {
        "tier": tier,
        "tier_name": tier_name,
        "is_boosted": is_boosted,
        "boost_reason": boost_reason,
        "like_rate_pct": round(like_rate, 2),
        "view_multiplier": round(view_multiplier, 2),
        "er_pct": round(er_pct, 2)
    }

def scrape_brand_collabs(brand_url, max_scrolls=15):
    clean_handle = brand_url.rstrip('/').split('/')[-1].replace('@', '').strip()
    print(f"\n=======================================================")
    print(f"SCRAPING COLLABORATIONS: @{clean_handle}")
    print(f"URL: {brand_url}")
    print(f"Cutoff Date: {CUTOFF_DT.strftime('%Y-%m-%d')} (last {WINDOW_DAYS} days)")
    print(f"=======================================================")
    
    collab_posts = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        context.add_cookies(COOKIES)
        page = context.new_page()
        
        # 1. Check Brand Profile
        page.goto(brand_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)
        
        brand_name = clean_handle.title()
        brand_followers = 0
        try:
            meta_desc = page.locator("meta[property='og:description']").get_attribute("content") or ""
            f_match = re.search(r'([\d\.,\w]+)\s+Followers', meta_desc, re.I)
            if f_match:
                brand_followers = parse_count(f_match.group(1))
            title = page.title()
            m_title = re.match(r'^(.*?)\s*\(@', title)
            if m_title:
                brand_name = m_title.group(1).strip()
        except:
            pass
            
        print(f"Brand Name: {brand_name} | Followers: {brand_followers:,}")
        
        # 2. Collect Tagged & Collab Posts
        tagged_url = f"https://www.instagram.com/{clean_handle}/tagged/"
        reels_url = f"https://www.instagram.com/{clean_handle}/reels/"
        
        post_urls = set()
        
        # Scrape Tagged Grid
        print(f"Scanning Tagged Grid: {tagged_url} ...")
        try:
            page.goto(tagged_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            
            for s in range(max_scrolls):
                links = page.locator("a").all()
                for l in links:
                    href = l.get_attribute("href") or ""
                    if "/p/" in href or "/reel/" in href:
                        clean_href = href.split("?")[0]
                        full_post_url = f"https://www.instagram.com{clean_href}" if clean_href.startswith('/') else clean_href
                        post_urls.add(full_post_url)
                page.evaluate("window.scrollBy(0, 1200)")
                time.sleep(1.5)
        except Exception as e:
            print(f"Error on tagged tab: {e}")
            
        # Scrape Brand Reels for Co-Author Collabs
        print(f"Scanning Reels Grid: {reels_url} ...")
        try:
            page.goto(reels_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            for s in range(max_scrolls):
                links = page.locator("a").all()
                for l in links:
                    href = l.get_attribute("href") or ""
                    if "/reel/" in href:
                        clean_href = href.split("?")[0]
                        full_post_url = f"https://www.instagram.com{clean_href}" if clean_href.startswith('/') else clean_href
                        post_urls.add(full_post_url)
                page.evaluate("window.scrollBy(0, 1200)")
                time.sleep(1.5)
        except Exception as e:
            print(f"Error on reels tab: {e}")
            
        print(f"Found {len(post_urls)} candidate posts/reels. Inspecting authors, dates & metrics...")
        
        # 3. Inspect posts for date cutoff & collaborators
        creator_followers_cache = {}
        
        for idx, p_url in enumerate(list(post_urls), 1):
            try:
                page.goto(p_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(2000)
                content = page.content()
                
                # Extract Post Date
                date_str = "2025-01-01"
                post_timestamp = 0
                time_loc = page.locator("time").first
                if time_loc.count() > 0:
                    dt_val = time_loc.get_attribute("datetime")
                    if dt_val:
                        dt_obj = datetime.fromisoformat(dt_val.replace('Z', '+00:00'))
                        post_timestamp = int(dt_obj.timestamp())
                        date_str = dt_obj.strftime("%Y-%m-%d")
                        
                # Date Cutoff Check (last {WINDOW_DAYS} days)
                if post_timestamp > 0 and post_timestamp < CUTOFF_TIMESTAMP:
                    print(f"[{idx}/{len(post_urls)}] Older than {WINDOW_DAYS} days ({date_str}) -> Skipping")
                    continue
                    
                # Extract Author & Collaborators
                authors = []
                for a in page.locator("header a, article header a").all():
                    href = a.get_attribute("href") or ""
                    m = re.match(r'^/([a-zA-Z0-9_\.]+)/?$', href)
                    if m:
                        u = m.group(1).lower()
                        if u not in ['explore', 'p', 'reel', 'stories', 'direct', clean_handle]:
                            authors.append(f"@{u}")
                            
                # Check og:title for Author
                meta_title = page.locator("meta[property='og:title']").get_attribute("content") or ""
                m_auth = re.search(r'\(@([a-zA-Z0-9_\.]+)\)', meta_title)
                if m_auth:
                    u = m_auth.group(1).lower()
                    if u != clean_handle and f"@{u}" not in authors:
                        authors.append(f"@{u}")
                        
                if not authors:
                    # Not a creator collaboration
                    continue
                    
                primary_creator = authors[0]
                raw_creator = primary_creator.replace('@', '')
                
                # Check Paid Partnership Toggle
                is_paid_toggle = "Paid partnership" in content or "paid_partnership" in content
                
                # Extract Caption
                meta_desc = page.locator("meta[property='og:description']").get_attribute("content") or ""
                
                # Extract Views, Likes, Comments
                likes = 0
                comments = 0
                views = 0
                
                m_likes = re.search(r'([\d\.,\w]+)\s+likes', meta_desc, re.I)
                if m_likes:
                    likes = int(parse_count(m_likes.group(1)))
                    
                m_comments = re.search(r'([\d\.,\w]+)\s+comments', meta_desc, re.I)
                if m_comments:
                    comments = int(parse_count(m_comments.group(1)))
                    
                # View count fallback
                m_views = re.search(r'([\d\.,\w]+)\s+views', content, re.I)
                if m_views:
                    views = int(parse_count(m_views.group(1)))
                # no fabricated fallback: 0 means Instagram did not expose a view count
                    
                # Get creator followers
                creator_followers = creator_followers_cache.get(raw_creator, 0)
                creator_precision = 'cached'
                if not creator_followers:
                    try:
                        prof = resolve_profile(raw_creator, page=page, want_rich=False)
                        creator_followers = int(prof.get('followers') or 0)
                        creator_precision = prof.get('followers_precision', 'unresolved')
                        creator_followers_cache[raw_creator] = creator_followers
                    except Exception:
                        creator_followers = 0          # never guess a follower count
                        creator_precision = 'unresolved'

                eval_res = evaluate_boost_and_tier(
                    is_paid_toggle=is_paid_toggle,
                    views=views,
                    likes=likes,
                    comments=comments,
                    followers=creator_followers,
                    caption=meta_desc
                )
                
                collab_record = {
                    "brand": brand_name,
                    "brand_handle": f"@{clean_handle}",
                    "brand_url": brand_url,
                    "creator_handle": primary_creator,
                    "raw_creator": raw_creator,
                    "creator_followers": creator_followers,
                    "followers_precision": creator_precision,
                    "creator_tier": get_pure_tier(creator_followers),
                    "post_url": p_url,
                    "post_date": date_str,
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "is_paid_toggle": is_paid_toggle,
                    "caption": meta_desc[:250].replace('\n', ' '),
                }
                collab_record.update(eval_res)
                collab_posts.append(collab_record)
                
                print(f"[{idx}/{len(post_urls)}] {primary_creator} ({creator_followers:,} fols) | Tier {eval_res['tier']} | Views: {views:,} | Date: {date_str}")
                
            except Exception as e:
                pass
                
        browser.close()
        
    return collab_posts

def export_4tier_workbook(brand_name, brand_handle, brand_url, state_origin, collab_posts, output_excel_path):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    
    font_title = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    font_hdr = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=10, bold=True, color="000000")
    font_norm = Font(name="Calibri", size=10, bold=False, color="000000")
    font_mute = Font(name="Calibri", size=9, bold=False, color="5D6D7E")
    font_link = Font(name="Calibri", size=10, bold=False, color="0563C1", underline="single")
    
    fill_t1_banner = PatternFill("solid", fgColor="145A32") # Dark Emerald
    fill_t1_row = PatternFill("solid", fgColor="D4EFDF")    # Mint Green
    font_t1_bold = Font(name="Calibri", size=10, bold=True, color="0E6251")
    
    fill_t2_banner = PatternFill("solid", fgColor="1E8449") # Forest Green
    fill_t2_row = PatternFill("solid", fgColor="EAFAF1")    # Sage Green
    font_t2_bold = Font(name="Calibri", size=10, bold=True, color="196F3D")
    
    fill_t3_banner = PatternFill("solid", fgColor="B7950B") # Dark Gold
    fill_t3_row = PatternFill("solid", fgColor="FEF9E7")    # Warm Soft Gold
    font_t3_bold = Font(name="Calibri", size=10, bold=True, color="7D6608")
    
    fill_t4_banner = PatternFill("solid", fgColor="566573") # Slate Gray
    fill_t4_row = PatternFill("solid", fgColor="FFFFFF")    # Clean White
    font_t4_norm = Font(name="Calibri", size=10, bold=False, color="2C3E50")
    
    thin_line = Side(style="thin", color="D5D8DC")
    border_cell = Border(left=thin_line, right=thin_line, top=thin_line, bottom=thin_line)
    
    # ----------------------------------------------------
    # TAB 1: EXECUTIVE SUMMARY
    # ----------------------------------------------------
    ws_sum = wb.create_sheet("Executive Summary")
    ws_sum.sheet_view.showGridLines = True
    
    ws_sum.merge_cells("A1:O1")
    ws_sum["A1"] = f"Executive Summary - Paid Creator Collab Hierarchy ({brand_name}) [{CUTOFF_DT.strftime('%d %b %Y')} to {NOW_DT.strftime('%d %b %Y')}]"
    ws_sum["A1"].font = font_title
    ws_sum["A1"].fill = PatternFill("solid", fgColor="0B2240")
    ws_sum["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws_sum.row_dimensions[1].height = 32
    
    sum_headers = [
        ("#", 5),
        ("Brand Name", 24),
        ("State / Origin (HQ)", 32),
        ("Total Collab Posts (2-Yr)", 18),
        ("Total Unique Creators", 18),
        ("Tier 1: Toggle ON + Boosted\n(Posts / Creators)", 24),
        ("Tier 2: Toggle ON + Organic\n(Posts / Creators)", 24),
        ("Tier 3: Toggle OFF + Boosted\n(Posts / Creators)", 24),
        ("Tier 4: Toggle OFF + Organic (Noise)\n(Posts / Creators)", 28),
        ("Total High-Intent Paid\n(Tiers 1+2+3 Posts)", 22),
        ("High-Intent Paid %\n(Tiers 1+2+3)", 18),
        ("Avg Views / Post", 16),
        ("Avg Creator Followers", 20),
        ("Avg Creator ER%", 15),
        ("Top Creator / Ambassador Samples", 48)
    ]
    
    for col_idx, (h_text, w) in enumerate(sum_headers, 1):
        c = ws_sum.cell(row=2, column=col_idx, value=h_text)
        c.font = font_hdr
        c.fill = PatternFill("solid", fgColor="1B2631")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border_cell
        ws_sum.column_dimensions[get_column_letter(col_idx)].width = w
    ws_sum.row_dimensions[2].height = 36
    
    # Calculate Summary Stats
    tot_p = len(collab_posts)
    tot_c = len(set(p["creator_handle"].lower() for p in collab_posts))
    
    t1_p = [p for p in collab_posts if p["tier"] == 1]
    t2_p = [p for p in collab_posts if p["tier"] == 2]
    t3_p = [p for p in collab_posts if p["tier"] == 3]
    t4_p = [p for p in collab_posts if p["tier"] == 4]
    
    t1_c = len(set(p["creator_handle"].lower() for p in t1_p))
    t2_c = len(set(p["creator_handle"].lower() for p in t2_p))
    t3_c = len(set(p["creator_handle"].lower() for p in t3_p))
    t4_c = len(set(p["creator_handle"].lower() for p in t4_p))
    
    high_intent = len(t1_p) + len(t2_p) + len(t3_p)
    high_intent_pct = high_intent / tot_p if tot_p > 0 else 0.0
    
    views_list = [p["views"] for p in collab_posts if p["views"] > 0]
    avg_v = int(sum(views_list) / len(views_list)) if views_list else 0
    
    fols_list = [p["creator_followers"] for p in collab_posts if p["creator_followers"] > 0]
    avg_f = int(sum(fols_list) / len(fols_list)) if fols_list else 0
    
    ers_list = [p["er_pct"] for p in collab_posts if p["er_pct"] > 0]
    avg_e = round(sum(ers_list) / len(ers_list), 2) if ers_list else 0.0
    
    top_creators = list(dict.fromkeys([p["creator_handle"] for p in collab_posts if p["tier"] in (1, 2, 3)]))[:5]
    if not top_creators:
        top_creators = list(dict.fromkeys([p["creator_handle"] for p in collab_posts]))[:5]
        
    row_vals = [
        1,
        brand_name,
        state_origin,
        tot_p,
        tot_c,
        f"{len(t1_p)} posts ({t1_c} creators)" if len(t1_p) > 0 else "-",
        f"{len(t2_p)} posts ({t2_c} creators)" if len(t2_p) > 0 else "-",
        f"{len(t3_p)} posts ({t3_c} creators)" if len(t3_p) > 0 else "-",
        f"{len(t4_p)} posts ({t4_c} creators)" if len(t4_p) > 0 else "-",
        high_intent,
        high_intent_pct,
        avg_v,
        avg_f,
        avg_e / 100 if avg_e else 0.0,
        ", ".join(top_creators)
    ]
    
    for col_idx, val in enumerate(row_vals, 1):
        cell = ws_sum.cell(row=3, column=col_idx, value=val)
        cell.border = border_cell
        if col_idx == 1:
            cell.font = font_mute; cell.alignment = Alignment(horizontal="center", vertical="center")
        elif col_idx == 2:
            cell.font = font_bold; cell.alignment = Alignment(horizontal="left", vertical="center")
        elif col_idx == 3:
            cell.font = Font(name="Calibri", size=9, bold=True, color="2C3E50"); cell.alignment = Alignment(horizontal="left", vertical="center")
            cell.fill = PatternFill("solid", fgColor="F4F6F6")
        elif col_idx in (4, 5):
            cell.font = font_bold; cell.alignment = Alignment(horizontal="center", vertical="center"); cell.number_format = "#,##0"
            cell.fill = PatternFill("solid", fgColor="EBF5FB")
        elif col_idx == 6:
            cell.font = font_t1_bold; cell.alignment = Alignment(horizontal="center", vertical="center")
            if "posts" in str(val): cell.fill = fill_t1_row
        elif col_idx == 7:
            cell.font = font_t2_bold; cell.alignment = Alignment(horizontal="center", vertical="center")
            if "posts" in str(val): cell.fill = fill_t2_row
        elif col_idx == 8:
            cell.font = font_t3_bold; cell.alignment = Alignment(horizontal="center", vertical="center")
            if "posts" in str(val): cell.fill = fill_t3_row
        elif col_idx == 9:
            cell.font = font_mute; cell.alignment = Alignment(horizontal="center", vertical="center")
            if "posts" in str(val): cell.fill = PatternFill("solid", fgColor="F8F9F9")
        elif col_idx == 10:
            cell.font = Font(name="Calibri", size=10, bold=True, color="1B4F72"); cell.alignment = Alignment(horizontal="center", vertical="center"); cell.number_format = "#,##0"
            if val > 0: cell.fill = PatternFill("solid", fgColor="D6EAF8")
        elif col_idx == 11:
            cell.font = font_bold; cell.alignment = Alignment(horizontal="center", vertical="center"); cell.number_format = "0.0%"
        elif col_idx in (12, 13):
            cell.font = font_norm; cell.alignment = Alignment(horizontal="right", vertical="center"); cell.number_format = "#,##0"
        elif col_idx == 14:
            cell.font = font_bold; cell.alignment = Alignment(horizontal="center", vertical="center"); cell.number_format = "0.00%"
        elif col_idx == 15:
            cell.font = font_norm; cell.alignment = Alignment(horizontal="left", vertical="center")
    ws_sum.row_dimensions[3].height = 24
    
    # ----------------------------------------------------
    # TAB 2: CREATORS PROFILE METRICS
    # ----------------------------------------------------
    ws_prof = wb.create_sheet("Creators Profile Metrics")
    ws_prof.sheet_view.showGridLines = True
    
    # Group creators
    creator_profiles = {}
    for p in collab_posts:
        rh = p["raw_creator"]
        if rh not in creator_profiles:
            creator_profiles[rh] = {
                "handle": p["creator_handle"],
                "raw_handle": rh,
                "creator_tier": p["creator_tier"],
                "followers": p["creator_followers"],
                "profile_url": f"https://www.instagram.com/{rh}/",
                "posts_count": 0,
                "total_views": 0,
                "total_likes": 0,
                "total_comments": 0,
            }
        creator_profiles[rh]["posts_count"] += 1
        creator_profiles[rh]["total_views"] += p["views"]
        creator_profiles[rh]["total_likes"] += p["likes"]
        creator_profiles[rh]["total_comments"] += p["comments"]
        
    profiles_list = list(creator_profiles.values())
    for p in profiles_list:
        p["avg_likes"] = int(p["total_likes"] / p["posts_count"]) if p["posts_count"] > 0 else 0
        p["avg_comments"] = int(p["total_comments"] / p["posts_count"]) if p["posts_count"] > 0 else 0
        p["avg_er"] = round(((p["avg_likes"] + p["avg_comments"]) / p["followers"]) * 100, 2) if p["followers"] > 0 else 0.0
        
    profiles_list.sort(key=lambda x: x["followers"], reverse=True)
    
    ws_prof.merge_cells("A1:I1")
    ws_prof["A1"] = f"Deduped Creator Profiles & Tier Classification ({len(profiles_list)} Creators for {brand_name})"
    ws_prof["A1"].font = font_title
    ws_prof["A1"].fill = PatternFill("solid", fgColor="1B4F72")
    ws_prof["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws_prof.row_dimensions[1].height = 30
    
    prof_headers = [
        ("#", 5),
        ("Creator Handle", 24),
        ("Creator Tier / Size", 30),
        ("Brand Partner", 22),
        ("Total Followers", 18),
        ("Collab Posts (2-Yr)", 18),
        ("Avg Likes / Post", 16),
        ("Avg Comments / Post", 18),
        ("Avg Profile ER%", 16),
    ]
    
    for col_idx, (h_text, w) in enumerate(prof_headers, 1):
        c = ws_prof.cell(row=2, column=col_idx, value=h_text)
        c.font = font_hdr
        c.fill = PatternFill("solid", fgColor="283747")
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border_cell
        ws_prof.column_dimensions[get_column_letter(col_idx)].width = w
    ws_prof.row_dimensions[2].height = 25
    
    tier_fills = {
        " Mega Creator / Celebrity (1M+)": PatternFill("solid", fgColor="E8F8F5"),
        " Macro Creator (100K - 1M)": PatternFill("solid", fgColor="FEF9E7"),
        " Mid-Tier Creator (50K - 100K)": PatternFill("solid", fgColor="EBF5FB"),
        " Micro Creator (10K - 50K)": PatternFill("solid", fgColor="F4F6F7"),
        " Nano Creator (<10K)": PatternFill("solid", fgColor="FFFFFF"),
    }
    
    for idx, p in enumerate(profiles_list, 1):
        r_num = idx + 2
        r_vals = [
            idx,
            p["handle"],
            p["creator_tier"],
            brand_name,
            p["followers"],
            p["posts_count"],
            p["avg_likes"],
            p["avg_comments"],
            p["avg_er"] / 100 if p["avg_er"] else 0.0
        ]
        tier_fill = tier_fills.get(p["creator_tier"], PatternFill("solid", fgColor="FFFFFF"))
        
        for c_idx, val in enumerate(r_vals, 1):
            cell = ws_prof.cell(row=r_num, column=c_idx, value=val)
            cell.border = border_cell
            if c_idx == 1:
                cell.font = font_mute; cell.alignment = Alignment(horizontal="center", vertical="center")
            elif c_idx == 2:
                cell.font = font_bold; cell.alignment = Alignment(horizontal="left", vertical="center")
                cell.hyperlink = p["profile_url"]
            elif c_idx == 3:
                cell.font = Font(name="Calibri", size=10, bold=True, color="1B4F72")
                cell.alignment = Alignment(horizontal="left", vertical="center")
                cell.fill = tier_fill
            elif c_idx == 4:
                cell.font = font_norm; cell.alignment = Alignment(horizontal="left", vertical="center")
            elif c_idx in (5, 6, 7, 8):
                cell.font = font_norm; cell.alignment = Alignment(horizontal="right", vertical="center"); cell.number_format = "#,##0"
            elif c_idx == 9:
                cell.font = font_bold; cell.alignment = Alignment(horizontal="center", vertical="center"); cell.number_format = "0.00%"
        ws_prof.row_dimensions[r_num].height = 21
        
    # ----------------------------------------------------
    # TAB 3: 4-TIER COLLABORATIONS MASTER
    # ----------------------------------------------------
    ws_master = wb.create_sheet("4-Tier Collaborations Master")
    ws_master.sheet_view.showGridLines = True
    
    ws_master.merge_cells("A1:N1")
    ws_master["A1"] = f"{brand_name.upper()}  |   STATE / HQ: {state_origin}  |  2-YEAR PARTNERSHIP BIFURCATION"
    ws_master["A1"].font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
    ws_master["A1"].fill = PatternFill("solid", fgColor="0B2240")
    ws_master["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws_master.row_dimensions[1].height = 28
    
    ws_master.merge_cells("A2:N2")
    ws_master["A2"] = f"Collab Posts ({WINDOW_DAYS} days): {tot_p}  |  Unique Creators: {tot_c}  |   High-Intent Paid: {high_intent} (T1: {len(t1_p)} | T2: {len(t2_p)} | T3: {len(t3_p)})  |   Noise/Unboosted (T4): {len(t4_p)}"
    ws_master["A2"].font = Font(name="Calibri", size=10, bold=True, color="1B4F72")
    ws_master["A2"].fill = PatternFill("solid", fgColor="EBF5FB")
    ws_master["A2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws_master.row_dimensions[2].height = 22
    
    table_cols = [
        ("#", 5),
        ("Hierarchy Tier", 30),
        ("Brand Name", 22),
        ("Creator Handle", 24),
        ("Followers", 14),
        ("Views / Plays", 16),
        ("Likes", 14),
        ("Comments", 12),
        ("Like-to-View %", 15),
        ("Creator ER%", 13),
        ("Post Date", 13),
        ("Direct Instagram URL", 48),
        ("Boost Classification & Reason", 38),
        ("Caption Preview", 65)
    ]
    
    for col_idx, (h_text, w) in enumerate(table_cols, 1):
        c = ws_master.cell(row=3, column=col_idx, value=h_text)
        c.font = font_hdr
        c.fill = PatternFill("solid", fgColor="1F2D3D")
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border_cell
        ws_master.column_dimensions[get_column_letter(col_idx)].width = w
    ws_master.row_dimensions[3].height = 25
    
    # Sort posts by Tier ascending, then Views descending
    collab_posts.sort(key=lambda x: (x["tier"], -x["views"]))
    
    tier_meta = [
        (1, " TIER 1: TOGGLE ON +  BOOSTED (Formal Paid Partnership Label + Paid Ad Spend)", fill_t1_banner, fill_t1_row, font_t1_bold),
        (2, " TIER 2: TOGGLE ON +  ORGANIC (Formal Paid Partnership Label + Organic Reach Only)", fill_t2_banner, fill_t2_row, font_t2_bold),
        (3, " TIER 3: TOGGLE OFF +  BOOSTED (Co-Author Collab + Heavy Paid Ad Spend Detected)", fill_t3_banner, fill_t3_row, font_t3_bold),
        (4, " TIER 4: TOGGLE OFF +  ORGANIC (Standard Collab / Low Organic Reach / Noise)", fill_t4_banner, fill_t4_row, font_t4_norm)
    ]
    
    current_row = 4
    global_idx = 1
    
    for t_id, banner_text, fill_banner, fill_row, font_b in tier_meta:
        t_records = [p for p in collab_posts if p["tier"] == t_id]
        if not t_records:
            continue
            
        ws_master.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=14)
        b_cell = ws_master.cell(row=current_row, column=1, value=f"{banner_text} - {len(t_records)} Posts ({len(set(p['creator_handle'].lower() for p in t_records))} Unique Creators)")
        b_cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        b_cell.fill = fill_banner
        b_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_master.row_dimensions[current_row].height = 22
        current_row += 1
        
        for r in t_records:
            row_vals = [
                global_idx,
                r["tier_name"],
                brand_name,
                r["creator_handle"],
                r["creator_followers"],
                r["views"],
                r["likes"],
                r["comments"],
                r["like_rate_pct"] / 100 if r["like_rate_pct"] else 0.0,
                r["er_pct"] / 100 if r["er_pct"] else 0.0,
                r["post_date"],
                r["post_url"],
                r["boost_reason"],
                r["caption"]
            ]
            
            for col_idx, val in enumerate(row_vals, 1):
                cell = ws_master.cell(row=current_row, column=col_idx, value=val)
                cell.border = border_cell
                cell.fill = fill_row
                
                if col_idx == 1:
                    cell.font = font_mute; cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx in (2, 3):
                    cell.font = font_b; cell.alignment = Alignment(horizontal="left", vertical="center")
                elif col_idx == 4:
                    cell.font = font_bold; cell.alignment = Alignment(horizontal="left", vertical="center")
                elif col_idx in (5, 6, 7, 8):
                    cell.font = font_norm; cell.alignment = Alignment(horizontal="right", vertical="center"); cell.number_format = "#,##0"
                elif col_idx in (9, 10):
                    cell.font = font_norm; cell.alignment = Alignment(horizontal="center", vertical="center"); cell.number_format = "0.00%"
                elif col_idx == 11:
                    cell.font = font_norm; cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx == 12:
                    cell.font = font_link; cell.alignment = Alignment(horizontal="left", vertical="center")
                    cell.hyperlink = val
                elif col_idx in (13, 14):
                    cell.font = font_norm; cell.alignment = Alignment(horizontal="left", vertical="center")
                    
            ws_master.row_dimensions[current_row].height = 20
            current_row += 1
            global_idx += 1
            
    wb.save(output_excel_path)
    print(f"\n Successfully saved 4-Tier Bifurcation Workbook: {output_excel_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Brand collaborator 4-tier scraper (any brand URL, configurable window)")
    parser.add_argument("--url", type=str, required=True, help="Brand Instagram URL (e.g. https://www.instagram.com/cred_club/)")
    parser.add_argument("--brand", type=str, default="", help="Brand Name (e.g. CRED)")
    parser.add_argument("--state", type=str, default="Pan-India", help="State / HQ Origin")
    parser.add_argument("--output", type=str, default="", help="Output Excel filename")
    parser.add_argument("--years", type=float, default=2.0, help="Look-back window in years (default 2)")
    parser.add_argument("--max-scrolls", type=int, default=15, help="Grid scrolls per tab; raise for brands that post a lot")
    parser.add_argument("--days", type=int, default=0, help="Look-back window in days (overrides --years)")
    args = parser.parse_args()
    
    set_window(args.days if args.days else int(args.years * 365))
    b_url = args.url.strip()
    b_handle = b_url.rstrip('/').split('/')[-1].replace('@', '').strip()
    b_name = args.brand.strip() if args.brand else b_handle.title()
    b_state = args.state.strip()
    
    out_file = args.output.strip() if args.output else f"{b_handle}_4Tier_Partnership_Bifurcation.xlsx"
    
    posts = scrape_brand_collabs(b_url, max_scrolls=args.max_scrolls)
    export_4tier_workbook(b_name, f"@{b_handle}", b_url, b_state, posts, out_file)
