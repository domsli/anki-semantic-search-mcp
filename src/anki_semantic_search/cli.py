"""Command line entry points for sync, serve, and the desktop window."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from anki_semantic_search.anki import AnkiError
from anki_semantic_search.config import Config, load_config
from anki_semantic_search.control import list_decks, list_note_types, preview_note, read_diff, save, status
from anki_semantic_search.index import sync_index
from anki_semantic_search.server import serve


def main(argv: list[str] | None = None) -> None:
    _use_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="anki-search",
        description="Index Anki notes locally and serve them to ChatGPT over MCP.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to config.toml (default: ./config.toml)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    sync = commands.add_parser("sync", help="Pull notes from Anki and update the local index.")
    sync.add_argument(
        "--rebuild",
        action="store_true",
        help="Re-embed every configured note, ignoring saved passage hashes.",
    )
    sync.add_argument("--json", action="store_true", help="Print JSON progress lines for the desktop window.")
    sync.set_defaults(func=_sync)

    serve_command = commands.add_parser("serve", help="Serve the local MCP endpoint on localhost.")
    serve_command.set_defaults(func=_serve)

    for name, func, help_text in (
        ("status", _status, "Show the last sync snapshot without contacting Anki."),
        ("decks", _decks, "List Anki decks and which ones are selected."),
        ("note-types", _note_types, "List Anki note types and their field roles."),
        ("diff", _diff, "Compare Anki with the index without embedding."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.set_defaults(func=func)

    preview = commands.add_parser("preview", help="Render one sample passage. Reads a JSON body from stdin.")
    preview.set_defaults(func=_preview)
    save_command = commands.add_parser("save", help="Write decks and note-type maps. Reads a JSON body from stdin.")
    save_command.set_defaults(func=_save)

    args = parser.parse_args(argv)
    config = load_config(args.config)
    args.func(config, args)


def _sync(config: Config, args: argparse.Namespace) -> None:
    def on_progress(done: int, total: int) -> None:
        _emit({"event": "progress", "embedded": done, "total": total})

    try:
        stats = sync_index(
            config,
            rebuild=args.rebuild,
            on_progress=on_progress if args.json else None,
        )
    except AnkiError as exc:
        if args.json:
            _emit({"ok": False, "error": str(exc)})
            raise SystemExit(1) from exc
        raise SystemExit(str(exc)) from exc
    payload = {
        "ok": True,
        "event": "done",
        "total": stats.total,
        "embedded": stats.embedded,
        "updated": stats.updated,
        "unchanged": stats.unchanged,
        "removed": stats.removed,
    }
    if args.json:
        _emit(payload)
        return
    print(
        f"Indexed {stats.total} notes: embedded {stats.embedded}, "
        f"updated {stats.updated}, unchanged {stats.unchanged}, removed {stats.removed}."
    )


def _serve(config: Config, args: argparse.Namespace) -> None:
    del args
    serve(config)


def _status(config: Config, args: argparse.Namespace) -> None:
    del args
    _emit(status(config))


def _decks(config: Config, args: argparse.Namespace) -> None:
    del args
    _emit(list_decks(config))


def _note_types(config: Config, args: argparse.Namespace) -> None:
    del args
    _emit(list_note_types(config))


def _diff(config: Config, args: argparse.Namespace) -> None:
    del args
    result = read_diff(config)
    _emit(result)
    if not result.get("ok", False):
        raise SystemExit(1)


def _preview(config: Config, args: argparse.Namespace) -> None:
    del args
    result = preview_note(config, _stdin_json())
    _emit(result)
    if not result.get("ok", False):
        raise SystemExit(1)


def _save(config: Config, args: argparse.Namespace) -> None:
    del args
    result = save(config, _stdin_json())
    _emit(result)
    if not result.get("ok", False):
        raise SystemExit(1)


def _use_utf8_stdio() -> None:
    """Keep Japanese deck names intact on Windows, where pipes default to a legacy code page."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="strict")
        except (OSError, ValueError):
            continue


def _stdin_json() -> dict:
    raw = _read_stdin()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _emit({"ok": False, "error": f"Invalid JSON: {exc}"})
        raise SystemExit(1) from exc
    if not isinstance(payload, dict):
        _emit({"ok": False, "error": "JSON body must be an object."})
        raise SystemExit(1)
    return payload


def _read_stdin() -> str:
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is None:
        return sys.stdin.read()
    return buffer.read().decode("utf-8")


def _emit(payload: dict) -> None:
    line = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        print(line.decode("utf-8"), end="", flush=True)
        return
    buffer.write(line)
    buffer.flush()


if __name__ == "__main__":
    main()
