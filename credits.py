"""Earned Pro (docs/business.md): recompute every account's `proUntil` from its surf reports and cams.

  python jobs.py credits          (every 15 minutes in the cloud)

- Each day (California time) you report a session earns REPORT_DAYS of Pro, stacked after your trial and
  any earlier credit, but never more than CAP_DAYS ahead of that report.
- An approved ("live") cam you added keeps Pro CAM_DAYS ahead of now, so it lapses soon after it's taken down.

It recomputes from all the reports each run (idempotent: deleting a report takes its credit back), and only
writes accounts whose `proUntil` changed. The browser can never write `proUntil` (firebase/firestore.rules);
payments will set it the same way later.

Talks to Firestore with the job's own credentials, or the emulator when FIRESTORE_EMULATOR_HOST is set.
"""
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TRIAL_DAYS, REPORT_DAYS, CAP_DAYS, CAM_DAYS = 14, 3, 30, 2
LOCAL = ZoneInfo("America/Los_Angeles")

def earned_until(created, report_times, has_cam, now):
    """The end of earned Pro (or None) for an account created at `created` with reports at `report_times`."""
    until = created + timedelta(days=TRIAL_DAYS)
    earned = False
    seen = set()
    for t in sorted(report_times):
        day = t.astimezone(LOCAL).date()
        if day in seen:
            continue
        seen.add(day)
        until = min(max(until, t) + timedelta(days=REPORT_DAYS), t + timedelta(days=CAP_DAYS))
        earned = True
    if has_cam:
        until, earned = max(until, now + timedelta(days=CAM_DAYS)), True
    return until if earned else None

def run(now=None):
    from google.cloud import firestore                   # only this job needs it
    now = now or datetime.now(timezone.utc)
    db = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    reports = defaultdict(list)
    for r in db.collection("reports").select(["uid", "at"]).stream():
        d = r.to_dict()
        if d.get("uid") and d.get("at"):
            reports[d["uid"]].append(d["at"])
    cams = {c.to_dict().get("uid") for c in db.collection("cams").where(filter=firestore.FieldFilter("status", "==", "live")).select(["uid"]).stream()}
    changed = 0
    for u in db.collection("users").stream():
        d = u.to_dict()
        if not d.get("created"):
            continue
        until = earned_until(d["created"], reports.get(u.id, []), u.id in cams, now)
        old = d.get("proUntil")
        if until is None and old is None:
            continue
        if old is not None and until is not None and abs((old - until).total_seconds()) < 1:
            continue
        u.reference.update({"proUntil": until if until is not None else firestore.DELETE_FIELD,
                            "earned": {"reportDays": len({t.astimezone(LOCAL).date() for t in reports.get(u.id, [])}), "cam": u.id in cams}})
        changed += 1
    print(f"credits: {len(reports)} reporters, {len(cams)} live cams, {changed} accounts updated")
    return 0
