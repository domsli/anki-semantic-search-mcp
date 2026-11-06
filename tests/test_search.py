import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from anki_semantic_search.anki import RawNote, StudyStats
from anki_semantic_search.config import Config, FieldMap
import lancedb

from anki_semantic_search.index import TABLE_NAME, sync_index
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
    added: datetime = datetime(2024, 1, 1, tzinfo=timezone.utc),
    study: StudyStats = StudyStats(),
) -> RawNote:
    return RawNote(
        note_id=note_id,
        model_name="Basic",
        tags=("vocab",),
        fields={"Front": word, "Back": definition},
        deck_names=(deck,),
        card_ids=(note_id,),
        added_at=added,
        introduced_at=introduced,
        study=study,
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


class StudyFilterTests(unittest.TestCase):
    """Three nervous words with different study histories. Only the filter decides which match."""

    def _search(self, data_dir: Path, **filters) -> object:
        return search_notes(_config(data_dir), "feeling nervous", embedder=MeaningEmbedder(), now=NOW, **filters)

    def _seed(self, data_dir: Path) -> None:
        old = datetime(2024, 1, 1, tzinfo=timezone.utc)
        recent = datetime(2026, 10, 25, tzinfo=timezone.utc)
        notes = [
            # Added and reviewed recently, forgotten often, short interval.
            _note(
                1, "そわそわ", "緊張", introduced=old, added=recent,
                study=StudyStats(last_reviewed_at=recent, modified_at=recent, review_count=9, lapses=3, interval_days=2),
            ),
            # Old, well known, suspended.
            _note(
                2, "不安", "緊張している", introduced=old,
                study=StudyStats(last_reviewed_at=old, review_count=20, lapses=0, interval_days=200, suspended=True),
            ),
            # Never studied.
            _note(3, "どきどき", "緊張して胸が鳴る"),
        ]
        sync_index(_config(data_dir), notes=notes, embedder=MeaningEmbedder())

    def _words(self, result) -> set[str]:
        return {hit.word for hit in result.hits}

    def test_each_filter_keeps_only_matching_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._seed(data_dir)
            cases = {
                "reviewed_within_days": (7, {"そわそわ"}),
                "added_within_days": (7, {"そわそわ"}),
                "edited_within_days": (7, {"そわそわ"}),
                "min_lapses": (2, {"そわそわ"}),
                "max_interval_days": (7, {"そわそわ"}),
                "suspended": (True, {"不安"}),
            }
            for name, (value, expected) in cases.items():
                with self.subTest(name):
                    self.assertEqual(self._words(self._search(data_dir, **{name: value})), expected)
            self.assertEqual(self._words(self._search(data_dir, suspended=False)), {"そわそわ", "どきどき"})

    def test_max_interval_leaves_out_cards_never_studied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._seed(data_dir)
            self.assertNotIn("どきどき", self._words(self._search(data_dir, max_interval_days=300)))

    def test_filters_combine_and_explain_an_empty_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._seed(data_dir)
            result = self._search(data_dir, reviewed_within_days=7, suspended=True)
            self.assertEqual(result.hits, ())
            self.assertIn("reviewed in the last 7 days and suspended", result.message or "")
            self.assertIn("larger reviewed_within_days", result.message or "")

    def test_hits_carry_the_study_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._seed(data_dir)
            hit = self._search(data_dir, min_lapses=2).as_dict()["hits"][0]
            self.assertEqual((hit["lapses"], hit["interval_days"], hit["review_count"]), (3, 2, 9))
            self.assertEqual(hit["last_reviewed_at"], "2026-10-25T00:00:00Z")

    def test_negative_values_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._seed(data_dir)
            self.assertIn("reviewed_within_days", self._search(data_dir, reviewed_within_days=0).message or "")
            self.assertIn("min_lapses", self._search(data_dir, min_lapses=-1).message or "")

    def test_old_index_asks_for_an_update_instead_of_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            self._seed(data_dir)
            db = lancedb.connect(str(data_dir))
            old = db.open_table(TABLE_NAME).to_arrow().drop_columns(["last_reviewed_at", "lapses"])
            db.create_table(TABLE_NAME, data=old, mode="overwrite")
            result = self._search(data_dir, reviewed_within_days=7)
            self.assertEqual(result.hits, ())
            self.assertIn("Update deck", result.message or "")
            # Filters on columns that exist, and plain searches, still work.
            self.assertTrue(self._search(data_dir).hits)
            self.assertEqual(self._search(data_dir).as_dict()["hits"][0]["lapses"], 0)


if __name__ == "__main__":
    unittest.main()
