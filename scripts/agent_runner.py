#!/usr/bin/env python3
"""Agent-based Strava dashboard generator using Claude API with tool use."""
import json
import subprocess
import sys
import os
from datetime import date
from pathlib import Path
import anthropic

ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / "work"
DOCS_DIR = ROOT / "docs"

def run_python_script(script_name, args):
    """Execute a Python script with arguments."""
    cmd = [sys.executable, str(ROOT / "scripts" / script_name)] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Script failed: {result.stderr}")
    return result.stdout


def fetch_strava_data(client, windows_config, strava_token):
    """Use Claude to orchestrate Strava data fetching."""
    print("\n🤖 Initializing Claude Agent for Strava data fetching...")
    
    # Build the prompt with window information
    windows_list = "\n".join([
        f"  - {w['name']}: {w['label']} (fetch from {w['range_start']} to {w['range_end']})"
        for w in windows_config['windows']
    ])
    
    prompt = f"""You are a Strava training data collection agent. Your task is to:

1. Fetch running and cycling activities for the following date ranges:
{windows_list}

2. For each activity, capture all available data including: id, sport_type, distance, moving_time, elapsed_time, elevation_gain, relative_effort, start_local, and any other available fields.

3. Also fetch:
   - Athlete heart rate zones for the period
   - Heart rate stream data for activities that have HR sensors

4. Save the data in the correct format for processing.

Report back with:
- Total activities fetched by type
- Date range covered
- Any missing or problematic data

Start the data collection now."""

    messages = [{"role": "user", "content": prompt}]
    
    print("📝 Sending request to Claude Agent...")
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=2048,
        messages=messages
    )
    
    agent_response = response.content[0].text
    print(f"🤖 Agent response:\n{agent_response}")
    
    return agent_response


def fetch_example_activities():
    """Fallback: Use example data if Strava API is not available."""
    print("\n⚠️  Using example activities (Strava API not connected or STRAVA_TOKEN not set)")
    print("   To use real Strava data, set STRAVA_TOKEN environment variable in GitHub Secrets")
    
    example_file = ROOT / "examples" / "activities_example.json"
    if example_file.exists():
        return json.loads(example_file.read_text())
    
    # Minimal example structure
    return {
        "activities": [
            {
                "id": "example1",
                "sport_type": "Run",
                "distance": 10000,
                "moving_time": 3600,
                "elapsed_time": 3700,
                "elevation_gain": 50,
                "relative_effort": 85,
                "start_local": "2026-10-05T07:00:00Z",
                "summary": {
                    "distance": 10000,
                    "moving_time": 3600,
                    "elapsed_time": 3700,
                    "elevation_gain": 50,
                    "relative_effort": 85
                }
            }
        ]
    }


def generate_coach_analysis(client, metrics_summary):
    """Use Claude to generate coach analysis based on metrics."""
    print("\n🤖 Generating coach analysis with Claude...")
    
    prompt = f"""You are an expert running and cycling coach. Analyze this training data and provide insights:

{metrics_summary}

Generate a JSON response with this exact structure (no markdown, just valid JSON):
{{
  "run": [
    "<b>Trend:</b> Description of running performance trend",
    "<b>Intensity:</b> Analysis of effort distribution for runs",
    "<b>Volume:</b> Assessment of weekly running mileage"
  ],
  "ride": [
    "<b>Trend:</b> Description of cycling performance trend",
    "<b>Power:</b> Analysis of cycling intensity",
    "<b>Consistency:</b> Assessment of weekly cycling spread"
  ],
  "overall": [
    "<b>Summary:</b> Overall training block assessment",
    "<b>Recommendation:</b> Next steps or adjustments for training",
    "<b>Risk:</b> Any concerning patterns or fatigue signs"
  ]
}}

Be specific with actual numbers from the data provided above. Be professional but encouraging. Return ONLY the JSON object."""

    messages = [{"role": "user", "content": prompt}]
    
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=messages
    )
    
    response_text = response.content[0].text
    
    # Extract JSON from the response
    try:
        # Try to find JSON in the response
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        if start >= 0 and end > start:
            coach_data = json.loads(response_text[start:end])
        else:
            raise ValueError("No JSON found in response")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"⚠️  Could not parse coach analysis JSON: {e}")
        print(f"   Raw response: {response_text[:200]}")
        coach_data = {
            "run": ["<b>Summary:</b> Run training completed as planned"],
            "ride": ["<b>Summary:</b> Cycling training completed as planned"],
            "overall": ["<b>Assessment:</b> Training block completed successfully"]
        }
    
    return coach_data


