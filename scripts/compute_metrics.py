#!/usr/bin/env python3
"""Compute running / cycling KPIs for a window and up to two comparison windows.

Window (the "current" period), in order of precedence:
  --start D [--end E]      custom range (E defaults to today; or --start D --weeks N)
  --weeks N [--end E]      N full weeks ending E (default: today)
  (nothing)                4 weeks ending today
Comparison windows (--compare, comma-separated, max 2, default "previous,last_year"):
  previous      the window of the same length immediately before
  last_year     the current window shifted back 364 days (weekdays line up)
  Nw / Nd       shifted back N weeks / N days (must not overlap the current window), e.g. 104w
  YYYY-MM-DD    a window of the same length starting on that date
  none          no comparison

Usage:
  compute_metrics.py --windows [--weeks N] [--start D] [--end E] [--compare ...] [--load-weeks K]   # ranges to fetch
  compute_metrics.py --activities work/activities.json [window options] --out work/metrics.json --summary
Input JSON: either {"<window key>": [...], ...} (keys from --windows) or one pooled list / list_activities
response containing all windows; each value is the `activities` array or the whole response.
"""
import argparse
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

MAX_WEEKS = 52
ROOT = Path(__file__).resolve().parent.parent
TD = dt.timedelta


def label(s, e):
    if s.year != e.year:
        return f"{s.day} {s:%b %Y} – {e.day} {e:%b %Y}"
    return f"{s.day} {s:%b} – {e.day} {e:%b %Y}"


def die(msg):
    sys.exit(f"error: {msg}")


def parse_date(x):
    try:
        return dt.date.fromisoformat(x)
    except ValueError:
        die(f"invalid date '{x}' (use YYYY-MM-DD)")


def resolve_current(weeks, start, end, today):
    if start and end and weeks and (end - start).days + 1 != 7 * weeks:
        die("--start/--end span does not match --weeks; give at most two of the three")
    if start:
        end = end or (start + TD(days=7 * weeks - 1) if weeks else today)
    else:
        end = end or today
        start = end - TD(days=7 * (weeks or 4) - 1)
    days = (end - start).days + 1
    if days < 7:
        die("the window must cover at least 7 days")
    if days > 7 * MAX_WEEKS:
        die(f"the window is limited to {MAX_WEEKS} weeks")
    if end > today:
        print(f"warning: end date {end} is in the future; the window will be incomplete", file=sys.stderr)
    return start, end, days


def make_periods(start, end, days, compare):
    full = days % 7 == 0
    wk = days // 7
    periods = [dict(key="current", name="This block", short="this block", start=start, end=end)]
    toks = [t.strip() for t in (compare or "previous,last_year").split(",") if t.strip()]
    if toks == ["none"]:
        toks = []
    seen = set()
    for t in toks:
        if t in seen:
            continue
        seen.add(t)
        if t == "previous":
            s, e = start - TD(days=days), start - TD(days=1)
            name, short = (f"Previous {wk} weeks", f"prev {wk} wks") if full else (f"Previous {days} days", f"prev {days} d")
        elif t == "last_year":
            s, e = start - TD(days=364), end - TD(days=364)
            name, short = ("Same weeks last year" if full else "Same period last year"), "last year"
        elif re.fullmatch(r"\d+[wd]", t):
            n = int(t[:-1]) * (7 if t[-1] == "w" else 1)
            if n < days:
                die(f"--compare {t} would overlap the current window ({days} days); use at least {days} days back")
            s, e = start - TD(days=n), end - TD(days=n)
            name = f"{t[:-1]} {'weeks' if t[-1] == 'w' else 'days'} earlier"
            short = f"{t[:-1]} {'wks' if t[-1] == 'w' else 'd'} earlier"
        else:
            s = parse_date(t)
            e = s + TD(days=days - 1)
            if e >= start:
                die(f"--compare {t} overlaps or follows the current window")
            name, short = f"Window from {s.day} {s:%b %Y}", f"window from {s.isoformat()}"
        if any((q["start"], q["end"]) == (s, e) for q in periods):
            print(f"warning: --compare {t} is identical to an earlier window for a {days}-day range; skipped", file=sys.stderr)
            continue
        periods.append(dict(key=t, name=name, short=short, start=s, end=e))
    if len(periods) > 3:
        die("--compare accepts at most two comparison windows")
    return periods


