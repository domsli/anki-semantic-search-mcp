"""JSON commands the desktop window uses to read Anki and edit config.toml."""

from __future__ import annotations

import json
from pathlib import Path

from anki_semantic_search.anki import AnkiClient, AnkiError
from anki_semantic_search.config import Config, FieldMap, save_settings
from anki_semantic_search.index import _META_NAME, diff_index
from anki_semantic_search.normalize import normalize_for_config, normalize_note

_ROLES = ("word", "reading", "definition", "extra", "skip")


def status(config: Config) -> dict:
    meta_path = config.data_dir / _META_NAME
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    return {
        "ok": True,
        "anki_url": config.anki_url,
        "host": config.host,
        "port": config.port,
        "decks": list(config.decks),
        "fields": config.fields.as_dict(),
        "note_types": {name: roles.as_dict() for name, roles in config.note_types.items()},
        "last_synced_at": meta.get("last_synced_at"),
        "note_count": meta.get("note_count", 0),
        "embedded": meta.get("embedded"),
        "updated": meta.get("updated"),
        "unchanged": meta.get("unchanged"),
        "removed": meta.get("removed"),
        "embedding_model": meta.get("embedding_model") or config.embedding_model,
    }


def list_decks(config: Config) -> dict:
    try:
        with AnkiClient(config.anki_url, config.anki_api_key) as client:
            live = client.deck_names()
    except AnkiError as exc:
        return {"ok": True, "anki_open": False, "error": str(exc), "decks": list(config.decks), "selected": list(config.decks)}
    names = list(dict.fromkeys([*live, *config.decks]))
    return {"ok": True, "anki_open": True, "decks": names, "selected": list(config.decks), "live": live}


def list_note_types(config: Config) -> dict:
    try:
        with AnkiClient(config.anki_url, config.anki_api_key) as client:
            live = client.note_types()
    except AnkiError as exc:
        return {"ok": True, "anki_open": False, "error": str(exc), "note_types": _saved_note_types(config)}
    types = []
    for item in live:
        name = item["name"]
        mapped = config.note_types.get(name)
        types.append(
            {
                "name": name,
                "fields": item["fields"],
                "mapped": mapped is not None,
                "roles": _roles_for(item["fields"], mapped if mapped is not None else config.fields, leftovers=mapped is None),
            }
        )
    return {"ok": True, "anki_open": True, "note_types": types}


def preview_note(config: Config, payload: dict) -> dict:
    note_type = str(payload.get("note_type") or "")
    if not note_type:
        return {"ok": False, "error": "Choose a note type to preview."}
    decks = config.decks if payload.get("decks") is None else payload.get("decks")
    try:
        with AnkiClient(config.anki_url, config.anki_api_key) as client:
            note = client.sample_note(note_type, decks)
    except AnkiError as exc:
        return {"ok": False, "error": str(exc)}
    if note is None:
        return {"ok": True, "passage": "", "message": "No notes of this type in the selected decks."}
    roles = payload.get("roles")
    if roles is None:
        normalized = normalize_for_config(note, config)
    else:
        normalized = normalize_note(note, _map_from_roles(roles), explicit=bool(payload.get("explicit", True)))
    return {
        "ok": True,
        "passage": normalized.passage,
        "word": normalized.word,
        "definition": normalized.definition,
    }


def save(config: Config, payload: dict) -> dict:
    path = config.path
    if path is None:
        return {"ok": False, "error": "This config was not loaded from a file."}
    try:
        updated = save_settings(path, decks=list(payload.get("decks") or []), note_types=payload.get("note_types"))
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return status(updated)


def read_diff(config: Config) -> dict:
    try:
        return diff_index(config)
    except AnkiError as exc:
        return {"ok": False, "error": str(exc)}


def _saved_note_types(config: Config) -> list[dict]:
    saved = []
    for name, roles in config.note_types.items():
        fields = [field_name for role in _ROLES for field_name in getattr(roles, role)]
        saved.append(
            {
                "name": name,
                "fields": fields,
                "mapped": True,
                "roles": _roles_for(fields, roles, leftovers=False),
            }
        )
    return saved


def _roles_for(field_names: list[str], field_map: FieldMap, *, leftovers: bool) -> dict[str, str]:
    roles = {name: "unassigned" for name in field_names}
    claimed: set[str] = set()
    for field_name in field_names:
        if _matches(field_name, field_map.skip):
            roles[field_name] = "skip"
            claimed.add(field_name)
    for role in ("word", "reading", "definition", "extra"):
        names = getattr(field_map, role)
        matched = 0
        for candidate in names:
            for field_name in field_names:
                if field_name in claimed or field_name.lower() != candidate.lower():
                    continue
                roles[field_name] = role
                claimed.add(field_name)
                matched += 1
                break
            if role != "extra" and matched:
                break
    if leftovers:
        for field_name in field_names:
            if field_name not in claimed:
                roles[field_name] = "extra"
    return roles


def _map_from_roles(roles: dict) -> FieldMap:
    lists = {role: [] for role in _ROLES}
    for role in _ROLES:
        for name in roles.get(role) or []:
            lists[role].append(str(name))
    return FieldMap(**{role: tuple(lists[role]) for role in _ROLES})


def _matches(name: str, names: tuple[str, ...]) -> bool:
    lowered = name.lower()
    return any(candidate.lower() == lowered for candidate in names)


def config_path_from(config: Config) -> Path | None:
    return config.path
