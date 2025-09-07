"""
Logging Utilities - Standardized logging setup for all agents

Provides:
- Consistent logging format across all agents
- File and console logging configuration  
- Log level management
- Structured logging for operational monitoring
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None,
    include_console: bool = True
) -> None:
    """
    Set up standardized logging for CropForecaster agents
    
    Args:
        level: Logging level (logging.DEBUG, logging.INFO, etc.)
        log_file: Optional file path for file logging
        format_string: Custom format string (uses default if None)
        include_console: Whether to include console output
    """
    # Default format optimized for operational monitoring
    if format_string is None:
        format_string = (
            '%(asctime)s - %(name)s - %(levelname)s - '
            '[%(filename)s:%(lineno)d] - %(message)s'
        )
        
    # Create formatter
    formatter = logging.Formatter(format_string)
    
    # Get root logger and clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    
    # Console handler
    if include_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
    # File handler with rotation
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use rotating file handler to prevent huge log files
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
    # Set specific logger levels for external libraries
    _configure_external_loggers()
    
    logging.info(f"Logging initialized: level={logging.getLevelName(level)}, "
                f"console={include_console}, file={log_file}")


def _configure_external_loggers():
    """Configure logging levels for external libraries to reduce noise"""
    
    # Reduce requests library verbosity
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    # Reduce pandas verbosity
    logging.getLogger('pandas').setLevel(logging.WARNING)
    
    # Keep our own loggers at configured level
    cropforecaster_loggers = [
        'src.agents.silo_wrangler',
        'src.agents.risk_engine', 
        'src.agents.insight_publisher',
        'src.common'
    ]
    
    for logger_name in cropforecaster_loggers:
        logger = logging.getLogger(logger_name)
        # Don't set level - inherit from root


def get_agent_logger(agent_name: str) -> logging.Logger:
    """
    Get a logger instance for a specific agent
    
    Args:
        agent_name: Name of the agent (silo_wrangler, risk_engine, insight_publisher)
        
    Returns:
        Configured logger instance for the agent
    """
    return logging.getLogger(f'src.agents.{agent_name}')


def log_agent_start(agent_name: str, config_info: dict) -> None:
    """
    Log standardized agent startup information
    
    Args:
        agent_name: Name of the starting agent
        config_info: Dictionary with configuration summary
    """
    logger = get_agent_logger(agent_name)
    logger.info(f"=== {agent_name.upper()} AGENT STARTING ===")
    
    for key, value in config_info.items():
        logger.info(f"Config - {key}: {value}")


def log_agent_completion(agent_name: str, results_summary: dict) -> None:
    """
    Log standardized agent completion information
    
    Args:
        agent_name: Name of the completed agent
        results_summary: Dictionary with execution results
    """
    logger = get_agent_logger(agent_name)
    
    for key, value in results_summary.items():
        logger.info(f"Result - {key}: {value}")
        
    logger.info(f"=== {agent_name.upper()} AGENT COMPLETED ===")


def log_error_with_context(logger: logging.Logger, error: Exception, context: dict) -> None:
    """
    Log error with additional context information
    
    Args:
        logger: Logger instance to use
        error: Exception that occurred
        context: Dictionary with context information
    """
    logger.error(f"Error occurred: {error}")
    
    for key, value in context.items():
        logger.error(f"Context - {key}: {value}")
        
    # Log full traceback at debug level
    logger.debug("Full traceback:", exc_info=True)