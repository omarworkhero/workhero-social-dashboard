#!/usr/bin/env python3
"""
WorkHero Social Media Dashboard Generator
Pulls live post data directly from Facebook, Instagram, YouTube, and LinkedIn APIs.

Usage:
    pip install requests
    python3 generate_social_dashboard.py
    open social_dashboard.html

See social_config.json for per-platform setup instructions.
"""

import json, requests
from datetime import datetime, timedelta, date as date_cls
from pathlib import Path

# ─── Config ──────────────────────────────────────────────────────────────────
cfg          = json.loads(Path("social_config.json").read_text())
DASHBOARD_PW = cfg.get("dashboard_password", "workhero2026")
LOOKBACK     = int(cfg.get("lookback_days", 90))
END_DATE     = date_cls.today()
START_DATE   = END_DATE - timedelta(days=LOOKBACK - 1)
START_STR    = START_DATE.strftime("%Y-%m-%d")
END_STR      = END_DATE.strftime("%Y-%m-%d")
OUTPUT_FILE  = "social_dashboard.html"

fb_cfg = cfg.get("facebook", {})
ig_cfg = cfg.get("instagram", {})
yt_cfg = cfg.get("youtube",   {})
li_cfg = cfg.get("linkedin",  {})

print(f"\n WorkHero Social Media Dashboard")
print(f"   Range: {START_STR} → {END_STR} ({LOOKBACK} days)\n")

# ─── Facebook ────────────────────────────────────────────────────────────────
def fetch_facebook():
    token   = fb_cfg.get("page_access_token", "").strip()
    page_id = fb_cfg.get("page_id", "").strip()
    if not token or not page_id:
        return [], "not_configured", None
    print("→ Facebook: fetching posts…")
    try:
        # Fetch current page follower count
        fb_followers = None
        ch_r = requests.get(f"https://graph.facebook.com/v25.0/{page_id}",
                            params={"fields": "followers_count", "access_token": token}, timeout=15)
        if ch_r.status_code == 200:
            fb_followers = ch_r.json().get("followers_count")
            if fb_followers is not None:
                print(f"  Page followers: {fb_followers:,}")

        posts, after = [], None
        while True:
            params = {
                "fields": "id,message,story,created_time,permalink_url,shares,"
                          "reactions.summary(true),comments.summary(true)",
                "limit": 100, "access_token": token, "since": START_STR,
            }
            if after:
                params["after"] = after
            r = requests.get(f"https://graph.facebook.com/v22.0/{page_id}/posts",
                             params=params, timeout=30)
            if r.status_code != 200:
                err = r.json().get("error", {}).get("message", r.text[:120])
                print(f"  ⚠  Facebook: {err}")
                return [], "error", None
            data = r.json()
            posts.extend(data.get("data", []))
            after = data.get("paging", {}).get("cursors", {}).get("after")
            if not after or not data.get("paging", {}).get("next"):
                break

        # Batch-fetch per-post views/reach in groups of 50.
        # post_impressions_unique/post_impressions deprecated by Meta for many pages (#100).
        # Falls back to post_video_views (works for reels) then post_clicks.
        print(f"  {len(posts)} posts found — fetching view/reach data…")
        reach_map = {}
        first_err  = None
        for metric in ("post_impressions_unique", "post_impressions",
                       "post_video_views", "post_clicks"):
            reach_map = {}
            for i in range(0, len(posts), 50):
                chunk = posts[i:i+50]
                batch = [{"method": "GET",
                          "relative_url": f"{p['id']}/insights?metric={metric}&period=lifetime"}
                         for p in chunk]
                rb = requests.post("https://graph.facebook.com/v25.0",
                                   params={"access_token": token},
                                   json={"batch": batch}, timeout=30)
                if rb.status_code != 200:
                    print(f"  ⚠  FB insights batch HTTP {rb.status_code}: {rb.text[:120]}")
                    break
                for j, item in enumerate(rb.json() or []):
                    if item and item.get("code") == 200:
                        body = json.loads(item.get("body", "{}"))
                        vals = (body.get("data") or [{}])[0].get("values") or []
                        v = vals[0].get("value") if vals else None
                        if v is not None:
                            reach_map[chunk[j]["id"]] = v
                    elif item and item.get("code") != 200 and first_err is None:
                        body = json.loads(item.get("body", "{}"))
                        first_err = body.get("error", {}).get("message", f"code {item.get('code')}")
            if reach_map:
                print(f"  view data: {len(reach_map)}/{len(posts)} posts via {metric}")
                break
        if not reach_map:
            print(f"  ⚠  view data unavailable ({first_err or 'no values returned'}) — engagement only")

        result = []
        for p in posts:
            likes = p.get("reactions", {}).get("summary", {}).get("total_count") or 0
            cmts  = p.get("comments",  {}).get("summary", {}).get("total_count") or 0
            shrs  = p.get("shares",    {}).get("count") or 0
            reach = reach_map.get(p["id"])
            eng   = likes + cmts + shrs
            result.append({
                "title":    ((p.get("message") or p.get("story") or "Facebook Post")[:100]
                             .replace("\n", " ").strip()),
                "date":     (p.get("created_time") or "")[:10],
                "platform": ["Facebook"],
                "ctype":    "",
                "views":    reach,   # post_video_views → views column
                "reach":    None,    # impressions unavailable (Meta deprecated)
                "likes":    likes,
                "comments": cmts,
                "shares":   shrs,
                "saves":    None,
                "followers": fb_followers, "new_users": None, "ctr": None,
                "url":      p.get("permalink_url", ""),
                "engagement": eng,
                "eng_rate": None,    # no reach → can't compute rate
            })
        print(f"  ✓ {len(result)} Facebook posts")
        return result, "ok", fb_followers
    except Exception as e:
        print(f"  ✗ Facebook exception: {e}")
        return [], "error", None

