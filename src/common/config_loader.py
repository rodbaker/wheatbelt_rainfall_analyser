"""
Configuration Loader - YAML configuration file handling

Provides centralized configuration loading for all agents with:
- YAML file parsing with error handling
- Environment variable substitution  
- Local override support (*.local.yaml files)
- Configuration validation and defaults
"""

import yaml
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def load_config(config_path: str, allow_local_override: bool = True) -> Dict[str, Any]:
    """
    Load YAML configuration file with optional local overrides
    
    Args:
        config_path: Path to main configuration file
        allow_local_override: Whether to look for and merge .local.yaml files
        
    Returns:
        Loaded and merged configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    config_path = Path(config_path)
    
    # Load main configuration
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        logger.info(f"Loaded configuration from {config_path}")
        
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Invalid YAML in {config_path}: {e}")
        
    # Apply environment variable substitutions
    config = _substitute_env_variables(config)
    
    # Load local override if it exists and is allowed
    if allow_local_override:
        local_config_path = config_path.with_suffix('.local.yaml')
        if local_config_path.exists():
            try:
                with open(local_config_path, 'r') as f:
                    local_config = yaml.safe_load(f)
                    
                config = _merge_configs(config, local_config)
                logger.info(f"Applied local overrides from {local_config_path}")
                
            except yaml.YAMLError as e:
                logger.warning(f"Invalid YAML in local override {local_config_path}: {e}")
                
    # Validate configuration structure
    _validate_config(config, config_path)
    
    return config


def _substitute_env_variables(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively substitute environment variables in config values
    
    Supports ${VAR_NAME} and ${VAR_NAME:default_value} syntax
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Configuration with environment variables substituted
    """
    if isinstance(config, dict):
        return {k: _substitute_env_variables(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [_substitute_env_variables(item) for item in config]
    elif isinstance(config, str):
        # Simple environment variable substitution
        if config.startswith('${') and config.endswith('}'):
            env_expr = config[2:-1]
            
            if ':' in env_expr:
                # Default value syntax: ${VAR:default}
                var_name, default_value = env_expr.split(':', 1)
                return os.getenv(var_name, default_value)
            else:
                # Simple syntax: ${VAR}
                var_value = os.getenv(env_expr)
                if var_value is None:
                    logger.warning(f"Environment variable {env_expr} not set")
                    return config  # Return original if not found
                return var_value
        return config
    else:
        return config


def _merge_configs(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge override configuration into base configuration
    
    Args:
        base_config: Base configuration dictionary
        override_config: Override configuration dictionary
        
    Returns:
        Merged configuration dictionary
    """
    merged = base_config.copy()
    
    for key, value in override_config.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            merged[key] = _merge_configs(merged[key], value)
        else:
            # Override or add new key
            merged[key] = value
            
    return merged


def _validate_config(config: Dict[str, Any], config_path: Path) -> None:
    """
    Validate configuration structure and required fields
    
    Args:
        config: Configuration dictionary to validate
        config_path: Path to config file for error messages
        
    Raises:
        ValueError: If configuration is invalid
    """
    if not isinstance(config, dict):
        raise ValueError(f"Configuration must be a dictionary in {config_path}")
        
    # Determine config type and apply appropriate validation
    config_name = config_path.stem
    
    if config_name == 'silo_sources':
        _validate_silo_config(config, config_path)
    elif config_name == 'crop_calendars':
        _validate_crop_calendar_config(config, config_path)
    elif config_name == 'assumptions':
        _validate_assumptions_config(config, config_path)
    else:
        logger.info(f"No specific validation for config type: {config_name}")


def _validate_silo_config(config: Dict[str, Any], config_path: Path) -> None:
    """Validate SILO sources configuration"""
    required_sections = ['api', 'variables', 'stations', 'output']
    
    for section in required_sections:
        if section not in config:
            raise ValueError(f"Missing required section '{section}' in {config_path}")
            
    # API configuration validation
    api_config = config['api']
    required_api_fields = ['base_url', 'username']
    
    for field in required_api_fields:
        if field not in api_config:
            raise ValueError(f"Missing required API field '{field}' in {config_path}")
            
    # Variables validation
    if not config['variables']:
        raise ValueError(f"No variables configured in {config_path}")
        
    # Stations validation  
    if not config['stations']:
        logger.warning(f"No stations configured in {config_path}")
        

def _validate_crop_calendar_config(config: Dict[str, Any], config_path: Path) -> None:
    """Validate crop calendar configuration"""
    if 'wheat' not in config:
        raise ValueError(f"Missing 'wheat' section in {config_path}")
        
    wheat_config = config['wheat']
    if 'stages' not in wheat_config:
        raise ValueError(f"Missing 'stages' section in wheat config in {config_path}")


def _validate_assumptions_config(config: Dict[str, Any], config_path: Path) -> None:
    """Validate assumptions configuration"""
    required_sections = ['detection', 'thresholds']
    
    for section in required_sections:
        if section not in config:
            logger.warning(f"Missing recommended section '{section}' in {config_path}")


def get_config_value(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """
    Get configuration value using dot notation path
    
    Args:
        config: Configuration dictionary
        key_path: Dot-separated path to value (e.g., 'api.base_url')
        default: Default value if path not found
        
    Returns:
        Configuration value or default
        
    Example:
        >>> config = {'api': {'base_url': 'https://example.com'}}
        >>> get_config_value(config, 'api.base_url')
        'https://example.com'
        >>> get_config_value(config, 'api.timeout', 30)
        30
    """
    keys = key_path.split('.')
    value = config
    
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        return default