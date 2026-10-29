"""Search the local note index by meaning, spelling, deck, and review date."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, Sequence

import lancedb

from anki_semantic_search.config import Config
from anki_semantic_search.index import TABLE_NAME, FastEmbedEmbedder

_META_NAME = "sync_meta.json"
_CANDIDATE_FLOOR = 40
_RRF_K = 60
_EXACT_BOOST = 1.0
_JAPANESE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
_DEFAULT_LIMIT = 8
_MAX_LIMIT = 25


class QueryEmbedder(Protocol):
    model_name: str

    def embed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class SearchHit:
    word: str
    reading: str
    definition: str
    extra: str
    decks: tuple[str, ...]
    tags: tuple[str, ...]
    introduced_at: str | None
    score: float


@dataclass(frozen=True)
class SearchResponse:
    hits: tuple[SearchHit, ...]
    message: str | None = None

    def as_dict(self) -> dict:
        payload: dict = {
            "hits": [
                {
                    "word": hit.word,
                    "reading": hit.reading,
                    "definition": hit.definition,
                    "extra": hit.extra,
                    "decks": list(hit.decks),
                    "tags": list(hit.tags),
                    "introduced_at": hit.introduced_at,
                    "score": round(hit.score, 4),
                }
                for hit in self.hits
            ]
        }
        if self.message:
            payload["message"] = self.message
        return payload


def list_decks(config: Config) -> dict:
    """Indexed deck names and the time of the last successful sync."""
    meta_path = config.data_dir / _META_NAME
    if not meta_path.is_file():
        return {
            "decks": [],
            "last_synced_at": None,
            "note_count": 0,
            "message": "The index is empty. Run anki-search sync while Anki is open.",
        }
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    decks: set[str] = set()
    table = _open_table(config)
    if table is not None and table.count_rows():
        column = table.to_arrow().column("deck_names").to_pylist()
        for raw in column:
            decks.update(json.loads(raw))
    return {
        "decks": sorted(decks),
        "last_synced_at": meta.get("last_synced_at"),
        "note_count": int(meta.get("note_count") or 0),
    }


def search_notes(
    config: Config,
    query: str,
    *,
    decks: Sequence[str] | None = None,
    learned_within_days: int | None = None,
    limit: int = _DEFAULT_LIMIT,
    embedder: QueryEmbedder | None = None,
    now: datetime | None = None,
) -> SearchResponse:
    """Return the notes whose word and definition are closest to `query`."""
    query = query.strip()
    if not query:
        return SearchResponse((), "Provide a word, phrase, or meaning to search for.")
    if learned_within_days is not None and learned_within_days < 1:
        return SearchResponse((), "learned_within_days must be at least 1.")

    limit = min(max(limit, 1), _MAX_LIMIT)
    table = _open_table(config)
    if table is None or table.count_rows() == 0:
        return SearchResponse((), "The index is empty. Run anki-search sync while Anki is open.")

    embedder = embedder or FastEmbedEmbedder(config.embedding_model)
    moment = now or datetime.now(timezone.utc)
    deck_names = tuple(name for name in (decks or ()) if name)
    vector = embedder.embed_query(query)
    hits = _blend(table, query, vector, _where(deck_names, learned_within_days, moment), limit)
    if hits:
        return SearchResponse(tuple(hits))

    if learned_within_days is not None:
        outside_window = _blend(table, query, vector, _where(deck_names, None, moment), 1)
        if outside_window:
            return SearchResponse(
                (),
                (
                    f"No indexed notes were first studied in the last {learned_within_days} days. "
                    "Matching notes exist outside that window. "
                    "Call search_notes again with a larger learned_within_days."
                ),
            )
    if deck_names and _blend(table, query, vector, None, 1):
        return SearchResponse((), f"No matching notes in {', '.join(deck_names)}.")
    return SearchResponse((), "No matching notes.")


def _blend(table, query: str, vector: list[float], where: str | None, limit: int) -> list[SearchHit]:
    candidates = max(limit * 5, _CANDIDATE_FLOOR)
    by_id: dict[int, dict] = {}
    scores: dict[int, float] = defaultdict(float)

    for rank, row in enumerate(_vector_hits(table, vector, where, candidates)):
        note_id = int(row["note_id"])
        by_id[note_id] = row
        scores[note_id] += 1.0 / (_RRF_K + rank)

    for column in ("word", "passage"):
        for rank, row in enumerate(_text_hits(table, query, column, where, candidates)):
            note_id = int(row["note_id"])
            by_id.setdefault(note_id, row)
            scores[note_id] += 1.0 / (_RRF_K + rank)

    if _JAPANESE.search(query):
        folded = query.strip()
        for note_id, row in by_id.items():
            word = str(row.get("word") or "")
            if word and (folded == word or folded in word):
                scores[note_id] += _EXACT_BOOST

    ordered = sorted(scores, key=lambda note_id: scores[note_id], reverse=True)
    return [_hit(by_id[note_id], scores[note_id]) for note_id in ordered[:limit]]


def _vector_hits(table, vector: list[float], where: str | None, limit: int) -> list[dict]:
    builder = table.search(vector, query_type="vector").limit(limit)
    if where:
        builder = builder.where(where, prefilter=True)
    return builder.to_list()


def _text_hits(table, query: str, column: str, where: str | None, limit: int) -> list[dict]:
    try:
        builder = table.search(query, query_type="fts", fts_columns=column).limit(limit)
        if where:
            builder = builder.where(where, prefilter=True)
        return builder.to_list()
    except (RuntimeError, ValueError, OSError):
        return []


def _hit(row: dict, score: float) -> SearchHit:
    introduced = str(row.get("introduced_at") or "") or None
    return SearchHit(
        word=str(row.get("word") or ""),
        reading=str(row.get("reading") or ""),
        definition=str(row.get("definition") or ""),
        extra=str(row.get("extra") or ""),
        decks=tuple(json.loads(row["deck_names"])),
        tags=tuple(json.loads(row["tags"])),
        introduced_at=introduced,
        score=score,
    )


def _where(decks: tuple[str, ...], learned_within_days: int | None, now: datetime) -> str | None:
    clauses: list[str] = []
    if decks:
        parts = [f"({_deck_like(name)})" for name in decks]
        clauses.append("(" + " OR ".join(parts) + ")")
    if learned_within_days is not None:
        cutoff = (now - timedelta(days=learned_within_days)).astimezone(timezone.utc)
        stamp = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        clauses.append(f"introduced_at >= '{stamp}' AND introduced_at != ''")
    if not clauses:
        return None
    return " AND ".join(clauses)


def _deck_like(name: str) -> str:
    escaped = name.replace("'", "''")
    exact = f"deck_names LIKE '%\"{escaped}\"%'"
    child = f"deck_names LIKE '%\"{escaped}::%'"
    return f"{exact} OR {child}"


def _open_table(config: Config):
    if not config.data_dir.is_dir():
        return None
    db = lancedb.connect(str(config.data_dir))
    names = set(db.list_tables())
    if TABLE_NAME not in names:
        return None
    return db.open_table(TABLE_NAME)
