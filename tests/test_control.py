import tempfile
import unittest
from pathlib import Path

from anki_semantic_search.config import load_config, save_settings
from anki_semantic_search.control import selected_decks


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


class SelectedDeckTests(unittest.TestCase):
    def test_missing_saved_deck_is_replaced_by_a_real_one(self) -> None:
        self.assertEqual(selected_decks(["Default", "Core"], ["Japanese"]), ["Core"])

    def test_saved_deck_is_kept_when_it_exists(self) -> None:
        self.assertEqual(selected_decks(["Default", "Core", "Mining"], ["Mining"]), ["Mining"])

    def test_only_the_first_saved_deck_is_selected(self) -> None:
        self.assertEqual(selected_decks(["Core", "Mining"], ["Mining", "Core"]), ["Mining"])

    def test_only_the_built_in_deck_is_used_when_it_is_the_only_one(self) -> None:
        self.assertEqual(selected_decks(["Default"], ["Japanese"]), ["Default"])


if __name__ == "__main__":
    unittest.main()
