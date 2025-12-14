"""
Configuration package for frankentrack.

Provides system-wide constants and user preferences management.
"""

from . import config

# Export commonly used config values
from .config import (
    # Application info
    APP_NAME,
    APP_VERSION,
    
    # Serial settings
    DEFAULT_SERIAL_PORT,
    DEFAULT_SERIAL_BAUD,
    
    # Filter parameters
    ALPHA_YAW,
    ALPHA_PITCH,
    ALPHA_ROLL,
    DEFAULT_CENTER_THRESHOLD,
    
    # Queue settings
    QUEUE_SIZE_DATA,
    QUEUE_SIZE_DISPLAY,
    QUEUE_SIZE_CONTROL,
    QUEUE_PUT_TIMEOUT,
    QUEUE_GET_TIMEOUT
)

__all__ = [
    'config',
    'APP_NAME',
    'APP_VERSION',
    'DEFAULT_SERIAL_PORT',
    'DEFAULT_SERIAL_BAUD',
    'ALPHA_YAW',
    'ALPHA_PITCH',
    'ALPHA_ROLL',
    'DEFAULT_CENTER_THRESHOLD',
    'QUEUE_SIZE_DATA',
    'QUEUE_SIZE_DISPLAY',
    'QUEUE_SIZE_CONTROL',
    'QUEUE_PUT_TIMEOUT',
    'QUEUE_GET_TIMEOUT'
]