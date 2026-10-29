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
class RawNote:
    note_id: int
    model_name: str
    tags: tuple[str, ...]
    fields: dict[str, str]
    deck_names: tuple[str, ...]
    card_ids: tuple[int, ...]
    added_at: datetime
    introduced_at: datetime | None


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
        for batch in _batches(list(card_to_note)):
            for card in self.invoke("cardsInfo", cards=batch) or []:
                note_id = card_to_note.get(int(card["cardId"]))
                deck_name = str(card.get("deckName") or "")
                if note_id is not None and deck_name and deck_name not in decks_by_note[note_id]:
                    decks_by_note[note_id].append(deck_name)

        first_review_ms: dict[int, int] = {}
        for batch in _batches(list(card_to_note)):
            reviews = self.invoke("getReviewsOfCards", cards=[str(card_id) for card_id in batch]) or {}
            for card_key, entries in reviews.items():
                note_id = card_to_note.get(int(card_key))
                if note_id is None:
                    continue
                for entry in entries or []:
                    reviewed_at = int(entry["id"])
                    previous = first_review_ms.get(note_id)
                    if previous is None or reviewed_at < previous:
                        first_review_ms[note_id] = reviewed_at

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
                )
            )
        return notes


def deck_query(decks: tuple[str, ...] | list[str]) -> str:
    parts = [f'deck:"{_escape_query(name)}"' for name in decks]
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
