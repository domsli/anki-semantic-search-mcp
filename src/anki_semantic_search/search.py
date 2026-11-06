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
    added_at: str | None = None
    modified_at: str | None = None
    last_reviewed_at: str | None = None
    review_count: int = 0
    lapses: int = 0
    interval_days: int = 0
    suspended: bool = False


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
                    "added_at": hit.added_at,
                    "introduced_at": hit.introduced_at,
                    "last_reviewed_at": hit.last_reviewed_at,
                    "modified_at": hit.modified_at,
                    "review_count": hit.review_count,
                    "lapses": hit.lapses,
                    "interval_days": hit.interval_days,
                    "suspended": hit.suspended,
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


@dataclass(frozen=True)
class StudyFilters:
    """Filters on a note's study history. None leaves a filter off."""

    added_within_days: int | None = None
    learned_within_days: int | None = None
    reviewed_within_days: int | None = None
    edited_within_days: int | None = None
    min_lapses: int | None = None
    max_interval_days: int | None = None
    suspended: bool | None = None

    def active(self) -> bool:
        return any(getattr(self, name) is not None for name in self.__dataclass_fields__)


# Day filter -> (column, words for "No indexed notes were ...").
_DAY_FILTERS = {
    "added_within_days": ("added_at", "added"),
    "learned_within_days": ("introduced_at", "first studied"),
    "reviewed_within_days": ("last_reviewed_at", "reviewed"),
    "edited_within_days": ("modified_at", "edited"),
}


def search_notes(
    config: Config,
    query: str,
    *,
    decks: Sequence[str] | None = None,
    learned_within_days: int | None = None,
    added_within_days: int | None = None,
    reviewed_within_days: int | None = None,
    edited_within_days: int | None = None,
    min_lapses: int | None = None,
    max_interval_days: int | None = None,
    suspended: bool | None = None,
    limit: int = _DEFAULT_LIMIT,
    embedder: QueryEmbedder | None = None,
    now: datetime | None = None,
) -> SearchResponse:
    """Return the notes whose word and definition are closest to `query`."""
    filters = StudyFilters(
        added_within_days=added_within_days,
        learned_within_days=learned_within_days,
        reviewed_within_days=reviewed_within_days,
        edited_within_days=edited_within_days,
        min_lapses=min_lapses,
        max_interval_days=max_interval_days,
        suspended=suspended,
    )
    query = query.strip()
    if not query:
        return SearchResponse((), "Provide a word, phrase, or meaning to search for.")
    problem = _invalid(filters)
    if problem:
        return SearchResponse((), problem)

    limit = min(max(limit, 1), _MAX_LIMIT)
    table = _open_table(config)
    if table is None or table.count_rows() == 0:
        return SearchResponse((), "The index is empty. Run anki-search sync while Anki is open.")
    missing = sorted(_columns(filters) - set(table.schema.names))
    if missing:
        return SearchResponse(
            (),
            "The index was built before these filters existed. "
            "Ask the user to press Update decks in the desktop window once, then search again.",
        )

    embedder = embedder or FastEmbedEmbedder(config.embedding_model)
    moment = now or datetime.now(timezone.utc)
    deck_names = tuple(name for name in (decks or ()) if name)
    vector = embedder.embed_query(query)
    hits = _blend(table, query, vector, _where(deck_names, filters, moment), limit)
    if hits:
        return SearchResponse(tuple(hits))

    if filters.active() and _blend(table, query, vector, _where(deck_names, StudyFilters(), moment), 1):
        return SearchResponse((), _filtered_out(filters))
    if deck_names and _blend(table, query, vector, None, 1):
        return SearchResponse((), f"No matching notes in {', '.join(deck_names)}.")
    return SearchResponse((), "No matching notes.")


def _invalid(filters: StudyFilters) -> str | None:
    for name in _DAY_FILTERS:
        value = getattr(filters, name)
        if value is not None and value < 1:
            return f"{name} must be at least 1."
    for name in ("min_lapses", "max_interval_days"):
        value = getattr(filters, name)
        if value is not None and value < 0:
            return f"{name} must be 0 or more."
    return None


def _columns(filters: StudyFilters) -> set[str]:
    columns = {column for name, (column, _) in _DAY_FILTERS.items() if getattr(filters, name) is not None}
    if filters.min_lapses is not None:
        columns.add("lapses")
    if filters.max_interval_days is not None:
        columns.add("interval_days")
    if filters.suspended is not None:
        columns.add("suspended")
    return columns


def _filtered_out(filters: StudyFilters) -> str:
    """Tell the model which filters emptied the result, and how to loosen them."""
    parts: list[str] = []
    widen: list[str] = []
    for name, (_, verb) in _DAY_FILTERS.items():
        value = getattr(filters, name)
        if value is not None:
            parts.append(f"{verb} in the last {value} days")
            widen.append(f"a larger {name}")
    if filters.min_lapses is not None:
        parts.append(f"forgotten at least {filters.min_lapses} times")
        widen.append("a smaller min_lapses")
    if filters.max_interval_days is not None:
        parts.append(f"studied with an interval of at most {filters.max_interval_days} days")
        widen.append("a larger max_interval_days")
    if filters.suspended is not None:
        parts.append("suspended" if filters.suspended else "not suspended")
        widen.append("no suspended filter")
    return (
        f"No indexed notes were {' and '.join(parts)}. "
        "Matching notes exist without these filters. "
        f"Call search_notes again with {' or '.join(widen)}."
    )


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
    introduced = _date(row, "introduced_at")
    return SearchHit(
        word=str(row.get("word") or ""),
        reading=str(row.get("reading") or ""),
        definition=str(row.get("definition") or ""),
        extra=str(row.get("extra") or ""),
        decks=tuple(json.loads(row["deck_names"])),
        tags=tuple(json.loads(row["tags"])),
        introduced_at=introduced,
        score=score,
        added_at=_date(row, "added_at"),
        modified_at=_date(row, "modified_at"),
        last_reviewed_at=_date(row, "last_reviewed_at"),
        review_count=int(row.get("review_count") or 0),
        lapses=int(row.get("lapses") or 0),
        interval_days=int(row.get("interval_days") or 0),
        suspended=bool(row.get("suspended") or False),
    )


def _date(row: dict, name: str) -> str | None:
    """An ISO date column, or None when it is empty or the table predates it."""
    return str(row.get(name) or "") or None


def _where(decks: tuple[str, ...], filters: StudyFilters, now: datetime) -> str | None:
    clauses: list[str] = []
    if decks:
        parts = [f"({_deck_like(name)})" for name in decks]
        clauses.append("(" + " OR ".join(parts) + ")")
    for name, (column, _) in _DAY_FILTERS.items():
        days = getattr(filters, name)
        if days is None:
            continue
        cutoff = (now - timedelta(days=days)).astimezone(timezone.utc)
        stamp = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        # Dates are ISO strings in UTC, so text order is time order. Empty means never.
        clauses.append(f"{column} >= '{stamp}' AND {column} != ''")
    if filters.min_lapses is not None:
        clauses.append(f"lapses >= {int(filters.min_lapses)}")
    if filters.max_interval_days is not None:
        # Unstudied cards also have interval 0, so require at least one review.
        clauses.append(f"interval_days <= {int(filters.max_interval_days)} AND introduced_at != ''")
    if filters.suspended is not None:
        clauses.append(f"suspended = {'true' if filters.suspended else 'false'}")
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
