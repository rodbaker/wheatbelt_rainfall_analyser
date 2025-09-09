"""
Power BI Export Generator - CropForecaster Insight Publisher

Generates CSV exports optimized for Power BI integration and downstream system consumption.
Provides structured data exports with stable schemas for automation.
"""

import pandas as pd
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional


class PowerBIExportGenerator:
    """Generate Power BI-compatible CSV exports from Risk Engine outputs."""
    
    def __init__(self, date: date, output_dir: Optional[str] = None, verbose: bool = False):
        """
        Initialize Power BI export generator.
        
        Args:
            date: Date to generate exports for
            output_dir: Override output directory (defaults to project data/exports/)
            verbose: Enable verbose logging
        """
        self.date = date
        self.verbose = verbose
        
        # Set up paths
        self.project_root = Path(__file__).parent.parent.parent.parent
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = self.project_root / "data" / "exports"
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Data paths
        self.data_dir = self.project_root / "data"
        self.event_log_path = self.data_dir / "derived" / "event_log.csv"
        self.stations_path = self.data_dir / "meta" / "wheatbelt_stations.csv"
        
        # Load station metadata for enrichment
        self._load_station_metadata()
    
    def _load_station_metadata(self):
        """Load station metadata for enriching exports with geographic context."""
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
    
    def _enrich_with_station_metadata(self, events_df: pd.DataFrame) -> pd.DataFrame:
        """Enrich events data with station metadata for geographic analysis."""
        if self.stations_df.empty:
            return events_df
        
        # Merge with station metadata
        enriched_df = events_df.merge(
            self.stations_df[['station_id', 'Station name', 'Lat', 'Lon', 'SA2_NAME16', 'STE_NAME16']], 
            on='station_id', 
            how='left'
        )
        
        # Standardize column names for Power BI
        enriched_df = enriched_df.rename(columns={
            'Station name': 'station_name',
            'Lat': 'latitude',
            'Lon': 'longitude',
            'SA2_NAME16': 'region_name',
            'STE_NAME16': 'state_name'
        })
        
        return enriched_df
    
    def _load_all_events(self) -> pd.DataFrame:
        """Load all historical events for comprehensive export."""
        try:
            events_df = pd.read_csv(self.event_log_path)
            events_df['date'] = pd.to_datetime(events_df['date'], format='mixed')
            
            if self.verbose:
                date_range = f"{events_df['date'].min().date()} to {events_df['date'].max().date()}"
                print(f"Loaded {len(events_df)} total events from {date_range}")
            
            return events_df
        except Exception as e:
            if self.verbose:
                print(f"Warning: Could not load events: {e}")
            return pd.DataFrame()
    
    def _load_events_for_date(self, target_date: date) -> pd.DataFrame:
        """Load events for a specific date."""
        try:
            events_df = pd.read_csv(self.event_log_path)
            events_df['date'] = pd.to_datetime(events_df['date'], format='mixed')
            
            # Filter for target date
            date_events = events_df[events_df['date'].dt.date == target_date]
            
            if self.verbose:
                print(f"Loaded {len(date_events)} events for {target_date}")
            
            return date_events
        except Exception as e:
            if self.verbose:
                print(f"Warning: Could not load events for {target_date}: {e}")
            return pd.DataFrame()
    
    def _prepare_powerbi_schema(self, events_df: pd.DataFrame) -> pd.DataFrame:
        """Prepare events data with Power BI-optimized schema and formatting."""
        if events_df.empty:
            # Return empty DataFrame with correct schema
            return pd.DataFrame(columns=[
                'station_id', 'date', 'event_type', 'severity', 'value', 'threshold',
                'confidence', 'data_quality', 'detected_at', 'station_name', 
                'latitude', 'longitude', 'region_name', 'state_name',
                'risk_score', 'export_timestamp'
            ])
        
        # Create a copy to avoid modifying original data
        export_df = events_df.copy()
        
        # Enrich with station metadata
        export_df = self._enrich_with_station_metadata(export_df)
        
        # Add computed columns for Power BI
        export_df['risk_score'] = self._calculate_risk_score(export_df)
        export_df['export_timestamp'] = datetime.now()
        
        # Format date columns for Power BI compatibility
        export_df['date'] = pd.to_datetime(export_df['date']).dt.date
        export_df['detected_at'] = pd.to_datetime(export_df['detected_at'])
        
        # Ensure consistent column order (include new phenology fields)
        column_order = [
            'station_id', 'station_name', 'latitude', 'longitude', 
            'region_name', 'state_name', 'date', 'event_type', 
            'severity', 'value', 'threshold', 'confidence', 'data_quality',
            'crop_stage', 'phenology_risk_multiplier', 'flowering_window_active',
            'days_since_flowering_start', 'risk_score', 'detected_at', 'export_timestamp'
        ]
        
        # Only include columns that exist in the DataFrame
        available_columns = [col for col in column_order if col in export_df.columns]
        export_df = export_df[available_columns]
        
        return export_df
    
    def _calculate_risk_score(self, events_df: pd.DataFrame) -> pd.Series:
        """
        Calculate a normalized risk score (0-100) for Power BI visualization.
        
        Based on event type, severity, and confidence.
        """
        if events_df.empty:
            return pd.Series(dtype=float)
        
        risk_scores = pd.Series(0.0, index=events_df.index)
        
        for idx, event in events_df.iterrows():
            base_score = 0
            
            # Base scores by event type and severity
            if event['event_type'] == 'frost':
                if event['severity'] == 'severe':
                    base_score = 90
                elif event['severity'] == 'moderate':
                    base_score = 70
                elif event['severity'] == 'light':
                    base_score = 50
            elif event['event_type'] == 'heat':
                if event.get('severity') == 'extreme':
                    base_score = 85
                elif event.get('severity') == 'high':
                    base_score = 65
                else:
                    base_score = 45
            elif event['event_type'] == 'rainfall':
                if event.get('severity') == 'high':
                    base_score = 80
                elif event.get('severity') == 'medium':
                    base_score = 60
                else:
                    base_score = 40
            
            # Adjust by confidence (multiply by confidence score)
            confidence = event.get('confidence', 1.0)
            adjusted_score = base_score * confidence
            
            # Cap at 100
            risk_scores[idx] = min(adjusted_score, 100.0)
        
        return risk_scores
    
    def generate_exports(self) -> List[Path]:
        """Generate all Power BI export files."""
        export_paths = []
        
        # Generate comprehensive historical export (all events)
        all_events_path = self._generate_all_events_export()
        if all_events_path:
            export_paths.append(all_events_path)
        
        # Generate current day export (today's events only)
        current_day_path = self._generate_current_day_export()
        if current_day_path:
            export_paths.append(current_day_path)
        
        return export_paths
    
    def _generate_all_events_export(self) -> Optional[Path]:
        """Generate comprehensive export of all historical events."""
        # Load all events
        events_df = self._load_all_events()
        
        if events_df.empty:
            if self.verbose:
                print("No events found for comprehensive export")
            return None
        
        # Prepare for Power BI
        export_df = self._prepare_powerbi_schema(events_df)
        
        # Write to CSV
        export_path = self.output_dir / "risk_events.csv"
        export_df.to_csv(export_path, index=False, date_format='%Y-%m-%d')
        
        if self.verbose:
            print(f"Generated comprehensive export: {export_path}")
            print(f"  - {len(export_df)} events")
            print(f"  - {export_df['station_id'].nunique()} unique stations")
            print(f"  - Date range: {export_df['date'].min()} to {export_df['date'].max()}")
        
        return export_path
    
    def _generate_current_day_export(self) -> Optional[Path]:
        """Generate export for current day events only."""
        # Load events for target date
        events_df = self._load_events_for_date(self.date)
        
        # Always create the file, even if empty (for automation stability)
        export_df = self._prepare_powerbi_schema(events_df)
        
        # Write to CSV
        export_path = self.output_dir / "risk_events_latest.csv"
        export_df.to_csv(export_path, index=False, date_format='%Y-%m-%d')
        
        if self.verbose:
            if not export_df.empty:
                print(f"Generated current day export: {export_path}")
                print(f"  - {len(export_df)} events for {self.date}")
                print(f"  - {export_df['station_id'].nunique()} unique stations")
            else:
                print(f"Generated empty current day export: {export_path}")
                print(f"  - No events detected for {self.date}")
        
        return export_path