---
name: strava-training-dashboard
description: Build a dark-themed, self-contained HTML training dashboard from the user's Strava running and cycling data, comparing the last 4 weeks with the previous 4 weeks and the same weeks last year, split into Global / Running / Cycling views with KPI tiles, a training-load card (anaerobic / high aerobic / low aerobic from HR zones), charts and a coach-style analysis. Use this whenever the user asks for a Strava dashboard, training report or review, "how is my training going", a 4-week or monthly summary, volume / intensity / consistency / training-load analysis, a year-over-year training comparison, or to re-run or refresh their dashboard, even if they never say "dashboard".
---

# Strava training dashboard

Produces one `dashboard.html` (no external dependencies; animated, with hover tooltips, legend toggles, a Run/Ride switch, week highlighting, a daily calendar heatmap, a load donut and KPI sparklines; see README "Interactive page") from three 28-day windows of Strava activity data:
**this block** (default: the 28 days ending today), the **previous 4 weeks**, and the **same weeks last year** (shifted 364 days so weekdays line up).

All numbers are computed by `scripts/compute_metrics.py`; the page is rendered from `assets/dashboard_template.html`.
Claude's own job is to fetch the data, write the coach's read, and deliver the file. Never compute totals by hand.

## Workflow

1. **Pick the window and comparisons.** Map the user's request to options (default: 4 weeks ending today, compared with the previous 4 weeks and the same weeks last year):

   | User says | Options |
   |---|---|
   | "last 8 weeks" | `--weeks 8` |
   | "4 weeks ending 12 Oct" | `--end 2026-10-12` |
   | "September", "1 Sep to 15 Oct" | `--start 2026-09-01 --end 2026-09-30` |
   | "vs last year only" | `--compare last_year` |
   | "vs 2 years ago" | `--compare 104w` (also `Nw`, `Nd`, or a start date `YYYY-MM-DD`) |
   | "no comparison" | `--compare none` |

   Rules: `--weeks` 1–52 (at least 7 days); give at most two of `--start`, `--end`, `--weeks`; `--compare` takes up to two windows and none may overlap the current one. A window that is not a multiple of 7 days gets a partial last week (marked `*`), and ACWR needs at least 4 full weeks, so it is hidden otherwise.
   Print the ranges: `python scripts/compute_metrics.py --windows [options]` (JSON with a `key` and `range_start` / `range_end` per window).
2. **Fetch from Strava.** Use the Strava connector's `list_activities` for each window (or one call over a range that covers several windows), with
   `range_start` / `range_end` from step 1, `ordering=StartDateLocalAsc`, `first=100`; keep paging while `has_next_page` is true.
   If the Strava tools are not loaded, search for them first (e.g. tool_search "Strava list activities"). If the connector is not connected, tell the user and stop.
   Save to `work/activities.json` either as `{"<window key>": [...], ...}` (keys from step 1) or as one pooled list containing every window; the script splits it by date. Keep all fields, including `id` and `elapsed_time`.
3. **Training load (HR zones, optional but on by default).** This feeds the "Training load by intensity" card (Anaerobic / High aerobic / Low aerobic).
   - Call `get_athlete_zones` (use `as_of_date` = the end date) and save the lower bound of each of the 5 `heart_rate_zones` as `work/zones.json`: `{"zones": [0, 119, 148, 163, 178]}`.
   - For every **run and ride** in the windows listed in `config.json → load.periods` (default `["current"]`; use the window keys from step 1), call `get_activity_streams` with `streams=["heart_rate"]` and `resolution=50` (heart rate only, to keep results small). Save `work/hr_streams.json` as `{"<activity id>": [bpm, ...], ...}`. Leave out activities that return no heart rate.
   - It costs about one call per activity, so the load card only covers the **last `load.max_weeks` weeks (default 8)** of each window (override with `--load-weeks K`); `--windows` prints a `load_start` date per window: fetch heart rate only for runs/rides on or after it.
   - It costs about one call per activity. Add `"previous"` / `"last_year"` to `load.periods` only when the user wants the load comparison chips (that is 60+ calls), and tell them so first.
   - If the user has no HR data, or declines, skip this step: the card stays hidden.
4. **Compute.** `python scripts/compute_metrics.py --activities work/activities.json [same window options as step 1] [--hr work/hr_streams.json --zones work/zones.json] --out work/metrics.json --summary`
   Then **tell the user the date range and total distance first** (this block: total km, run km, ride km, elevation) before anything else.
5. **Write the coach's read** to `work/coach.json`: `{"run": [...], "ride": [...], "overall": [...]}`, each item one HTML bullet such as `"<b>Pace:</b> ..."`.
   Read `references/coach_guidelines.md` first; base every statement on the `--summary` output and its `FLAG:` lines.
6. **Render.** `python scripts/render_dashboard.py --metrics work/metrics.json --coach work/coach.json --out /mnt/user-data/outputs/dashboard.html`
   (use any output path outside claude.ai).
7. **Deliver.** Present the HTML file. If the user asked for a code block, or no file tool exists, paste the full HTML in one code block instead.
   Add a short bulleted coach summary in chat (volume, intensity distribution, training load, consistency, risks, next steps).

## Configuration

`config.json` controls the sport types that count as runs/rides, the "hard session" effort threshold, the effort-mix bucket edges,
the training-load settings (`load.periods`, zone `weights`, which zones count as low aerobic / high aerobic / anaerobic), and optional repeated **loops** (distance and elevation bands) whose average time is compared across periods. Edit the loops to match the user's regular routes, or set `"loops": []`.

## Things to know

- Intensity KPIs are Strava **Relative Effort**. The training-load card is the only HR-zone based view: points = minutes in zone × zone weight (default Z1-2 low aerobic, Z3-4 high aerobic, Z5 anaerobic), from ~50 HR samples per session, so brief spikes can be missed. Say so.
- Walks, HIIT, kayaking and other sports are excluded; mention it.
- Distances are metric. Weeks are 7-day blocks from each window's start (not calendar weeks). Last year is shifted 364 days so weekdays line up.
- Re-running with an unchanged window and the same data must give the same numbers; if a number surprises you, re-check `--summary`, not memory.
