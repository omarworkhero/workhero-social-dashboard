#!/usr/bin/env python3
"""
Social Dashboard Health Check
Validates all API credentials before running the dashboard generator.
Exits with code 1 if any critical platform credential is broken.
Run automatically by the GHA workflow before generate_social_dashboard.py.
"""

import json, sys, requests
from pathlib import Path

cfg    = json.loads(Path("social_config.json").read_text())
fb_cfg = cfg.get("facebook", {})
ig_cfg = cfg.get("instagram", {})
yt_cfg = cfg.get("youtube",   {})

APP_ID     = fb_cfg.get("app_id",     "1501983588253582")
APP_SECRET = fb_cfg.get("app_secret", "bc3fa7579a555fff7e82df44c481129d")

ok  = []
bad = []

def check(name, fn):
    try:
        result = fn()
        if result:
            ok.append(f"  ✓  {name}: {result}")
        else:
            bad.append(f"  ✗  {name}: returned empty/false")
    except Exception as e:
        bad.append(f"  ✗  {name}: {e}")

# ── Facebook / Instagram page token ──────────────────────────────────────────
def check_fb():
    token = fb_cfg.get("page_access_token", "").strip()
    if not token:
        raise ValueError("FB_PAGE_TOKEN secret is empty")
    r = requests.get(
        "https://graph.facebook.com/debug_token",
        params={"input_token": token, "access_token": f"{APP_ID}|{APP_SECRET}"},
        timeout=15,
    )
    d = r.json().get("data", {})
    if not d.get("is_valid"):
        err = r.json().get("data", {}).get("error", {}).get("message", "token invalid")
        raise ValueError(err)
    expires = d.get("expires_at", 0)
    scopes  = d.get("scopes", [])
    has_insights = "read_insights" in scopes
    expiry_str = "never expires" if expires == 0 else f"expires {expires}"
    return f"valid PAGE token · {expiry_str} · read_insights={'yes' if has_insights else 'NO — reach will be missing'}"

check("Facebook/Instagram token", check_fb)

# ── YouTube API key ───────────────────────────────────────────────────────────
def check_yt():
    key = yt_cfg.get("api_key", "").strip()
    if not key:
        return "not configured (skipping)"
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "id", "id": yt_cfg.get("channel_id", ""), "key": key},
        timeout=15,
    )
    if r.status_code != 200:
        err = r.json().get("error", {}).get("message", r.text[:80])
        raise ValueError(err)
    return f"API key valid · channel found"

check("YouTube API key", check_yt)

# ── Print results ─────────────────────────────────────────────────────────────
print("\n── Social Dashboard Health Check ──────────────────────")
for line in ok:
    print(line)
for line in bad:
    print(line)
print("────────────────────────────────────────────────────────\n")

if bad:
    print(f"FAIL: {len(bad)} credential(s) broken. Fix before dashboard will work.\n")
    sys.exit(1)

print(f"All {len(ok)} credential(s) healthy.\n")
