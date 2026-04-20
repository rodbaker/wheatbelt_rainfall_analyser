#!/usr/bin/env python3
"""
Insight Publisher - Main CLI Runner

Generates daily risk digests and data exports from Risk Engine outputs.
Part of the CropForecaster three-agent architecture (SILO Wrangler → Risk Engine → Insight Publisher).

Usage:
    python -m src.agents.insight_publisher.run_publisher --daily
    python -m src.agents.insight_publisher.run_publisher --export-powerbi
    python -m src.agents.insight_publisher.run_publisher --weekly
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.agents.insight_publisher.report_generator import DailyReportGenerator, SeasonReportGenerator
from src.agents.insight_publisher.export_generator import PowerBIExportGenerator


def main():
    parser = argparse.ArgumentParser(description='CropForecaster Insight Publisher')
    parser.add_argument('--daily', action='store_true', help='Generate daily risk digest')
    parser.add_argument('--export-powerbi', action='store_true', help='Generate Power BI exports')
    parser.add_argument('--weekly', action='store_true', help='Generate weekly outlook (future)')
    parser.add_argument('--season', type=int, metavar='YEAR',
                        help='Generate full-season summary (e.g. --season 2025 covers Jul 2025–Jun 2026)')
    parser.add_argument('--date', type=str, help='Date to process (YYYY-MM-DD), defaults to today')
    parser.add_argument('--output-dir', type=str, help='Override output directory')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')

    args = parser.parse_args()

    # Default to daily if no specific action provided
    if not any([args.daily, args.export_powerbi, args.weekly, args.season]):
        args.daily = True
    
    # Parse date or use today
    if args.date:
        try:
            process_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD format.")
            sys.exit(1)
    else:
        process_date = datetime.now().date()
    
    print(f"CropForecaster Insight Publisher - Processing {process_date}")
    
    # Generate daily risk digest
    if args.daily:
        print("📊 Generating daily risk digest...")
        try:
            generator = DailyReportGenerator(
                date=process_date,
                output_dir=args.output_dir,
                verbose=args.verbose
            )
            report_path = generator.generate_report()
            print(f"✅ Daily risk digest generated: {report_path}")
        except Exception as e:
            print(f"❌ Error generating daily report: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)
    
    # Generate Power BI exports
    if args.export_powerbi:
        print("📈 Generating Power BI exports...")
        try:
            exporter = PowerBIExportGenerator(
                date=process_date,
                output_dir=args.output_dir,
                verbose=args.verbose
            )
            export_paths = exporter.generate_exports()
            for path in export_paths:
                print(f"✅ Power BI export generated: {path}")
        except Exception as e:
            print(f"❌ Error generating Power BI exports: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)
    
    # Generate season summary report
    if args.season:
        print(f"📅 Generating {args.season}/{str(args.season + 1)[-2:]} season summary...")
        try:
            generator = SeasonReportGenerator(
                season_year=args.season,
                output_dir=args.output_dir,
                verbose=args.verbose,
            )
            report_path = generator.generate_report()
            print(f"✅ Season summary generated: {report_path}")
        except Exception as e:
            print(f"❌ Error generating season report: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    # Weekly outlook (placeholder for future implementation)
    if args.weekly:
        print("📅 Weekly outlook generation not yet implemented")
        print("   This will be added in a future milestone")
    
    print("🎉 Insight Publisher completed successfully")


if __name__ == '__main__':
    main()