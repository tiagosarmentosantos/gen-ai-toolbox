"""Smoke test: example data -> metrics -> HTML. Run: python tests/test_pipeline.py"""
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

with tempfile.TemporaryDirectory() as tmp:
    m, h = Path(tmp) / "metrics.json", Path(tmp) / "dashboard.html"
    subprocess.run([PY, ROOT / "scripts/compute_metrics.py", "--activities", ROOT / "examples/activities_example.json",
                    "--end", "2026-10-03", "--out", m], check=True, capture_output=True)
    d = json.load(open(m))
    assert [p["label"] for p in d["periods"]] == ["6 Sep – 3 Oct 2026", "9 Aug – 5 Sep 2026", "7 Sep – 4 Oct 2025"], d["periods"]
    assert [x["km"] for x in d["all"]] == [354.5, 283.0, 276.1], [x["km"] for x in d["all"]]
    assert (d["run"][0]["km"], d["ride"][0]["km"], d["all"][0]["elev"]) == (39.5, 315.0, 5228)
    assert d["all"][0]["days"] == 18 and d["run"][0]["hard"] == 3 and d["ride"][0]["n"] == 28
    assert d["acwr"]["re"] == 1.32, d["acwr"]
    assert [l["n"] for l in d["loops"]] == [[11, 3, 11], [8, 2, 10]], d["loops"]
    assert "load" not in d  # no HR data supplied -> card stays hidden
    m2 = Path(tmp) / "metrics_load.json"
    subprocess.run([PY, ROOT / "scripts/compute_metrics.py", "--activities", ROOT / "examples/activities_example.json",
                    "--end", "2026-10-03", "--hr", ROOT / "examples/hr_streams_example.json",
                    "--zones", ROOT / "examples/zones_example.json", "--out", m2], check=True, capture_output=True)
    ld = json.load(open(m2))["load"]
    cur = ld["periods"][0]
    assert (cur["cov"], cur["n"], cur["total"]) == (32, 32, 2379), cur
    assert [cur["cat"][c]["share"] for c in ("low", "high", "ana")] == [54, 46, 0], cur["cat"]
    assert ld["periods"][1] is None and ld["periods"][2] is None
    subprocess.run([PY, ROOT / "scripts/render_dashboard.py", "--metrics", m, "--coach", ROOT / "examples/coach_example.json",
                    "--out", h], check=True, capture_output=True)
    html = h.read_text()
    assert "/*__DATA__*/null" not in html and "/*__COACH__*/null" not in html and "354.5" in html
print("OK")

# ---- flexible windows: --weeks / --start / --end / --compare (pooled input, split by date) ----
import datetime as dt
ex = json.load(open(ROOT / "examples/activities_example.json"))
pool = [a for k in ("current", "previous", "last_year") for a in ex[k]]


def run(*extra, activities=pool):
    with tempfile.TemporaryDirectory() as tmp:
        f, out = Path(tmp) / "a.json", Path(tmp) / "m.json"
        json.dump(activities, open(f, "w"))
        r = subprocess.run([PY, ROOT / "scripts/compute_metrics.py", "--activities", f, "--out", out, *map(str, extra)],
                           capture_output=True, text=True)
        return r, (json.load(open(out)) if r.returncode == 0 else None)


def km(start, end):
    return round(sum(a["summary"]["distance"] for a in pool
                     if start <= a["start_local"][:10] <= end and a["sport_type"] in ("Run", "Ride")) / 1000, 1)


# --weeks 2: previous = the 14 days before, last year = shifted 364 days
r, d = run("--weeks", 2, "--end", "2026-10-03")
assert r.returncode == 0, r.stderr
assert (d["weeks"], d["days"], len(d["all"][0]["cum"])) == (2, 14, 14)
assert [p["label"] for p in d["periods"]] == ["20 Sep – 3 Oct 2026", "6 Sep – 19 Sep 2026", "21 Sep – 4 Oct 2025"], d["periods"]
assert d["all"][0]["km"] == km("2026-09-20", "2026-10-03") and d["all"][1]["km"] == km("2026-09-06", "2026-09-19")
assert d["acwr"]["re"] is None and any("ACWR" in f for f in d["flags"])

