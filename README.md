# strava-training-dashboard

A Claude **skill** that turns your Strava running and cycling data into a dark, self-contained HTML dashboard:
this 4-week block vs the previous 4 weeks vs the same weeks last year, split into **Global**, **Running** and **Cycling**
(KPI tiles with deltas and sparklines, a daily training **calendar heatmap**, a **training-load card** with donut (anaerobic / high aerobic / low aerobic from HR zones), head-to-head tables, cumulative/weekly charts, pace trend, effort mix, recent sessions and a coach's read).

```
SKILL.md                      workflow Claude follows
config.json                   sport types, hard-effort threshold, effort buckets, repeated "loops"
scripts/compute_metrics.py    activities -> metrics.json (and the date windows to fetch)
scripts/render_dashboard.py   metrics.json (+ coach.json) -> dashboard.html
scripts/fetch_strava.py       Strava REST API -> the input files above (no Claude; used by the workflow)
.github/workflows/            tests.yml (every push) and dashboard.yml (scheduled / manual build)
assets/dashboard_template.html  data-driven template (no dependencies)
references/coach_guidelines.md  how the coach's read is written
examples/                     sample input + coach text
tests/test_pipeline.py        pipeline and window tests
tests/test_fetch.py           fetcher tests against a fake Strava API
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

## Run it in GitHub Actions (no Claude)
`scripts/fetch_strava.py` talks to Strava's REST API directly, so the whole pipeline (fetch → compute → render) runs in CI with the standard library only. The coach's read is Claude-written, so it is **not** produced in CI: the page renders without those cards.

1. **Strava API app:** create one at <https://www.strava.com/settings/api> (callback domain `localhost`).
2. **One-time authorisation** (scope `activity:read_all` is needed for private activities and heart-rate data):
   open `https://www.strava.com/oauth/authorize?client_id=YOUR_ID&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=read,activity:read_all`, approve, and copy the `code` from the address bar of the page that fails to load; then
   `curl -X POST https://www.strava.com/oauth/token -d client_id=YOUR_ID -d client_secret=YOUR_SECRET -d code=THE_CODE -d grant_type=authorization_code` and keep the `refresh_token` from the answer.
3. **Repo secrets** (Settings → Secrets and variables → Actions): `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN`. Optional `GH_PAT` (a token that can write secrets) lets the job store a rotated refresh token.
4. **Run it:** Actions → *strava-dashboard* → *Run workflow* (inputs: weeks, start, end, compare, load_weeks), or wait for the Monday schedule. Download `dashboard.html` from the run's artifacts; the training summary is also on the run page. The artifact is private to people with access to the repo. A public GitHub Pages site would expose your training data, so it is not set up.
5. **Try it locally first:** `STRAVA_CLIENT_ID=… STRAVA_CLIENT_SECRET=… STRAVA_REFRESH_TOKEN=… python scripts/fetch_strava.py --weeks 4 --out work`, then the compute and render commands above.

Differences from the Claude-run skill: Strava's REST field `suffer_score` (Relative Effort, Strava subscribers only) feeds the effort KPIs, and `--detail-effort` fetches it per activity if the list omits it; heart-rate zones are the current ones (not as-of a date); the script waits when it nears Strava's rate limits (`--max-wait`).
`.github/workflows/tests.yml` runs the tests on every push. The fetch tests use a fake Strava API: they prove the mapping and file formats, not Strava's live responses, so check the first real run.

## Notes
- Intensity KPIs use Strava Relative Effort. The training-load card uses your HR zones: points = minutes in zone × weight; Z1–2 = low aerobic, Z3–4 = high aerobic, Z5 = anaerobic (configurable). It needs one `get_activity_streams` call per run/ride, so by default only the current block is loaded (`load.periods` in `config.json`).
- Distances are metric.
- Edit `config.json` `loops` to the repeated routes you want compared (or set `[]`).
- `examples/` contains real activity data: keep the repo **private** or replace the files.
