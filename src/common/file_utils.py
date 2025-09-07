"""
File Utilities - Atomic file operations for data integrity

Provides:
- Atomic CSV write operations 
- Atomic CSV append operations
- Backup and recovery utilities
- File integrity checking
"""

import pandas as pd
import tempfile
import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def atomic_csv_write(df: pd.DataFrame, output_path: str, backup: bool = True) -> bool:
    """
    Write DataFrame to CSV atomically (write to temp, then move)
    
    Args:
        df: DataFrame to write
        output_path: Target CSV file path
        backup: Whether to create backup of existing file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create backup if file exists and backup requested
        if backup and output_path.exists():
            backup_path = output_path.with_suffix('.backup.csv')
            shutil.copy2(output_path, backup_path)
            logger.debug(f"Created backup: {backup_path}")
        
        # Write to temporary file first
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.csv',
            dir=output_path.parent,
            delete=False
        ) as temp_file:
            df.to_csv(temp_file.name, index=False)
            temp_path = Path(temp_file.name)
        
        # Atomic move
        shutil.move(temp_path, output_path)
        logger.info(f"Successfully wrote {len(df)} records to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to write CSV to {output_path}: {e}")
        return False


def atomic_csv_append(df: pd.DataFrame, output_path: str, deduplicate_column: Optional[str] = None) -> bool:
    """
    Append DataFrame to existing CSV file atomically
    
    Args:
        df: DataFrame to append
        output_path: Target CSV file path
        deduplicate_column: Column name to use for deduplication (e.g., 'date')
        
    Returns:
        True if successful, False otherwise
    """
    try:
        output_path = Path(output_path)
        
        # Read existing data if file exists
        if output_path.exists():
            existing_df = pd.read_csv(output_path)
            logger.info(f"Loaded {len(existing_df)} existing records from {output_path}")
            
            # Combine and deduplicate if requested
            if deduplicate_column and deduplicate_column in df.columns and deduplicate_column in existing_df.columns:
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=[deduplicate_column], keep='last')
                logger.info(f"Deduplicated on {deduplicate_column}: {len(combined_df)} total records")
            else:
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                logger.info(f"Appended without deduplication: {len(combined_df)} total records")
        else:
            combined_df = df.copy()
            logger.info(f"Creating new file with {len(combined_df)} records")
        
        # Use atomic write for the combined data
        return atomic_csv_write(combined_df, output_path, backup=True)
        
    except Exception as e:
        logger.error(f"Failed to append CSV to {output_path}: {e}")
        return False