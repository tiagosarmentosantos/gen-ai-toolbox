#!/usr/bin/env python3
"""Fetch Strava data with the REST API (no Claude, standard library only) and write the input files
that compute_metrics.py expects:

  <out>/activities.json   {"<window key>": [activity, ...], ...}   (activity shaped like the Strava connector)
  <out>/zones.json        {"zones": [z1_min, ..., z5_min]}          (heart-rate zone lower bounds)
  <out>/hr_streams.json   {"<activity id>": [bpm, ...]}             (for the training-load card)

Window options are the same as compute_metrics.py (--weeks / --start / --end / --compare / --load-weeks).

Credentials (environment variables, or flags):
  STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN   (recommended, scope activity:read_all)
  or STRAVA_ACCESS_TOKEN                                         (short-lived, skips the refresh)

Notes
  * Strava's REST API names the effort field `suffer_score` (Relative Effort, Strava subscribers only);
    it is mapped to `relative_effort`. Use --detail-effort to fetch it per activity if the list omits it.
  * Rate limits (15-minute and daily) are read from the response headers; the script waits when it gets close.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compute_metrics as cm  # noqa: E402

API = "https://www.strava.com/api/v3"
TOKEN_URL = "https://www.strava.com/oauth/token"
PER_PAGE = 200


class StravaError(RuntimeError):
    pass


class StravaClient:
    """Minimal REST client with token refresh, 429 handling and rate-limit awareness."""

    def __init__(self, access_token=None, client_id=None, client_secret=None, refresh_token=None, max_wait=1200):
        self.access_token, self.client_id, self.client_secret = access_token, client_id, client_secret
        self.refresh_token, self.new_refresh_token = refresh_token, None
        self.max_wait = max_wait
        self.limit, self.usage = (100, 1000), (0, 0)
        if not self.access_token:
            self.refresh()

    # -- auth ---------------------------------------------------------------------------------
    def refresh(self):
        if not (self.client_id and self.client_secret and self.refresh_token):
            raise StravaError("set STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET and STRAVA_REFRESH_TOKEN (or STRAVA_ACCESS_TOKEN)")
        body = urllib.parse.urlencode({"client_id": self.client_id, "client_secret": self.client_secret,
                                       "grant_type": "refresh_token", "refresh_token": self.refresh_token}).encode()
        data = self._open(urllib.request.Request(TOKEN_URL, data=body, method="POST"), auth=False)
        self.access_token = data["access_token"]
        if data.get("refresh_token") and data["refresh_token"] != self.refresh_token:
            self.new_refresh_token = data["refresh_token"]

    # -- http ---------------------------------------------------------------------------------
    def _wait_for_window(self, reason):
        now = dt.datetime.now(dt.timezone.utc)
        nxt = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0) + dt.timedelta(minutes=15)
        wait = (nxt - now).total_seconds() + 5
        if wait > self.max_wait:
            raise StravaError(f"{reason}; the next rate-limit window is {int(wait)}s away (> --max-wait {self.max_wait}s)")
        print(f"rate limit: {reason}; waiting {int(wait)}s", file=sys.stderr)
        time.sleep(wait)

    def _open(self, req, auth=True, retries=3):
        if auth:
            req.add_header("Authorization", f"Bearer {self.access_token}")
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    self._note_limits(r.headers)
                    return json.loads(r.read().decode() or "null")
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < retries:
                    self._wait_for_window("HTTP 429")
                    continue
                if e.code == 401:
                    raise StravaError("HTTP 401 from Strava: token invalid or missing the activity:read_all scope") from e
                raise StravaError(f"HTTP {e.code} for {req.full_url}: {e.read().decode()[:200]}") from e
        raise StravaError("too many retries")

    def _note_limits(self, headers):
        try:
            self.limit = tuple(int(x) for x in headers["X-RateLimit-Limit"].split(","))
            self.usage = tuple(int(x) for x in headers["X-RateLimit-Usage"].split(","))
        except (KeyError, AttributeError, ValueError):
            pass

    def get(self, path, **params):
        if self.usage[0] >= self.limit[0] - 2:
            self._wait_for_window("15-minute limit nearly used")
        if self.usage[1] >= self.limit[1] - 5:
            raise StravaError("daily Strava rate limit nearly used; try again tomorrow")
        qs = "?" + urllib.parse.urlencode(params) if params else ""
        return self._open(urllib.request.Request(f"{API}{path}{qs}"))


# ---------------------------------------------------------------------------------------------
def to_connector_shape(a):
    """Strava REST SummaryActivity -> the shape compute_metrics.normalize() reads."""
    s = {"distance": a.get("distance"), "moving_time": a.get("moving_time"), "elapsed_time": a.get("elapsed_time"),
         "elevation_gain": a.get("total_elevation_gain"), "relative_effort": a.get("suffer_score"),
         "avg_cadence": a.get("average_cadence")}
    return {"id": str(a["id"]), "sport_type": a.get("sport_type") or a.get("type"),
            "start_local": (a.get("start_date_local") or a["start_date"]).rstrip("Z"), "has_heartrate": bool(a.get("has_heartrate")),
            "summary": {k: v for k, v in s.items() if v is not None}}


def fetch_window(client, start, end):
    """All activities whose local start date is in [start, end] (fetches one day extra each side, then filters)."""
    after = int(dt.datetime.combine(start - dt.timedelta(days=1), dt.time.min, dt.timezone.utc).timestamp())
    before = int(dt.datetime.combine(end + dt.timedelta(days=2), dt.time.min, dt.timezone.utc).timestamp())
    out, page = [], 1
    while True:
        batch = client.get("/athlete/activities", after=after, before=before, per_page=PER_PAGE, page=page)
        out += batch
        if len(batch) < PER_PAGE:
            break
        page += 1
    acts = [to_connector_shape(a) for a in out]
    return [a for a in acts if start.isoformat() <= a["start_local"][:10] <= end.isoformat()]


def downsample(samples, k):
    """k evenly spaced samples (k <= 0 keeps everything), like the connector's `resolution`."""
    n = len(samples)
    if k <= 0 or n <= k:
        return list(samples)
    return [samples[round(i * (n - 1) / (k - 1))] for i in range(k)]