# ─── Instagram ───────────────────────────────────────────────────────────────
def fetch_instagram():
    token = ig_cfg.get("page_access_token", "").strip()
    ig_id = ig_cfg.get("ig_user_id", "").strip()
    if not token or not ig_id:
        return [], "not_configured", None
    print("→ Instagram: fetching media…")
    try:
        # Fetch current follower count
        ig_followers = None
        fl_r = requests.get(f"https://graph.facebook.com/v22.0/{ig_id}",
                            params={"fields": "followers_count", "access_token": token}, timeout=15)
        if fl_r.status_code == 200:
            ig_followers = fl_r.json().get("followers_count")
            if ig_followers is not None:
                print(f"  IG followers: {ig_followers:,}")

        media, after = [], None
        while True:
            params = {
                "fields": "id,caption,media_type,timestamp,permalink,like_count,comments_count",
                "limit": 100, "access_token": token,
            }
            if after:
                params["after"] = after
            r = requests.get(f"https://graph.facebook.com/v19.0/{ig_id}/media",
                             params=params, timeout=30)
            if r.status_code != 200:
                err = r.json().get("error", {}).get("message", r.text[:120])
                print(f"  ⚠  Instagram: {err}")
                return [], "error", None
            data = r.json()
            for m in data.get("data", []):
                if (m.get("timestamp") or "")[:10] >= START_STR:
                    media.append(m)
            after = data.get("paging", {}).get("cursors", {}).get("after")
            if not after or not data.get("paging", {}).get("next"):
                break

        print(f"  {len(media)} posts in range — fetching insights…")
        result = []
        for m in media:
            mtype = m.get("media_type", "IMAGE")

            reach = saves = total_interactions = None
            ins_r = requests.get(
                f"https://graph.facebook.com/v22.0/{m['id']}/insights",
                params={"metric": "reach,saved,total_interactions", "access_token": token}, timeout=15)
            if ins_r.status_code == 200:
                for d in ins_r.json().get("data", []):
                    name = d.get("name")
                    val  = d.get("value")
                    if val is None and d.get("values"):
                        val = d["values"][0].get("value")
                    if name == "reach":               reach               = val
                    if name == "saved":               saves               = val
                    if name == "total_interactions":  total_interactions  = val

            likes = m.get("like_count")    or 0
            cmts  = m.get("comments_count") or 0
            eng   = total_interactions or (likes + cmts + (saves or 0))
            result.append({
                "title":    ((m.get("caption") or "Instagram Post")[:100]
                             .replace("\n", " ").strip()),
                "date":     (m.get("timestamp") or "")[:10],
                "platform": ["Instagram"],
                "ctype":    mtype.lower(),
                "views":    reach,
                "reach":    reach,
                "likes":    likes,
                "comments": cmts,
                "shares":   None,   # Instagram share count not exposed via this API
                "saves":    saves,  # bookmarks/saves from IG insights
                "followers": ig_followers, "new_users": None, "ctr": None,
                "url":      m.get("permalink", ""),
                "engagement": eng,
                "eng_rate": round(eng / reach * 100, 2) if reach and reach > 0 else None,
            })
        print(f"  ✓ {len(result)} Instagram posts")
        return result, "ok", ig_followers
    except Exception as e:
        print(f"  ✗ Instagram exception: {e}")
        return [], "error", None

# ─── YouTube ─────────────────────────────────────────────────────────────────
def fetch_youtube():
    api_key    = yt_cfg.get("api_key", "").strip()
    channel_id = yt_cfg.get("channel_id", "").strip()
    if not api_key or not channel_id:
        return [], "not_configured", None
    print("→ YouTube: fetching videos…")
    try:
        # Fetch subscriber count from channel stats
        yt_followers = None
        ch_r = requests.get("https://www.googleapis.com/youtube/v3/channels",
                            params={"part": "statistics", "id": channel_id, "key": api_key}, timeout=15)
        if ch_r.status_code == 200:
            ch_items = ch_r.json().get("items", [])
            if ch_items:
                raw_sub = ch_items[0].get("statistics", {}).get("subscriberCount")
                if raw_sub:
                    yt_followers = int(raw_sub)
                    print(f"  Subscribers: {yt_followers:,}")

        video_ids, next_token = [], None
        while True:
            params = {
                "channelId": channel_id, "type": "video",
                "part": "id", "maxResults": 50, "order": "date",
                "publishedAfter": f"{START_STR}T00:00:00Z",
                "key": api_key,
            }
            if next_token:
                params["pageToken"] = next_token
            r = requests.get("https://www.googleapis.com/youtube/v3/search",
                             params=params, timeout=30)
            if r.status_code != 200:
                err = r.json().get("error", {}).get("message", r.text[:120])
                print(f"  ⚠  YouTube search: {err}")
                return [], "error", None
            data = r.json()
            video_ids.extend(item["id"]["videoId"] for item in data.get("items", []))
            next_token = data.get("nextPageToken")
            if not next_token:
                break

        if not video_ids:
            print("  No videos in date range")
            return [], "ok", yt_followers

        print(f"  {len(video_ids)} videos — fetching stats…")
        result = []
        for i in range(0, len(video_ids), 50):
            r2 = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
                "id": ",".join(video_ids[i:i+50]),
                "part": "statistics,snippet", "key": api_key,
            }, timeout=30)
            if r2.status_code != 200:
                continue
            for item in r2.json().get("items", []):
                snip  = item.get("snippet", {})
                stats = item.get("statistics", {})
                views = int(stats.get("viewCount")    or 0)
                likes = int(stats.get("likeCount")    or 0)
                cmts  = int(stats.get("commentCount") or 0)
                eng   = likes + cmts
                result.append({
                    "title":    (snip.get("title") or "YouTube Video")[:100],
                    "date":     (snip.get("publishedAt") or "")[:10],
                    "platform": ["youtube"],
                    "ctype":    "video",
                    "views":    views,
                    "reach":    views,
                    "likes":    likes,
                    "comments": cmts,
                    "shares":   None,
                    "saves":    None,
                    "followers": yt_followers, "new_users": None,
                    "ctr":      None,
                    "url":      f"https://www.youtube.com/watch?v={item['id']}",
                    "engagement": eng,
                    "eng_rate": round(eng / views * 100, 2) if views > 0 else None,
                })
        print(f"  ✓ {len(result)} YouTube videos")
        return result, "ok", yt_followers
    except Exception as e:
        print(f"  ✗ YouTube exception: {e}")
        return [], "error", None

