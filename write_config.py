import json, os

cfg = {
    "lookback_days": 90,
    "dashboard_password": os.environ["DASHBOARD_PASSWORD"],
    "facebook": {
        "page_access_token": os.environ["FB_PAGE_TOKEN"],
        "page_id": os.environ["FB_PAGE_ID"]
    },
    "instagram": {
        "page_access_token": os.environ["FB_PAGE_TOKEN"],
        "ig_user_id": os.environ["IG_USER_ID"]
    },
    "youtube": {"api_key": "", "channel_id": ""},
    "linkedin": {"access_token": "", "company_id": ""}
}

open("social_config.json", "w").write(json.dumps(cfg))
print("social_config.json written")
