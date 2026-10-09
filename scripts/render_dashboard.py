#!/usr/bin/env python3
"""Inject metrics (and optional coach text) into the HTML template -> one self-contained file.

Usage: render_dashboard.py --metrics work/metrics.json [--coach work/coach.json] --out out/dashboard.html
coach.json: {"run": ["<b>Lead:</b> text", ...], "ride": [...], "overall": [...]}
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def dump(obj):
    # keep the JSON safe inside a <script> block
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--coach")
    ap.add_argument("--template", default=str(ROOT / "assets" / "dashboard_template.html"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    tpl = Path(a.template).read_text(encoding="utf-8")
    for token in ("/*__DATA__*/null", "/*__COACH__*/null"):
        if token not in tpl:
            raise SystemExit(f"template is missing placeholder {token}")
    metrics = json.load(open(a.metrics, encoding="utf-8"))
    coach = json.load(open(a.coach, encoding="utf-8")) if a.coach else {}
    html = tpl.replace("/*__DATA__*/null", dump(metrics), 1).replace("/*__COACH__*/null", dump(coach), 1)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(html, encoding="utf-8")
    print(f"wrote {a.out} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
