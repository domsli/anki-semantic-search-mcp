"""Turn Anki field HTML into the passage that gets embedded."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser

from anki_semantic_search.anki import RawNote
from anki_semantic_search.config import FieldMap

_SOUND = re.compile(r"\[sound:[^\]]*\]", re.IGNORECASE)
_CLOZE = re.compile(r"\{\{c\d+::(.*?)(?:::[^}]*)?\}\}", re.DOTALL)
_URL = re.compile(r"^https?://\S+$", re.IGNORECASE)
_SPACE = re.compile(r"[ \t]+")
_IGNORED_TAGS = {"script", "style", "rp"}
_BREAK_TAGS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4"}


@dataclass(frozen=True)
class NormalizedNote:
    note_id: int
    model_name: str
    tags: tuple[str, ...]
    deck_names: tuple[str, ...]
    word: str
    reading: str
    definition: str
    extra: str
    passage: str
    added_at: datetime
    introduced_at: datetime | None


def normalize_note(note: RawNote, fields: FieldMap) -> NormalizedNote:
    """Map a note's fields onto word, reading, definition, and extra text.

    A field name that matches none of the configured roles is still kept.
    When neither the word nor the definition matches, the passage is labeled
    with the original Anki field names so a rename does not drop the text.
    """
    cleaned: dict[str, str] = {}
    for name, html in note.fields.items():
        if _matches(name, fields.skip):
            continue
        text = html_to_text(html)
        if not text or _is_url_only(text):
            continue
        cleaned[name] = text

    used: set[str] = set()
    word = _take(cleaned, fields.word, used)
    reading = _take(cleaned, fields.reading, used)
    definition = _take(cleaned, fields.definition, used)
    mapped_extra = _take(cleaned, fields.extra, used)
    leftovers = [(name, text) for name, text in cleaned.items() if name not in used]

    if word or definition:
        extra_parts = [part for part in (mapped_extra, *(text for _, text in leftovers)) if part]
        extra = "\n".join(extra_parts)
        passage = _role_passage(word, reading, definition, extra)
    else:
        labeled = [(name, text) for name, text in cleaned.items()]
        extra = "\n".join(text for _, text in labeled)
        passage = "\n".join(f"{name}: {text}" for name, text in labeled)
        word = ""
        reading = ""
        definition = ""

    return NormalizedNote(
        note_id=note.note_id,
        model_name=note.model_name,
        tags=note.tags,
        deck_names=note.deck_names,
        word=word,
        reading=reading,
        definition=definition,
        extra=extra,
        passage=passage,
        added_at=note.added_at,
        introduced_at=note.introduced_at,
    )


def content_hash(passage: str, embedding_model: str) -> str:
    digest = hashlib.sha256()
    digest.update(embedding_model.encode())
    digest.update(b"\0")
    digest.update(passage.encode())
    return digest.hexdigest()


def html_to_text(html: str) -> str:
    html = _CLOZE.sub(r"\1", html)
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    text = "".join(extractor.parts).replace("\xa0", " ")
    text = _SOUND.sub("", text)
    lines = [_SPACE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "rt":
            self.parts.append(" ")
        if tag in _BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        if tag in _BREAK_TAGS and tag != "br":
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _role_passage(word: str, reading: str, definition: str, extra: str) -> str:
    lines: list[str] = []
    if word:
        lines.append(f"Word: {word}")
    if reading:
        lines.append(f"Reading: {reading}")
    if definition:
        lines.append(f"Definition: {definition}")
    if extra:
        lines.append(f"Extra: {extra}")
    return "\n".join(lines)


def _take(cleaned: dict[str, str], names: tuple[str, ...], used: set[str]) -> str:
    for name in names:
        for field_name, text in cleaned.items():
            if field_name.lower() == name.lower() and field_name not in used:
                used.add(field_name)
                return text
    return ""


def _matches(name: str, names: tuple[str, ...]) -> bool:
    lowered = name.lower()
    return any(candidate.lower() == lowered for candidate in names)


def _is_url_only(text: str) -> bool:
    lines = [line for line in text.splitlines() if line]
    return bool(lines) and all(_URL.match(line) for line in lines)
