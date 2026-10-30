"""Embed Anki notes into a local LanceDB table."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Callable, Sequence
from typing import Protocol

import lancedb
from lancedb.index import FTS, IvfFlat

from anki_semantic_search.anki import AnkiClient, RawNote
from anki_semantic_search.config import Config
from anki_semantic_search.normalize import NormalizedNote, content_hash, normalize_for_config

TABLE_NAME = "notes"
_META_NAME = "sync_meta.json"
_VECTOR_INDEX_MIN_ROWS = 256
_EMBED_BATCH = 32


class Embedder(Protocol):
    model_name: str

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class SyncStats:
    total: int
    embedded: int
    updated: int
    unchanged: int
    removed: int


class FastEmbedEmbedder:
    """Local fastembed model. E5 models get passage prefixes; bge-m3 does not."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: object | None = None

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        prepared = [passage_input(self.model_name, text) for text in texts]
        return self._embed(prepared)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([query_input(self.model_name, text)])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH):
            chunk = texts[start : start + _EMBED_BATCH]
            vectors.extend(vector.tolist() for vector in model.embed(chunk))
        return vectors

    def _load(self) -> object:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
        return self._model


def passage_input(model_name: str, text: str) -> str:
    if _uses_e5_prefix(model_name):
        return f"passage: {text}"
    return text


def query_input(model_name: str, text: str) -> str:
    if _uses_e5_prefix(model_name):
        return f"query: {text}"
    return text


def diff_index(config: Config, notes: Sequence[RawNote] | None = None) -> dict:
    """Compare Anki with the index without embedding or writing."""
    if notes is None:
        with AnkiClient(config.anki_url, config.anki_api_key) as client:
            notes = client.fetch_notes(config.decks)
    prepared = _prepare(config, notes)
    existing = _read_existing(_connect(config.data_dir)) if config.data_dir.is_dir() else {}
    classified = _classify(prepared, existing, config.embedding_model, _model_changed(existing, config.embedding_model))
    return {
        "ok": True,
        "would_embed": len(classified.embed),
        "would_update": len(classified.update),
        "unchanged": classified.unchanged,
        "would_remove": len(classified.remove_ids),
        "examples": {
            "embed": [_example(note) for note, _digest in classified.embed[:5]],
            "update": [_example(note) for note in classified.update[:5]],
            "remove": classified.remove_words[:5],
        },
    }


def sync_index(
    config: Config,
    *,
    rebuild: bool = False,
    notes: Sequence[RawNote] | None = None,
    embedder: Embedder | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> SyncStats:
    """Refresh the on-disk index from Anki notes.

    Notes whose passage and embedding model are unchanged keep their vectors.
    Deck, tags, and introduced_at are still updated. The previous table stays
    readable until the new rows are written.
    """
    if notes is None:
        with AnkiClient(config.anki_url, config.anki_api_key) as client:
            notes = client.fetch_notes(config.decks)
    embedder = embedder or FastEmbedEmbedder(config.embedding_model)
    prepared = _prepare(config, notes)

    config.data_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(config.data_dir))
    existing = _read_existing(db)
    full_rewrite = rebuild or _model_changed(existing, embedder.model_name)
    classified = _classify(prepared, existing, embedder.model_name, full_rewrite)

    total_embed = len(classified.embed)
    if on_progress:
        on_progress(0, total_embed)
    vectors: list[list[float]] = []
    passages = [note.passage for note, _digest in classified.embed]
    done = 0
    while done < total_embed:
        chunk = passages[done : done + _EMBED_BATCH]
        vectors.extend(embedder.embed_passages(chunk))
        done += len(chunk)
        if on_progress:
            on_progress(done, total_embed)
    fresh_rows = [
        _row(note, vector, embedder.model_name, digest)
        for (note, digest), vector in zip(classified.embed, vectors, strict=True)
    ]
    reused_rows = [
        _row(note, vector, embedder.model_name, content_hash(note.passage, embedder.model_name))
        for note, vector in zip(classified.update, classified.update_vectors, strict=True)
    ]
    unchanged = classified.unchanged
    stale_ids = classified.remove_ids
    wrote_text = bool(fresh_rows) or bool(stale_ids) or full_rewrite

    if full_rewrite or not _has_table(db):
        rows = fresh_rows + reused_rows
        table = db.create_table(TABLE_NAME, data=rows, mode="overwrite") if rows else _empty_existing(db)
    else:
        table = db.open_table(TABLE_NAME)
        changed = fresh_rows + reused_rows
        if changed:
            (
                table.merge_insert("note_id")
                .when_matched_update_all()
                .when_not_matched_insert_all()
                .execute(changed)
            )
        if stale_ids:
            table.delete(f"note_id IN ({', '.join(str(note_id) for note_id in stale_ids)})")

    if table is not None and wrote_text:
        _ensure_indexes(table)

    total = 0 if table is None else table.count_rows()
    stats = SyncStats(
        total=total,
        embedded=len(fresh_rows),
        updated=len(reused_rows),
        unchanged=unchanged,
        removed=len(stale_ids),
    )
    _write_meta(config, embedder.model_name, stats)
    return stats


