"""Load config.toml into a small typed object."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FieldMap:
    word: tuple[str, ...]
    reading: tuple[str, ...]
    definition: tuple[str, ...]
    extra: tuple[str, ...]
    skip: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    anki_url: str
    anki_api_key: str | None
    decks: tuple[str, ...]
    embedding_model: str
    host: str
    port: int
    data_dir: Path
    fields: FieldMap


def load_config(path: Path) -> Config:
    if not path.is_file():
        example = path.with_name("config.example.toml")
        hint = f" Copy {example.name} to {path.name} and edit the deck list." if example.is_file() else ""
        raise SystemExit(f"Config file not found: {path}.{hint}")

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    fields = raw.get("fields") or {}
    decks = tuple(str(name) for name in raw.get("decks") or [])
    if not decks:
        raise SystemExit(f"{path} must list at least one deck under decks.")

    data_dir = Path(str(raw.get("data_dir", "data")))
    if not data_dir.is_absolute():
        data_dir = path.parent / data_dir

    api_key = raw.get("anki_api_key")
    api_key = str(api_key).strip() if api_key else None

    return Config(
        anki_url=str(raw.get("anki_url", "http://127.0.0.1:8765")).rstrip("/"),
        anki_api_key=api_key or None,
        decks=decks,
        embedding_model=str(raw.get("embedding_model", "BAAI/bge-m3")),
        host=str(raw.get("host", "127.0.0.1")),
        port=int(raw.get("port", 8000)),
        data_dir=data_dir,
        fields=FieldMap(
            word=_names(fields, "word"),
            reading=_names(fields, "reading"),
            definition=_names(fields, "definition"),
            extra=_names(fields, "extra"),
            skip=_names(fields, "skip"),
        ),
    )


def _names(fields: dict, key: str) -> tuple[str, ...]:
    value = fields.get(key) or []
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)