# --start/--end custom range, 33 days -> 5 weeks with a partial last week
r, d = run("--start", "2026-09-01", "--end", "2026-10-03", "--compare", "previous")
assert r.returncode == 0, r.stderr
assert (d["weeks"], d["days"], d["partial_days"]) == (5, 33, 5) and d["week_labels"][-1] == "Wk 5*"
assert len(d["periods"]) == 2 and d["periods"][1]["label"] == "30 Jul – 31 Aug 2026"
assert d["acwr"]["re"] is None and len(d["all"][0]["wk_km"]) == 5

# --start + --weeks, --compare none / Nw / date
r, d = run("--start", "2026-09-06", "--weeks", 4, "--compare", "none")
assert r.returncode == 0 and len(d["periods"]) == 1 and d["all"][0]["km"] == 354.5, r.stderr
r, d = run("--end", "2026-10-03", "--compare", "52w,2025-08-10")
assert r.returncode == 0 and [p["key"] for p in d["periods"]] == ["current", "52w", "2025-08-10"], r.stderr
assert d["all"][1]["km"] == 276.1

# invalid combinations fail with a clear message
for bad in (["--weeks", 4, "--start", "2026-09-01", "--end", "2026-10-03"], ["--weeks", 53], ["--compare", "2w", "--weeks", 4],
            ["--compare", "previous,last_year,26w"], ["--end", "2026-10-03", "--compare", "2026-09-20"]):
    r, _ = run(*bad)
    assert r.returncode != 0 and "error:" in r.stderr, (bad, r.stderr)

# every mode renders to a page
with tempfile.TemporaryDirectory() as tmp:
    for i, extra in enumerate((["--weeks", 8], ["--compare", "none"], ["--weeks", 1])):
        m, h = Path(tmp) / f"m{i}.json", Path(tmp) / f"h{i}.html"
        subprocess.run([PY, ROOT / "scripts/compute_metrics.py", "--activities", ROOT / "examples/activities_example.json",
                        "--end", "2026-10-03", "--out", m, *map(str, extra)], check=True, capture_output=True)
        subprocess.run([PY, ROOT / "scripts/render_dashboard.py", "--metrics", m, "--out", h], check=True, capture_output=True)
print("OK (windows)")

# ---- up to 52 weeks; HR load limited to the last K weeks ----
r, d = run("--weeks", 52, "--end", "2026-10-03", "--compare", "previous")
assert r.returncode == 0, r.stderr
assert (d["weeks"], d["days"], len(d["all"][0]["wk_km"]), len(d["all"][0]["cum"])) == (52, 364, 52, 364)
assert d["acwr"]["re"] is not None
r, d = run("--weeks", 12, "--end", "2026-10-03", "--compare", "none", "--hr", ROOT / "examples/hr_streams_example.json",
           "--zones", ROOT / "examples/zones_example.json")
assert r.returncode == 0, r.stderr
ld = d["load"]
assert (ld["weeks"], ld["restricted"], ld["labels"][0], len(ld["periods"][0]["wk"]["low"])) == (8, True, "Wk 1", 8), ld["weeks"]
assert ld["periods"][0]["cov"] == 32 and ld["periods"][0]["n"] == 44, ld["periods"][0]
assert any("HR data for 32 of 44" in f for f in d["flags"]), d["flags"]
print("OK (52 weeks, load window)")

r, d = run("--weeks", 52, "--end", "2026-10-03")  # last_year == previous for 52 weeks -> duplicate skipped
assert r.returncode == 0 and [p["key"] for p in d["periods"]] == ["current", "previous"] and "identical" in r.stderr, r.stderr
print("OK (52-week default compare)")