def fetch_hr(client, ids, k):
    streams = {}
    for i, aid in enumerate(ids, 1):
        try:
            data = client.get(f"/activities/{aid}/streams", keys="heartrate", key_by_type="true")
        except StravaError as e:
            print(f"warning: no HR stream for {aid}: {e}", file=sys.stderr)
            continue
        hr = (data or {}).get("heartrate", {}).get("data") if isinstance(data, dict) else None
        if hr:
            streams[aid] = downsample(hr, k)
        if i % 25 == 0:
            print(f"  heart-rate streams: {i}/{len(ids)}", file=sys.stderr)
    return streams


def main(argv=None, client=None):
    ap = argparse.ArgumentParser(description="Fetch Strava data for the training dashboard (no Claude needed)")
    ap.add_argument("--weeks", type=int)
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--compare")
    ap.add_argument("--load-weeks", type=int)
    ap.add_argument("--config", default=str(cm.ROOT / "config.json"))
    ap.add_argument("--out", default="work", help="output directory (default: work)")
    ap.add_argument("--hr-samples", type=int, help="HR samples kept per activity, 0 = all (default: config load.resolution)")
    ap.add_argument("--no-load", action="store_true", help="skip zones and heart-rate streams (no training-load card)")
    ap.add_argument("--detail-effort", action="store_true", help="fetch each activity's detail when the list has no suffer_score")
    ap.add_argument("--max-wait", type=int, default=1200, help="longest rate-limit wait in seconds (default 1200)")
    ap.add_argument("--token-out", help="write a rotated refresh token to this file")
    ap.add_argument("--client-id", default=os.environ.get("STRAVA_CLIENT_ID"))
    ap.add_argument("--client-secret", default=os.environ.get("STRAVA_CLIENT_SECRET"))
    ap.add_argument("--refresh-token", default=os.environ.get("STRAVA_REFRESH_TOKEN"))
    ap.add_argument("--access-token", default=os.environ.get("STRAVA_ACCESS_TOKEN"))
    a = ap.parse_args(argv)
    if a.weeks is not None and a.weeks < 1:
        cm.die("--weeks must be at least 1")

    periods, days = cm.plan(a)
    cfg = json.load(open(a.config))
    load_cfg = cfg.get("load", {})
    k = load_cfg.get("resolution", 50) if a.hr_samples is None else a.hr_samples
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if client is None:
        try:
            client = StravaClient(a.access_token, a.client_id, a.client_secret, a.refresh_token, a.max_wait)
        except StravaError as e:
            cm.die(str(e))

    try:
        acts = {}
        for p in periods:
            acts[p["key"]] = fetch_window(client, p["start"], p["end"])
            print(f"{p['name']}: {len(acts[p['key']])} activities ({p['start']} to {p['end']})", file=sys.stderr)
        json.dump(acts, open(out / "activities.json", "w"))

        run_ride = [x for lst in acts.values() for x in lst
                    if x["sport_type"] in set(cfg["run_types"]) | set(cfg["ride_types"])]
        if run_ride and all("relative_effort" not in x["summary"] for x in run_ride):
            msg = "Strava returned no suffer_score (Relative Effort): effort KPIs will be empty (try --detail-effort; needs a Strava subscription)"
            print(f"warning: {msg}\n::warning::{msg}", file=sys.stderr)
        if a.detail_effort:
            todo = [x for x in run_ride if "relative_effort" not in x["summary"]]
            for i, x in enumerate(todo, 1):
                d = client.get(f"/activities/{x['id']}") or {}
                if d.get("suffer_score") is not None:
                    x["summary"]["relative_effort"] = d["suffer_score"]
                if i % 25 == 0:
                    print(f"  activity details: {i}/{len(todo)}", file=sys.stderr)
            json.dump(acts, open(out / "activities.json", "w"))

        if not a.no_load:
            zones = client.get("/athlete/zones")
            zl = [z["min"] for z in (zones or {}).get("heart_rate", {}).get("zones", [])]
            if len(zl) == 5:
                json.dump({"zones": zl}, open(out / "zones.json", "w"))
                keys = set(load_cfg.get("periods", ["current"]))
                ids, seen = [], set()
                for p in periods:
                    if p["key"] not in keys:
                        continue
                    ls = cm.load_window(p, days, cfg, a.load_weeks)[0].isoformat()
                    for x in acts[p["key"]]:
                        if (x["sport_type"] in set(cfg["run_types"]) | set(cfg["ride_types"]) and x["has_heartrate"]
                                and x["start_local"][:10] >= ls and x["id"] not in seen):
                            seen.add(x["id"])
                            ids.append(x["id"])
                print(f"fetching heart-rate streams for {len(ids)} activities", file=sys.stderr)
                json.dump(fetch_hr(client, ids, k), open(out / "hr_streams.json", "w"))
            else:
                print("warning: heart-rate zones unavailable; training-load card skipped", file=sys.stderr)
    except StravaError as e:
        cm.die(str(e))

    if getattr(client, "new_refresh_token", None) and a.token_out:
        Path(a.token_out).write_text(client.new_refresh_token)
        print("::warning::Strava issued a new refresh token; update the STRAVA_REFRESH_TOKEN secret", file=sys.stderr)
    print(f"wrote {out}/", file=sys.stderr)


if __name__ == "__main__":
    main()
