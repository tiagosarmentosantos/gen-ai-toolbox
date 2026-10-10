#!/usr/bin/env python3
"""Generate index pages for the docs site with links to all reports."""
from datetime import datetime
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


def generate_main_index():
    """Generate main index.html with latest dashboard and recent reports."""
    
    # Get list of recent reports
    reports_dir = DOCS_DIR / "reports"
    recent_reports = []
    
    if reports_dir.exists():
        for report_file in sorted(reports_dir.glob("report-*.html"), reverse=True)[:10]:
            date_str = report_file.stem.replace("report-", "")
            try:
                report_date = datetime.fromisoformat(date_str)
                recent_reports.append({
                    "date": date_str,
                    "formatted": report_date.strftime("%A, %B %d, %Y"),
                    "file": f"reports/{report_file.name}"
                })
            except ValueError:
                continue
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Strava Training Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #0f0f0f;
            color: #e0e0e0;
        }}
        .header {{
            text-align: center;
            padding: 40px 0;
            border-bottom: 2px solid #4a9eff;
            margin-bottom: 40px;
        }}
        .header h1 {{
            margin: 0;
            color: #4a9eff;
            font-size: 2.5em;
        }}
        .header p {{
            margin: 10px 0 0 0;
            color: #999;
            font-size: 1.1em;
        }}
        .content {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 40px;
        }}
        @media (max-width: 768px) {{
            .content {{
                grid-template-columns: 1fr;
            }}
        }}
        .card {{
            background: #1a1a1a;
            border: 2px solid #2a2a2a;
            border-radius: 8px;
            padding: 25px;
            transition: border-color 0.3s;
        }}
        .card:hover {{
            border-color: #4a9eff;
        }}
        .card h2 {{
            margin-top: 0;
            color: #4a9eff;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .card p {{
            color: #bbb;
            line-height: 1.6;
        }}
        .card ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .button {{
            display: inline-block;
            padding: 12px 24px;
            background: #4a9eff;
            color: #000;
            text-decoration: none;
            border-radius: 4px;
            font-weight: bold;
            margin-top: 15px;
            transition: background 0.3s;
        }}
        .button:hover {{
            background: #5aafff;
        }}
        .reports {{
            background: #1a1a1a;
            border: 2px solid #2a2a2a;
            border-radius: 8px;
            padding: 25px;
        }}
        .reports h2 {{
            margin-top: 0;
            color: #4a9eff;
        }}
        .report-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .report-list li {{
            padding: 12px;
            border-bottom: 1px solid #2a2a2a;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .report-list li:last-child {{
            border-bottom: none;
        }}
        .report-list a {{
            color: #4a9eff;
            text-decoration: none;
        }}
        .report-list a:hover {{
            text-decoration: underline;
        }}
        .badge {{
            background: #4a9eff;
            color: #000;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 0.85em;
            font-weight: bold;
        }}
        .footer {{
            text-align: center;
            padding-top: 40px;
            border-top: 1px solid #333;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏃 Strava Training Dashboard</h1>
        <p>AI-Powered Training Analysis with Real Strava Data</p>
    </div>
    
    <div class="content">
        <div class="card">
            <h2>📊 Latest Dashboard</h2>
            <p>View your complete training dashboard with interactive charts, metrics, and training load analysis.</p>
            <p><strong>Features:</strong></p>
            <ul>
                <li>Comparative analysis (vs previous & last year)</li>
                <li>Weekly breakdown with KPIs</li>
                <li>Training load by intensity zones</li>
                <li>Interactive charts with hover details</li>
            </ul>
            <a href="dashboard.html" class="button">View Full Dashboard →</a>
        </div>
        
        <div class="card">
            <h2>💡 Coach Analysis</h2>
            <p>Expert coaching insights based on your training data, providing personalized recommendations and trend analysis.</p>
            <p><strong>Includes:</strong></p>
            <ul>
                <li>Performance trends</li>
                <li>Intensity distribution</li>
                <li>Volume assessment</li>
                <li>Risk indicators</li>
            </ul>
            <p style="color: #999; font-size: 0.9em;">↓ See detailed analysis in the dashboard</p>
        </div>
    </div>
    
    <div class="reports">
        <h2>📋 Recent Reports</h2>
        {"<p style='color: #999;'>No reports yet. Check back after the first scheduled run (Sundays at 9 AM UTC).</p>" if not recent_reports else ""}
        {"<ul class='report-list'>" if recent_reports else ""}
        {"".join(f'<li><a href="{r["file"]}">{r["formatted"]}</a><span class="badge">Report</span></li>' for r in recent_reports)}
        {"</ul>" if recent_reports else ""}
    </div>
    
    <div class="footer">
        <p>📅 Updates every Sunday at 9 AM UTC • Powered by Strava API</p>
        <p><a href="https://github.com/tiagosarmentosantos/gen-ai-toolbox" style="color: #4a9eff;">View on GitHub</a></p>
    </div>
</body>
</html>"""
    
    (DOCS_DIR / "index.html").write_text(html_content)
    print("✅ Generated main index.html")


def generate_reports_index():
    """Generate reports archive index."""
    
    reports_dir = DOCS_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    all_reports = []
    for report_file in sorted(reports_dir.glob("report-*.html"), reverse=True):
        date_str = report_file.stem.replace("report-", "")
        try:
            report_date = datetime.fromisoformat(date_str)
            all_reports.append({
                "date": date_str,
                "formatted": report_date.strftime("%A, %B %d, %Y"),
                "file": report_file.name
            })
        except ValueError:
            continue
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Training Reports Archive</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #0f0f0f;
            color: #e0e0e0;
        }}
        .header {{
            text-align: center;
            padding-bottom: 20px;
            border-bottom: 2px solid #4a9eff;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0;
            color: #4a9eff;
        }}
        .header a {{
            color: #4a9eff;
            text-decoration: none;
        }}
        .header a:hover {{
            text-decoration: underline;
        }}
        .reports {{
            background: #1a1a1a;
            border: 2px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
        }}
        .report-item {{
            padding: 15px;
            border-bottom: 1px solid #2a2a2a;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .report-item:last-child {{
            border-bottom: none;
        }}
        .report-item a {{
            color: #4a9eff;
            text-decoration: none;
            font-weight: 500;
        }}
        .report-item a:hover {{
            text-decoration: underline;
        }}
        .report-date {{
            color: #999;
            font-size: 0.9em;
        }}
        .empty {{
            text-align: center;
            color: #666;
            padding: 40px 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📋 Training Reports Archive</h1>
        <p><a href="../">← Back to Dashboard</a></p>
    </div>
    
    <div class="reports">
        {"<div class='empty'><p>No reports yet. Check back after the first scheduled run.</p></div>" if not all_reports else ""}
        {"".join(f'<div class="report-item"><a href="{r["file"]}">{r["formatted"]}</a><span class="report-date">{r["date"]}</span></div>' for r in all_reports)}
    </div>
</body>
</html>"""
    
    (reports_dir / "index.html").write_text(html_content)
    print("✅ Generated reports index.html")


if __name__ == "__main__":
    generate_main_index()
    generate_reports_index()
    print("\n✨ Index pages generated successfully!")
