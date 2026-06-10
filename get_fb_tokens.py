#!/usr/bin/env python3
"""
Facebook/Instagram Token Setup Helper

Converts a short-lived User Token into a long-lived Page Access Token (never expires
for Page admins) and saves it to social_config.json.

Usage:
    1. Go to developers.facebook.com/tools/explorer — select "WorkHero API" app
    2. Click "Generate Access Token" with scopes:
       pages_show_list, pages_read_engagement, read_insights,
       instagram_basic, instagram_manage_insights
    3. Run: python3 get_fb_tokens.py
    4. Paste the token when prompted

App credentials: find them at developers.facebook.com → WorkHero API → Settings → Basic
"""

import json, requests
from pathlib import Path

config_path = Path("social_config.json")
cfg = json.loads(config_path.read_text())

fb_cfg = cfg.setdefault("facebook", {})
APP_ID     = fb_cfg.get("app_id", "").strip()
APP_SECRET = fb_cfg.get("app_secret", "").strip()

if not APP_ID or not APP_SECRET:
    print("\n  App ID and Secret not found in social_config.json.")
    print("  Find them at: developers.facebook.com → WorkHero API → Settings → Basic\n")
    APP_ID     = input("  Paste App ID:     ").strip()
    APP_SECRET = input("  Paste App Secret: ").strip()
    fb_cfg["app_id"]     = APP_ID
    fb_cfg["app_secret"] = APP_SECRET
    cfg["instagram"].setdefault("app_id", APP_ID)

user_token = input("\nPaste your short-lived User Token from Graph API Explorer:\n> ").strip()
if not user_token:
    print("No token entered. Exiting.")
    exit(1)

# ── Step 1: Exchange for long-lived user token (60-day expiry) ────────────────
print("\n→ Exchanging for long-lived user token…")
rx = requests.get("https://graph.facebook.com/v25.0/oauth/access_token", params={
    "grant_type":        "fb_exchange_token",
    "client_id":         APP_ID,
    "client_secret":     APP_SECRET,
    "fb_exchange_token": user_token,
})
if rx.status_code != 200:
    print(f"  ✗ Exchange failed: {rx.json().get('error', {}).get('message', rx.text)}")
    print("  Using short-lived token as fallback (will expire in ~1 hour).")
    long_token = user_token
else:
    long_token = rx.json()["access_token"]
    expires_in = rx.json().get("expires_in", "?")
    print(f"  ✓ Long-lived token obtained (expires in {expires_in}s / ~60 days)")

# ── Step 2: Get all pages you manage ─────────────────────────────────────────
print("\n→ Fetching your pages via /me/accounts…")
r = requests.get("https://graph.facebook.com/v25.0/me/accounts", params={
    "fields": "id,name,access_token,instagram_business_account",
    "access_token": long_token,
})
if r.status_code != 200:
    print(f"✗ Error: {r.json().get('error', {}).get('message', r.text)}")
    exit(1)

pages = r.json().get("data", [])
if not pages:
    print("✗ No pages found. Make sure you're an admin of a Facebook Page.")
    exit(1)

print(f"\n  Found {len(pages)} page(s):\n")
for i, p in enumerate(pages):
    ig = p.get("instagram_business_account", {}).get("id", "none")
    print(f"  [{i}] {p['name']}  (Page ID: {p['id']}, IG Account: {ig})")

if len(pages) == 1:
    idx = 0
    print(f"\n  Auto-selecting: {pages[0]['name']}")
else:
    idx = int(input("\nEnter the number of your WorkHero page: "))

page       = pages[idx]
page_id    = page["id"]
page_name  = page["name"]
page_token = page["access_token"]  # derived from long-lived token → never expires for admins
ig_id      = page.get("instagram_business_account", {}).get("id", "")

print(f"\n  Page:     {page_name}")
print(f"  Page ID:  {page_id}")
print(f"  IG ID:    {ig_id or '(not connected)'}")

# ── Step 3: Verify ────────────────────────────────────────────────────────────
print("\n→ Verifying page token…")
rv = requests.get(f"https://graph.facebook.com/v25.0/{page_id}", params={
    "fields": "name,fan_count", "access_token": page_token,
})
if rv.status_code == 200:
    print(f"  ✓ {rv.json()['name']} ({rv.json().get('fan_count','?')} followers)")
else:
    print(f"  ⚠ {rv.json().get('error', {}).get('message', '')}")

if ig_id:
    print(f"\n→ Verifying Instagram @{ig_id}…")
    ri = requests.get(f"https://graph.facebook.com/v25.0/{ig_id}", params={
        "fields": "username,followers_count", "access_token": page_token,
    })
    if ri.status_code == 200:
        d = ri.json()
        print(f"  ✓ @{d.get('username','?')} — {d.get('followers_count','?')} followers")
    else:
        print(f"  ⚠ {ri.json().get('error', {}).get('message', '')}")

# ── Step 4: Write everything back ────────────────────────────────────────────
cfg["facebook"]["app_id"]            = APP_ID
cfg["facebook"]["app_secret"]        = APP_SECRET
cfg["facebook"]["page_access_token"] = page_token
cfg["facebook"]["page_id"]           = page_id
cfg["instagram"]["page_access_token"] = page_token
cfg["instagram"]["ig_user_id"]        = ig_id

config_path.write_text(json.dumps(cfg, indent=2))
print(f"\n✓ social_config.json updated — page token never expires for admins.")
print(f"\nNext: python3 generate_social_dashboard.py\n")
