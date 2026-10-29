"""Command line entry points for sync and serve."""

from __future__ import annotations

import argparse
from pathlib import Path

from anki_semantic_search.config import Config, load_config


def main(argv: list[str] | None = None) -> None:
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
    sync.set_defaults(func=_sync)

    serve = commands.add_parser("serve", help="Serve the local MCP endpoint on localhost.")
    serve.set_defaults(func=_serve)

    args = parser.parse_args(argv)
    config = load_config(args.config)
    args.func(config, args)


def _sync(config: Config, args: argparse.Namespace) -> None:
    del config, args
    raise SystemExit("sync is not implemented yet.")


def _serve(config: Config, args: argparse.Namespace) -> None:
    del config, args
    raise SystemExit("serve is not implemented yet.")


if __name__ == "__main__":
    main()
