"""Configuration Loader — hierarchical configuration management.

Loads and merges configuration from multiple sources:
1. Default settings
2. User configuration files
3. Project-specific configuration
4. Environment variables
5. Runtime overrides
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from backend.config import settings

logger = logging.getLogger("tenderclaw.runtime.config_loader")

# Configuration search paths
CONFIG_FILES = [
    # User config (highest priority)
    Path.home() / ".tenderclaw" / "config.yaml",
    Path.home() / ".tenderclaw" / "config.json",
    # Project config
    Path.cwd() / ".tenderclaw.yaml",
    Path.cwd() / ".tenderclaw.json",
    Path.cwd() / "tenderclaw.config.yaml",
    Path.cwd() / "tenderclaw.config.json",
    # Default config (lowest priority)
    Path(__file__).parent.parent.parent / "config" / "default.yaml",
]

# Environment variable prefixes
ENV_PREFIX = "TENDERCLAW_"


@dataclass
class RuntimeConfig:
    """Runtime configuration container."""
    # Model settings
    default_model: str = settings.default_model
    max_tokens: int = 16384
    temperature: float = 0.7
    
    # Session settings
    session_timeout_hours: int = 24
    auto_save_interval: int = 30  # seconds
    max_message_history: int = 100
    
    # Tool settings
    enable_tool_streaming: bool = True
    tool_timeout_seconds: int = 120
    
    # Permission settings
    default_permission_mode: str = "DEFAULT"  # TRUST, AUTO, PLAN, DEFAULT
    
    # MCP settings
    mcp_server_timeout: int = 30
    mcp_stdio_buffer_size: int = 8192
    
    # Feature flags
    enable_background_agents: bool = True
    enable_skill_auto_trigger: bool = True
    enable_workflow_enforcement: bool = True
    
    # Logging
    log_level: str = "INFO"
    enable_performance_logging: bool = False
    
    # Additional settings (for extensibility)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RuntimeConfig':
        """Create from dictionary."""
        # Filter out unknown keys to prevent errors
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered_data)


class ConfigLoader:
    """Loads configuration from multiple sources with proper precedence."""
    
    def __init__(self):
        self._config: Optional[RuntimeConfig] = None
        self._sources: List[str] = []

    def load(self) -> RuntimeConfig:
        """Load configuration from all sources with proper precedence."""
        if self._config is not None:
            return self._config
        
        # Start with default configuration
        config_data: Dict[str, Any] = {}
        sources = []
        
        # 1. Load default configuration
        default_config = self._load_default_config()
        if default_config:
            config_data.update(default_config)
            sources.append("default")
        
        # 2. Load from config files (in order of precedence)
        file_config = self._load_config_files()
        if file_config:
            config_data.update(file_config)
            sources.append("file")
        
        # 3. Load from environment variables
        env_config = self._load_env_config()
        if env_config:
            config_data.update(env_config)
            sources.append("environment")
        
        # 4. Apply runtime overrides (handled separately)
        
        self._config = RuntimeConfig.from_dict(config_data)
        self._sources = sources
        
        logger.info("Loaded configuration from sources: %s", ", ".join(sources))
        return self._config

    def _load_default_config(self) -> Dict[str, Any]:
        """Load default configuration from bundled files."""
        default_paths = [
            Path(__file__).parent.parent.parent / "config" / "default.yaml",
            Path(__file__).parent.parent.parent / "config" / "default.json",
        ]
        
        for path in default_paths:
            if path.exists():
                try:
                    if path.suffix in (".yaml", ".yml"):
                        with open(path, 'r', encoding='utf-8') as f:
                            return yaml.safe_load(f) or {}
                    elif path.suffix == ".json":
                        with open(path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                except Exception as e:
                    logger.warning("Failed to load default config from %s: %s", path, e)
        
        return {}

    def _load_config_files(self) -> Dict[str, Any]:
        """Load configuration from user and project files."""
        config_data: Dict[str, Any] = {}
        
        for path in CONFIG_FILES:
            if not path.exists():
                continue
            
            try:
                if path.suffix in (".yaml", ".yml"):
                    with open(path, 'r', encoding='utf-8') as f:
                        file_data = yaml.safe_load(f) or {}
                elif path.suffix == ".json":
                    with open(path, 'r', encoding='utf-8') as f:
                        file_data = json.load(f)
                else:
                    continue
                
                # Later files override earlier ones
                config_data.update(file_data)
                logger.debug("Loaded configuration from %s", path)
            except Exception as e:
                logger.warning("Failed to load config from %s: %s", path, e)
        
        return config_data

    def _load_env_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        config_data: Dict[str, Any] = {}
        
        for key, value in os.environ.items():
            if not key.startswith(ENV_PREFIX):
                continue
            
            # Convert TENDERCLAW_SETTING_NAME -> setting_name
            config_key = key[len(ENV_PREFIX):].lower()
            
            # Handle nested keys (e.g., TENDERCLAW_LOG_LEVEL -> log_level)
            # For simplicity, we'll handle common ones directly
            env_mapping = {
                'default_model': str,
                'max_tokens': int,
                'temperature': float,
                'session_timeout_hours': int,
                'auto_save_interval': int,
                'max_message_history': int,
                'enable_tool_streaming': lambda x: x.lower() in ('true', '1', 'yes'),
                'tool_timeout_seconds': int,
                'default_permission_mode': str,
                'mcp_server_timeout': int,
                'mcp_stdio_buffer_size': int,
                'enable_background_agents': lambda x: x.lower() in ('true', '1', 'yes'),
                'enable_skill_auto_trigger': lambda x: x.lower() in ('true', '1', 'yes'),
                'enable_workflow_enforcement': lambda x: x.lower() in ('true', '1', 'yes'),
                'log_level': str,
                'enable_performance_logging': lambda x: x.lower() in ('true', '1', 'yes'),
            }
            
            if config_key in env_mapping:
                try:
                    converter = env_mapping[config_key]
                    config_data[config_key] = converter(value)
                    logger.debug("Loaded %s from environment: %s", config_key, value)
                except Exception as e:
                    logger.warning("Failed to convert environment variable %s=%s: %s", key, value, e)
            else:
                # Store unknown env vars in extra
                if 'extra' not in config_data:
                    config_data['extra'] = {}
                config_data['extra'][config_key] = value
        
        return config_data

    def get_config(self) -> RuntimeConfig:
        """Get the current configuration, loading if necessary."""
        if self._config is None:
            return self.load()
        return self._config

    def reload(self) -> RuntimeConfig:
        """Force reload configuration from all sources."""
        self._config = None
        self._sources = []
        return self.load()

    def get_sources(self) -> List[str]:
        """Get list of configuration sources that were loaded."""
        return self._sources.copy()

    def update_runtime(self, updates: Dict[str, Any]) -> None:
        """Update runtime configuration (does not persist to disk)."""
        if self._config is None:
            self.load()
        
        current_dict = self._config.to_dict()
        current_dict.update(updates)
        self._config = RuntimeConfig.from_dict(current_dict)
        logger.debug("Applied runtime configuration updates: %s", list(updates.keys()))


# Global instance
config_loader = ConfigLoader()

def get_runtime_config() -> RuntimeConfig:
    """Get the current runtime configuration."""
    return config_loader.get_config()

def reload_config() -> RuntimeConfig:
    """Reload configuration from all sources."""
    return config_loader.reload()