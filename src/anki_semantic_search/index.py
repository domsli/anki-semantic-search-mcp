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
_BGE_M3 = "BAAI/bge-m3"
_BGE_M3_DOWNLOAD = "2.3 GB"
# The full 8192-token context makes one attention step ask for about 5 GB.
_BGE_M3_MAX_TOKENS = 512
_BGE_M3_BATCH = 4


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

    def __init__(self, model_name: str, on_status: Callable[[str], None] | None = None) -> None:
        self.model_name = model_name
        self._on_status = on_status
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
            batch_size = _BGE_M3_BATCH if self.model_name.lower() == _BGE_M3.lower() else len(chunk)
            vectors.extend(vector.tolist() for vector in model.embed(chunk, batch_size=batch_size))
        return vectors

    def _load(self) -> object:
        if self._model is None:
            from fastembed import TextEmbedding

            if self._on_status is not None:
                if _weights_cached(self.model_name):
                    self._on_status(f"Loading {self.model_name}…")
                else:
                    size = f" ({_BGE_M3_DOWNLOAD})" if self.model_name.lower() == _BGE_M3.lower() else ""
                    self._on_status(f"Downloading {self.model_name}{size}…")
            _register_bge_m3(self.model_name)
            model = TextEmbedding(model_name=self.model_name)
            if self.model_name.lower() == _BGE_M3.lower():
                _cap_sequence(model, _BGE_M3_MAX_TOKENS)
            self._model = model
        return self._model


def _register_bge_m3(model_name: str) -> None:
    """fastembed 0.9 has no built-in BGE-M3. Register the official ONNX export."""
    if model_name.lower() != _BGE_M3.lower():
        return
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    supported = TextEmbedding.list_supported_models()
    if any(model["model"].lower() == _BGE_M3.lower() for model in supported):
        return
    TextEmbedding.add_custom_model(
        model=_BGE_M3,
        pooling=PoolingType.CLS,
        normalization=True,
        sources=ModelSource(hf=_BGE_M3),
        dim=1024,
        model_file="onnx/model.onnx",
        description="Multilingual dense embeddings.",
        license="mit",
        size_in_gb=2.27,
        additional_files=["onnx/model.onnx_data"],
    )


def _weights_cached(model_name: str) -> bool:
    import tempfile
    from pathlib import Path

    repo = Path(tempfile.gettempdir()) / "fastembed_cache" / f"models--{model_name.replace('/', '--')}"
    if not repo.is_dir():
        return False
    return any(repo.rglob("model.onnx_data")) or any(repo.rglob("model.onnx"))


def _cap_sequence(model: object, max_length: int) -> None:
    inner = getattr(model, "model", None)
    tokenizer = getattr(inner, "tokenizer", None)
    if tokenizer is None:
        return
    truncation = tokenizer.truncation or {}
    direction = truncation.get("direction", "right") if isinstance(truncation, dict) else "right"
    tokenizer.enable_truncation(max_length=max_length, direction=direction)


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
    model_changed = _model_changed(existing, config.embedding_model)
    classified = _classify(
        prepared,
        existing,
        config.embedding_model,
        model_changed,
        scope=None if model_changed else config.decks,
    )
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
    on_status: Callable[[str], None] | None = None,
) -> SyncStats:
    """Refresh the chosen decks in the on-disk index from Anki notes.

    Notes whose passage and embedding model are unchanged keep their vectors.
    Deck, tags, and introduced_at are still updated. Notes from decks that were
    synced earlier stay in the index. Only a changed embedding model drops
    them, because their vectors no longer fit. The previous table stays
    readable until the new rows are written.
    """
    if notes is None:
        with AnkiClient(config.anki_url, config.anki_api_key) as client:
            notes = client.fetch_notes(config.decks)
    embedder = embedder or FastEmbedEmbedder(config.embedding_model, on_status=on_status)
    prepared = _prepare(config, notes)

    config.data_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(config.data_dir))
    _add_missing_columns(db)
    existing = _read_existing(db)
    # A new model makes every stored vector incompatible, so the table starts over.
    # A rebuild only re-embeds the chosen decks and keeps the others.
    full_rewrite = _model_changed(existing, embedder.model_name)
    classified = _classify(
        prepared,
        existing,
        embedder.model_name,
        full_rewrite or rebuild,
        scope=None if full_rewrite else config.decks,
    )

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
    gone = set(stale_ids) | classified.desired_ids
    kept = {} if full_rewrite else {note_id: row for note_id, row in existing.items() if note_id not in gone}
    _write_meta(config, embedder.model_name, stats, _indexed_decks(config, kept, keep_previous=not full_rewrite))
    return stats


@dataclass
class _Classified:
    embed: list[tuple[NormalizedNote, str]]
    update: list[NormalizedNote]
    update_vectors: list[list[float]]
    unchanged: int
    remove_ids: list[int]
    remove_words: list[str]
    desired_ids: set[int]


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
    *,
    scope: Sequence[str] | None,
) -> _Classified:
    """Sort notes into embed, update, unchanged, and remove.

    Only stored notes inside `scope` can be removed. None means every stored note.
    """
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
    remove_ids = [
        note_id
        for note_id, row in existing.items()
        if note_id not in desired_ids and (scope is None or _in_scope(row, scope))
    ]
    remove_words = [str(existing[note_id].get("word") or "") for note_id in remove_ids[:5]]
    return _Classified(embed, update, update_vectors, unchanged, remove_ids, remove_words, desired_ids)


