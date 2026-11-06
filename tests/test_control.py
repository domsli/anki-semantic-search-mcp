import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import lancedb

from anki_semantic_search.config import Config, FieldMap, load_config, save_settings
from anki_semantic_search.anki import RawNote
from anki_semantic_search.control import list_note_types, remove_deck, tracked_decks
from anki_semantic_search.index import TABLE_NAME, sync_index


class DefaultConfigTests(unittest.TestCase):
    def test_missing_config_is_created_from_the_example(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            example = folder / "config.example.toml"
            example.write_text(
                'anki_url = "http://127.0.0.1:8765"\ndecks = ["Japanese"]\nembedding_model = "BAAI/bge-m3"\n',
                encoding="utf-8",
            )
            target = folder / "config.toml"
            loaded = load_config(target)
            self.assertTrue(target.is_file())
            self.assertEqual(loaded.decks, ("Japanese",))
            self.assertEqual(loaded.embedding_model, "BAAI/bge-m3")


class SaveSettingsTests(unittest.TestCase):
    def test_save_keeps_the_model_and_writes_note_type_maps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                "\n".join(
                    [
                        'anki_url = "http://127.0.0.1:8765"',
                        'decks = ["Japanese"]',
                        'embedding_model = "BAAI/bge-m3"',
                        'host = "127.0.0.1"',
                        "port = 8000",
                        "",
                        "[fields]",
                        'word = ["Front"]',
                        'definition = ["Back"]',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            save_settings(
                path,
                decks=["Japanese", "Japanese::Core"],
                note_types={"Basic": {"word": ["Front"], "definition": ["Back"], "skip": ["Audio"]}},
            )
            loaded = load_config(path)
            self.assertEqual(loaded.embedding_model, "BAAI/bge-m3")
            self.assertEqual(loaded.decks, ("Japanese", "Japanese::Core"))
            self.assertEqual(loaded.note_types["Basic"].word, ("Front",))
            self.assertEqual(loaded.note_types["Basic"].skip, ("Audio",))
            self.assertEqual(loaded.fields.definition, ("Back",))

    def test_japanese_deck_names_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                'anki_url = "http://127.0.0.1:8765"\ndecks = ["Japanese"]\nembedding_model = "BAAI/bge-m3"\n',
                encoding="utf-8",
            )
            save_settings(path, decks=["日本語", "日本語::単語"])
            loaded = load_config(path)
            self.assertEqual(loaded.decks, ("日本語", "日本語::単語"))
            self.assertIn("日本語::単語", path.read_text(encoding="utf-8"))

    def test_empty_deck_list_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                'anki_url = "http://127.0.0.1:8765"\ndecks = []\nembedding_model = "BAAI/bge-m3"\n',
                encoding="utf-8",
            )
            self.assertEqual(load_config(path).decks, ())


class _Embedder:
    model_name = "fake"

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]


def _note(note_id: int, word: str, deck: str) -> RawNote:
    return RawNote(
        note_id=note_id,
        model_name="Basic",
        tags=(),
        fields={"Front": word, "Back": "meaning"},
        deck_names=(deck,),
        card_ids=(note_id,),
        added_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        introduced_at=None,
    )


class TrackedDeckTests(unittest.TestCase):
    def _setup(self, folder: Path) -> Path:
        path = folder / "config.toml"
        path.write_text(
            'anki_url = "http://127.0.0.1:8765"\ndecks = ["Core", "Mining"]\nembedding_model = "fake"\n'
            "[fields]\nword = [\"Front\"]\ndefinition = [\"Back\"]\n",
            encoding="utf-8",
        )
        config = load_config(path)
        notes = [
            _note(1, "猫", "Core"),
            _note(2, "犬", "Core::Animals"),
            _note(3, "鳥", "Mining"),
        ]
        sync_index(config, notes=notes, embedder=_Embedder())
        return path

    def _words(self, folder: Path) -> set[str]:
        table = lancedb.connect(str(folder / "data")).open_table(TABLE_NAME)
        return {row["word"] for row in table.to_arrow().to_pylist()}

    def test_decks_in_the_index_are_tracked_even_when_the_config_lost_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = self._setup(folder)
            save_settings(path, decks=["Mining"])
            self.assertEqual(tracked_decks(load_config(path)), ["Mining", "Core"])

    def test_removing_a_deck_deletes_its_notes_and_nested_decks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = self._setup(folder)
            result = remove_deck(load_config(path), {"decks": ["Core"]})
            self.assertTrue(result["ok"])
            self.assertEqual(result["deleted"], 2)
            self.assertEqual(result["decks"], ["Mining"])
            self.assertEqual(result["note_count"], 1)
            self.assertEqual(result["indexed_configuration"]["decks"], ["Mining"])
            meta = json.loads((folder / "data" / "sync_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["seen_note_ids"], {"Mining": [3]})
            self.assertEqual(self._words(folder), {"鳥"})
            self.assertEqual(load_config(path).decks, ("Mining",))

    def test_a_note_in_a_remaining_deck_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = self._setup(folder)
            save_settings(path, decks=["Core", "Core::Animals", "Mining"])
            result = remove_deck(load_config(path), {"decks": ["Core"]})
            self.assertEqual(result["deleted"], 1)
            self.assertEqual(self._words(folder), {"犬", "鳥"})

    def test_removing_the_last_deck_leaves_an_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = self._setup(folder)
            remove_deck(load_config(path), {"decks": ["Core", "Mining"]})
            self.assertEqual(load_config(path).decks, ())
            self.assertEqual(self._words(folder), set())
            meta = json.loads((folder / "data" / "sync_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["configuration"]["decks"], [])

    def test_removing_needs_a_deck_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._setup(Path(tmp))
            self.assertFalse(remove_deck(load_config(path), {"decks": []})["ok"])


class NoteTypeRoleTests(unittest.TestCase):
    def _config(self, note_types: dict[str, FieldMap]) -> Config:
        return Config(
            anki_url="http://127.0.0.1:8765",
            anki_api_key=None,
            decks=("Japanese",),
            embedding_model="BAAI/bge-m3",
            host="127.0.0.1",
            port=8000,
            data_dir=Path("data"),
            fields=FieldMap(word=("Front",), definition=("Back",), skip=("Audio",)),
            note_types=note_types,
        )

    def _list(self, config: Config) -> dict:
        client = mock.MagicMock()
        client.__enter__.return_value.note_types_in_decks.return_value = [
            {"name": "Basic", "fields": ["Front", "Back", "Audio", "Notes"]}
        ]
        with mock.patch("anki_semantic_search.control.AnkiClient", return_value=client):
            return list_note_types(config, ["Japanese"])["note_types"][0]

    def test_default_card_type_shows_the_default_roles(self) -> None:
        item = self._list(self._config({}))
        expected = {"Front": "word", "Back": "definition", "Audio": "unassigned", "Notes": "extra"}
        self.assertFalse(item["mapped"])
        self.assertEqual(item["roles"], expected)
        self.assertEqual(item["default_roles"], expected)

    def test_custom_card_type_keeps_the_defaults_for_reset(self) -> None:
        item = self._list(self._config({"Basic": FieldMap(word=("Back",), definition=("Front",))}))
        self.assertTrue(item["mapped"])
        self.assertEqual(
            item["roles"],
            {"Front": "definition", "Back": "word", "Audio": "unassigned", "Notes": "unassigned"},
        )
        self.assertEqual(item["default_roles"]["Front"], "word")


if __name__ == "__main__":
    unittest.main()