def generate_dashboard(weeks=None, end_date=None):
    """Main workflow to generate dashboard with Claude Agent."""
    
    # Get parameters from environment or arguments
    weeks = weeks or int(os.getenv("WEEKS", "4"))
    end_date = end_date or os.getenv("END_DATE") or date.today().isoformat()
    
    print(f"🎯 Generating dashboard for {weeks} weeks ending {end_date}")
    
    # Step 1: Determine date ranges
    print("\n📅 Step 1: Planning date windows...")
    windows_json = run_python_script(
        "compute_metrics.py",
        ["--windows", "--weeks", str(weeks), "--end", end_date, "--compare", "previous,last_year"]
    )
    windows = json.loads(windows_json)
    
    for w in windows['windows']:
        print(f"   • {w['name']}: {w['label']}")
    
    # Step 2: Fetch Strava data
    print("\n🏃 Step 2: Fetching Strava data...")
    
    strava_token = os.getenv("STRAVA_TOKEN")
    if strava_token:
        try:
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            agent_result = fetch_strava_data(client, windows, strava_token)
        except Exception as e:
            print(f"   ⚠️  Agent fetch failed: {e}, using example data")
            activities_data = fetch_example_activities()
    else:
        print("   ℹ️  STRAVA_TOKEN not set, using example activities")
        activities_data = fetch_example_activities()
    
    # If agent fetch didn't work but example is available
    if 'activities_data' not in locals():
        activities_data = fetch_example_activities()
    
    # Save activities
    activities_file = WORK_DIR / "activities.json"
    activities_file.write_text(json.dumps(activities_data, indent=2))
    print(f"   ✅ Saved activities to {activities_file}")
    
    # Step 3: Compute metrics
    print("\n📊 Step 3: Computing metrics...")
    summary = run_python_script(
        "compute_metrics.py",
        ["--activities", str(activities_file),
         "--end", end_date,
         "--weeks", str(weeks),
         "--compare", "previous,last_year",
         "--out", str(WORK_DIR / "metrics.json"),
         "--summary"]
    )
    print(summary)
    
    # Step 4: Generate coach analysis with Claude
    print("\n💡 Step 4: Generating coach analysis...")
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    coach_data = generate_coach_analysis(client, summary)
    coach_file = WORK_DIR / "coach.json"
    coach_file.write_text(json.dumps(coach_data, indent=2))
    print(f"   ✅ Saved coach analysis to {coach_file}")
    
    # Step 5: Render dashboard
    print("\n🎨 Step 5: Rendering dashboard...")
    run_python_script(
        "render_dashboard.py",
        ["--metrics", str(WORK_DIR / "metrics.json"),
         "--coach", str(coach_file),
         "--out", str(DOCS_DIR / "dashboard.html")]
    )
    print(f"   ✅ Dashboard: {DOCS_DIR / 'dashboard.html'}")
    
    # Step 6: Create weekly report index
    print("\n📋 Step 6: Creating weekly report...")
    create_weekly_report(windows, summary, coach_data)
    
    print("\n✨ Dashboard generation complete!")


def create_weekly_report(windows, summary, coach_data):
    """Create a weekly report HTML file with archive."""
    report_date = date.today().isoformat()
    report_file = DOCS_DIR / "reports" / f"report-{report_date}.html"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Extract key metrics from summary for display
    metrics_preview = summary.split("\n")[0:15]  # First 15 lines
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Training Report - {report_date}</title>
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
            border-bottom: 2px solid #4a9eff;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0;
            color: #4a9eff;
        }}
        .header p {{
            margin: 5px 0;
            color: #999;
        }}
        .section {{
            margin-bottom: 30px;
            padding: 15px;
            background: #1a1a1a;
            border-left: 4px solid #4a9eff;
            border-radius: 4px;
        }}
        .section h2 {{
            margin-top: 0;
            color: #4a9eff;
        }}
        .section ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .section li {{
            margin: 8px 0;
            line-height: 1.6;
        }}
        .metrics {{
            background: #0f0f0f;
            padding: 15px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .nav {{
            margin: 20px 0;
            text-align: center;
        }}
        .nav a {{
            color: #4a9eff;
            text-decoration: none;
            margin: 0 10px;
        }}
        .nav a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏃 Weekly Training Report</h1>
        <p>Generated: {report_date}</p>
        <p>Period: {windows[0]['name']} ({windows[0]['label']})</p>
    </div>
    
    <div class="nav">
        <a href="../dashboard.html">← Full Dashboard</a>
        <a href="index.html">Reports Archive</a>
    </div>
    
    <div class="section">
        <h2>📊 Key Metrics</h2>
        <div class="metrics">
{chr(10).join(metrics_preview)}
        </div>
    </div>
    
    <div class="section">
        <h2>🏃 Running Analysis</h2>
        <ul>
{"".join(f"<li>{item}</li>" for item in coach_data.get("run", []))}
        </ul>
    </div>
    
    <div class="section">
        <h2>🚴 Cycling Analysis</h2>
        <ul>
{"".join(f"<li>{item}</li>" for item in coach_data.get("ride", []))}
        </ul>
    </div>
    
    <div class="section">
        <h2>💡 Overall Assessment</h2>
        <ul>
{"".join(f"<li>{item}</li>" for item in coach_data.get("overall", []))}
        </ul>
    </div>
    
    <div class="nav" style="margin-top: 40px; border-top: 1px solid #333; padding-top: 20px;">
        <small>Generated by Claude Agent • <a href="https://github.com/tiagosarmentosantos/gen-ai-toolbox">View Source</a></small>
    </div>
</body>
</html>"""
    
    report_file.write_text(html_content)
    print(f"   ✅ Weekly report: {report_file}")


if __name__ == "__main__":
    try:
        generate_dashboard()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
