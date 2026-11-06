"""JSON commands the desktop window uses to read Anki and edit config.toml."""

from __future__ import annotations

import json
from pathlib import Path

from anki_semantic_search.anki import AnkiClient, AnkiError
from anki_semantic_search.config import Config, FieldMap, save_settings
from anki_semantic_search.index import _META_NAME, diff_index, indexed_decks, remove_decks
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
        "indexed_configuration": meta.get("configuration"),
    }


def connection(config: Config) -> dict:
    """Where Anki and the index are. Only the window's main process asks for this."""
    return {
        "ok": True,
        "anki_url": config.anki_url,
        "anki_api_key": config.anki_api_key,
        "meta_path": str(config.data_dir / _META_NAME),
    }


def list_decks(config: Config) -> dict:
    tracked = tracked_decks(config)
    try:
        with AnkiClient(config.anki_url, config.anki_api_key) as client:
            live = client.deck_names()
    except AnkiError as exc:
        return {"ok": True, "anki_open": False, "error": str(exc), "decks": [], "tracked": tracked}
    return {"ok": True, "anki_open": True, "decks": live, "tracked": tracked}


def tracked_decks(config: Config) -> list[str]:
    """Decks in config.toml, plus decks that are in the index but missing from it.

    Older versions searched one deck at a time, so the index can hold decks the
    config no longer names. Listing them lets the window keep or remove them.
    """
    tracked = list(config.decks)
    for name in indexed_decks(config):
        if name not in tracked:
            tracked.append(name)
    return tracked


def remove_deck(config: Config, payload: dict) -> dict:
    """Stop tracking decks, and delete their notes from the vector database."""
    path = config.path
    if path is None:
        return {"ok": False, "error": "Couldn't save your settings."}
    removed = [str(name) for name in payload.get("decks") or [] if str(name)]
    if not removed:
        return {"ok": False, "error": "Name a deck to remove."}
    remaining = [name for name in tracked_decks(config) if name not in removed]
    try:
        updated = save_settings(path, decks=remaining)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    deleted = remove_decks(updated, removed, remaining=remaining)
    return {**status(updated), "deleted": deleted}


def list_note_types(config: Config, decks: list[str] | None = None) -> dict:
    chosen = list(config.decks if decks is None else decks)
    if decks is not None and not chosen:
        return {"ok": True, "anki_open": True, "note_types": []}
    try:
        with AnkiClient(config.anki_url, config.anki_api_key) as client:
            live = client.note_types() if decks is None else client.note_types_in_decks(chosen)
    except AnkiError as exc:
        return {"ok": True, "anki_open": False, "error": str(exc), "note_types": []}
    types = []
    for item in live:
        name = item["name"]
        mapped = config.note_types.get(name)
        default_roles = _roles_for(item["fields"], config.fields, leftovers=True)
        types.append(
            {
                "name": name,
                "fields": item["fields"],
                "mapped": mapped is not None,
                "roles": default_roles if mapped is None else _roles_for(item["fields"], mapped, leftovers=False),
                "default_roles": default_roles,
            }
        )
    return {"ok": True, "anki_open": True, "note_types": types}


def preview_note(config: Config, payload: dict) -> dict:
    note_type = str(payload.get("note_type") or "")
    if not note_type:
        return {"ok": False, "error": "Choose a card type first."}
    decks = config.decks if payload.get("decks") is None else payload.get("decks")
    try:
        with AnkiClient(config.anki_url, config.anki_api_key) as client:
            note = client.sample_note(note_type, decks)
    except AnkiError as exc:
        return {"ok": False, "error": str(exc)}
    if note is None:
        return {"ok": True, "passage": "", "message": "None of these cards are in the decks you chose."}
    roles = payload.get("roles")
    if roles is None and payload.get("explicit") is False:
        # The default field names, even when this card type has custom settings saved.
        normalized = normalize_note(note, config.fields)
    elif roles is None:
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
        return {"ok": False, "error": "Couldn't save your settings."}
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


def _roles_for(field_names: list[str], field_map: FieldMap, *, leftovers: bool) -> dict[str, str]:
    roles = {name: "unassigned" for name in field_names}
    claimed: set[str] = set()
    for field_name in field_names:
        if _matches(field_name, field_map.skip):
            roles[field_name] = "unassigned"  # shown as Ignore
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
