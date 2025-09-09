"""
Daily Report Generator - CropForecaster Insight Publisher

Generates markdown-based daily risk digests from Risk Engine outputs.
Provides human-readable summaries of frost, heat, and rainfall events.
"""

import pandas as pd
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional


class DailyReportGenerator:
    """Generate daily risk digest reports in markdown format."""
    
    def __init__(self, date: date, output_dir: Optional[str] = None, verbose: bool = False):
        """
        Initialize daily report generator.
        
        Args:
            date: Date to generate report for
            output_dir: Override output directory (defaults to project reports/daily/)
            verbose: Enable verbose logging
        """
        self.date = date
        self.verbose = verbose
        
        # Set up paths
        self.project_root = Path(__file__).parent.parent.parent.parent
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = self.project_root / "reports" / "daily"
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Data paths
        self.data_dir = self.project_root / "data"
        self.event_log_path = self.data_dir / "derived" / "event_log.csv"
        self.stations_path = self.data_dir / "meta" / "wheatbelt_stations.csv"
        
        # Load station metadata for enrichment
        self._load_station_metadata()
    
    def _load_station_metadata(self):
        """Load station metadata for enriching reports with names and locations."""
        try:
            self.stations_df = pd.read_csv(self.stations_path)
            # Standardize station_id column name
            if 'Station number' in self.stations_df.columns:
                self.stations_df = self.stations_df.rename(columns={'Station number': 'station_id'})
            
            if self.verbose:
                print(f"Loaded metadata for {len(self.stations_df)} stations")
        except Exception as e:
            print(f"Warning: Could not load station metadata: {e}")
            self.stations_df = pd.DataFrame()
    
    def _get_station_name(self, station_id: int) -> str:
        """Get human-readable station name from station ID."""
        if not self.stations_df.empty:
            match = self.stations_df[self.stations_df['station_id'] == station_id]
            if not match.empty:
                name = match.iloc[0].get('Station name', f"Station {station_id}")
                state = match.iloc[0].get('STE_NAME16', '')
                if state and state != 'Western Australia':  # Avoid redundancy
                    return f"{name}, {state}"
                return name
        return f"Station {station_id}"
    
    def _load_events_for_date(self) -> pd.DataFrame:
        """Load all events for the target date."""
        try:
            events_df = pd.read_csv(self.event_log_path)
            
            # Handle mixed date formats (date vs datetime)
            events_df['date'] = pd.to_datetime(events_df['date'], format='mixed', errors='coerce').dt.date
            
            # Filter for target date
            date_events = events_df[events_df['date'] == self.date]
            
            if self.verbose:
                print(f"Loaded {len(date_events)} events for {self.date}")
            
            return date_events
        except Exception as e:
            if self.verbose:
                print(f"Warning: Could not load events: {e}")
            return pd.DataFrame()
    
    def _generate_summary_stats(self, events_df: pd.DataFrame) -> Dict[str, int]:
        """Generate summary statistics for the daily digest header."""
        stats = {
            'total_events': len(events_df),
            'frost_events': len(events_df[events_df['event_type'] == 'frost']),
            'heat_events': len(events_df[events_df['event_type'] == 'heat']),
            'rainfall_events': len(events_df[events_df['event_type'] == 'rainfall']),
            'stations_affected': events_df['station_id'].nunique() if not events_df.empty else 0
        }
        return stats
    
    def _generate_frost_section(self, events_df: pd.DataFrame) -> str:
        """Generate frost events section of the report."""
        frost_events = events_df[events_df['event_type'] == 'frost']
        
        if frost_events.empty:
            return "**No frost events detected**\n"
        
        section = f"**{len(frost_events)} frost event(s) detected:**\n\n"
        
        # Add phenology context if available
        if not frost_events.empty and 'flowering_window_active' in frost_events.columns:
            flowering_events = frost_events[frost_events['flowering_window_active'] == True]
            if not flowering_events.empty:
                section += f"⚠️ **{len(flowering_events)} event(s) occurred during flowering window** (elevated risk)\n\n"
        
        # Group by severity for better organization
        severity_groups = frost_events.groupby('severity')
        
        for severity, group in severity_groups:
            section += f"*{severity.title()} Frost (< {group.iloc[0]['threshold']}°C):*\n"
            
            for _, event in group.iterrows():
                station_name = self._get_station_name(event['station_id'])
                
                # Base event info
                event_line = f"- **{station_name}**: {event['value']}°C"
                
                # Add phenology context
                if 'crop_stage' in event and pd.notna(event['crop_stage']):
                    event_line += f" ({event['crop_stage']} stage"
                    
                    # Add flowering context
                    if 'flowering_window_active' in event and event['flowering_window_active']:
                        event_line += ", in flowering window"
                    
                    # Add phenology risk multiplier if available
                    if 'phenology_risk_multiplier' in event and pd.notna(event['phenology_risk_multiplier']):
                        risk_mult = event['phenology_risk_multiplier']
                        if risk_mult > 1.5:
                            event_line += f", high phenological risk {risk_mult:.1f}x"
                        elif risk_mult > 1.0:
                            event_line += f", elevated risk {risk_mult:.1f}x"
                    
                    event_line += ")"
                
                # Add confidence
                event_line += f" (confidence: {event['confidence']:.1f})"
                
                section += event_line + "\n"
            
            section += "\n"
        
        return section
    
    def _generate_heat_section(self, events_df: pd.DataFrame) -> str:
        """Generate heat events section of the report."""
        heat_events = events_df[events_df['event_type'] == 'heat']
        
        if heat_events.empty:
            return "**No heat stress events detected**\n"
        
        section = f"**{len(heat_events)} heat event(s) detected:**\n\n"
        
        for _, event in heat_events.iterrows():
            station_name = self._get_station_name(event['station_id'])
            section += f"- **{station_name}**: {event['value']}°C (>{event['threshold']}°C threshold)\n"
        
        return section + "\n"
    
    def _generate_rainfall_section(self, events_df: pd.DataFrame) -> str:
        """Generate rainfall events section of the report."""
        rainfall_events = events_df[events_df['event_type'] == 'rainfall']
        
        if rainfall_events.empty:
            return "**No significant rainfall events detected**\n"
        
        section = f"**{len(rainfall_events)} rainfall event(s) detected:**\n\n"
        
        for _, event in rainfall_events.iterrows():
            station_name = self._get_station_name(event['station_id'])
            section += f"- **{station_name}**: {event['value']}mm ({event['severity']} risk)\n"
        
        return section + "\n"
    
    def _generate_data_quality_section(self, events_df: pd.DataFrame) -> str:
        """Generate data quality assessment section."""
        if events_df.empty:
            return "**Data Quality**: No events to assess\n"
        
        # Calculate quality metrics
        total_events = len(events_df)
        high_confidence = len(events_df[events_df['confidence'] >= 0.9])
        perfect_quality = len(events_df[events_df['data_quality'] == 0])
        
        section = "## Data Quality Assessment\n\n"
        section += f"- **Events processed**: {total_events}\n"
        section += f"- **High confidence events** (≥90%): {high_confidence}/{total_events} ({high_confidence/total_events*100:.1f}%)\n"
        section += f"- **Perfect data quality**: {perfect_quality}/{total_events} ({perfect_quality/total_events*100:.1f}%)\n"
        
        if events_df['data_quality'].max() > 0:
            section += f"- **Data quality flags detected** - review source data quality\n"
        
        return section + "\n"
    
    def generate_report(self) -> Path:
        """Generate the complete daily risk digest report."""
        # Load events data
        events_df = self._load_events_for_date()
        
        # Generate summary statistics
        stats = self._generate_summary_stats(events_df)
        
        # Build the report
        report_lines = []
        
        # Header
        report_lines.append(f"# Daily Risk Digest - {self.date.strftime('%A, %B %d, %Y')}")
        report_lines.append("")
        report_lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by CropForecaster*")
        report_lines.append("")
        
        # Executive Summary
        report_lines.append("## Executive Summary")
        report_lines.append("")
        if stats['total_events'] == 0:
            report_lines.append("**No significant weather risk events detected today** across monitored wheatbelt stations.")
        else:
            report_lines.append(f"**{stats['total_events']} weather risk event(s)** detected across **{stats['stations_affected']} station(s)**:")
            if stats['frost_events'] > 0:
                report_lines.append(f"- 🥶 **{stats['frost_events']} frost event(s)**")
            if stats['heat_events'] > 0:
                report_lines.append(f"- 🔥 **{stats['heat_events']} heat stress event(s)**")
            if stats['rainfall_events'] > 0:
                report_lines.append(f"- 🌧️ **{stats['rainfall_events']} rainfall event(s)**")
        
        report_lines.append("")
        
        # Event Details
        report_lines.append("## Event Details")
        report_lines.append("")
        
        # Frost Events
        report_lines.append("### 🥶 Frost Risk")
        report_lines.append(self._generate_frost_section(events_df))
        
        # Heat Events
        report_lines.append("### 🔥 Heat Stress Risk")
        report_lines.append(self._generate_heat_section(events_df))
        
        # Rainfall Events  
        report_lines.append("### 🌧️ Harvest Rainfall Risk")
        report_lines.append(self._generate_rainfall_section(events_df))
        
        # Data Quality
        report_lines.append(self._generate_data_quality_section(events_df))
        
        # Footer
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("*CropForecaster Daily Risk Digest - Automated weather risk monitoring for Australian wheatbelt*")
        report_lines.append("*Data source: SILO API | Event detection: Risk Engine | Report generation: Insight Publisher*")
        
        # Write the report
        report_filename = f"{self.date.strftime('%Y-%m-%d')}_risk_digest.md"
        report_path = self.output_dir / report_filename
        
        with open(report_path, 'w') as f:
            f.write('\n'.join(report_lines))
        
        if self.verbose:
            print(f"Report written to: {report_path}")
            print(f"Report contains {len(report_lines)} lines")
        
        return report_path