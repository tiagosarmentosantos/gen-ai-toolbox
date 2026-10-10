"""fetch_strava.py against a fake Strava REST API (no network). Run: python tests/test_fetch.py

This proves the mapping, windowing, pagination, downsampling and file formats; it does NOT prove that
Strava's live API returns exactly these fields. Check a first real run (see README)."""
import contextlib, datetime as dt, io, json, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_strava as fs
import compute_metrics as cm

ex = json.load(open(ROOT / "examples/activities_example.json"))
hr = {k: v for k, v in json.load(open(ROOT / "examples/hr_streams_example.json")).items() if not k.startswith("_")}
pool = [a for k in ("current", "previous", "last_year") for a in ex[k]]


def rest(a, with_effort=True):
    s = a["summary"]
    r = {"id": int(a["id"]) if a["id"].isdigit() else a["id"], "sport_type": a["sport_type"],
         "start_date_local": a["start_local"] + "Z", "distance": s["distance"], "moving_time": s["moving_time"],
         "elapsed_time": s.get("elapsed_time", s["moving_time"]), "total_elevation_gain": s["elevation_gain"], "has_heartrate": a["id"] in hr}
    if with_effort:
        r["suffer_score"] = s["relative_effort"]
    if "avg_cadence" in s:
        r["average_cadence"] = s["avg_cadence"]
    return r


class Fake:
    new_refresh_token = None

    def __init__(self, effort=True):
        self.effort, self.calls = effort, []

    def get(self, path, **p):
        self.calls.append((path, p))
        if path == "/athlete/activities":
            lo, hi = p["after"], p["before"]
            rows = [rest(a, self.effort) for a in pool
                    if lo <= dt.datetime.fromisoformat(a["start_local"]).replace(tzinfo=dt.timezone.utc).timestamp() < hi]
            i = (p["page"] - 1) * p["per_page"]
            return rows[i:i + p["per_page"]]
        if path == "/athlete/zones":
            return {"heart_rate": {"custom_zones": False, "zones": [{"min": 0, "max": 118}, {"min": 119, "max": 147},
                    {"min": 148, "max": 162}, {"min": 163, "max": 177}, {"min": 178}]}}
        if path.endswith("/streams"):
            aid = path.split("/")[2]
            if aid not in hr:
                raise fs.StravaError("HTTP 404")
            return {"heartrate": {"data": hr[aid], "series_type": "time"}}
        aid = path.split("/")[2]  # /activities/{id}
        a = next(x for x in pool if x["id"] == aid)
        return {"id": aid, "suffer_score": a["summary"]["relative_effort"]}


def run_fetch(*args, client=None):
    err = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
        fs.main(["--out", tmp, "--end", "2026-10-03", *map(str, args)], client=client or Fake())
        files = {f.name: json.load(open(f)) for f in Path(tmp).glob("*.json")}
    return files, err.getvalue()


# helpers
assert fs.to_connector_shape({"id": 1, "type": "Run", "start_date_local": "2026-09-27T08:24:59Z", "distance": 5})["start_local"] == "2026-09-27T08:24:59"
s = list(range(100))
assert len(fs.downsample(s, 50)) == 50 and fs.downsample(s, 50)[0] == 0 and fs.downsample(s, 50)[-1] == 99
assert fs.downsample(s, 0) == s and fs.downsample([1, 2], 50) == [1, 2]

# full run, small pages to exercise pagination
fs.PER_PAGE = 5
files, log = run_fetch("--hr-samples", 0)
assert set(files) == {"activities.json", "zones.json", "hr_streams.json"}, files.keys()
assert files["zones.json"] == {"zones": [0, 119, 148, 163, 178]}
assert [len(files["activities.json"][k]) for k in ("current", "previous", "last_year")] == [32, 12, 25]
assert len(files["hr_streams.json"]) == 32 and "32 activities" in log

# feed the existing pipeline: same numbers as the Claude-driven runs
with tempfile.TemporaryDirectory() as tmp:
    for n, v in files.items():
        json.dump(v, open(Path(tmp) / n, "w"))
    d = cm.build(files["activities.json"], json.load(open(ROOT / "config.json")), *cm.plan(type("A", (), dict(
        weeks=None, start=None, end="2026-10-03", compare=None))()), hr=files["hr_streams.json"],
        zones=cm.load_zones(Path(tmp) / "zones.json", ["current", "previous", "last_year"]))
assert [m["km"] for m in d["all"]] == [354.5, 283.0, 276.1] and d["all"][0]["elev"] == 5228 and d["acwr"]["re"] == 1.32
assert d["load"]["periods"][0]["total"] == 2379 and d["load"]["periods"][1] is None

# default sampling keeps 50 samples per activity
files, _ = run_fetch()
assert all(len(v) <= 50 for v in files["hr_streams.json"].values())

# --no-load, --compare none, load window limit
c = Fake()
files, _ = run_fetch("--no-load", "--compare", "none", client=c)
assert set(files) == {"activities.json"} and list(files["activities.json"]) == ["current"]
assert not any(p.endswith("/streams") or p == "/athlete/zones" for p, _ in c.calls)
c = Fake()
files, _ = run_fetch("--weeks", 12, "--compare", "none", "--hr-samples", 0, client=c)
assert len(files["hr_streams.json"]) == 32  # only the last 8 weeks (config load.max_weeks) are fetched

# missing suffer_score: warning, then --detail-effort fills it
files, log = run_fetch(client=Fake(effort=False))
assert "no suffer_score" in log and "relative_effort" not in files["activities.json"]["current"][0]["summary"]
files, log = run_fetch("--detail-effort", client=Fake(effort=False))
assert files["activities.json"]["current"][0]["summary"]["relative_effort"] == 149

# rotated refresh token is written out
c = Fake(); c.new_refresh_token = "new-token"
with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()):
    fs.main(["--out", tmp, "--end", "2026-10-03", "--no-load", "--token-out", f"{tmp}/t.txt"], client=c)
    assert Path(f"{tmp}/t.txt").read_text() == "new-token"
print("OK (fetch)")
