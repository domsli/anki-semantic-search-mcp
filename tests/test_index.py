import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import lancedb

from anki_semantic_search.anki import RawNote
from anki_semantic_search.config import Config, FieldMap
from anki_semantic_search.index import TABLE_NAME, diff_index, sync_index

FIELDS = FieldMap(
    word=("Front",),
    reading=(),
    definition=("Back",),
    extra=(),
    skip=("Audio",),
)


class FakeEmbedder:
    def __init__(self, model_name: str = "fake") -> None:
        self.model_name = model_name
        self.calls: list[str] = []

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.calls.extend(texts)
        return [[float(len(text)), 1.0] for text in texts]


def _note(note_id: int, word: str, definition: str, *, introduced: datetime | None = None) -> RawNote:
    return RawNote(
        note_id=note_id,
        model_name="Basic",
        tags=("vocab",),
        fields={"Front": word, "Back": definition},
        deck_names=("Japanese",),
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


def _rows(data_dir: Path) -> list[dict]:
    db = lancedb.connect(str(data_dir))
    return db.open_table(TABLE_NAME).to_arrow().to_pylist()


class SyncTests(unittest.TestCase):
    def test_second_sync_skips_unchanged_passages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            notes = [_note(1, "そわそわ", "緊張している感じ"), _note(2, "猫", "cat")]
            first = FakeEmbedder()
            stats = sync_index(_config(data_dir), notes=notes, embedder=first)
            self.assertEqual(stats.embedded, 2)
            self.assertEqual(len(first.calls), 2)

            second = FakeEmbedder()
            stats = sync_index(_config(data_dir), notes=notes, embedder=second)
            self.assertEqual(stats.embedded, 0)
            self.assertEqual(stats.unchanged, 2)
            self.assertEqual(second.calls, [])
            self.assertEqual({row["word"] for row in _rows(data_dir)}, {"そわそわ", "猫"})

    def test_changed_definition_is_reembedded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            sync_index(_config(data_dir), notes=[_note(1, "そわそわ", "緊張")], embedder=FakeEmbedder())
            embedder = FakeEmbedder()
            stats = sync_index(
                _config(data_dir),
                notes=[_note(1, "そわそわ", "落ち着かない")],
                embedder=embedder,
            )
            self.assertEqual(stats.embedded, 1)
            self.assertEqual(len(embedder.calls), 1)
            self.assertIn("落ち着かない", _rows(data_dir)[0]["definition"])

    def test_review_time_updates_without_a_new_vector(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            sync_index(_config(data_dir), notes=[_note(1, "猫", "cat")], embedder=FakeEmbedder())
            introduced = datetime(2026, 10, 1, tzinfo=timezone.utc)
            embedder = FakeEmbedder()
            stats = sync_index(
                _config(data_dir),
                notes=[_note(1, "猫", "cat", introduced=introduced)],
                embedder=embedder,
            )
            self.assertEqual((stats.embedded, stats.updated), (0, 1))
            self.assertEqual(embedder.calls, [])
            self.assertEqual(_rows(data_dir)[0]["introduced_at"], "2026-10-01T00:00:00Z")

    def test_notes_that_left_the_deck_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            sync_index(
                _config(data_dir),
                notes=[_note(1, "猫", "cat"), _note(2, "犬", "dog")],
                embedder=FakeEmbedder(),
            )
            stats = sync_index(_config(data_dir), notes=[_note(1, "猫", "cat")], embedder=FakeEmbedder())
            self.assertEqual(stats.removed, 1)
            self.assertEqual([row["word"] for row in _rows(data_dir)], ["猫"])

    def test_rebuild_reembeds_every_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            notes = [_note(1, "猫", "cat")]
            sync_index(_config(data_dir), notes=notes, embedder=FakeEmbedder())
            embedder = FakeEmbedder()
            stats = sync_index(_config(data_dir), notes=notes, embedder=embedder, rebuild=True)
            self.assertEqual(stats.embedded, 1)
            self.assertEqual(len(embedder.calls), 1)

    def test_model_change_rewrites_the_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            notes = [_note(1, "猫", "cat")]
            sync_index(_config(data_dir), notes=notes, embedder=FakeEmbedder("fake"))
            stats = sync_index(_config(data_dir), notes=notes, embedder=FakeEmbedder("other"))
            self.assertEqual(stats.embedded, 1)
            self.assertEqual(_rows(data_dir)[0]["embedding_model"], "other")

    def test_diff_counts_a_changed_definition_without_rewriting_vectors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            config = _config(data_dir)
            sync_index(config, notes=[_note(1, "そわそわ", "緊張")], embedder=FakeEmbedder())
            before = _rows(data_dir)[0]["vector"]
            report = diff_index(config, notes=[_note(1, "そわそわ", "落ち着かない")])
            self.assertEqual(report["would_embed"], 1)
            self.assertEqual(report["examples"]["embed"], ["そわそわ"])
            self.assertEqual(_rows(data_dir)[0]["vector"], before)
            self.assertEqual(_rows(data_dir)[0]["definition"], "緊張")

    def test_sync_reports_embed_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events: list[tuple[int, int]] = []
            sync_index(
                _config(Path(tmp)),
                notes=[_note(1, "猫", "cat"), _note(2, "犬", "dog")],
                embedder=FakeEmbedder(),
                on_progress=lambda done, total: events.append((done, total)),
            )
            self.assertEqual(events, [(0, 2), (2, 2)])

    def test_sync_records_when_the_snapshot_was_taken(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            sync_index(_config(data_dir), notes=[_note(1, "猫", "cat")], embedder=FakeEmbedder())
            meta = json.loads((data_dir / "sync_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["note_count"], 1)
            self.assertEqual(meta["embedded"], 1)
            self.assertTrue(meta["last_synced_at"])


if __name__ == "__main__":
    unittest.main()
