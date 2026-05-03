"""
Daily Report Generator - CropForecaster Insight Publisher

Generates markdown-based daily risk digests from Risk Engine outputs.
Provides human-readable summaries of frost, heat, and rainfall events.
"""

import logging
import yaml
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


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
        self._load_seasonal_context()
        self._crop_context_lookup = self._load_crop_context()
    
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

    def _load_seasonal_context(self):
        """Load wa_seasonal_context.yaml for disease alert context."""
        context_path = self.data_dir / "meta" / "wa_seasonal_context.yaml"
        try:
            with open(context_path) as f:
                self.seasonal_context = yaml.safe_load(f)
        except Exception as e:
            if self.verbose:
                print(f"Warning: Could not load seasonal context: {e}")
            self.seasonal_context = {}

    def _load_crop_context(self):
        """Load optional ABS crop context lookup (Phase 5 publisher enrichment).

        Mirrors the Phase 4 risk-engine boundary:
          disabled (default) → returns None, no file access
          enabled + CSV present → returns CropContextLookup
          enabled + missing + required=True → raises FileNotFoundError
          enabled + missing + required=False → warns, returns None
        """
        config_path = self.project_root / "config" / "crop_calendars.yaml"
        try:
            with open(config_path) as f:
                crop_config = yaml.safe_load(f)
        except Exception as e:
            if self.verbose:
                logger.warning(f"Could not load crop_calendars.yaml: {e}")
            return None

        cc_cfg = (crop_config or {}).get('crop_context', {})
        if not cc_cfg.get('enabled', False):
            return None

        from src.common.crop_context_loader import load_crop_context_lookup

        default_path = 'data/meta/crop_context_sa2.csv'
        csv_path = self.project_root / cc_cfg.get('path', default_path)
        required = cc_cfg.get('required', False)

        if not csv_path.exists():
            if required:
                raise FileNotFoundError(
                    f"Crop context CSV required but not found: {csv_path}. "
                    "Run scripts/build_crop_context.py to generate it."
                )
            logger.warning(
                f"Crop context enabled but CSV not found: {csv_path} "
                "— continuing without it"
            )
            return None

        try:
            lookup = load_crop_context_lookup(csv_path)
            if self.verbose:
                logger.info(
                    f"Loaded crop context lookup ({len(lookup.records)} records)"
                )
            return lookup
        except Exception as e:
            logger.warning(
                f"Failed to load crop context from {csv_path}: {e} "
                "— continuing without it"
            )
            return None

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
        def _count(event_type):
            return len(events_df[events_df['event_type'] == event_type]) if not events_df.empty else 0

        stats = {
            'total_events': len(events_df),
            'frost_events': _count('frost'),
            'heat_events': _count('heat'),
            'rainfall_events': _count('rainfall'),
            'seeding_rain_events': _count('seeding_rain'),
            'development_rain_events': _count('development_rain'),
            'stations_affected': events_df['station_id'].nunique() if not events_df.empty else 0,
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
    
    def _generate_seeding_rain_section(self, events_df: pd.DataFrame) -> str:
        """Generate seeding rain section grouped by crop type then SA2 region."""
        seeding_events = events_df[events_df['event_type'] == 'seeding_rain']

        if seeding_events.empty:
            return "**No seeding rain events detected**\n"

        severity_order = ['adequate', 'marginal', 'marginal_low', 'inadequate']

        crop_labels = {
            'canola': 'Canola (Mar–Apr window)',
            'wheat_barley': 'Wheat/Barley (Apr–May, ANZAC Day dry sow)',
            'lupins': 'Lupins/Legumes (Apr–May, deep sow option)',
        }

        n_stations = seeding_events['station_id'].nunique()
        section = f"**{len(seeding_events)} seeding rain event(s)** across **{n_stations} station(s)**:\n\n"

        has_crop_type = 'crop_type' in seeding_events.columns and seeding_events['crop_type'].notna().any()
        has_sa2 = 'sa2_name' in seeding_events.columns and seeding_events['sa2_name'].notna().any()

        def _sa2_block(crop_events: pd.DataFrame) -> str:
            """Build a severity-tiered SA2 regional breakdown for a subset of events."""
            sev_rank = {s: i for i, s in enumerate(severity_order)}
            block = ""

            if has_sa2 and crop_events['sa2_name'].notna().any():
                sa2_summary = (
                    crop_events
                    .assign(_rank=crop_events['severity'].map(sev_rank))
                    .sort_values('_rank')
                    .groupby('sa2_name', sort=False)
                    .agg(
                        best_severity=('severity', 'first'),
                        max_value=('value', 'max'),
                        station_count=('station_id', 'nunique'),
                        sa3_name=('sa3_name', 'first'),
                        threshold=('threshold', 'first'),
                    )
                    .reset_index()
                )
                sa2_summary['_rank'] = sa2_summary['best_severity'].map(sev_rank)
                sa2_summary = sa2_summary.sort_values('_rank')

                for sev in severity_order:
                    tier = sa2_summary[sa2_summary['best_severity'] == sev]
                    if tier.empty:
                        continue
                    thresh = tier.iloc[0]['threshold']
                    block += f"*{sev.replace('_', '-').title()} (≥{thresh:.0f}mm/7d):*\n"
                    for _, row in tier.iterrows():
                        context = f" ({row['sa3_name']})" if pd.notna(row.get('sa3_name')) else ""
                        block += (
                            f"- **{row['sa2_name']}**{context}: "
                            f"{row['max_value']:.1f}mm max, {int(row['station_count'])} station(s)\n"
                        )
                    block += "\n"
            else:
                # Fallback: list by station
                for _, event in crop_events.iterrows():
                    station_name = self._get_station_name(event['station_id'])
                    block += f"- **{station_name}**: {event['value']:.1f}mm ({event['severity']})\n"
                block += "\n"

            return block

        if has_crop_type:
            # Group by crop type in defined order
            crop_order = ['canola', 'wheat_barley', 'lupins']
            for crop in crop_order:
                crop_events = seeding_events[seeding_events['crop_type'] == crop]
                if crop_events.empty:
                    continue
                label = crop_labels.get(crop, crop.replace('_', ' ').title())
                section += f"**{label}:**\n"
                section += _sa2_block(crop_events)
        else:
            # Legacy events without crop_type — flat SA2 breakdown
            section += _sa2_block(seeding_events)

        return section

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
    
    def _generate_seasonal_moisture_section(self, events_df: pd.DataFrame) -> str:
        """Generate a year-round seasonal moisture tracker section."""
        report_month = self.date.month

        # Determine which windows are active
        in_seeding = report_month in [4, 5, 6]
        in_development = report_month in [7, 8, 9, 10]
        in_harvest = report_month in [11, 12, 1]

        def _window_status(event_type: str, adequate_severities: list, dry_severities: list) -> str:
            if events_df.empty or event_type not in events_df['event_type'].values:
                return "No data"
            window_events = events_df[events_df['event_type'] == event_type]
            if window_events.empty:
                return "No events detected"
            adequate_count = len(window_events[window_events['severity'].isin(adequate_severities)])
            dry_count = len(window_events[window_events['severity'].isin(dry_severities)])
            stations_dry = window_events[window_events['severity'].isin(dry_severities)]['station_id'].nunique()
            if dry_count > 0:
                return f"DRY SPELL — {stations_dry} station(s) below threshold"
            if adequate_count > 0:
                return f"Adequate — {adequate_count} event(s) met moisture threshold"
            return "Monitoring"

        section = "## Seasonal Moisture Status\n\n"

        # Seeding window
        if in_seeding:
            status = _window_status('seeding_rain', ['adequate'], ['inadequate'])
            prefix = "WARNING: " if "DRY SPELL" in status else ""
            section += f"- **Seeding window (Apr–Jun):** {prefix}{status}\n"
        else:
            section += f"- **Seeding window (Apr–Jun):** {'Active' if in_seeding else 'Pre-season' if report_month < 4 else 'Complete'}\n"

        # Development window
        if in_development:
            status = _window_status('development_rain', [], ['dry_spell', 'moisture_stress'])
            prefix = "WARNING: " if "DRY SPELL" in status else ""
            section += f"- **Development period (Jul–Oct):** {prefix}{status}\n"
        else:
            section += f"- **Development period (Jul–Oct):** {'Active' if in_development else 'Pre-season' if report_month < 7 else 'Complete'}\n"

        # Harvest window
        if in_harvest:
            status = _window_status('rainfall', [], ['moderate', 'high', 'severe'])
            prefix = ""
            section += f"- **Harvest window (Nov–Jan):** Active — {len(events_df[events_df['event_type'] == 'rainfall'])} rainfall risk event(s)\n"
        else:
            section += f"- **Harvest window (Nov–Jan):** {'Active' if in_harvest else 'Pre-season' if report_month < 11 else 'Complete'}\n"

        # Key dry stations (if any)
        dry_events = pd.DataFrame()
        if not events_df.empty and 'event_type' in events_df.columns:
            dry_events = events_df[
                (events_df['event_type'].isin(['seeding_rain', 'development_rain'])) &
                (events_df['severity'].isin(['inadequate', 'dry_spell', 'moisture_stress']))
            ]

        if not dry_events.empty:
            section += "\n**Stations with moisture stress:**\n"
            for station_id in dry_events['station_id'].unique()[:5]:
                station_name = self._get_station_name(station_id)
                station_dry = dry_events[dry_events['station_id'] == station_id].iloc[0]
                section += f"- {station_name}: {station_dry['value']:.1f}mm over {station_dry['accumulation_window']}-day window\n"

        return section + "\n"

    def _generate_disease_watch_section(self, events_df: pd.DataFrame) -> str:
        """Generate Disease Watch section when frost or rainfall events trigger it.

        Fires when today has frost OR any rainfall events AND at least one disease
        alert carries report_flag: true in wa_seasonal_context.yaml.
        """
        if not self.seasonal_context:
            return ""

        has_frost = not events_df.empty and (events_df['event_type'] == 'frost').any()
        has_rainfall = not events_df.empty and events_df['event_type'].isin(
            ['rainfall', 'seeding_rain', 'development_rain']
        ).any()

        if not (has_frost or has_rainfall):
            return ""

        disease_alerts = self.seasonal_context.get('disease_alerts', {})
        smut_alert = self.seasonal_context.get('smut_season_alert', {})

        # Collect diseases with report_flag: true
        flagged = []
        for crop, diseases in disease_alerts.items():
            for disease_name, alert in diseases.items():
                if alert.get('report_flag', False):
                    flagged.append((crop, disease_name, alert))

        if not flagged and not smut_alert.get('active'):
            return ""

        # Build trigger context line
        trigger_parts = []
        if has_frost:
            frost_events = events_df[events_df['event_type'] == 'frost']
            n = len(frost_events)
            if 'crop_stage' in frost_events.columns:
                stages = frost_events['crop_stage'].dropna().unique()
                stage_str = f" during {', '.join(stages)}" if len(stages) > 0 else ""
            else:
                stage_str = ""
            trigger_parts.append(f"{n} frost event(s){stage_str}")
        if has_rainfall:
            rain_events = events_df[events_df['event_type'].isin(
                ['rainfall', 'seeding_rain', 'development_rain']
            )]
            trigger_parts.append(f"{len(rain_events)} rainfall event(s)")

        section = "## Disease Watch\n\n"
        section += f"*Triggered by: {'; '.join(trigger_parts)}*\n\n"

        # Cross-crop smut season alert
        if smut_alert.get('active'):
            crops = ', '.join(c.title() for c in smut_alert.get('crops', []))
            section += f"**Smut Season Alert — {crops}** | {smut_alert.get('risk_level', 'elevated').title()} risk\n\n"
            reason = smut_alert.get('reason', '').strip()
            if reason:
                section += f"{reason}\n\n"
            mgmt = smut_alert.get('management', '').strip()
            if mgmt:
                section += f"Management: {mgmt}\n\n"

        # Per-disease entries
        for crop, disease_name, alert in flagged:
            severity = alert.get('severity', 'unknown').title()
            trend = alert.get('risk_trend', 'unknown')
            display_name = disease_name.replace('_', ' ').title()
            flags = []
            if alert.get('new_pathotype'):
                flags.append('new pathotype')
            if alert.get('fungicide_resistance'):
                flags.append('fungicide resistance detected')
            flag_str = f" ⚠ {', '.join(flags)}" if flags else ""

            section += f"**{crop.title()} — {display_name}**{flag_str} | {severity} risk | Trend: {trend}\n\n"

            summary = alert.get('summary', '').strip()
            if summary:
                section += f"{summary}\n\n"

            # Susceptible varieties grouped by rating
            susc = alert.get('susceptible_varieties', {})
            if susc:
                for rating, varieties in susc.items():
                    if not isinstance(varieties, list) or not varieties:
                        continue
                    names = [v.replace('_', ' ') for v in varieties]
                    line = f"- Susceptible ({rating}): {', '.join(names[:6])}"
                    if len(names) > 6:
                        line += f" (+{len(names) - 6} more)"
                    section += line + "\n"
                section += "\n"

            mgmt = alert.get('management', '').strip()
            if mgmt:
                section += f"Management: {mgmt}\n\n"

        return section

    def _generate_abs_crop_context_section(self, events_df: pd.DataFrame) -> str:
        """Generate optional ABS crop context section for affected SA2 regions.

        Returns empty string when disabled, lookup unavailable, or no SA2 data
        matches. Never modifies risk ratings or implies current-year conditions.
        """
        if self._crop_context_lookup is None:
            return ""
        if events_df.empty:
            return ""

        # Collect unique station IDs from today's events
        if 'station_id' not in events_df.columns:
            return ""
        station_ids = events_df['station_id'].dropna().unique()
        if len(station_ids) == 0:
            return ""

        # Map station_id → SA2_5DIG16 using loaded station metadata
        if self.stations_df.empty or 'SA2_5DIG16' not in self.stations_df.columns:
            return ""

        # Build {sa2_5dig: sa2_name} for affected stations (deduplicated)
        sa2_map: dict[str, str] = {}
        for sid in station_ids:
            match = self.stations_df[self.stations_df['station_id'] == sid]
            if match.empty:
                continue
            row = match.iloc[0]
            sa2_5dig = str(row.get('SA2_5DIG16', '') or '').strip()
            sa2_name = str(row.get('SA2_NAME16', '') or '').strip()
            if sa2_5dig:
                sa2_map[sa2_5dig] = sa2_name or sa2_5dig

        if not sa2_map:
            return ""

        # Collect crop context rows per SA2, sorted by area_share desc
        sa2_blocks: list[str] = []
        baseline_year: Optional[str] = None

        for sa2_5dig, sa2_name in sorted(sa2_map.items()):
            records = self._crop_context_lookup.for_station_sa2(sa2_5dig)
            if not records:
                continue
            # Use area_share to rank crops; skip records with None area_share
            ranked = sorted(
                [r for r in records if r.area_share is not None],
                key=lambda r: r.area_share,
                reverse=True,
            )
            unranked = [r for r in records if r.area_share is None]
            ordered = ranked + unranked

            if not ordered:
                continue

            # Capture baseline year from first record
            if baseline_year is None and ordered[0].financial_year:
                baseline_year = ordered[0].financial_year

            crop_lines: list[str] = []
            for rec in ordered[:5]:
                share_str = (
                    f"{rec.area_share * 100:.0f}% area share"
                    if rec.area_share is not None
                    else "area share not available"
                )
                area_str = (
                    f"{rec.area_ha:,.0f} ha"
                    if rec.area_ha is not None
                    else "area not available"
                )
                crop_lines.append(
                    f"  - {rec.crop.title()}: {share_str} ({area_str})"
                )

            sa2_blocks.append(
                f"**{sa2_name}** (SA2 {sa2_5dig}):\n" + "\n".join(crop_lines)
            )

        if not sa2_blocks:
            return ""

        year_label = baseline_year or "historical"
        section = (
            f"## ABS Crop Context ({year_label} baseline)\n\n"
            "_Historical ABS census estimates — not current-year planted area. "
            "Does not change risk ratings._\n\n"
        )
        section += "\n\n".join(sa2_blocks) + "\n\n"
        return section

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
                report_lines.append(f"- 🌧️ **{stats['rainfall_events']} harvest rainfall event(s)**")
            if stats['seeding_rain_events'] > 0:
                report_lines.append(f"- 🌱 **{stats['seeding_rain_events']} seeding rainfall event(s)**")
            if stats['development_rain_events'] > 0:
                report_lines.append(f"- 💧 **{stats['development_rain_events']} development moisture event(s)**")
        
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

        # Seeding Rain Events (Apr–Jun)
        if stats['seeding_rain_events'] > 0 or self.date.month in [4, 5, 6]:
            report_lines.append("### 🌱 Seeding Rainfall (Apr–Jun)")
            report_lines.append(self._generate_seeding_rain_section(events_df))

        # Seasonal Moisture Tracker (year-round)
        report_lines.append(self._generate_seasonal_moisture_section(events_df))

        # Disease Watch (frost or rainfall events + report_flag: true alerts)
        disease_watch = self._generate_disease_watch_section(events_df)
        if disease_watch:
            report_lines.append(disease_watch)

        # ABS Crop Context (optional historical enrichment — disabled by default)
        abs_section = self._generate_abs_crop_context_section(events_df)
        if abs_section:
            report_lines.append(abs_section)

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


class SeasonReportGenerator:
    """Generate a full-season risk summary report from the complete event log."""

    MONTH_NAMES = {
        1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
        7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec',
    }

    def __init__(self, season_year: int, output_dir: Optional[str] = None, verbose: bool = False):
        """
        Args:
            season_year: The harvest year (e.g. 2025 covers Jul 2025 – Jun 2026).
            output_dir: Override output directory (defaults to reports/).
            verbose: Enable verbose logging.
        """
        self.season_year = season_year
        self.verbose = verbose

        self.project_root = Path(__file__).parent.parent.parent.parent
        self.output_dir = Path(output_dir) if output_dir else self.project_root / "reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.event_log_path = self.project_root / "data" / "derived" / "event_log.csv"
        self.stations_path = self.project_root / "data" / "meta" / "wheatbelt_stations.csv"
        self._load_station_metadata()

    def _load_station_metadata(self):
        try:
            self.stations_df = pd.read_csv(self.stations_path)
            if 'Station number' in self.stations_df.columns:
                self.stations_df = self.stations_df.rename(columns={'Station number': 'station_id'})
        except Exception:
            self.stations_df = pd.DataFrame()

    def _get_station_name(self, station_id: int) -> str:
        if not self.stations_df.empty:
            match = self.stations_df[self.stations_df['station_id'] == station_id]
            if not match.empty:
                return match.iloc[0].get('Station name', f"Station {station_id}")
        return f"Station {station_id}"

    def _load_season_events(self) -> pd.DataFrame:
        """Load all events in the season window (Jul season_year – Jun season_year+1)."""
        df = pd.read_csv(self.event_log_path)
        df['date'] = pd.to_datetime(df['date'], format='mixed', errors='coerce')
        df = df.dropna(subset=['date'])
        df['month'] = df['date'].dt.month
        df['year'] = df['date'].dt.year

        # Season window: Aug of season_year to Jun of season_year+1 (wheat season)
        season_start = pd.Timestamp(f"{self.season_year}-07-01")
        season_end = pd.Timestamp(f"{self.season_year + 1}-06-30")
        mask = (df['date'] >= season_start) & (df['date'] <= season_end)
        season_df = df[mask].copy()

        if self.verbose:
            print(f"Season events loaded: {len(season_df)} (from {len(df)} total)")
        return season_df

    def _monthly_breakdown_table(self, df: pd.DataFrame) -> str:
        """Markdown table: rows=month, cols=event types."""
        event_types = ['frost', 'heat', 'rainfall', 'development_rain', 'seeding_rain']
        col_labels = {'frost': 'Frost', 'heat': 'Heat', 'rainfall': 'Harvest Rain',
                      'development_rain': 'Dev Rain', 'seeding_rain': 'Seeding Rain'}

        df['month_num'] = df['date'].dt.month
        df['year_num'] = df['date'].dt.year

        months_in_season = []
        for y, m in [(self.season_year, mo) for mo in range(7, 13)] + \
                     [(self.season_year + 1, mo) for mo in range(1, 7)]:
            if not df[(df['year_num'] == y) & (df['month_num'] == m)].empty:
                months_in_season.append((y, m))

        header = "| Month | " + " | ".join(col_labels[t] for t in event_types) + " | Total |"
        sep = "|-------|" + "-------|" * len(event_types) + "-------|"
        rows = [header, sep]

        for y, m in months_in_season:
            month_df = df[(df['year_num'] == y) & (df['month_num'] == m)]
            label = f"{self.MONTH_NAMES[m]} {y}"
            counts = [str(len(month_df[month_df['event_type'] == t])) for t in event_types]
            rows.append(f"| {label} | " + " | ".join(counts) + f" | {len(month_df)} |")

        total_counts = [str(len(df[df['event_type'] == t])) for t in event_types]
        rows.append(f"| **TOTAL** | " + " | ".join(f"**{c}**" for c in total_counts) + f" | **{len(df)}** |")
        return "\n".join(rows)

    def _peak_events_section(self, df: pd.DataFrame) -> str:
        """Highlight worst single-day events per type."""
        lines = []

        # Frost: coldest day
        frost = df[df['event_type'] == 'frost']
        if not frost.empty:
            worst = frost.loc[frost['value'].idxmin()]
            lines.append(f"- **Coldest frost**: {worst['value']:.1f}°C at "
                         f"{self._get_station_name(int(worst['station_id']))} "
                         f"on {worst['date'].strftime('%d %b %Y')} ({worst['severity']})")

        # Heat: hottest day
        heat = df[df['event_type'] == 'heat']
        if not heat.empty:
            worst = heat.loc[heat['value'].idxmax()]
            lines.append(f"- **Hottest heat event**: {worst['value']:.1f}°C at "
                         f"{self._get_station_name(int(worst['station_id']))} "
                         f"on {worst['date'].strftime('%d %b %Y')} ({worst['severity']})")

        # Harvest rainfall: highest single event
        rain = df[df['event_type'] == 'rainfall']
        if not rain.empty:
            worst = rain.loc[rain['value'].idxmax()]
            lines.append(f"- **Largest harvest rainfall**: {worst['value']:.1f}mm at "
                         f"{self._get_station_name(int(worst['station_id']))} "
                         f"on {worst['date'].strftime('%d %b %Y')} ({worst['severity']})")

        # Development rain: most stressed station (most events)
        dev = df[df['event_type'] == 'development_rain']
        if not dev.empty:
            top_station = dev['station_id'].value_counts().idxmax()
            count = dev['station_id'].value_counts().max()
            lines.append(f"- **Most development moisture stress**: "
                         f"{self._get_station_name(int(top_station))} — {count} events")

        return "\n".join(lines) if lines else "No extreme events on record."

    def _top_stations_section(self, df: pd.DataFrame) -> str:
        """Top 5 stations by total event count."""
        counts = df.groupby('station_id').size().sort_values(ascending=False).head(5)
        lines = []
        for station_id, count in counts.items():
            lines.append(f"- **{self._get_station_name(int(station_id))}** (ID {int(station_id)}): {count} events")
        return "\n".join(lines) if lines else "No station data."

    def generate_report(self) -> Path:
        """Generate and write the season summary report."""
        df = self._load_season_events()

        lines = []

        # Header
        lines += [
            f"# CropForecaster — {self.season_year}/{str(self.season_year + 1)[-2:]} Season Risk Summary",
            "",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
            f"Events: {len(df)} | Stations: {df['station_id'].nunique()} | "
            f"Date range: {df['date'].min().strftime('%d %b %Y')} – {df['date'].max().strftime('%d %b %Y')}*",
            "",
        ]

        if df.empty:
            lines.append("No events found for this season.")
        else:
            # Executive summary
            frost_count = len(df[df['event_type'] == 'frost'])
            heat_count = len(df[df['event_type'] == 'heat'])
            rain_count = len(df[df['event_type'] == 'rainfall'])
            dev_count = len(df[df['event_type'] == 'development_rain'])
            seed_count = len(df[df['event_type'] == 'seeding_rain'])

            lines += [
                "## Executive Summary",
                "",
                f"The {self.season_year}/{str(self.season_year + 1)[-2:]} season recorded **{len(df)} weather risk events** "
                f"across **{df['station_id'].nunique()} stations**.",
                "",
                f"| Event Type | Count | % of Season |",
                f"|------------|-------|-------------|",
                f"| Frost | {frost_count} | {frost_count/len(df)*100:.1f}% |",
                f"| Heat Stress | {heat_count} | {heat_count/len(df)*100:.1f}% |",
                f"| Harvest Rainfall Risk | {rain_count} | {rain_count/len(df)*100:.1f}% |",
                f"| Crop Development Moisture | {dev_count} | {dev_count/len(df)*100:.1f}% |",
                f"| Seeding Rainfall | {seed_count} | {seed_count/len(df)*100:.1f}% |",
                "",
            ]

            # Severity breakdown for frost
            if frost_count > 0:
                frost_df = df[df['event_type'] == 'frost']
                sev = frost_df['severity'].value_counts()
                lines += [
                    "### Frost Severity Breakdown",
                    "",
                    f"- Light (≤2°C): **{sev.get('light', 0)}** events",
                    f"- Moderate (≤0°C): **{sev.get('moderate', 0)}** events",
                    f"- Severe (≤-2°C): **{sev.get('severe', 0)}** events",
                    "",
                ]

            # Monthly breakdown
            lines += [
                "## Monthly Breakdown",
                "",
                self._monthly_breakdown_table(df),
                "",
            ]

            # Season highlights
            lines += [
                "## Season Highlights",
                "",
                self._peak_events_section(df),
                "",
            ]

            # Top stations
            lines += [
                "## Most Affected Stations",
                "",
                self._top_stations_section(df),
                "",
            ]

        # Footer
        lines += [
            "---",
            "",
            "*CropForecaster Season Risk Summary — Australian Wheatbelt*",
            "*Data source: SILO API | Analysis: Risk Engine | Report: Insight Publisher*",
        ]

        report_path = self.output_dir / f"{self.season_year}-{str(self.season_year + 1)[-2:]}_season_summary.md"
        with open(report_path, 'w') as f:
            f.write('\n'.join(lines))

        if self.verbose:
            print(f"Season report written to: {report_path}")

        return report_path