# ─── LinkedIn ────────────────────────────────────────────────────────────────
def fetch_linkedin():
    token      = li_cfg.get("access_token", "").strip()
    company_id = str(li_cfg.get("company_id", "")).strip()
    if not token or not company_id:
        return [], "not_configured", None
    print("→ LinkedIn: fetching posts…")
    try:
        org_urn = f"urn:li:organization:{company_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202305",
        }
        # Fetch UGC posts
        posts, start = [], 0
        while True:
            r = requests.get(
                "https://api.linkedin.com/v2/ugcPosts",
                headers=headers,
                params={"q": "authors", "authors": f"List({org_urn})",
                        "count": 100, "start": start},
                timeout=30,
            )
            if r.status_code != 200:
                print(f"  ⚠  LinkedIn ({r.status_code}): {r.text[:200]}")
                return [], "error", None
            elements = r.json().get("elements", [])
            posts.extend(elements)
            if len(elements) < 100:
                break
            start += 100

        # Filter to date range
        start_ms = int(datetime.fromisoformat(START_STR).timestamp() * 1000)
        posts    = [p for p in posts if p.get("created", {}).get("time", 0) >= start_ms]

        if not posts:
            print("  No posts in range")
            return [], "ok", None

        print(f"  {len(posts)} posts — fetching analytics…")

        # Batch share statistics
        urns_param = "List(" + ",".join(p["id"] for p in posts) + ")"
        stats_map  = {}
        rs = requests.get(
            "https://api.linkedin.com/v2/organizationalEntityShareStatistics",
            headers=headers,
            params={"q": "organizationalEntity",
                    "organizationalEntity": org_urn,
                    "shares": urns_param},
            timeout=30,
        )
        if rs.status_code == 200:
            for el in rs.json().get("elements", []):
                urn = el.get("ugcPost") or el.get("share", "")
                stats_map[urn] = el.get("totalShareStatistics", {})

        result = []
        for p in posts:
            s   = stats_map.get(p["id"], {})
            ts  = p.get("created", {}).get("time", 0)
            d   = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
            txt = (p.get("specificContent", {})
                    .get("com.linkedin.ugc.ShareContent", {})
                    .get("shareCommentary", {})
                    .get("text", "") or "LinkedIn Post")
            imp  = s.get("impressionCount") or 0
            likes = s.get("likeCount")  or 0
            cmts  = s.get("commentCount") or 0
            shrs  = s.get("shareCount")  or 0
            clks  = s.get("clickCount")  or 0
            eng   = likes + cmts + shrs
            result.append({
                "title":    txt[:100].replace("\n", " ").strip(),
                "date":     d,
                "platform": ["LinkedIn"],
                "ctype":    "",
                "views":    imp,
                "reach":    imp,
                "likes":    likes,
                "comments": cmts,
                "shares":   shrs,
                "saves":    None,
                "followers": None, "new_users": None,
                "ctr":      round(clks / imp * 100, 2) if imp > 0 else None,
                "url":      "",
                "engagement": eng,
                "eng_rate": round(eng / imp * 100, 2) if imp > 0 else None,
            })
        print(f"  ✓ {len(result)} LinkedIn posts")
        return result, "ok", None
    except Exception as e:
        print(f"  ✗ LinkedIn exception: {e}")
        return [], "error", None

# ─── Fetch all platforms ──────────────────────────────────────────────────────
fb_posts, fb_status, fb_followers = fetch_facebook()
ig_posts, ig_status, ig_followers = fetch_instagram()
yt_posts, yt_status, yt_followers = fetch_youtube()
li_posts, li_status, li_followers = fetch_linkedin()

raw_posts = sorted(
    fb_posts + ig_posts + yt_posts + li_posts,
    key=lambda p: p["date"]
)

generated   = datetime.now().strftime("%Y-%m-%d %H:%M")
total_posts = len(raw_posts)

followers_by_platform = {
    "Facebook":  fb_followers,
    "Instagram": ig_followers,
    "youtube":   yt_followers,
}
followers_json = json.dumps(followers_by_platform)

print(f"\n  Total posts loaded: {total_posts}")

# Status badge helper for HTML header
def status_badge(label, color_key, status, count):
    color_map = {
        "fb": "#1877f2", "ig": "#e1306c", "yt": "#ff0000", "li": "#0077b5"
    }
    bg = color_map.get(color_key, "#64748b")
    if status == "ok":
        return (f'<span style="background:{bg};color:#fff;font-size:11px;'
                f'padding:3px 8px;border-radius:4px;font-weight:600">'
                f'{label} ✓ {count}</span>')
    elif status == "error":
        return (f'<span style="background:#7f1d1d;color:#fca5a5;font-size:11px;'
                f'padding:3px 8px;border-radius:4px;font-weight:600">'
                f'{label} ✗</span>')
    else:
        return (f'<span style="background:#1e293b;color:#475569;font-size:11px;'
                f'padding:3px 8px;border-radius:4px;font-weight:600">'
                f'{label} —</span>')

badges_html = " ".join([
    status_badge("FB", "fb", fb_status, len(fb_posts)),
    status_badge("IG", "ig", ig_status, len(ig_posts)),
    status_badge("YT", "yt", yt_status, len(yt_posts)),
    status_badge("LI", "li", li_status, len(li_posts)),
])

any_connected = any(s == "ok" for s in [fb_status, ig_status, yt_status, li_status])
none_configured = all(s == "not_configured" for s in [fb_status, ig_status, yt_status, li_status])

# ─── HTML ─────────────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WorkHero — Social Media Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{
  --bg:#f8f9fa;--card:#fff;--border:#e5e7eb;--text:#111827;--muted:#6b7280;
  --blue:#2563eb;--green:#16a34a;--red:#dc2626;--orange:#d97706;--purple:#7c3aed;
  --li:#0077b5;--ig:#e1306c;--fb:#1877f2;--yt:#ff0000;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.5}}
