"""OALD content table definitions."""

from tgbot.db.schema.oald.audio_files import oald_audio_files
from tgbot.db.schema.oald.audio_variants import oald_audio_variants
from tgbot.db.schema.oald.entries import oald_entries
from tgbot.db.schema.oald.entry_audio_sources import oald_entry_audio_sources
from tgbot.db.schema.oald.oxford_lexical_entries import oxford_lexical_entries

__all__ = [
    "oald_audio_files",
    "oald_audio_variants",
    "oald_entries",
    "oald_entry_audio_sources",
    "oxford_lexical_entries",
]
