"""
Vertical Video Recipes Module

Shared processing for ALL vertical video recipe parsers.
Source-agnostic recipe parsing from caption + transcript.

Used by:
- Instagram Parser
- TikTok Parser
- Facebook Parser (future)
- YouTube Parser (future)
"""

from .vertical_video_processor import VerticalVideoProcessor

__all__ = ['VerticalVideoProcessor']
