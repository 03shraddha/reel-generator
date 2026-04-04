"""Deprecated: use tts.py directly.

This module is a compatibility shim only. No new code should import from here.
Import generate_voiceover from verticals.tts instead.
"""

from pathlib import Path
from .tts import generate_voiceover

__all__ = ["generate_voiceover"]
