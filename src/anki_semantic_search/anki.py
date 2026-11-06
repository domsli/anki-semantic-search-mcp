"""Read notes from a running Anki through AnkiConnect."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

API_VERSION = 6
_BATCH_SIZE = 100


class AnkiError(RuntimeError):
    """AnkiConnect is unreachable or returned an error."""


@dataclass(frozen=True)
class StudyStats:
    """Review details for one note, summed over its cards.

    Manual reschedules in the review log (ease 0) are not counted as reviews.
    """

    modified_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    review_count: int = 0
    lapses: int = 0
    # The longest interval, in days, among the note's cards.
    interval_days: int = 0
    # True when every card of the note is suspended.
    suspended: bool = False


@dataclass(frozen=True)
class RawNote:
    note_id: int
    model_name: str
    tags: tuple[str, ...]
    fields: dict[str, str]
    deck_names: tuple[str, ...]
    card_ids: tuple[int, ...]
    added_at: datetime
    introduced_at: datetime | None
    study: StudyStats = StudyStats()


class AnkiClient:
    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.url = url
        self.api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=120.0)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> AnkiClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def invoke(self, action: str, **params: Any) -> Any:
        payload: dict[str, Any] = {"action": action, "version": API_VERSION, "params": params}
        if self.api_key:
            payload["key"] = self.api_key
        try:
            response = self._client.post(self.url, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AnkiError(
                f"Cannot reach AnkiConnect at {self.url}. Open Anki and check that AnkiConnect is installed."
            ) from exc
        body = response.json()
        error = body.get("error")
        if error:
            raise AnkiError(str(error))
        return body.get("result")

    def fetch_notes(self, decks: tuple[str, ...] | list[str]) -> list[RawNote]:
        if not decks:
            return []
        note_ids = [int(note_id) for note_id in self.invoke("findNotes", query=deck_query(decks)) or []]
        if not note_ids:
            return []

        info_by_id: dict[int, dict[str, Any]] = {}
        for batch in _batches(note_ids):
            for info in self.invoke("notesInfo", notes=batch) or []:
                info_by_id[int(info["noteId"])] = info

        card_to_note: dict[int, int] = {}
        for note_id, info in info_by_id.items():
            for card_id in info.get("cards") or []:
                card_to_note[int(card_id)] = note_id

        decks_by_note: dict[int, list[str]] = {note_id: [] for note_id in info_by_id}
        lapses: dict[int, int] = {}
        interval_days: dict[int, int] = {}
        unsuspended: set[int] = set()
        for batch in _batches(list(card_to_note)):
            for card in self.invoke("cardsInfo", cards=batch) or []:
                note_id = card_to_note.get(int(card["cardId"]))
                if note_id is None:
                    continue
                deck_name = str(card.get("deckName") or "")
                if deck_name and deck_name not in decks_by_note[note_id]:
                    decks_by_note[note_id].append(deck_name)
                lapses[note_id] = lapses.get(note_id, 0) + int(card.get("lapses") or 0)
                # A negative interval is a learning step in seconds, not days.
                interval = max(int(card.get("interval") or 0), 0)
                interval_days[note_id] = max(interval_days.get(note_id, 0), interval)
                if int(card.get("queue", 0)) != -1:
                    unsuspended.add(note_id)

        first_review_ms: dict[int, int] = {}
        last_review_ms: dict[int, int] = {}
        review_count: dict[int, int] = {}
        for batch in _batches(list(card_to_note)):
            reviews = self.invoke("getReviewsOfCards", cards=[str(card_id) for card_id in batch]) or {}
            for card_key, entries in reviews.items():
                note_id = card_to_note.get(int(card_key))
                if note_id is None:
                    continue
                for entry in entries or []:
                    if int(entry.get("ease", 1)) == 0:
                        continue
                    reviewed_at = int(entry["id"])
                    review_count[note_id] = review_count.get(note_id, 0) + 1
                    if reviewed_at < first_review_ms.get(note_id, reviewed_at + 1):
                        first_review_ms[note_id] = reviewed_at
                    if reviewed_at > last_review_ms.get(note_id, -1):
                        last_review_ms[note_id] = reviewed_at

        notes: list[RawNote] = []
        for note_id in note_ids:
            info = info_by_id.get(note_id)
            if info is None:
                continue
            fields = {
                str(name): _field_value(raw)
                for name, raw in (info.get("fields") or {}).items()
            }
            card_ids = tuple(int(card_id) for card_id in info.get("cards") or [])
            introduced = first_review_ms.get(note_id)
            last_reviewed = last_review_ms.get(note_id)
            modified = info.get("mod")
            study = StudyStats(
                modified_at=_from_anki_ms(int(modified) * 1000) if modified else None,
                last_reviewed_at=_from_anki_ms(last_reviewed) if last_reviewed is not None else None,
                review_count=review_count.get(note_id, 0),
                lapses=lapses.get(note_id, 0),
                interval_days=interval_days.get(note_id, 0),
                suspended=bool(card_ids) and note_id not in unsuspended,
            )
            notes.append(
                RawNote(
                    note_id=note_id,
                    model_name=str(info.get("modelName") or ""),
                    tags=tuple(str(tag) for tag in info.get("tags") or []),
                    fields=fields,
                    deck_names=tuple(decks_by_note.get(note_id) or []),
                    card_ids=card_ids,
                    added_at=_from_anki_ms(note_id),
                    introduced_at=_from_anki_ms(introduced) if introduced is not None else None,
                    study=study,
                )
            )
        return notes

    def deck_names(self) -> list[str]:
        return [str(name) for name in self.invoke("deckNames") or []]

    def note_types(self) -> list[dict[str, Any]]:
        names = [str(name) for name in self.invoke("modelNames") or []]
        return [self._note_type(name) for name in names]

    def note_types_in_decks(self, decks: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
        """Note types that actually have cards in these decks, including decks inside them."""
        if not decks:
            return []
        note_ids = [int(note_id) for note_id in self.invoke("findNotes", query=deck_query(decks)) or []]
        names: list[str] = []
        seen: set[str] = set()
        for batch in _batches(note_ids):
            for info in self.invoke("notesInfo", notes=batch) or []:
                name = str(info.get("modelName") or "")
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
        return [self._note_type(name) for name in names]

    def _note_type(self, name: str) -> dict[str, Any]:
        fields = [str(field) for field in self.invoke("modelFieldNames", modelName=name) or []]
        return {"name": name, "fields": fields}

    def sample_note(self, model_name: str, decks: tuple[str, ...] | list[str]) -> RawNote | None:
        query = f'note:"{_escape_query(model_name)}"'
        if decks:
            query = f"{deck_query(decks)} {query}"
        note_ids = [int(note_id) for note_id in self.invoke("findNotes", query=query) or []]
        if not note_ids:
            return None
        info = (self.invoke("notesInfo", notes=[note_ids[0]]) or [None])[0]
        if not info:
            return None
        fields = {str(name): _field_value(raw) for name, raw in (info.get("fields") or {}).items()}
        return RawNote(
            note_id=int(info["noteId"]),
            model_name=str(info.get("modelName") or model_name),
            tags=tuple(str(tag) for tag in info.get("tags") or []),
            fields=fields,
            deck_names=(),
            card_ids=tuple(int(card_id) for card_id in info.get("cards") or []),
            added_at=_from_anki_ms(int(info["noteId"])),
            introduced_at=None,
        )


def deck_query(decks: tuple[str, ...] | list[str]) -> str:
    parts = [f'deck:"{_escape_query(name)}"' for name in decks if name]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"({' OR '.join(parts)})"


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _field_value(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("value") or "")
    return str(raw or "")


def _from_anki_ms(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def _batches(items: list[int], size: int = _BATCH_SIZE) -> list[list[int]]:
    return [items[start : start + size] for start in range(0, len(items), size)]
