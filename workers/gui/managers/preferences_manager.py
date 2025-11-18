"""
Preferences Manager for centralized GUI preference persistence.

Handles loading and saving user preferences to config/config.cfg file.
Uses atomic writes to prevent corruption if process is killed during save.
"""

import os
import configparser
from typing import Dict, Optional

from config.config import PREFS_FILE_NAME


class PreferencesManager:
    """Manages loading and saving GUI preferences to config file."""
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize preferences manager.
        
        Args:
            config_dir: Optional path to config directory. If None, will auto-detect
                       relative to project structure (../config from workers directory)
        """
        self.config_path = self._determine_config_path(config_dir)
        self._ensure_config_dir()
    
    def _determine_config_path(self, config_dir: Optional[str] = None) -> str:
        """Determine the full path to the config file.
        
        Args:
            config_dir: Optional explicit config directory path
            
        Returns:
            Full path to config.cfg file
        """
        if config_dir:
            return os.path.join(config_dir, PREFS_FILE_NAME)
        
        # Auto-detect: go up from workers/gui/managers to project root
        try:
            current = os.path.dirname(__file__)  # .../workers/gui/managers
            workers_gui = os.path.dirname(current)  # .../workers/gui
            workers = os.path.dirname(workers_gui)  # .../workers
            project_root = os.path.dirname(workers)  # .../acceltrack
            cfg_dir = os.path.join(project_root, 'config')
            return os.path.join(cfg_dir, PREFS_FILE_NAME)
        except Exception:
            # Fallback to current directory
            return PREFS_FILE_NAME
    
    def _ensure_config_dir(self):
        """Ensure the config directory exists."""
        config_dir = os.path.dirname(self.config_path)
        if config_dir and not os.path.exists(config_dir):
            try:
                os.makedirs(config_dir, exist_ok=True)
            except Exception:
                pass
    
    def load(self) -> Dict[str, str]:
        """Load preferences from config file.
        
        Returns:
            Dictionary of preference key-value pairs from [gui] section.
            Returns empty dict if file doesn't exist or can't be read.
        """
        if not os.path.exists(self.config_path):
            return {}
        
        cfg = configparser.ConfigParser()
        try:
            cfg.read(self.config_path)
            if 'gui' not in cfg:
                return {}
            
            # Convert ConfigParser section to plain dict
            return dict(cfg['gui'])
        except Exception as e:
            print(f"[PreferencesManager] Error loading preferences: {e}")
            return {}
    
    def save(self, preferences: Dict[str, str]) -> bool:
        """Save preferences to config file using atomic write.
        
        Args:
            preferences: Dictionary of preference key-value pairs to save
            
        Returns:
            True if save succeeded, False otherwise
        """
        cfg = configparser.ConfigParser()
        cfg['gui'] = {str(k): str(v) for k, v in preferences.items()}
        
        tmp_path = self.config_path + '.tmp'
        
        try:
            # Write to temporary file first
            with open(tmp_path, 'w', encoding='utf-8') as f:
                cfg.write(f)
            
            # Atomic replace (or fallback to non-atomic)
            try:
                os.replace(tmp_path, self.config_path)
            except Exception:
                # Fallback for systems where replace might fail
                try:
                    if os.path.exists(self.config_path):
                        os.remove(self.config_path)
                except Exception:
                    pass
                try:
                    os.rename(tmp_path, self.config_path)
                except Exception:
                    # Last resort: copy contents
                    with open(tmp_path, 'r', encoding='utf-8') as fr:
                        with open(self.config_path, 'w', encoding='utf-8') as fw:
                            fw.write(fr.read())
            
            return True
            
        except Exception as e:
            print(f"[PreferencesManager] Error saving preferences: {e}")
            # Clean up temp file
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return False
    
    def get(self, key: str, default: str = '') -> str:
        """Get a single preference value.
        
        Args:
            key: Preference key to retrieve
            default: Default value if key not found
            
        Returns:
            Preference value or default
        """
        prefs = self.load()
        return prefs.get(key, default)
    
    def set(self, key: str, value: str) -> bool:
        """Set a single preference value.
        
        Args:
            key: Preference key to set
            value: Preference value to set
            
        Returns:
            True if save succeeded
        """
        prefs = self.load()
        prefs[key] = str(value)
        return self.save(prefs)
    
    def update(self, updates: Dict[str, str]) -> bool:
        """Update multiple preference values at once.
        
        Args:
            updates: Dictionary of key-value pairs to update
            
        Returns:
            True if save succeeded
        """
        prefs = self.load()
        prefs.update({str(k): str(v) for k, v in updates.items()})
        return self.save(prefs)
    
    def delete(self, key: str) -> bool:
        """Delete a preference key.
        
        Args:
            key: Preference key to delete
            
        Returns:
            True if save succeeded
        """
        prefs = self.load()
        if key in prefs:
            del prefs[key]
            return self.save(prefs)
        return True  # Key didn't exist, nothing to do
    
    def clear(self) -> bool:
        """Clear all preferences.
        
        Returns:
            True if save succeeded
        """
        return self.save({})
    
    def exists(self) -> bool:
        """Check if preferences file exists.
        
        Returns:
            True if config file exists
        """
        return os.path.exists(self.config_path)
