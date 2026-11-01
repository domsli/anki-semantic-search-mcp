"""Load and save config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

_ROLES = ("word", "reading", "definition", "extra", "skip")


@dataclass(frozen=True)
class FieldMap:
    word: tuple[str, ...] = ()
    reading: tuple[str, ...] = ()
    definition: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()
    skip: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, list[str]]:
        return {role: list(getattr(self, role)) for role in _ROLES}


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
    path: Path | None = None
    note_types: dict[str, FieldMap] = field(default_factory=dict)


def load_config(path: Path) -> Config:
    if not path.is_file():
        example = path.with_name("config.example.toml")
        if example.is_file() and example.resolve() != path.resolve():
            path.write_bytes(example.read_bytes())
        else:
            raise SystemExit(f"Config file not found: {path}.")

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    decks = tuple(str(name) for name in raw.get("decks") or [])
    if not decks:
        raise SystemExit(f"{path} must list at least one deck under decks.")

    data_dir = Path(str(raw.get("data_dir", "data")))
    if not data_dir.is_absolute():
        data_dir = path.parent / data_dir

    api_key = raw.get("anki_api_key")
    api_key = str(api_key).strip() if api_key else None
    note_types = {
        str(name): field_map_from(roles or {})
        for name, roles in (raw.get("note_types") or {}).items()
    }

    return Config(
        anki_url=str(raw.get("anki_url", "http://127.0.0.1:8765")).rstrip("/"),
        anki_api_key=api_key or None,
        decks=decks,
        embedding_model=str(raw.get("embedding_model", "BAAI/bge-m3")),
        host=str(raw.get("host", "127.0.0.1")),
        port=int(raw.get("port", 8000)),
        data_dir=data_dir,
        fields=field_map_from(raw.get("fields") or {}),
        path=path,
        note_types=note_types,
    )


def save_settings(
    path: Path,
    *,
    decks: list[str],
    note_types: dict[str, dict] | None = None,
) -> Config:
    """Write decks and note-type maps. Other settings in the file stay put."""
    chosen = [str(name) for name in decks if str(name).strip()]
    if not chosen:
        raise ValueError("Choose at least one deck.")
    if not path.is_file():
        raise ValueError("Couldn't find your settings.")

    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    raw["decks"] = chosen
    if note_types is not None:
        raw["note_types"] = {
            str(name): {role: [str(item) for item in (roles.get(role) or [])] for role in _ROLES}
            for name, roles in note_types.items()
        }
    path.write_text(tomli_w.dumps(raw), encoding="utf-8")
    return load_config(path)


def field_map_from(raw: dict) -> FieldMap:
    return FieldMap(
        word=_names(raw, "word"),
        reading=_names(raw, "reading"),
        definition=_names(raw, "definition"),
        extra=_names(raw, "extra"),
        skip=_names(raw, "skip"),
    )


def _names(fields: dict, key: str) -> tuple[str, ...]:
    value = fields.get(key) or []
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)
