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
    "If the result says that window was empty, call search_notes again with a larger learned_within_days. "
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
        limit: int = 8,
    ) -> dict:
        """Search indexed Anki notes by meaning or by the Japanese word.

        Use this when the user asks for a word or phrase they learned.
        Pass learned_within_days=30 when they say recently.
        Definitions may be Japanese or English. Quote the returned fields.
        """
        return search_notes(
            config,
            query,
            decks=decks,
            learned_within_days=learned_within_days,
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
