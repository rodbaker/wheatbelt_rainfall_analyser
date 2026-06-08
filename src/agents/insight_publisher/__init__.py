"""
Insight Publisher Agent - CropForecaster System

Mission: Package risk detections into human-ready updates and reusable exports

Key Responsibilities:
- Daily Risk Digest: key events, top Statistical Divisions at risk, sparkline tables (markdown)
- Weekly Outlook: 7/14-day summaries, agronomic implications, PDF export  
- Power BI exports: risk_events.csv, risk_events_latest.csv (current day)
- Changelog tracking, maintain /reports/ index

Inputs → Outputs:
- In: event_log, sd_risk_rollup, prior reports
- Out: reports/daily/*.md, reports/weekly/*.md, data/exports/*.csv

Guardrails: Stable file names for automation, no price analysis
"""