def _in_scope(row: dict, decks: Sequence[str]) -> bool:
    """True when a stored note was in one of `decks` or a deck inside one."""
    stored = json.loads(row.get("deck_names") or "[]")
    return any(name == deck or name.startswith(f"{deck}::") for name in stored for deck in decks if deck)


def indexed_decks(config: Config) -> list[str]:
    """Deck names recorded by the last sync or removal, in the order they were added."""
    meta = _read_meta(config)
    return [str(name) for name in (meta.get("configuration") or {}).get("decks") or [] if str(name)]


def remove_decks(config: Config, decks: Sequence[str], *, remaining: Sequence[str]) -> int:
    """Delete the indexed notes of `decks`, and return how many were deleted.

    A note that is also in one of the `remaining` tracked decks stays. Notes are
    matched by the deck names stored at the last sync, including nested decks.
    """
    removed_decks = [name for name in decks if name]
    deleted = 0
    if removed_decks and config.data_dir.is_dir():
        db = lancedb.connect(str(config.data_dir))
        existing = _read_existing(db)
        stale = [
            note_id
            for note_id, row in existing.items()
            if _in_scope(row, removed_decks) and not _in_scope(row, remaining)
        ]
        if stale:
            db.open_table(TABLE_NAME).delete(f"note_id IN ({', '.join(str(note_id) for note_id in stale)})")
            deleted = len(stale)
    meta = _read_meta(config)
    if meta:
        configuration = dict(meta.get("configuration") or {})
        configuration["decks"] = [name for name in configuration.get("decks") or [] if name not in removed_decks]
        meta["configuration"] = configuration
        meta["note_count"] = max(int(meta.get("note_count") or 0) - deleted, 0)
        (config.data_dir / _META_NAME).write_text(json.dumps(meta), encoding="utf-8")
    return deleted


def _read_meta(config: Config) -> dict:
    meta_path = config.data_dir / _META_NAME
    if not meta_path.is_file():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _indexed_decks(config: Config, kept: dict[int, dict], *, keep_previous: bool) -> list[str]:
    """The chosen decks, plus earlier decks that still have notes in the index."""
    decks = list(config.decks)
    if not keep_previous:
        return decks
    previous = indexed_decks(config)
    rows = list(kept.values())
    for deck in previous:
        if deck not in decks and any(_in_scope(row, (deck,)) for row in rows):
            decks.append(deck)
    return decks


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
        "note_type": note.model_name,
        "added_at": _iso(note.added_at),
        **_metadata(note),
    }


def _metadata(note: NormalizedNote) -> dict:
    """Columns that can change without changing the passage. They never need a new vector."""
    study = note.study
    return {
        "deck_names": json.dumps(list(note.deck_names), ensure_ascii=False),
        "tags": json.dumps(list(note.tags), ensure_ascii=False),
        "introduced_at": _iso(note.introduced_at),
        "modified_at": _iso(study.modified_at),
        "last_reviewed_at": _iso(study.last_reviewed_at),
        "review_count": study.review_count,
        "lapses": study.lapses,
        "interval_days": study.interval_days,
        "suspended": study.suspended,
    }


def _stored_metadata(row: dict) -> dict:
    stored = {}
    for name, default in _METADATA_DEFAULTS.items():
        value = row.get(name)
        stored[name] = default if value is None else type(default)(value)
    return stored


# Columns added after the first release, with the value an existing row gets.
_ADDED_COLUMNS = {
    "modified_at": "CAST('' AS STRING)",
    "last_reviewed_at": "CAST('' AS STRING)",
    "review_count": "CAST(0 AS BIGINT)",
    "lapses": "CAST(0 AS BIGINT)",
    "interval_days": "CAST(0 AS BIGINT)",
    "suspended": "CAST(false AS BOOLEAN)",
}

_METADATA_DEFAULTS = {
    "deck_names": "[]",
    "tags": "[]",
    "introduced_at": "",
    "modified_at": "",
    "last_reviewed_at": "",
    "review_count": 0,
    "lapses": 0,
    "interval_days": 0,
    "suspended": False,
}


def _add_missing_columns(db: lancedb.DBConnection) -> None:
    """Give a table from an older version the newer columns, without touching vectors."""
    if not _has_table(db):
        return
    table = db.open_table(TABLE_NAME)
    present = set(table.schema.names)
    missing = {name: expression for name, expression in _ADDED_COLUMNS.items() if name not in present}
    if missing:
        table.add_columns(missing)


def _as_floats(vector: object) -> list[float]:
    return [float(value) for value in vector]  # type: ignore[arg-type]


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uses_e5_prefix(model_name: str) -> bool:
    return "e5" in model_name.lower()


def _write_meta(config: Config, model_name: str, stats: SyncStats, decks: list[str]) -> None:
    payload = {
        "last_synced_at": _iso(datetime.now(timezone.utc)),
        "embedding_model": model_name,
        "note_count": stats.total,
        "embedded": stats.embedded,
        "updated": stats.updated,
        "unchanged": stats.unchanged,
        "removed": stats.removed,
        "configuration": {
            "decks": decks,
            "note_types": {name: mapping.as_dict() for name, mapping in config.note_types.items()},
        },
    }
    (config.data_dir / _META_NAME).write_text(json.dumps(payload), encoding="utf-8")