def plan(args, today=None):
    today = today or dt.date.today()
    start, end, days = resolve_current(args.weeks, parse_date(args.start) if args.start else None,
                                       parse_date(args.end) if args.end else None, today)
    return make_periods(start, end, days, args.compare), days


def normalize(raw, cfg, start, end):
    acts = raw["activities"] if isinstance(raw, dict) else raw
    run_t, ride_t = set(cfg["run_types"]), set(cfg["ride_types"])
    seen, out = set(), []
    for a in acts:
        t = a.get("sport_type") or a.get("type")
        kind = "run" if t in run_t else "ride" if t in ride_t else None
        if not kind:
            continue
        aid = a.get("id")
        if aid is not None and aid in seen:
            continue
        seen.add(aid)
        s = a.get("summary", a)
        d = a["start_local"][:10]
        if not (start <= dt.date.fromisoformat(d) <= end):
            continue
        dist = (s.get("distance") or 0) / 1000
        if dist <= 0:
            continue
        out.append(dict(id=None if aid is None else str(aid), kind=kind, date=d, hm=a["start_local"][11:16], dist=dist,
                        time=s.get("moving_time") or 0, elapsed=s.get("elapsed_time") or s.get("moving_time") or 0, elev=s.get("elevation_gain") or 0,
                        re=s.get("relative_effort") or 0, cad=s.get("avg_cadence") or 0))
    out.sort(key=lambda a: (a["date"], a["hm"]))
    return out


def ratio(w):
    """ACWR: last week vs the mean of the 3 weeks before it (needs >= 4 weeks)."""
    if len(w) < 4:
        return None
    base = sum(w[-4:-1]) / 3
    return round(w[-1] / base, 2) if base else None


