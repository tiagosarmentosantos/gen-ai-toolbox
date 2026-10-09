# strava-training-dashboard

A Claude **skill** that turns your Strava running and cycling data into a dark, self-contained HTML dashboard:
this 4-week block vs the previous 4 weeks vs the same weeks last year, split into **Global**, **Running** and **Cycling**
(KPI tiles with deltas and sparklines, a daily training **calendar heatmap**, a **training-load card** with donut (anaerobic / high aerobic / low aerobic from HR zones), head-to-head tables, cumulative/weekly charts, pace trend, effort mix, recent sessions and a coach's read).

```
SKILL.md                      workflow Claude follows
config.json                   sport types, hard-effort threshold, effort buckets, repeated "loops"
scripts/compute_metrics.py    activities -> metrics.json (and the date windows to fetch)
scripts/render_dashboard.py   metrics.json (+ coach.json) -> dashboard.html
assets/dashboard_template.html  data-driven template (no dependencies)
references/coach_guidelines.md  how the coach's read is written
examples/                     sample input + coach text
tests/test_pipeline.py        smoke test
```

## Interactive page
- **Legend pills** hide or show a period in every chart; the **View** switch (All / Run / Ride) re-draws the global charts and the calendar for that sport.
- **Click a week** (a bar, or a calendar cell) to highlight it everywhere; a chip shows that week's totals. Click again or "clear" to reset.
- **Calendar:** pick the period and metric (distance or effort); windows up to 8 weeks show a weekday grid with the km in each cell, longer ones a GitHub-style strip.
- **Motion:** bars grow, lines draw in and the donut sweeps when a chart scrolls into view (disabled with `prefers-reduced-motion`). All charts have hover tooltips and wide ones scroll sideways.

## Options
`compute_metrics.py` (and so the skill) takes:

| Option | Meaning |
|---|---|
| `--weeks N` | window of N weeks (1–52, default 4) |
| `--end YYYY-MM-DD` | last day of the window (default today) |
| `--start YYYY-MM-DD` | first day of a custom window; with `--end`, or `--weeks`, or alone (ends today) |
| `--compare LIST` | up to 2 comparison windows: `previous`, `last_year` (364 days back), `Nw` / `Nd` (e.g. `104w`), a start date, or `none`. Default `previous,last_year` |

| `--load-weeks K` | training-load card covers only the last K weeks of each window (default 8, `load.max_weeks`), so long windows need few heart-rate fetches |

Examples: `--weeks 8`, `--start 2026-09-01 --end 2026-09-30 --compare last_year`, `--weeks 12 --compare previous,104w`.
Charts that would get crowded (weekly bars over ~11 weeks, many runs, long load windows) become horizontally scrollable inside their card, marked "← scroll →", so a 52-week window keeps readable bars with value labels; all charts show hover tooltips. For a 52-week window `last_year` equals `previous`, so the duplicate is skipped. A window that is not a multiple of 7 days ends with a partial week (`*`), and ACWR (needs 4+ full weeks) is hidden when it does not apply.

## Use it
Needs Claude with the **Strava connector** enabled.

- **Claude.ai / Cowork:** Settings → Capabilities → Skills → upload `strava-training-dashboard.skill` (or zip this folder).
- **Claude Code:** copy the folder to `~/.claude/skills/strava-training-dashboard/`.

Then ask: *"Run my Strava dashboard"*, or be specific: *"last 8 weeks vs last year"*, *"September compared with the previous month"*, *"4 weeks ending 12 Oct, no comparison"*.

## Run the pipeline offline
```bash
python scripts/compute_metrics.py --windows --end 2026-10-03 [--weeks N --compare ...]   # ranges to fetch
python scripts/compute_metrics.py --activities examples/activities_example.json --end 2026-10-03 --out work/metrics.json --summary
# add the training-load card (HR zones):
python scripts/compute_metrics.py --activities examples/activities_example.json --end 2026-10-03 --hr examples/hr_streams_example.json --zones examples/zones_example.json --out work/metrics.json
python scripts/render_dashboard.py --metrics work/metrics.json --coach examples/coach_example.json --out out/dashboard.html
python tests/test_pipeline.py
```
Python 3.9+, standard library only.

## Notes
- Intensity KPIs use Strava Relative Effort. The training-load card uses your HR zones: points = minutes in zone × weight; Z1–2 = low aerobic, Z3–4 = high aerobic, Z5 = anaerobic (configurable). It needs one `get_activity_streams` call per run/ride, so by default only the current block is loaded (`load.periods` in `config.json`).
- Distances are metric.
- Edit `config.json` `loops` to the repeated routes you want compared (or set `[]`).
- `examples/` contains real activity data: keep the repo **private** or replace the files.