@dataclass
class _Classified:
    embed: list[tuple[NormalizedNote, str]]
    update: list[NormalizedNote]
    update_vectors: list[list[float]]
    unchanged: int
    remove_ids: list[int]
    remove_words: list[str]


def _prepare(config: Config, notes: Sequence[RawNote]) -> list[NormalizedNote]:
    return [note for note in (normalize_for_config(raw, config) for raw in notes) if note.passage]


def _connect(data_dir):
    if not data_dir.is_dir():
        return None
    return lancedb.connect(str(data_dir))


def _model_changed(existing: dict[int, dict], model_name: str) -> bool:
    return bool(existing) and any(row["embedding_model"] != model_name for row in existing.values())


def _classify(
    prepared: list[NormalizedNote],
    existing: dict[int, dict],
    model_name: str,
    full_rewrite: bool,
) -> _Classified:
    embed: list[tuple[NormalizedNote, str]] = []
    update: list[NormalizedNote] = []
    update_vectors: list[list[float]] = []
    unchanged = 0
    desired_ids: set[int] = set()
    for note in prepared:
        desired_ids.add(note.note_id)
        digest = content_hash(note.passage, model_name)
        previous = existing.get(note.note_id)
        if (
            not full_rewrite
            and previous is not None
            and previous["content_hash"] == digest
            and previous["embedding_model"] == model_name
        ):
            if _metadata(note) == _stored_metadata(previous):
                unchanged += 1
            else:
                update.append(note)
                update_vectors.append(_as_floats(previous["vector"]))
            continue
        embed.append((note, digest))
    remove_ids = [note_id for note_id in existing if note_id not in desired_ids]
    remove_words = [str(existing[note_id].get("word") or "") for note_id in remove_ids[:5]]
    return _Classified(embed, update, update_vectors, unchanged, remove_ids, remove_words)


def _example(note: NormalizedNote) -> str:
    return note.word or note.definition or note.passage.splitlines()[0]


def _has_table(db: lancedb.DBConnection) -> bool:
    return TABLE_NAME in set(db.list_tables())


def _read_existing(db: lancedb.DBConnection) -> dict[int, dict]:
    if not _has_table(db):
        return {}
    table = db.open_table(TABLE_NAME)
    if table.count_rows() == 0:
        return {}
    rows = table.to_arrow().to_pylist()
    return {int(row["note_id"]): row for row in rows}


def _empty_existing(db: lancedb.DBConnection):
    if not _has_table(db):
        return None
    table = db.open_table(TABLE_NAME)
    if table.count_rows():
        table.delete("note_id IS NOT NULL")
    return table


def _ensure_indexes(table) -> None:
    if table.count_rows() == 0:
        return
    fts = FTS(
        base_tokenizer="ngram",
        ngram_min_length=1,
        ngram_max_length=2,
        stem=False,
        remove_stop_words=False,
        lower_case=True,
        max_token_length=256,
    )
    for field in ("word", "passage"):
        table.create_index(field, config=fts, replace=True)
    if table.count_rows() >= _VECTOR_INDEX_MIN_ROWS:
        table.create_index("vector", config=IvfFlat(distance_type="cosine"), replace=True)


def _row(note: NormalizedNote, vector: list[float], model_name: str, digest: str) -> dict:
    decks, tags, introduced = _metadata(note)
    return {
        "note_id": note.note_id,
        "vector": vector,
        "content_hash": digest,
        "embedding_model": model_name,
        "passage": note.passage,
        "word": note.word,
        "reading": note.reading,
        "definition": note.definition,
        "extra": note.extra,
        "deck_names": decks,
        "tags": tags,
        "note_type": note.model_name,
        "added_at": _iso(note.added_at),
        "introduced_at": introduced,
    }


def _metadata(note: NormalizedNote) -> tuple[str, str, str]:
    return (
        json.dumps(list(note.deck_names), ensure_ascii=False),
        json.dumps(list(note.tags), ensure_ascii=False),
        _iso(note.introduced_at),
    )


def _stored_metadata(row: dict) -> tuple[str, str, str]:
    return (str(row["deck_names"]), str(row["tags"]), str(row["introduced_at"] or ""))


def _as_floats(vector: object) -> list[float]:
    return [float(value) for value in vector]  # type: ignore[arg-type]


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uses_e5_prefix(model_name: str) -> bool:
    return "e5" in model_name.lower()


def _write_meta(config: Config, model_name: str, stats: SyncStats) -> None:
    payload = {
        "last_synced_at": _iso(datetime.now(timezone.utc)),
        "embedding_model": model_name,
        "note_count": stats.total,
        "embedded": stats.embedded,
        "updated": stats.updated,
        "unchanged": stats.unchanged,
        "removed": stats.removed,
    }
    (config.data_dir / _META_NAME).write_text(json.dumps(payload), encoding="utf-8")
