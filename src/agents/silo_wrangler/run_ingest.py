"""
Daily Ingest Runner - Main execution script for SILO Wrangler agent

Orchestrates:
- Configuration loading
- API data retrieval for all configured stations  
- Data processing and quality checking
- CSV output and run logging
- Error handling and recovery
"""

import click
import logging
import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from src.common.config_loader import load_config
from src.common.logging_utils import setup_logging
from src.common.stations_loader import load_wheatbelt_stations_for_config, generate_data_drill_grid
from src.data.duckdb_storage import DuckDBStorage
from src.agents.silo_wrangler.api_client import SILOAPIClient
from src.agents.silo_wrangler.data_processor import WeatherDataProcessor
from src.agents.silo_wrangler.quality_checker import DataQualityChecker

logger = logging.getLogger(__name__)


@click.command()
@click.option('--config', '-c', default='config/silo_sources.yaml', help='Path to SILO configuration file')
@click.option('--date', 'target_date', default=None, help='Fetch data for a specific date (YYYY-MM-DD). Overrides --days and rolling-window mode.')
@click.option('--stations', '-s', help='Comma-separated station IDs to process (overrides config)')
@click.option('--days', '-d', type=int, help='Number of days to retrieve (overrides config)')
@click.option('--tiers', default='active', help='Station tiers to include: active,unverified,inactive,all (default: active)')
@click.option('--include-poor', is_flag=True, help='Include stations with poor data quality (overrides auto-filtering)')
@click.option('--use-bom-dataset', is_flag=True, help='Use BOM wheatbelt stations dataset instead of config stations')
@click.option('--states', help='Comma-separated state names when using BOM dataset (e.g., "Western Australia,South Australia")')
@click.option('--sample-size', type=int, help='Random sample size from BOM dataset for testing')
@click.option('--sample-seed', type=int, help='Random seed for reproducible sampling')
@click.option('--min-cropping-area', type=int, help='Minimum cropping area (hectares) for station filtering')
@click.option('--dry-run', is_flag=True, help='Run without writing output files (skips Data Drill API calls)')
@click.option('--hybrid', is_flag=True, help='Gap-fill with SILO Data Drill after PPD station ingestion')
@click.option('--hybrid-states', help='Comma-separated state names to run Data Drill for (e.g., "Western Australia"). Defaults to all wheatbelt_bounds regions.')
@click.option('--dd-max-points', type=int, default=None, help='Limit Data Drill grid points (useful for testing)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def run_daily_ingest(config: str, target_date: str, stations: str, days: int, tiers: str, include_poor: bool,
                    use_bom_dataset: bool, states: str, sample_size: int, sample_seed: int,
                    min_cropping_area: int, dry_run: bool, hybrid: bool, hybrid_states: str,
                    dd_max_points: int, verbose: bool):
    """
    Run daily SILO data ingestion for configured stations
    
    This is the main entry point for the SILO Wrangler agent.
    Retrieves weather data from SILO API and produces clean CSV outputs.
    """
    # Setup logging
    log_level = logging.DEBUG if verbose else logging.INFO
    setup_logging(log_level)
    
    logger.info("Starting SILO Wrangler daily ingestion")
    if target_date:
        logger.info(f"Target date override: {target_date}")
    
    try:
        # Load configuration
        silo_config = load_config(config)
        logger.info(f"Loaded configuration from {config}")
        
        # Load stations based on CLI options or configuration
        if stations:
            # Direct station ID override
            station_list = {s.strip(): f"CLI_{s.strip()}" for s in stations.split(',')}
            silo_config['stations'] = station_list
            logger.info(f"Using CLI-provided stations: {list(station_list.keys())}")
        elif use_bom_dataset:
            # Use BOM wheatbelt dataset with filtering
            filter_params = {}
            
            if states:
                filter_params['states'] = [s.strip() for s in states.split(',')]
            
            if sample_size:
                filter_params['sample_size'] = sample_size
                
            if sample_seed is not None:
                filter_params['sample_seed'] = sample_seed
                
            if min_cropping_area:
                filter_params['min_cropping_area'] = min_cropping_area
            
            # Warning when no state filter is applied
            if not states and sample_size:
                logger.warning(f"No --states filter specified with BOM dataset sampling. "
                             f"Will sample {sample_size} stations from ALL states (WA, SA, NSW, QLD, VIC, TAS). "
                             f"To filter by state, use: --states 'Western Australia'")
            
            station_list = load_wheatbelt_stations_for_config(filter_params)
            silo_config['stations'] = station_list
            
            # Show actual states represented in the final selection
            from src.common.stations_loader import WheatbeltStationsLoader
            loader = WheatbeltStationsLoader()
            actual_states = set()
            for station_id in station_list.keys():
                station_info = loader.get_station_info(station_id)
                if station_info:
                    actual_states.add(station_info.state_name)
            
            filter_desc = []
            if 'states' in filter_params:
                filter_desc.append(f"states: {filter_params['states']}")
            else:
                filter_desc.append("states: ALL (WA, SA, NSW, QLD, VIC, TAS)")
            if 'sample_size' in filter_params:
                filter_desc.append(f"sample: {filter_params['sample_size']}")
            if 'min_cropping_area' in filter_params:
                filter_desc.append(f"min_area: {filter_params['min_cropping_area']}ha")
            
            filter_str = ", ".join(filter_desc) if filter_desc else "no filters"
            actual_states_str = ", ".join(sorted(actual_states))
            logger.info(f"Using BOM wheatbelt dataset: {len(station_list)} stations loaded ({filter_str})")
            logger.info(f"Final selection includes stations from: {actual_states_str}")
        else:
            # Load stations by tier from config
            station_list = load_stations_by_tier(silo_config, tiers)
            silo_config['stations'] = station_list
            logger.info(f"Using {tiers} tier stations: {len(station_list)} stations loaded")
            
        # Initialize agents
        api_client = SILOAPIClient(silo_config)
        data_processor = WeatherDataProcessor(silo_config)
        quality_checker = DataQualityChecker(silo_config)
        storage = DuckDBStorage({'database_path': 'data/weather.duckdb'})
        
        # Prepare run metadata
        run_metadata = {
            'run_id': f"silo_ingest_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'start_time': datetime.now().isoformat(),
            'config_file': config,
            'stations_requested': list(silo_config['stations'].keys()),
            'collection_mode': silo_config['collection']['mode'],
            'variables': list(silo_config['variables'].keys())
        }
        
        # Process each station
        successful_stations = []
        failed_stations = []
        total_records = 0
        
        for station_id, station_name in silo_config['stations'].items():
            logger.info(f"Processing station {station_id} ({station_name})")
            
            try:
                # Determine date range based on collection mode
                if target_date:
                    # Explicit date override — fetch exactly one day
                    _d = target_date.replace('-', '')
                    raw_data = api_client.get_daily_data(station_id, _d, _d)
                elif days:
                    # CLI override
                    raw_data = api_client.get_rolling_window_data(station_id, days)
                elif silo_config['collection']['mode'] == 'rolling_window':
                    rolling_days = silo_config['collection']['rolling_days']
                    raw_data = api_client.get_rolling_window_data(station_id, rolling_days)
                else:
                    # Default to yesterday for daily operations
                    raw_data = api_client.get_yesterday_data(station_id)
                
                if raw_data is None or raw_data.empty:
                    logger.warning(f"No data retrieved for station {station_id}")
                    failed_stations.append({
                        'station_id': station_id,
                        'error': 'no_data_retrieved',
                        'timestamp': datetime.now().isoformat()
                    })
                    continue
                    
                # Process the raw data
                processed_data = data_processor.process_station_data(raw_data, station_id)
                
                if processed_data.empty:
                    logger.warning(f"No processable data for station {station_id}")
                    failed_stations.append({
                        'station_id': station_id, 
                        'error': 'processing_failed',
                        'timestamp': datetime.now().isoformat()
                    })
                    continue
                
                # Quality assessment
                quality_assessment = quality_checker.assess_data_quality(processed_data, station_id)
                logger.info(f"Station {station_id}: {quality_assessment['overall_quality']} quality, "
                           f"confidence={quality_assessment['confidence_score']:.2f}")
                
                # Check for automatic exclusion of poor quality stations
                auto_exclude = silo_config.get('quality', {}).get('auto_exclude_poor_stations', False)
                min_confidence = silo_config.get('quality', {}).get('min_confidence_threshold', 0.3)
                
                if auto_exclude and not include_poor and quality_assessment['confidence_score'] < min_confidence:
                    logger.warning(f"Station {station_id} excluded due to low confidence score "
                                 f"({quality_assessment['confidence_score']:.2f} < {min_confidence}). "
                                 f"Use --include-poor to override.")
                    failed_stations.append({
                        'station_id': station_id,
                        'error': f'auto_excluded_low_confidence_{quality_assessment["confidence_score"]:.2f}',
                        'timestamp': datetime.now().isoformat()
                    })
                    continue
                
                # Apply quality filtering
                filtered_data = quality_checker.filter_by_quality(processed_data)
                
                # Write to output files (unless dry run)
                if not dry_run:
                    success = data_processor.append_to_daily_observations(filtered_data)
                    if success:
                        # Also write to DuckDB — rename CSV columns to match DuckDB schema
                        duckdb_df = filtered_data.rename(columns={
                            'min_temperature': 'min_temp',
                            'max_temperature': 'max_temp',
                            'min_temperature_quality': 'min_temp_quality',
                            'max_temperature_quality': 'max_temp_quality',
                            'timestamp_processed': 'ingested_at',
                        })
                        duckdb_cols = ['station_id', 'date', 'min_temp', 'max_temp', 'rainfall',
                                       'min_temp_quality', 'max_temp_quality', 'rainfall_quality', 'ingested_at']
                        storage.upsert_observations(duckdb_df[[c for c in duckdb_cols if c in duckdb_df.columns]])
                    if success:
                        successful_stations.append({
                            'station_id': station_id,
                            'station_name': station_name,
                            'records_processed': len(filtered_data),
                            'quality_assessment': quality_assessment,
                            'timestamp': datetime.now().isoformat()
                        })
                        total_records += len(filtered_data)
                        logger.info(f"Successfully processed {len(filtered_data)} records for station {station_id}")
                    else:
                        failed_stations.append({
                            'station_id': station_id,
                            'error': 'output_write_failed',
                            'timestamp': datetime.now().isoformat()
                        })
                else:
                    # Dry run - just log what would be done
                    successful_stations.append({
                        'station_id': station_id,
                        'station_name': station_name, 
                        'records_processed': len(filtered_data),
                        'quality_assessment': quality_assessment,
                        'timestamp': datetime.now().isoformat(),
                        'dry_run': True
                    })
                    total_records += len(filtered_data)
                    logger.info(f"[DRY RUN] Would process {len(filtered_data)} records for station {station_id}")
                    
            except Exception as e:
                logger.error(f"Error processing station {station_id}: {e}", exc_info=True)
                failed_stations.append({
                    'station_id': station_id,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
                
        # --- DATA DRILL GAP-FILL (--hybrid mode) ---
        if hybrid and dry_run:
            logger.info("Hybrid mode: [DRY RUN] skipping Data Drill API calls — use without --dry-run to ingest")
        elif hybrid:
            dd_config = silo_config.get('data_drill', {})
            bounds_list = dd_config.get('wheatbelt_bounds', [])
            if hybrid_states:
                hs = [s.strip() for s in hybrid_states.split(',')]
                bounds_list = [b for b in bounds_list if b.get('name') in hs]
                logger.info(f"Data Drill: restricted to {[b['name'] for b in bounds_list]} via --hybrid-states")
            resolution = dd_config.get('grid_resolution_deg', 0.5)
            proximity = dd_config.get('proximity_threshold_deg', 0.4)

            # Use all 1,376 wheatbelt stations (not just this run's stations) for
            # proximity suppression — avoids querying Data Drill near real stations
            # even if we didn't ingest them today.
            from src.common.stations_loader import WheatbeltStationsLoader
            bom_loader = WheatbeltStationsLoader()
            all_station_coords = bom_loader.get_all_station_coords()

            geojson_path = dd_config.get('wheatbelt_geojson')
            gap_points = generate_data_drill_grid(
                bounds_list=bounds_list,
                resolution=resolution,
                existing_coords=all_station_coords,
                proximity_threshold=proximity,
                geojson_path=geojson_path,
            )
            if dd_max_points and len(gap_points) > dd_max_points:
                logger.info(f"Data Drill: limiting to {dd_max_points} of {len(gap_points)} gap points (--dd-max-points)")
                gap_points = gap_points[:dd_max_points]
            logger.info(f"Data Drill: {len(gap_points)} gap points to ingest")

            # Determine date range (reuse same logic as PPD stations)
            from datetime import datetime as _dt
            if target_date:
                _d = target_date.replace('-', '')
                _start = _d
                _end = _d
            elif days:
                _end = _dt.now().strftime('%Y%m%d')
                _start = (_dt.now() - __import__('datetime').timedelta(days=days)).strftime('%Y%m%d')
            elif silo_config['collection']['mode'] == 'rolling_window':
                _rolling = silo_config['collection']['rolling_days']
                _end = _dt.now().strftime('%Y%m%d')
                _start = (_dt.now() - __import__('datetime').timedelta(days=_rolling)).strftime('%Y%m%d')
            else:
                _yesterday = (_dt.now() - __import__('datetime').timedelta(days=1)).strftime('%Y%m%d')
                _start = _yesterday
                _end = _yesterday

            dd_success = 0
            dd_failed = 0
            for lat, lon in gap_points:
                synthetic_id = f"DD_{lat:.2f}_{lon:.2f}"
                try:
                    raw_data = api_client.get_data_drill_data(lat, lon, _start, _end)
                    if raw_data is None or raw_data.empty:
                        logger.warning(f"No Data Drill data for ({lat}, {lon})")
                        dd_failed += 1
                        continue

                    processed_data = data_processor.process_station_data(raw_data, synthetic_id)
                    if processed_data.empty:
                        dd_failed += 1
                        continue

                    # Skip auto-exclusion for Data Drill: 100% interpolated is expected
                    filtered_data = quality_checker.filter_by_quality(processed_data)

                    if not dry_run:
                        success = data_processor.append_to_daily_observations(filtered_data)
                        if success:
                            duckdb_df = filtered_data.rename(columns={
                                'min_temperature': 'min_temp',
                                'max_temperature': 'max_temp',
                                'min_temperature_quality': 'min_temp_quality',
                                'max_temperature_quality': 'max_temp_quality',
                                'timestamp_processed': 'ingested_at',
                            })
                            duckdb_cols = ['station_id', 'date', 'min_temp', 'max_temp', 'rainfall',
                                           'min_temp_quality', 'max_temp_quality', 'rainfall_quality', 'ingested_at']
                            storage.upsert_observations(duckdb_df[[c for c in duckdb_cols if c in duckdb_df.columns]])
                            dd_success += 1
                            total_records += len(filtered_data)
                        else:
                            dd_failed += 1
                    else:
                        dd_success += 1
                        total_records += len(filtered_data)
                        logger.info(f"[DRY RUN] Would write {len(filtered_data)} Data Drill records for {synthetic_id}")

                except Exception as e:
                    logger.error(f"Data Drill error for ({lat}, {lon}): {e}", exc_info=True)
                    dd_failed += 1

            logger.info(f"Data Drill gap-fill: {dd_success} points succeeded, {dd_failed} failed")
            run_metadata['data_drill'] = {'points_success': dd_success, 'points_failed': dd_failed}

        # Complete run metadata
        run_metadata.update({
            'end_time': datetime.now().isoformat(),
            'successful_stations': successful_stations,
            'failed_stations': failed_stations,
            'total_records_processed': total_records,
            'success_rate': len(successful_stations) / len(silo_config['stations']) if silo_config['stations'] else 0.0
        })
        
        # Log run results
        if not dry_run:
            log_run_results(run_metadata, silo_config['output']['run_log'])
        
        # Summary
        logger.info(f"SILO Wrangler ingestion completed:")
        logger.info(f"  Successful stations: {len(successful_stations)}")
        logger.info(f"  Failed stations: {len(failed_stations)}")
        logger.info(f"  Total records: {total_records}")
        
        if dry_run:
            logger.info("  [DRY RUN] No files were written")
            
    except Exception as e:
        logger.error(f"Fatal error in SILO Wrangler ingestion: {e}", exc_info=True)
        raise click.ClickException(f"Ingestion failed: {e}")


def load_stations_by_tier(silo_config: Dict[str, Any], tiers: str) -> Dict[str, str]:
    """
    Load stations from configuration based on tier selection
    
    Args:
        silo_config: SILO configuration dictionary
        tiers: Comma-separated tier names (active, unverified, inactive, all)
        
    Returns:
        Dict mapping station_id to station_name for selected tiers
    """
    station_list = {}
    tier_names = [t.strip().lower() for t in tiers.split(',')]
    
    # Handle 'all' tier
    if 'all' in tier_names:
        tier_names = ['active', 'unverified', 'inactive']
    
    # Load stations from each requested tier
    for tier in tier_names:
        if tier in silo_config.get('stations', {}):
            tier_stations = silo_config['stations'][tier]
            station_list.update(tier_stations)
            logger.info(f"Loaded {len(tier_stations)} stations from '{tier}' tier")
        else:
            logger.warning(f"Tier '{tier}' not found in configuration")
    
    # Apply automatic quality filtering if enabled
    if silo_config.get('quality', {}).get('auto_exclude_poor_stations', False):
        logger.info("Automatic quality filtering is enabled - poor quality stations will be filtered during processing")
    
    return station_list


def log_run_results(run_metadata: Dict[str, Any], log_file_path: str):
    """
    Log run results to JSONL file for tracking and monitoring
    
    Args:
        run_metadata: Run results and metadata
        log_file_path: Path to JSONL log file
    """
    try:
        log_path = Path(log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Append run metadata as JSON line
        with open(log_path, 'a') as f:
            f.write(json.dumps(run_metadata) + '\\n')
            
        logger.info(f"Run metadata logged to {log_path}")
        
    except Exception as e:
        logger.error(f"Failed to log run metadata: {e}")


if __name__ == '__main__':
    run_daily_ingest()