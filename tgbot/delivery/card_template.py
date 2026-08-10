"""Safe, reloadable HTML card template rendering."""

from __future__ import annotations

import html
import string
from collections.abc import Mapping
from pathlib import Path

from tgbot.delivery.types import TELEGRAM_MESSAGE_MAX_LEN

# Placeholders aligned with oald_entries / Card fields (+ display helpers).
WORD_FIELDS = frozenset({"word", "word_us", "word_gb"})
IPA_FIELDS = frozenset({"ipa", "ipa_us", "ipa_gb"})
BOTH_IPA_FIELDS = IPA_FIELDS - {"ipa"}
REQUIRED_FIELDS = frozenset(
    {
        "lexical_category",
        "cefr",
        "definition",
        "example",
        "translation",
    }
)
DISPLAY_FIELDS = frozenset(
    {
        "dialect",
        "dialect_flag",
        "heading_definition",
        "heading_example",
        "heading_translation",
        "flag_us",
        "flag_gb",
    }
)
ALLOWED_FIELDS = WORD_FIELDS | IPA_FIELDS | REQUIRED_FIELDS | DISPLAY_FIELDS


class CardTemplateError(ValueError):
    """Raised when a card template is missing or unsafe."""


class CardTemplate:
    def __init__(self, path: Path):
        self.path = path
        self.mtime_ns = -1
        self.template = ""
        self.load_if_changed()

    def render(self, values: Mapping[str, str]) -> str:
        self.load_if_changed()
        escaped = {
            field: html.escape(str(values.get(field, "")), quote=False)
            for field in ALLOWED_FIELDS
        }
        rendered = self.template.format_map(escaped)
        if len(rendered) > TELEGRAM_MESSAGE_MAX_LEN:
            raise CardTemplateError(
                "rendered card exceeds Telegram's "
                f"{TELEGRAM_MESSAGE_MAX_LEN}-character text limit"
            )
        return rendered

    def load_if_changed(self) -> None:
        """Reload from disk when the template file mtime changes."""
        try:
            mtime_ns = self.path.stat().st_mtime_ns
        except OSError as exc:
            raise CardTemplateError(
                f"could not read card template {self.path}: {exc}"
            ) from exc

        if mtime_ns == self.mtime_ns:
            return

        self.template = load_template(self.path)
        self.mtime_ns = mtime_ns


def load_template(path: Path) -> str:
    """Read and validate a card template file."""
    try:
        template = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CardTemplateError(f"could not read card template {path}: {exc}") from exc

    if not template:
        raise CardTemplateError("card template must not be empty")

    fields = template_fields(template)
    missing = sorted(REQUIRED_FIELDS - fields)
    if missing:
        raise CardTemplateError(
            f"card template is missing required fields: {', '.join(missing)}"
        )
    if not fields & WORD_FIELDS:
        raise CardTemplateError("card template must contain at least one word field")
    if "ipa" not in fields and not BOTH_IPA_FIELDS.issubset(fields):
        raise CardTemplateError(
            "card template must contain {ipa}, or both {ipa_us} and {ipa_gb}"
        )
    return template


def template_fields(template: str) -> set[str]:
    """Collect `{field}` names; reject unknown or formatted placeholders."""
    fields: set[str] = set()
    try:
        for _, field_name, format_spec, conversion in string.Formatter().parse(
            template
        ):
            if field_name is None:
                continue
            if field_name not in ALLOWED_FIELDS:
                raise CardTemplateError(
                    f"unsupported card template field {field_name!r}"
                )
            if format_spec or conversion:
                raise CardTemplateError(
                    "format specifications and conversions are not allowed"
                )
            fields.add(field_name)
    except ValueError as exc:
        raise CardTemplateError(f"invalid card template: {exc}") from exc
    return fields
