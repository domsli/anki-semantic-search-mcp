"""Local MCP server that searches the Anki note index."""

from __future__ import annotations

from fastmcp import FastMCP

from anki_semantic_search.config import Config
from anki_semantic_search.search import QueryEmbedder, list_decks, search_notes

INSTRUCTIONS = (
    "This server searches the user's Anki decks. "
    "Use search_notes when the user asks for a word or phrase they learned, "
    "including a word that means something like feeling nervous. "
    "When the user says recently, set learned_within_days to 30. "
    "When they mean words they reviewed or that came up lately, use reviewed_within_days instead. "
    "Use added_within_days for words they added, and edited_within_days for cards they changed. "
    "For words they keep forgetting, set min_lapses to 2. For words they do not know well yet, "
    "set max_interval_days to 7. "
    "If the result says the filters left nothing, follow its advice and call search_notes again. "
    "Answer with the returned word and definition. Do not invent readings or Japanese words. "
    "Use list_decks to see indexed deck names and the last sync time."
)

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}


def build_server(config: Config, embedder: QueryEmbedder | None = None) -> FastMCP:
    mcp = FastMCP("Anki Semantic Search", instructions=INSTRUCTIONS)

    @mcp.tool(name="list_decks", annotations=_READ_ONLY)
    def list_decks_tool() -> dict:
        """List decks in the local Anki index and when it was last synced.

        Use this to choose a deck name before searching, or to see whether the index is stale.
        """
        return list_decks(config)

    @mcp.tool(name="search_notes", annotations=_READ_ONLY)
    def search_notes_tool(
        query: str,
        decks: list[str] | None = None,
        learned_within_days: int | None = None,
        reviewed_within_days: int | None = None,
        added_within_days: int | None = None,
        edited_within_days: int | None = None,
        min_lapses: int | None = None,
        max_interval_days: int | None = None,
        suspended: bool | None = None,
        limit: int = 8,
    ) -> dict:
        """Search indexed Anki notes by meaning or by the Japanese word.

        Use this when the user asks for a word or phrase they learned.
        Definitions may be Japanese or English. Quote the returned fields.

        Optional filters, all combined with AND:
        - learned_within_days: first studied in the last N days. Use 30 for "recently learned".
        - reviewed_within_days: last reviewed in the last N days.
        - added_within_days: card created in the last N days.
        - edited_within_days: note edited in the last N days.
        - min_lapses: forgotten at least N times.
        - max_interval_days: studied, with a review interval of at most N days (not well known yet).
        - suspended: true for only suspended cards, false to leave them out.

        Each hit also has added_at, introduced_at (first review), last_reviewed_at,
        modified_at, review_count, lapses, interval_days, and suspended. Dates are UTC.
        """
        return search_notes(
            config,
            query,
            decks=decks,
            learned_within_days=learned_within_days,
            reviewed_within_days=reviewed_within_days,
            added_within_days=added_within_days,
            edited_within_days=edited_within_days,
            min_lapses=min_lapses,
            max_interval_days=max_interval_days,
            suspended=suspended,
            limit=limit,
            embedder=embedder,
        ).as_dict()

    return mcp


def serve(config: Config) -> None:
    if config.host not in _LOOPBACK:
        raise SystemExit(
            f"Refusing to listen on {config.host}. Keep the server on localhost and use the OpenAI tunnel."
        )
    build_server(config).run(transport="http", host=config.host, port=config.port, path="/mcp")
