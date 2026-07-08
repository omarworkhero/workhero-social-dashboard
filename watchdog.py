"""
Social Dashboard watchdog — runs every 12h via watchdog.yml
Checks if the live dashboard is fresh. Fails loudly + Slack alert if stale >36h.
"""
import os, re, sys, requests
from datetime import datetime, timezone

DASHBOARD_URL = "https://omarworkhero.github.io/workhero-social-dashboard/"
STALE_THRESHOLD_HOURS = 36
SLACK = os.environ.get("SLACK_WEBHOOK_URL", "")

def slack_alert(msg):
    if not SLACK:
        return
    try:
        requests.post(SLACK, json={"text": msg}, timeout=10)
    except Exception as e:
        print(f"Slack notify failed (non-fatal): {e}")

print(f"Fetching {DASHBOARD_URL} ...")
try:
    resp = requests.get(DASHBOARD_URL, timeout=30)
    resp.raise_for_status()
except Exception as e:
    msg = f"Social dashboard unreachable: {e}"
    print(f"::error title=Social Dashboard Unreachable::{msg}")
    slack_alert(f":rotating_light: *Social Dashboard Unreachable*\n{msg}")
    sys.exit(1)

match = re.search(r"Generated (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", resp.text)
if not match:
    msg = "Could not find Generated timestamp — dashboard may be broken."
    print(f"::error title=Social Dashboard Parse Error::{msg}")
    slack_alert(f":rotating_light: *Social Dashboard Parse Error*\n{msg}")
    sys.exit(1)

generated_str = match.group(1)
generated = datetime.strptime(generated_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
now = datetime.now(timezone.utc)
age_hours = (now - generated).total_seconds() / 3600

print(f"Generated: {generated_str} UTC ({age_hours:.1f}h ago)")

if age_hours > STALE_THRESHOLD_HOURS:
    msg = (
        f"Social Dashboard is STALE — last updated {age_hours:.0f}h ago. "
        f"Trigger: https://github.com/omarworkhero/workhero-social-dashboard/actions/workflows/refresh.yml"
    )
    print(f"::error title=Social Dashboard Stale — {age_hours:.0f}h::{msg}")
    slack_alert(f":rotating_light: *Social Dashboard Stale*\nLast updated {age_hours:.0f}h ago.\nTrigger: https://github.com/omarworkhero/workhero-social-dashboard/actions")
    sys.exit(1)

print(f"Dashboard is fresh. ({age_hours:.1f}h old, threshold {STALE_THRESHOLD_HOURS}h)")
