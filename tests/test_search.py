import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from anki_semantic_search.anki import RawNote
from anki_semantic_search.config import Config, FieldMap
from anki_semantic_search.index import sync_index
from anki_semantic_search.search import list_decks, search_notes

FIELDS = FieldMap(
    word=("Front",),
    reading=(),
    definition=("Back",),
    extra=(),
    skip=("Audio",),
)
NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


class MeaningEmbedder:
    model_name = "fake"

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        if text == "猫":
            return [1.0, 0.0]
        if "Word: 猫" in text:
            return [0.0, 1.0]
        if "Word: 犬" in text:
            return [0.9, 0.1]
        if any(token in text for token in ("nervous", "緊張", "そわそわ")):
            return [1.0, 0.0]
        return [0.0, 0.0]


def _note(
    note_id: int,
    word: str,
    definition: str,
    *,
    deck: str = "Japanese",
    introduced: datetime | None = None,
) -> RawNote:
    return RawNote(
        note_id=note_id,
        model_name="Basic",
        tags=("vocab",),
        fields={"Front": word, "Back": definition},
        deck_names=(deck,),
        card_ids=(note_id,),
        added_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        introduced_at=introduced,
    )


def _config(data_dir: Path) -> Config:
    return Config(
        anki_url="http://127.0.0.1:8765",
        anki_api_key=None,
        decks=("Japanese",),
        embedding_model="fake",
        host="127.0.0.1",
        port=8000,
        data_dir=data_dir,
        fields=FIELDS,
    )


class SearchTests(unittest.TestCase):
    def test_english_query_finds_a_japanese_definition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            config = _config(data_dir)
            sync_index(
                config,
                notes=[
                    _note(1, "そわそわ", "緊張している感じ", introduced=datetime(2026, 10, 12, tzinfo=timezone.utc)),
                    _note(2, "猫", "cat", introduced=datetime(2026, 10, 12, tzinfo=timezone.utc)),
                ],
                embedder=MeaningEmbedder(),
            )
            result = search_notes(
                config,
                "feeling nervous",
                learned_within_days=30,
                embedder=MeaningEmbedder(),
                now=NOW,
            )
            self.assertIsNone(result.message)
            self.assertEqual(result.hits[0].word, "そわそわ")
            self.assertIn("緊張", result.hits[0].definition)
            self.assertEqual(result.as_dict()["hits"][0]["decks"], ["Japanese"])

    def test_japanese_query_ranks_the_exact_word_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            config = _config(data_dir)
            sync_index(
                config,
                notes=[_note(1, "犬", "dog"), _note(2, "猫", "animal")],
                embedder=MeaningEmbedder(),
            )
            result = search_notes(config, "猫", embedder=MeaningEmbedder(), now=NOW)
            self.assertEqual(result.hits[0].word, "猫")

    def test_recent_window_excludes_older_notes_and_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            config = _config(data_dir)
            recent = _note(1, "そわそわ", "緊張", introduced=datetime(2026, 10, 20, tzinfo=timezone.utc))
            older = _note(2, "不安", "緊張している", introduced=datetime(2024, 1, 1, tzinfo=timezone.utc))
            sync_index(config, notes=[recent, older], embedder=MeaningEmbedder())
            result = search_notes(
                config,
                "feeling nervous",
                learned_within_days=30,
                embedder=MeaningEmbedder(),
                now=NOW,
            )
            self.assertEqual([hit.word for hit in result.hits], ["そわそわ"])

            sync_index(config, notes=[older], embedder=MeaningEmbedder())
            empty = search_notes(
                config,
                "feeling nervous",
                learned_within_days=30,
                embedder=MeaningEmbedder(),
                now=NOW,
            )
            self.assertEqual(empty.hits, ())
            self.assertIn("30 days", empty.message or "")
            self.assertIn("larger learned_within_days", empty.message or "")

    def test_deck_filter_names_the_deck_when_nothing_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            config = _config(data_dir)
            sync_index(
                config,
                notes=[_note(1, "そわそわ", "緊張", deck="Japanese::Core")],
                embedder=MeaningEmbedder(),
            )
            result = search_notes(
                config,
                "feeling nervous",
                decks=["Other"],
                embedder=MeaningEmbedder(),
                now=NOW,
            )
            self.assertEqual(result.hits, ())
            self.assertIn("Other", result.message or "")

    def test_child_deck_matches_a_parent_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            config = _config(data_dir)
            sync_index(
                config,
                notes=[_note(1, "そわそわ", "緊張", deck="Japanese::Core")],
                embedder=MeaningEmbedder(),
            )
            result = search_notes(
                config,
                "feeling nervous",
                decks=["Japanese"],
                embedder=MeaningEmbedder(),
                now=NOW,
            )
            self.assertEqual(result.hits[0].decks, ("Japanese::Core",))

    def test_list_decks_reports_the_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            config = _config(data_dir)
            self.assertIn("empty", list_decks(config)["message"])
            sync_index(
                config,
                notes=[_note(1, "猫", "cat", deck="Japanese::Core")],
                embedder=MeaningEmbedder(),
            )
            listed = list_decks(config)
            self.assertEqual(listed["decks"], ["Japanese::Core"])
            self.assertEqual(listed["note_count"], 1)
            self.assertTrue(listed["last_synced_at"])


if __name__ == "__main__":
    unittest.main()