.header{{background:#0f172a;color:#f1f5f9;padding:0 24px;display:flex;align-items:stretch;justify-content:space-between}}
.header-left{{display:flex;align-items:center;gap:16px;padding:14px 0}}
.brand{{font-size:13px;font-weight:700;color:#94a3b8;letter-spacing:.05em;text-transform:uppercase}}
.page-title{{font-size:15px;font-weight:600}}
.tab-nav{{display:flex;gap:0}}
.tab-btn{{padding:0 20px;height:100%;display:flex;align-items:center;font-size:12px;font-weight:500;color:#94a3b8;cursor:pointer;border-bottom:3px solid transparent;background:none;border-top:none;border-left:none;border-right:none;transition:color .15s,border-color .15s}}
.tab-btn:hover{{color:#e2e8f0}}
.tab-btn.active{{color:#f1f5f9;border-bottom-color:#3b82f6}}
.header-right{{display:flex;align-items:center;gap:8px;padding:14px 0}}
.gen-time{{font-size:11px;color:#475569;margin-left:4px}}
.reload-btn{{background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:4px 12px;border-radius:4px;font-size:11px;cursor:pointer;margin-left:4px}}
.panel{{display:none}}.panel.active{{display:block}}
.filter-bar{{background:var(--card);border-bottom:1px solid var(--border);padding:10px 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
.filter-label{{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}
.preset-btns{{display:flex;gap:6px}}
.preset{{padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer;border:1px solid var(--border);background:var(--card);color:var(--text);transition:background .1s}}
.preset:hover{{background:#f1f5f9}}
.preset.active{{background:var(--text);color:#fff;border-color:var(--text)}}
.plat-sep{{width:1px;height:24px;background:var(--border);margin:0 4px}}
.plat-btn{{padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer;border:1px solid var(--border);background:var(--card);color:var(--text)}}
.pba{{background:var(--text);color:#fff;border-color:var(--text)}}
.pbli{{background:var(--li);color:#fff;border-color:var(--li)}}
.pbig{{background:var(--ig);color:#fff;border-color:var(--ig)}}
.pbfb{{background:var(--fb);color:#fff;border-color:var(--fb)}}
.pbyt{{background:var(--yt);color:#fff;border-color:var(--yt)}}
.date-inputs{{display:flex;align-items:center;gap:6px;margin-left:auto}}
.date-inputs input{{padding:4px 8px;border:1px solid var(--border);border-radius:4px;font-size:12px;color:var(--text);background:var(--card)}}
.apply-btn{{padding:4px 12px;background:var(--blue);color:#fff;border:none;border-radius:4px;font-size:12px;cursor:pointer}}
.warn-box{{background:#fefce8;border:1px solid #fbbf24;border-radius:6px;padding:10px 14px;font-size:12px;margin-bottom:16px;display:flex;align-items:flex-start;gap:10px}}
.warn-box b{{font-weight:700}}
.warn-steps{{margin-top:4px;color:#92400e;line-height:1.8}}
.warn-steps code{{background:#fef9c3;padding:1px 5px;border-radius:3px;font-family:monospace;font-size:11px}}
.main{{max-width:1200px;margin:0 auto;padding:20px 24px}}
.stat-banner{{border-radius:8px;padding:14px 20px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;background:#eff6ff}}
.stat-right{{text-align:right;font-size:12px;color:var(--muted)}}
.stat-big{{font-size:20px;font-weight:700;color:var(--text)}}
.kpi-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:16px}}
.kpi-card{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px}}
.kpi-label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}}
.kpi-value{{font-size:20px;font-weight:700}}
.kpi-sub{{font-size:11px;color:var(--muted);margin-top:2px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:16px;overflow:hidden}}
.card-header{{padding:10px 16px;border-bottom:1px solid var(--border);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);display:flex;align-items:center;gap:8px}}
.card-body{{padding:16px}}
.chart-tabs{{display:flex;gap:6px}}
.ctab{{padding:3px 10px;border-radius:4px;font-size:11px;cursor:pointer;border:1px solid var(--border);background:var(--card)}}
.ctab.active{{background:var(--text);color:#fff;border-color:var(--text)}}
.chart-wrap{{height:200px}}
.charts-row{{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:16px}}
.charts-row .card{{margin-bottom:0}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;padding:8px 12px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);border-bottom:1px solid var(--border)}}
th.r,td.r{{text-align:right}}
th.s{{cursor:pointer;user-select:none}}
th.s:hover{{color:var(--text)}}
td{{padding:8px 12px;border-bottom:1px solid var(--border);font-size:12px}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#f9fafb}}
.td-t{{max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.na{{color:var(--muted);font-style:italic}}
.pb{{display:inline-block;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:700;color:#fff;margin:1px}}
.pbli2{{background:var(--li)}}.pbig2{{background:var(--ig)}}.pbfb2{{background:var(--fb)}}.pbyt2{{background:var(--yt)}}
.ct{{display:inline-block;padding:2px 6px;border-radius:3px;font-size:10px;background:#f1f5f9;color:#64748b}}
.ev{{font-weight:700;color:var(--purple)}}
@media(max-width:900px){{.kpi-grid{{grid-template-columns:repeat(2,1fr)}}.charts-row{{grid-template-columns:1fr}}}}
</style>
</head>
<body>

<!-- Lock screen -->
<div id="lockScreen" style="position:fixed;inset:0;background:#0f172a;z-index:9999;display:flex;align-items:center;justify-content:center">
  <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;padding:40px 48px;text-align:center;width:360px">
    <div style="font-size:13px;font-weight:700;color:#94a3b8;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px">WorkHero</div>
    <div style="font-size:18px;font-weight:600;color:#f1f5f9;margin-bottom:24px">Social Media Dashboard</div>
    <input id="pwInput" type="password" placeholder="Enter password"
      style="width:100%;padding:10px 14px;background:#0f172a;border:1px solid #334155;border-radius:6px;color:#f1f5f9;font-size:14px;outline:none;margin-bottom:12px"
      onkeydown="if(event.key==='Enter')checkPw()"
    />
    <div id="pwError" style="color:#f87171;font-size:12px;margin-bottom:10px;min-height:16px"></div>
    <button onclick="checkPw()"
      style="width:100%;padding:10px;background:#2563eb;color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer">
      Unlock
    </button>
  </div>
</div>
<script>
(function(){{
  if(sessionStorage.getItem('wh_social_auth')==='1')
    document.getElementById('lockScreen').style.display='none';
}})();
function checkPw(){{
  const v=document.getElementById('pwInput').value;
  if(v===atob('{__import__("base64").b64encode(DASHBOARD_PW.encode()).decode()}')){{
    sessionStorage.setItem('wh_social_auth','1');
    document.getElementById('lockScreen').style.display='none';
  }}else{{
    document.getElementById('pwError').textContent='Incorrect password';
    document.getElementById('pwInput').value='';
    document.getElementById('pwInput').focus();
  }}
}}
</script>

<div class="header">
  <div class="header-left">
    <span class="brand">WorkHero</span>
    <span class="page-title">Social Media Dashboard</span>
  </div>
  <div class="tab-nav">
    <button class="tab-btn active" onclick="switchTab('overview',this)">Overview</button>
    <button class="tab-btn" onclick="switchTab('posts',this)">All Posts</button>
  </div>
  <div class="header-right">
    {badges_html}
    <span class="gen-time">Generated {generated}</span>
    <button class="reload-btn" onclick="window.location.reload()">↻ Reload</button>
  </div>
</div>

<div id="staleBanner" style="display:none;background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:10px 18px;margin:8px 20px;font-size:13px;color:#92400e;align-items:center;gap:10px">
  <span>⚠</span>
  <span id="staleMsg">Dashboard data is stale — last refresh was more than 48 hours ago.</span>
  <a href="https://github.com/omarworkhero/workhero-social-dashboard/actions" target="_blank" style="margin-left:auto;color:#b45309;font-weight:600;white-space:nowrap">Check GHA →</a>
</div>
<div class="filter-bar">
  <span class="filter-label">Date range</span>
  <div class="preset-btns">
    <button class="preset" onclick="setPreset(7,this)">Last 7d</button>
    <button class="preset active" onclick="setPreset(30,this)">Last 30d</button>
    <button class="preset" onclick="setPresetMonth(0,this)">This month</button>
    <button class="preset" onclick="setPresetMonth(-1,this)">Last month</button>
    <button class="preset" onclick="setPreset(90,this)">Last 90d</button>
  </div>
  <div class="plat-sep"></div>
  <span class="filter-label">Platform</span>
  <button class="plat-btn pba" id="pbAll" onclick="setPlatform('all',this,'pba')">All</button>
  <button class="plat-btn"    id="pbLi"  onclick="setPlatform('LinkedIn',this,'pbli')">LinkedIn</button>
  <button class="plat-btn"    id="pbIg"  onclick="setPlatform('Instagram',this,'pbig')">Instagram</button>
  <button class="plat-btn"    id="pbFb"  onclick="setPlatform('Facebook',this,'pbfb')">Facebook</button>
  <button class="plat-btn"    id="pbYt"  onclick="setPlatform('youtube',this,'pbyt')">YouTube</button>
  <div class="date-inputs">
    <input type="date" id="dateFrom"/>
    <span style="color:var(--muted)">→</span>
    <input type="date" id="dateTo"/>
    <button class="apply-btn" onclick="applyCustom()">Apply</button>
  </div>
</div>

<!-- OVERVIEW -->
<div id="panel-overview" class="panel active">
<div class="main">

  {('''<div class="warn-box">
    <span style="font-size:16px">⚠</span>
    <div>
      <b>No platforms connected yet.</b> Edit <code>social_config.json</code> and add your API credentials, then rerun: <code>python3 generate_social_dashboard.py</code><br>
      <div class="warn-steps">
        <b>Facebook/Instagram:</b> developers.facebook.com/tools/explorer → WorkHero API app → pages_read_engagement scope<br>
        <b>YouTube:</b> console.cloud.google.com → YouTube Data API v3 → create API key<br>
        <b>LinkedIn:</b> linkedin.com/developers → r_organization_social scope
      </div>
    </div>
  </div>''' if none_configured else '')}

  <div class="stat-banner">
    <div>
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:2px">Top Platform · Reach</div>
      <div id="statPlatName" style="font-size:18px;font-weight:700;color:var(--blue)">—</div>
    </div>
    <div class="stat-right">
      <div id="statBig" class="stat-big"></div>
      <div id="statSub"></div>
    </div>
  </div>

  <div class="kpi-grid">
    <div class="kpi-card"><div class="kpi-label">Total Reach</div><div class="kpi-value" id="kpiReach">—</div><div class="kpi-sub" id="kpiReachSub"></div></div>
    <div class="kpi-card"><div class="kpi-label">Total Views</div><div class="kpi-value" id="kpiViews">—</div><div class="kpi-sub" id="kpiViewsSub"></div></div>
    <div class="kpi-card"><div class="kpi-label">Total Engagement</div><div class="kpi-value ev" id="kpiEng">—</div><div class="kpi-sub" id="kpiEngRate"></div></div>
    <div class="kpi-card"><div class="kpi-label">Posts Published</div><div class="kpi-value" id="kpiPosts">—</div><div class="kpi-sub" id="kpiPostsSub"></div></div>
    <div class="kpi-card"><div class="kpi-label">Total Likes</div><div class="kpi-value" style="color:var(--green)" id="kpiLikes">—</div><div class="kpi-sub" id="kpiLikesSub"></div></div>
  </div>

  <div class="card" style="margin-bottom:16px">
    <div class="card-header">Platform Followers</div>
    <div class="card-body" style="padding:12px 16px">
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
        <div style="text-align:center;padding:10px 0">
          <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--fb);margin-bottom:4px">Facebook</div>
          <div style="font-size:22px;font-weight:700" id="kpiFbFollowers">—</div>
          <div style="font-size:11px;color:var(--muted)">Page Followers</div>
        </div>
        <div style="text-align:center;padding:10px 0;border-left:1px solid var(--border);border-right:1px solid var(--border)">
          <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--ig);margin-bottom:4px">Instagram</div>
          <div style="font-size:22px;font-weight:700" id="kpiIgFollowers">—</div>
          <div style="font-size:11px;color:var(--muted)">Followers</div>
        </div>
        <div style="text-align:center;padding:10px 0">
          <div style="font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--yt);margin-bottom:4px">YouTube</div>
          <div style="font-size:22px;font-weight:700" id="kpiYtFollowers">—</div>
          <div style="font-size:11px;color:var(--muted)">Subscribers</div>
        </div>
      </div>
    </div>
  </div>

  <div class="charts-row">
    <div class="card">
      <div class="card-header">
        Trend
        <div class="chart-tabs" style="margin-left:auto">
          <button class="ctab active" onclick="showCtab('reach',this)">Reach &amp; Views</button>
          <button class="ctab" onclick="showCtab('eng',this)">Engagement</button>
          <button class="ctab" onclick="showCtab('freq',this)">Post Frequency</button>
        </div>
      </div>
      <div class="card-body">
        <div id="cw-reach" class="chart-wrap"><canvas id="reachChart"></canvas></div>
        <div id="cw-eng"   class="chart-wrap" style="display:none"><canvas id="engChart"></canvas></div>
        <div id="cw-freq"  class="chart-wrap" style="display:none"><canvas id="freqChart"></canvas></div>
      </div>
    </div>
    <div class="card">
      <div class="card-header">Reach by Platform</div>
      <div class="card-body" style="padding-top:10px">
        <div style="height:160px"><canvas id="platChart"></canvas></div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header">Platform Summary</div>
    <table><thead><tr>
      <th>Platform</th><th class="r">Posts</th><th class="r">Reach</th>
      <th class="r">Views</th><th class="r">Likes</th><th class="r">Comments</th>
      <th class="r">Shares</th><th class="r">Engagement</th><th class="r">Avg Eng Rate</th>
    </tr></thead><tbody id="platTable"></tbody></table>
  </div>

  <div class="card">
    <div class="card-header">Content Type Performance</div>
    <table><thead><tr>
      <th>Type</th><th class="r">Posts</th><th class="r">Avg Reach</th>
      <th class="r">Avg Views</th><th class="r">Avg Engagement</th><th class="r">Avg Eng Rate</th>
    </tr></thead><tbody id="ctypeTable"></tbody></table>
  </div>

</div></div>

<!-- POSTS -->
<div id="panel-posts" class="panel">
<div class="main">
  <div class="card">
    <div class="card-header">
      All Posts <span style="margin-left:8px;font-weight:400;color:var(--muted)" id="postsCount"></span>
      <span style="margin-left:auto;font-size:10px;font-weight:400;color:var(--muted)">Click headers to sort</span>
    </div>
    <div style="overflow-x:auto">
    <table><thead><tr>
      <th class="s" onclick="sortPosts('date')">Date ↕</th>
      <th>Title</th><th>Platform</th><th>Type</th>
      <th class="r s" onclick="sortPosts('reach')">Reach ↕</th>
      <th class="r s" onclick="sortPosts('views')">Views ↕</th>
      <th class="r s" onclick="sortPosts('likes')">Likes ↕</th>
      <th class="r s" onclick="sortPosts('comments')">Comments ↕</th>
      <th class="r s" onclick="sortPosts('shares')">Shares ↕</th>
      <th class="r s" onclick="sortPosts('saves')">Saves ↕</th>
      <th class="r s" onclick="sortPosts('engagement')">Engagement ↕</th>
      <th class="r s" onclick="sortPosts('eng_rate')">Eng Rate ↕</th>
      <th class="r s" onclick="sortPosts('ctr')">CTR ↕</th>
      <th class="r s" onclick="sortPosts('followers')">Followers ↕</th>
      <th>Link</th>
    </tr></thead><tbody id="postsBody"></tbody></table>
    </div>
  </div>
</div></div>

<script>
const RAW = {json.dumps(raw_posts)};
const FOLLOWERS = {followers_json};
let from=null,to=null,plat='all',sortKey='date',sortDir=-1;
let charts={{}};

const PLATS=['LinkedIn','Instagram','Facebook','youtube'];
const PLAT_LABELS=['LinkedIn','Instagram','Facebook','YouTube'];
const PLAT_COLORS=['#0077b5','#e1306c','#1877f2','#ff0000'];
const PLAT_KEYS={{'LinkedIn':'pbli2','Instagram':'pbig2','Facebook':'pbfb2','youtube':'pbyt2'}};

function switchTab(n,btn){{
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('panel-'+n).classList.add('active');
  if(n==='posts') renderPosts();
}}

function toISO(d){{return d.toISOString().slice(0,10);}}
function setPreset(days,btn){{
  const to=new Date();to.setHours(0,0,0,0);
  const from=new Date(to);from.setDate(from.getDate()-days+1);
  applyRange(toISO(from),toISO(to));
  document.querySelectorAll('.preset').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
}}
function setPresetMonth(offset,btn){{
  const n=new Date(),from=new Date(n.getFullYear(),n.getMonth()+offset,1);
  const cap=new Date();cap.setHours(0,0,0,0);
  const toD=new Date(n.getFullYear(),n.getMonth()+offset+1,0);
  applyRange(toISO(from),toISO(new Date(Math.min(toD,cap))));
  document.querySelectorAll('.preset').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
}}
function applyCustom(){{
  const f=document.getElementById('dateFrom').value,t=document.getElementById('dateTo').value;
  if(f&&t&&f<=t){{applyRange(f,t);document.querySelectorAll('.preset').forEach(b=>b.classList.remove('active'));}}
}}
function applyRange(f,t){{
  from=f;to=t;
  document.getElementById('dateFrom').value=f;
  document.getElementById('dateTo').value=t;
  render();
}}
function setPlatform(p,btn,cls){{
  plat=p;
  document.querySelectorAll('.plat-btn').forEach(b=>b.className='plat-btn');
  btn.className='plat-btn '+cls;
  render();
}}

function filter(){{
  return RAW.filter(p=>p.date>=from&&p.date<=to&&(plat==='all'||(p.platform||[]).includes(plat)));
}}
function sum(arr){{return arr.reduce((s,v)=>s+(v||0),0);}}
function avg(arr){{const v=arr.filter(x=>x!=null);return v.length?v.reduce((s,x)=>s+x,0)/v.length:null;}}
function fmt(v,dec=0){{
  if(v==null||v===undefined)return'<span class="na">—</span>';
  if(v>=1e6)return(v/1e6).toFixed(1)+'M';
  if(v>=1e3)return(v/1e3).toFixed(1)+'k';
  return v.toFixed(dec);
}}
function fmtP(v){{return v==null?'<span class="na">—</span>':v.toFixed(1)+'%';}}

function render(){{
  const posts=filter();
  const tReach=sum(posts.map(p=>p.reach));
  const tViews=sum(posts.map(p=>p.views));
  const tEng=sum(posts.map(p=>p.engagement));
  const tLikes=sum(posts.map(p=>p.likes));
  const aEng=avg(posts.map(p=>p.eng_rate));
  const n=posts.length;

  // When posts exist but metric is 0, show 0 rather than — so users can tell data loaded vs truly absent
  const hasData=n>0;
  document.getElementById('kpiReach').innerHTML=fmt(tReach||null);
  document.getElementById('kpiReachSub').textContent=n+' posts';
  document.getElementById('kpiViews').innerHTML=hasData?fmt(tViews):fmt(null);
  document.getElementById('kpiViewsSub').textContent='';
  document.getElementById('kpiEng').innerHTML=hasData?fmt(tEng):fmt(null);
  document.getElementById('kpiEngRate').innerHTML=aEng!=null?fmtP(aEng)+' avg':'';
  document.getElementById('kpiPosts').textContent=n;
  document.getElementById('kpiLikes').innerHTML=hasData?fmt(tLikes):fmt(null);

  // Top platform
  const byP={{}};
  posts.forEach(p=>{{(p.platform||[]).forEach(pl=>{{
    if(!byP[pl])byP[pl]={{reach:0,posts:0,eng:0}};
    byP[pl].reach+=p.reach||0;byP[pl].posts++;byP[pl].eng+=p.engagement||0;
  }})}});
  const top=Object.entries(byP).sort((a,b)=>(b[1].reach||b[1].eng)-(a[1].reach||a[1].eng))[0];
  if(top){{
    document.getElementById('statPlatName').textContent=top[0]==='youtube'?'YouTube':top[0];
    const hasReach=top[1].reach>0;
    document.getElementById('statBig').innerHTML=hasReach?fmt(top[1].reach)+' reach':fmt(top[1].eng)+' engagements';
    document.getElementById('statSub').textContent=top[1].posts+' posts'+(hasReach?' · '+fmt(top[1].eng)+' engagements':'');
  }}else{{
    document.getElementById('statPlatName').textContent='No data';
    document.getElementById('statBig').innerHTML='';
    document.getElementById('statSub').textContent='';
  }}

  buildTrends(posts);
  buildPlatChart(byP);

  // Platform table — sorted by reach (or engagement when reach unavailable)
  let ptRows=[];
  PLATS.forEach(pl=>{{
    const pp=posts.filter(p=>(p.platform||[]).includes(pl));
    if(!pp.length)return;
    const r=sum(pp.map(p=>p.reach)),v=sum(pp.map(p=>p.views)),
          l=sum(pp.map(p=>p.likes)),c=sum(pp.map(p=>p.comments)),
          s=sum(pp.map(p=>p.shares)),e=l+c+s,
          er=r>0?e/r*100:null;
    ptRows.push({{pl,pp,r,v,l,c,s,e,er}});
  }});
  ptRows.sort((a,b)=>(b.r||b.e)-(a.r||a.e));
  let ptHTML='';
  ptRows.forEach(({{'pl':pl,'pp':pp,'r':r,'v':v,'l':l,'c':c,'s':s,'e':e,'er':er}})=>{{
    const label=pl==='youtube'?'YouTube':pl;
    const bk=PLAT_KEYS[pl]||'';
    const reachCell=r>0?fmt(r):'<span class="na" title="reach data unavailable">—</span>';
    ptHTML+=`<tr>
      <td><span class="pb ${{bk}}">${{label.slice(0,2).toUpperCase()}}</span> ${{label}}</td>
      <td class="r">${{pp.length}}</td><td class="r">${{reachCell}}</td>
      <td class="r">${{fmt(v||null)}}</td><td class="r">${{fmt(l||null)}}</td>
      <td class="r">${{fmt(c||null)}}</td><td class="r">${{fmt(s||null)}}</td>
      <td class="r ev">${{fmt(e||null)}}</td><td class="r">${{fmtP(er)}}</td>
    </tr>`;
  }});
  document.getElementById('platTable').innerHTML=ptHTML||'<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:20px">No data</td></tr>';

  // Content type table
  const byC={{}};
  posts.forEach(p=>{{
    const k=p.ctype||'(none)';
    if(!byC[k])byC[k]={{posts:[],reach:[],views:[],eng:[],er:[]}};
    byC[k].posts.push(p);
    if(p.reach!=null)byC[k].reach.push(p.reach);
    if(p.views!=null)byC[k].views.push(p.views);
    byC[k].eng.push(p.engagement);
    if(p.eng_rate!=null)byC[k].er.push(p.eng_rate);
  }});
  const sortedC=Object.entries(byC).sort((a,b)=>(avg(b[1].reach)||0)-(avg(a[1].reach)||0));
  let ctHTML='';
  sortedC.forEach(([ct,d])=>{{
    ctHTML+=`<tr>
      <td><span class="ct">${{ct}}</span></td>
      <td class="r">${{d.posts.length}}</td>
      <td class="r">${{fmt(avg(d.reach))}}</td>
      <td class="r">${{fmt(avg(d.views))}}</td>
      <td class="r ev">${{fmt(avg(d.eng))}}</td>
      <td class="r">${{fmtP(avg(d.er))}}</td>
    </tr>`;
  }});
  document.getElementById('ctypeTable').innerHTML=ctHTML||'<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:20px">No data</td></tr>';

  if(document.getElementById('panel-posts').classList.contains('active'))renderPosts();
}}

function buildTrends(posts){{
  const wb={{}};
  posts.forEach(p=>{{
    const d=new Date(p.date+'T00:00:00'),day=d.getDay();
    const mon=new Date(d);mon.setDate(d.getDate()-(day===0?6:day-1));
    const wk=toISO(mon);
    if(!wb[wk])wb[wk]={{reach:0,views:0,eng:0,posts:0}};
    wb[wk].reach+=p.reach||0;wb[wk].views+=p.views||0;
    wb[wk].eng+=p.engagement||0;wb[wk].posts++;
  }});
  const wks=Object.keys(wb).sort(),labels=wks.map(w=>w.slice(5));
  const opts={{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:'bottom',labels:{{font:{{size:11}}}}}}}},
    scales:{{y:{{ticks:{{callback:v=>v>=1000?(v/1000).toFixed(0)+'k':v}}}},x:{{ticks:{{font:{{size:10}},maxTicksLimit:14}}}}}}}};
  const barOpts={{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:'bottom',labels:{{font:{{size:11}}}}}}}},
    scales:{{x:{{ticks:{{font:{{size:10}},maxTicksLimit:14}}}}}}}};

  ['reachChart','engChart','freqChart'].forEach(id=>{{
    if(charts[id])charts[id].destroy();
  }});
  charts.reachChart=new Chart(document.getElementById('reachChart').getContext('2d'),{{
    type:'line',data:{{labels,datasets:[
      {{label:'Reach',data:wks.map(w=>wb[w].reach),borderColor:'#2563eb',backgroundColor:'rgba(37,99,235,.08)',fill:true,tension:.3,pointRadius:3}},
      {{label:'Views',data:wks.map(w=>wb[w].views),borderColor:'#7c3aed',backgroundColor:'rgba(124,58,237,.05)',fill:true,tension:.3,pointRadius:3}},
    ]}},options:opts
  }});
  charts.engChart=new Chart(document.getElementById('engChart').getContext('2d'),{{
    type:'bar',data:{{labels,datasets:[{{label:'Engagement',data:wks.map(w=>wb[w].eng),backgroundColor:'rgba(124,58,237,.7)'}}]}},options:barOpts
  }});
  charts.freqChart=new Chart(document.getElementById('freqChart').getContext('2d'),{{
    type:'bar',data:{{labels,datasets:[{{label:'Posts',data:wks.map(w=>wb[w].posts),backgroundColor:'rgba(37,99,235,.6)'}}]}},options:barOpts
  }});
}}

function buildPlatChart(byP){{
  // For platforms with 0 reach but positive engagement, use engagement so they remain visible.
  // Platforms with reach → show reach. Platforms with 0 reach → show engagement so they remain visible.
  const data=PLATS.map(pl=>{{
    if(!byP[pl])return 0;
    return byP[pl].reach||byP[pl].eng||0;
  }});
  if(charts.platChart)charts.platChart.destroy();
  charts.platChart=new Chart(document.getElementById('platChart').getContext('2d'),{{
    type:'doughnut',
    data:{{labels:PLAT_LABELS,datasets:[{{data,backgroundColor:PLAT_COLORS,borderWidth:2,borderColor:'#fff'}}]}},
    options:{{responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{position:'bottom',labels:{{font:{{size:11}},padding:8}}}},
        tooltip:{{callbacks:{{label:ctx=>{{
          const pl=PLATS[ctx.dataIndex],r=(byP[pl]?.reach||0),e=(byP[pl]?.eng||0);
          return r>0?' '+ctx.label+': '+fmt(r)+' reach':' '+ctx.label+': '+fmt(e)+' engagements';
        }}}}}}
      }}
    }}
  }});
}}

function showCtab(type,btn){{
  document.querySelectorAll('.ctab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  [['reach','cw-reach'],['eng','cw-eng'],['freq','cw-freq']].forEach(([t,id])=>{{
    document.getElementById(id).style.display=type===t?'':'none';
  }});
}}

function renderPosts(){{
  const posts=filter();
  document.getElementById('postsCount').textContent=`(${{posts.length}} posts)`;
  const sorted=[...posts].sort((a,b)=>{{
    const av=a[sortKey]??(sortDir===1?Infinity:-Infinity);
    const bv=b[sortKey]??(sortDir===1?Infinity:-Infinity);
    return av<bv?sortDir:av>bv?-sortDir:0;
  }});
  let html='';
  sorted.forEach(p=>{{
    const badges=(p.platform||[]).map(pl=>{{
      const k=PLAT_KEYS[pl]||'';
      const lbl=pl==='youtube'?'YT':pl.slice(0,2).toUpperCase();
      return `<span class="pb ${{k}}">${{lbl}}</span>`;
    }}).join('');
    const link=p.url?`<a href="${{p.url}}" target="_blank" style="color:var(--blue);font-size:11px">→</a>`:'<span class="na">—</span>';
    html+=`<tr>
      <td style="white-space:nowrap">${{p.date}}</td>
      <td class="td-t" title="${{p.title}}">${{p.title}}</td>
      <td style="white-space:nowrap">${{badges||'<span class="na">—</span>'}}</td>
      <td><span class="ct">${{p.ctype||'—'}}</span></td>
      <td class="r">${{fmt(p.reach)}}</td><td class="r">${{fmt(p.views)}}</td>
      <td class="r">${{fmt(p.likes)}}</td><td class="r">${{fmt(p.comments)}}</td>
      <td class="r">${{fmt(p.shares)}}</td>
      <td class="r">${{fmt(p.saves)}}</td>
      <td class="r ev">${{fmt(p.engagement)}}</td>
      <td class="r">${{fmtP(p.eng_rate)}}</td>
      <td class="r">${{fmtP(p.ctr)}}</td>
      <td class="r">${{fmt(p.followers)}}</td>
      <td>${{link}}</td>
    </tr>`;
  }});
  document.getElementById('postsBody').innerHTML=html||'<tr><td colspan="15" style="text-align:center;color:var(--muted);padding:24px">No posts in this range</td></tr>';
}}

function sortPosts(key){{
  sortKey===key?sortDir=-sortDir:(sortKey=key,sortDir=-1);
  renderPosts();
}}

(function(){{
  // Populate platform followers cards (static — not date-filtered)
  function fmtF(v){{return v==null?'—':v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(1)+'k':String(v);}}
  const fKeys={{Facebook:'kpiFbFollowers',Instagram:'kpiIgFollowers',youtube:'kpiYtFollowers'}};
  Object.entries(fKeys).forEach(([pl,id])=>{{
    const el=document.getElementById(id);
    if(el)el.textContent=fmtF(FOLLOWERS[pl]);
  }});

  const to=new Date();to.setHours(0,0,0,0);
  const from=new Date(to);from.setDate(from.getDate()-29);
  applyRange(toISO(from),toISO(to));

  // Stale data warning: show banner if dashboard is > 48 hours old
  const genEl=document.querySelector('.gen-time');
  if(genEl){{
    const genText=genEl.textContent.replace('Generated ','').trim();
    const genMs=new Date(genText).getTime();
    if(!isNaN(genMs)){{
      const hoursOld=(Date.now()-genMs)/3600000;
      if(hoursOld>48){{
        const b=document.getElementById('staleBanner');
        const h=Math.round(hoursOld);
        document.getElementById('staleMsg').textContent=
          `Dashboard data is ${{h}} hours old — the daily refresh may have failed.`;
        b.style.display='flex';
      }}
    }}
  }}
}})();
</script>
</body>
</html>"""

with open(OUTPUT_FILE, "w") as f:
    f.write(html)

print(f"\n✓  Written → {OUTPUT_FILE}")
print(f"   Open: open {OUTPUT_FILE}\n")
