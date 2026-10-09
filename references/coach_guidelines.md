# Writing the coach's read

Three lists in `coach.json`: `run`, `ride`, `overall` (4–6 bullets for run/ride, 2–4 for overall). Each bullet is an HTML string starting with a bold lead word, e.g. `"<b>Volume:</b> ..."`. No other markup, no emoji.

## Content, in this order
1. **Volume** – distance, sessions, active days, vs previous block and vs last year (use the Δ figures from `--summary`).
2. **Intensity** – effort per hour, hard-session count, effort mix, pace/speed trends. Name which sport carries the hard work.
3. **Consistency** – weeks with activity, active days, longest gap.
4. **Training load** (only if the summary has a `Load` line) – share of low aerobic / high aerobic / anaerobic points, which sport supplies each (`run` / `ride` split), the weekly trend, and the HR coverage. Do not quote a universal 'ideal' split; describe what the balance implies and what a small change would do. Near-zero anaerobic load can reflect real training or the coarse sampling: say which is plausible.
5. **Risk** – ACWR (≈0.8–1.3 is the usual comfortable zone), week-over-week jumps, anything the FLAG lines raise.
6. **Next steps** – 2–4 concrete, small actions (e.g. one easy week, one long easy ride, one structured session).

## Rules
- Use only numbers from the summary. Round the same way the dashboard does.
- Treat FLAG lines as caveats: if the previous block is lumpy or has an empty week, say it is a weak baseline and lean on last year.
- Do not state causes as fact ("slower because of fatigue"); offer them as possible explanations.
- Intensity is Relative Effort based; say "effort" not "heart rate". Do not give medical advice.
- Highlight outliers (a single very fast run) and say not to read them as a new baseline.
- Keep bullets to 1–3 sentences. Make the overall bullets about the trade-off between sports and the plan for the next 4 weeks.