def metrics(acts, start, cfg, days, sessions=False):
    e0, e1, e2 = cfg["mix_edges"]
    W = math.ceil(days / 7)
    wk_km, wk_elev = [0.0] * W, [0.0] * W
    wk_re, wk_n, wk_t = [0] * W, [0] * W, [0] * W
    perday_re = {}
    wk_days = [set() for _ in range(W)]
    perday, km, time, elev, re = {}, 0.0, 0, 0, 0
    for a in acts:
        w = min(max((dt.date.fromisoformat(a["date"]) - start).days // 7, 0), W - 1)
        wk_km[w] += a["dist"]; wk_elev[w] += a["elev"]; wk_re[w] += a["re"]; wk_n[w] += 1
        wk_days[w].add(a["date"]); wk_t[w] += a["time"]
        perday_re[a["date"]] = perday_re.get(a["date"], 0) + a["re"]
        perday[a["date"]] = perday.get(a["date"], 0) + a["dist"]
        km += a["dist"]; time += a["time"]; elev += a["elev"]; re += a["re"]
    n, hrs = len(acts), time / 3600
    cum, c = [], 0.0
    for i in range(days):
        c += perday.get((start + dt.timedelta(days=i)).isoformat(), 0)
        cum.append(round(c, 1))
    res = [a["re"] for a in acts]
    cads = [a["cad"] for a in acts if a["cad"] > 0]
    m = dict(
        n=n, km=round(km, 1), hrs=round(hrs, 2), elev=round(elev), re=round(re),
        days=len({a["date"] for a in acts}), weeks_active=sum(1 for x in wk_n if x),
        wk_km=[round(x, 1) for x in wk_km], wk_elev=[round(x) for x in wk_elev],
        wk_re=wk_re, wk_n=wk_n, wk_hrs=[round(x / 3600, 2) for x in wk_t],
        day_re=[perday_re.get((start + TD(days=i)).isoformat(), 0) for i in range(days)], wk_days=[len(s) for s in wk_days], cum=cum,
        kmh=round(km / hrs, 1) if hrs else None, pace=round(time / km) if km else None,
        m_per_km=round(elev / km, 1) if km else None, avg_km=round(km / n, 1) if n else None,
        longest=round(max((a["dist"] for a in acts), default=0), 1), peak=round(max(wk_km), 1),
        avg_re=round(re / n, 1) if n else None, re_hr=round(re / hrs) if hrs else None,
        hard=sum(1 for x in res if x >= cfg["hard_effort"]),
        easy_pct=round(100 * sum(1 for x in res if x < e0) / n) if n else None,
        mix=[sum(1 for x in res if x < e0), sum(1 for x in res if e0 <= x < e1),
             sum(1 for x in res if e1 <= x < e2), sum(1 for x in res if x >= e2)],
        cad=round(sum(cads) / len(cads), 1) if cads else None,
        acwr_re=None if days % 7 else ratio(wk_re), acwr_km=None if days % 7 else ratio(wk_km))
    if sessions:
        m["sessions"] = [dict(date=a["date"], hm=a["hm"], km=round(a["dist"], 2), time=a["time"],
                              pace=round(a["time"] / a["dist"]), elev=a["elev"], re=a["re"]) for a in acts]
    return m


def loop_stats(rides, loop):
    sel = [a for a in rides if loop["dist_km"][0] <= a["dist"] <= loop["dist_km"][1]
           and loop["elev_m"][0] <= a["elev"] <= loop["elev_m"][1]]
    return (round(sum(a["time"] for a in sel) / len(sel)) if sel else None), len(sel)


CATS = ["low", "high", "ana"]


def zone_of(bpm, mins):
    z = 0
    for i, m in enumerate(mins):
        if bpm >= m:
            z = i
    return z


def load_metrics(acts, start, hr, mins, cfg, days):
    """Training load split by HR-zone intensity.
    Each HR sample stands for elapsed/len(samples) seconds; load points = minutes x zone weight.
    Zones map to categories via config (default Z1-2 low aerobic, Z3-4 high aerobic, Z5 anaerobic)."""
    lc = cfg.get("load", {})
    weights = lc.get("weights", [1, 2, 3, 4, 5])
    cats = lc.get("categories", {"low": [1, 2], "high": [3, 4], "ana": [5]})
    cat_of = {z - 1: c for c, zs in cats.items() for z in zs}
    zmin = [0.0] * 5
    pts = {c: 0.0 for c in CATS}
    mins_c = {c: 0.0 for c in CATS}
    W = math.ceil(days / 7)
    wk = {c: [0.0] * W for c in CATS}
    sport = {k: {c: 0.0 for c in CATS} for k in ("run", "ride")}
    cov = 0
    for a in acts:
        samples = hr.get(a["id"]) if a["id"] else None
        if not samples:
            continue
        cov += 1
        dur = (a["elapsed"] or a["time"]) / len(samples) / 60
        w = min(max((dt.date.fromisoformat(a["date"]) - start).days // 7, 0), W - 1)
        for bpm in samples:
            z = zone_of(bpm, mins)
            c = cat_of[z]
            p = dur * weights[z]
            zmin[z] += dur; pts[c] += p; mins_c[c] += dur; wk[c][w] += p; sport[a["kind"]][c] += p
    if not cov:
        return None
    tot = sum(pts.values()) or 1
    return dict(
        cov=cov, n=len(acts), zone_min=[round(x, 1) for x in zmin], total=round(tot),
        cat={c: dict(pts=round(pts[c]), min=round(mins_c[c]), share=round(100 * pts[c] / tot)) for c in CATS},
        wk={c: [round(x) for x in wk[c]] for c in CATS},
        sport={k: {c: round(v[c]) for c in CATS} for k, v in sport.items()})


def load_zones(path, keys):
    raw = json.load(open(path))
    if isinstance(raw, dict) and "zones" in raw:
        raw = raw["zones"]
    if isinstance(raw, list):
        return {k: raw for k in keys}
    return {k: raw.get(k) or raw["current"] for k in keys}


def load_window(p, days, cfg, load_weeks=None):
    """HR-based load is limited to the last K weeks of each window (K = --load-weeks or config load.max_weeks)
    so long windows do not need hundreds of heart-rate fetches. Returns (start, days, restricted)."""
    W = math.ceil(days / 7)
    k = load_weeks or cfg.get("load", {}).get("max_weeks")
    if k and k < W:
        return p["end"] - TD(days=7 * k - 1), 7 * k, True
    return p["start"], days, False


def find_flags(data):
    out, W = [], data["weeks"]
    for sport in ("all", "run", "ride"):
        for k in range(1, len(data["periods"])):
            m, nm = data[sport][k], data["periods"][k]["name"]
            if m["n"] and m["n"] < 5:
                out.append(f"{nm} / {sport}: only {m['n']} session(s) – small sample, avoid strong conclusions.")
            if sport != "run" and m["km"] and any(x == 0 for x in m["wk_km"]):
                out.append(f"{nm} / {sport}: at least one week has no activity – baseline is uneven.")
            if sport != "run" and W >= 4 and m["km"] and m["peak"] > 0.5 * m["km"]:
                out.append(f"{nm} / {sport}: one week is {round(100 * m['peak'] / m['km'])}% of the block – baseline is lumpy.")
            if not m["n"]:
                out.append(f"{nm} / {sport}: no activity found in this window.")
    return out


def pool(raw, periods, cfg):
    keyed = isinstance(raw, dict) and any(p["key"] in raw for p in periods)
    return {p["key"]: normalize(raw.get(p["key"], []) if keyed else raw, cfg, p["start"], p["end"]) for p in periods}


def build(raw, cfg, periods, days, hr=None, zones=None, load_weeks=None):
    W = math.ceil(days / 7)
    acts_all = pool(raw, periods, cfg)
    part = days % 7
    data = {"generated": dt.date.today().isoformat(), "title": cfg.get("title", "Training Dashboard"),
            "config": {"hard": cfg["hard_effort"], "edges": cfg["mix_edges"]},
            "weeks": W, "days": days, "partial_days": part,
            "week_labels": [f"Wk {i + 1}" for i in range(W - 1)] + [f"Wk {W}" + ("*" if part else "")],
            "periods": [{"key": p["key"], "name": p["name"], "short": p["short"], "label": label(p["start"], p["end"]),
                         "start": p["start"].isoformat(), "end": p["end"].isoformat()} for p in periods],
            "all": [], "run": [], "ride": [], "loops": []}
    for p in periods:
        acts = acts_all[p["key"]]
        data["all"].append(metrics(acts, p["start"], cfg, days))
        data["run"].append(metrics([a for a in acts if a["kind"] == "run"], p["start"], cfg, days, sessions=True))
        data["ride"].append(metrics([a for a in acts if a["kind"] == "ride"], p["start"], cfg, days, sessions=True))
    for loop in cfg.get("loops", []):
        stats = [loop_stats([a for a in acts_all[p["key"]] if a["kind"] == "ride"], loop) for p in periods]
        data["loops"].append({"name": loop["name"], "dist_km": loop["dist_km"], "elev_m": loop["elev_m"],
                              "t": [x[0] for x in stats], "n": [x[1] for x in stats]})
    if hr and zones:
        loads = []
        for p in periods:
            ls, ld, restricted = load_window(p, days, cfg, load_weeks)
            sub = [a for a in acts_all[p["key"]] if a["date"] >= ls.isoformat()]
            loads.append(load_metrics(sub, ls, hr, zones[p["key"]], cfg, ld))
        if loads[0]:
            lc = cfg.get("load", {})
            nw = ld // 7 if restricted else W
            data["load"] = {"periods": loads, "weeks": nw, "restricted": restricted,
                            "labels": [f"Wk {i + 1}" for i in range(nw)] if restricted else data["week_labels"], "zones": [zones[p["key"]] for p in periods],
                            "weights": lc.get("weights", [1, 2, 3, 4, 5]),
                            "categories": lc.get("categories", {"low": [1, 2], "high": [3, 4], "ana": [5]})}
    a = data["all"]
    data["acwr"] = {"re": a[0]["acwr_re"], "km": a[0]["acwr_km"],
                    "base": [{"short": data["periods"][k]["short"], "re": a[k]["acwr_re"], "km": a[k]["acwr_km"]}
                             for k in range(1, len(a))]}
    data["flags"] = find_flags(data)
    for p, m in zip(periods, data.get("load", {}).get("periods", [])):
        if m and m["cov"] < m["n"]:
            data["flags"].append(f"Training load ({p['name']}): HR data for {m['cov']} of {m['n']} sessions only.")
    if part:
        data["flags"].append(f"The last week is partial ({part} days): weekly bars marked * and ACWR are not comparable.")
    if W < 4:
        data["flags"].append("ACWR needs at least 4 full weeks and is not shown.")
    return data


def summary(d):
    print("Windows: " + " | ".join(f"{p['name']}: {p['label']}" for p in d["periods"]) + f"  ({d['days']} days, {d['weeks']} weeks)")
    rows = [("km", "distance km"), ("n", "sessions"), ("days", "active days"), ("hrs", "moving h"), ("elev", "elevation m"),
            ("re", "rel. effort"), ("re_hr", "effort/h"), ("avg_re", "avg effort/session"), ("hard", "hard sessions"),
            ("kmh", "avg km/h"), ("pace", "avg pace s/km"), ("longest", "longest km"), ("peak", "peak week km"),
            ("easy_pct", "easy % (<edge0)"), ("m_per_km", "m climb/km"), ("cad", "cadence")]
    for sport in ("all", "run", "ride"):
        print(f"\n[{sport}]  " + " | ".join(p["short"] for p in d["periods"]))
        for k, name in rows:
            vals = [m.get(k) for m in d[sport]]
            if all(v is None for v in vals):
                continue
            print(f"  {name:22s} " + " | ".join("-" if v is None else str(v) for v in vals))
        print("  weekly km             " + "  ||  ".join(str(m["wk_km"]) for m in d[sport]))
    for l in d["loops"]:
        print(f"\nLoop {l['name']}: avg time s {l['t']} (n {l['n']})")
    for i, m in enumerate((d.get("load") or {}).get("periods", [])):
        if m:
            print(f"\nLoad [{d['periods'][i]['name']}] total {m['total']} pts, HR coverage {m['cov']}/{m['n']}: "
                  + ", ".join(f"{c} {m['cat'][c]['pts']} pts ({m['cat'][c]['share']}%, {m['cat'][c]['min']} min)" for c in CATS)
                  + f" | run {m['sport']['run']} ride {m['sport']['ride']} | weekly {m['wk']}")
    print(f"\nACWR: {d['acwr']}")
    for f in d["flags"]:
        print("FLAG:", f)


def main():
    ap = argparse.ArgumentParser(description="Strava training dashboard metrics (see module docstring for window rules)")
    ap.add_argument("--activities")
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--weeks", type=int, help="window length in weeks (default 4)")
    ap.add_argument("--start", help="first day of a custom window, YYYY-MM-DD")
    ap.add_argument("--end", help="last day of the window, YYYY-MM-DD (default: today)")
    ap.add_argument("--compare", help="comma list of comparison windows: previous, last_year, Nw, Nd, YYYY-MM-DD, none "
                                      "(default previous,last_year; max 2)")
    ap.add_argument("--load-weeks", type=int, help="limit the training-load card to the last K weeks of each window "
                                                   "(default: config load.max_weeks, 8)")
    ap.add_argument("--hr", help="JSON {activity_id: [bpm samples]} for the training-load card (optional)")
    ap.add_argument("--zones", help="JSON with HR zone lower bounds [z1..z5] (required with --hr)")
    ap.add_argument("--out")
    ap.add_argument("--windows", action="store_true", help="print the date ranges to fetch and exit")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    if args.weeks is not None and args.weeks < 1:
        die("--weeks must be at least 1")
    periods, days = plan(args)
    cfg = json.load(open(args.config))
    if args.windows:
        print(json.dumps({"weeks": math.ceil(days / 7), "days": days, "windows": [
            {"key": p["key"], "name": p["name"], "start": p["start"].isoformat(), "end": p["end"].isoformat(),
             "range_start": f"{p['start']}T00:00:00", "range_end": f"{p['end']}T23:59:59",
             "load_start": load_window(p, days, cfg, args.load_weeks)[0].isoformat()} for p in periods]}, indent=2))
        return
    if not args.activities:
        die("--activities is required (or use --windows)")
    hr = {k: v for k, v in json.load(open(args.hr)).items() if not k.startswith("_")} if args.hr else None
    zones = load_zones(args.zones, [p["key"] for p in periods]) if args.zones else None
    data = build(json.load(open(args.activities)), cfg, periods, days, hr, zones, args.load_weeks)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        json.dump(data, open(args.out, "w"), ensure_ascii=False)
    if args.summary or not args.out:
        summary(data)


if __name__ == "__main__":
    main()
