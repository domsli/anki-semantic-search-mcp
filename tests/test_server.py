import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from anki_semantic_search.anki import RawNote
from anki_semantic_search.config import Config, FieldMap
from anki_semantic_search.index import sync_index
from anki_semantic_search.server import INSTRUCTIONS, build_server, serve

FIELDS = FieldMap(word=("Front",), reading=(), definition=("Back",), extra=(), skip=("Audio",))


class MeaningEmbedder:
    model_name = "fake"

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        if any(token in text for token in ("nervous", "緊張", "そわそわ")):
            return [1.0, 0.0]
        return [0.0, 1.0]


def _config(data_dir: Path, host: str = "127.0.0.1") -> Config:
    return Config(
        anki_url="http://127.0.0.1:8765",
        anki_api_key=None,
        decks=("Japanese",),
        embedding_model="fake",
        host=host,
        port=8000,
        data_dir=data_dir,
        fields=FIELDS,
    )


class ServerTests(unittest.TestCase):
    def test_tools_are_read_only_and_named_for_the_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mcp = build_server(_config(Path(tmp)))
            self.assertIn("learned_within_days to 30", INSTRUCTIONS)
            self.assertIn(INSTRUCTIONS, mcp.instructions or "")
            tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
            self.assertEqual(set(tools), {"list_decks", "search_notes"})
            self.assertTrue(tools["search_notes"].annotations.read_only_hint)
            self.assertIn("recently", tools["search_notes"].description)

    def test_search_tool_returns_the_indexed_word(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            config = _config(data_dir)
            embedder = MeaningEmbedder()
            sync_index(
                config,
                notes=[
                    RawNote(
                        note_id=1,
                        model_name="Basic",
                        tags=(),
                        fields={"Front": "そわそわ", "Back": "緊張している感じ"},
                        deck_names=("Japanese",),
                        card_ids=(1,),
                        added_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                        introduced_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
                    )
                ],
                embedder=embedder,
            )
            mcp = build_server(config, embedder=embedder)
            result = asyncio.run(mcp.call_tool("search_notes", {"query": "feeling nervous", "learned_within_days": 30}))
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["hits"][0]["word"], "そわそわ")

    def test_serve_refuses_a_public_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as caught:
                serve(_config(Path(tmp), host="0.0.0.0"))
            self.assertIn("localhost", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
