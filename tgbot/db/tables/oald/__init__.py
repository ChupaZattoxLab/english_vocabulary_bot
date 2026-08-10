"""OALD content table definitions."""

from tgbot.db.tables.oald.audio_files import OaldAudioFile, oald_audio_files
from tgbot.db.tables.oald.audio_variants import OaldAudioVariant, oald_audio_variants
from tgbot.db.tables.oald.entries import OaldEntry, oald_entries
from tgbot.db.tables.oald.entry_audio_sources import (
    OaldEntryAudioSource,
    oald_entry_audio_sources,
)
from tgbot.db.tables.oald.oxford_lexical_entries import (
    OxfordLexicalEntry,
    oxford_lexical_entries,
)

__all__ = [
    "OaldAudioFile",
    "OaldAudioVariant",
    "OaldEntry",
    "OaldEntryAudioSource",
    "OxfordLexicalEntry",
    "oald_audio_files",
    "oald_audio_variants",
    "oald_entries",
    "oald_entry_audio_sources",
    "oxford_lexical_entries",
]
