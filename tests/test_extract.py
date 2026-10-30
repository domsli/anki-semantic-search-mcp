import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx

from anki_semantic_search.anki import AnkiClient, AnkiError, RawNote, deck_query
from anki_semantic_search.config import Config, FieldMap
from anki_semantic_search.normalize import content_hash, html_to_text, normalize_for_config, normalize_note

FIELDS = FieldMap(
    word=("Expression", "Word", "Front"),
    reading=("Reading",),
    definition=("Meaning", "Back"),
    extra=("Notes",),
    skip=("Audio", "Image"),
)


def _note(**fields: str) -> RawNote:
    return RawNote(
        note_id=1_700_000_000_000,
        model_name="Basic",
        tags=("vocab",),
        fields=dict(fields),
        deck_names=("Japanese",),
        card_ids=(42,),
        added_at=datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc),
        introduced_at=None,
    )


class HtmlTests(unittest.TestCase):
    def test_line_breaks_and_media_are_cleaned(self) -> None:
        text = html_to_text(
            '<div>そわそわ</div><div>next<br>line</div><img src="a.jpg"><script>no</script>'
            "[sound:a.mp3]"
        )
        self.assertEqual(text, "そわそわ\nnext\nline")

    def test_ruby_keeps_base_and_reading(self) -> None:
        text = html_to_text("<ruby>漢<rp>(</rp><rt>かん</rt><rp>)</rp></ruby>")
        self.assertEqual(text, "漢 かん")

    def test_cloze_hint_is_dropped(self) -> None:
        self.assertEqual(html_to_text("{{c1::緊張::hint}}"), "緊張")


class NormalizeTests(unittest.TestCase):
    def test_input_card_maps_word_and_definition(self) -> None:
        note = normalize_note(
            _note(Front="そわそわ", Back="落ち着かない<br>nervous", Audio="[sound:a.mp3]"),
            FIELDS,
        )
        self.assertEqual(note.word, "そわそわ")
        self.assertEqual(note.definition, "落ち着かない\nnervous")
        self.assertEqual(note.passage, "Word: そわそわ\nDefinition: 落ち着かない\nnervous")

    def test_field_match_is_case_insensitive_and_config_order_wins(self) -> None:
        note = normalize_note(_note(expression="語", meaning="意味", Back="ignored"), FIELDS)
        self.assertEqual(note.word, "語")
        self.assertEqual(note.definition, "意味")

    def test_renamed_definition_stays_in_the_passage(self) -> None:
        note = normalize_note(_note(Front="そわそわ", Gloss="緊張している感じ"), FIELDS)
        self.assertEqual(note.word, "そわそわ")
        self.assertEqual(note.definition, "")
        self.assertIn("緊張している感じ", note.passage)

    def test_unmapped_note_keeps_original_field_names(self) -> None:
        note = normalize_note(_note(Term="そわそわ", Gloss="緊張"), FIELDS)
        self.assertEqual(note.word, "")
        self.assertEqual(note.passage, "Term: そわそわ\nGloss: 緊張")

    def test_url_only_field_is_skipped(self) -> None:
        note = normalize_note(_note(Front="語", Back="https://example.com/a"), FIELDS)
        self.assertEqual(note.definition, "")
        self.assertNotIn("example.com", note.passage)

    def test_hash_changes_when_the_model_changes(self) -> None:
        self.assertNotEqual(content_hash("Word: 語", "BAAI/bge-m3"), content_hash("Word: 語", "other"))

    def test_explicit_map_drops_unassigned_fields(self) -> None:
        mapped = FieldMap(word=("Front",), definition=("Back",), skip=("Audio",))
        note = normalize_note(
            _note(Front="語", Back="意味", Gloss="余分", Audio="clip"),
            mapped,
            explicit=True,
        )
        self.assertEqual(note.passage, "Word: 語\nDefinition: 意味")
        self.assertNotIn("余分", note.passage)

    def test_unmapped_note_type_uses_the_fallback_list(self) -> None:
        config = Config(
            anki_url="http://127.0.0.1:8765",
            anki_api_key=None,
            decks=("Japanese",),
            embedding_model="fake",
            host="127.0.0.1",
            port=8000,
            data_dir=Path("."),
            fields=FIELDS,
            note_types={"Other": FieldMap(word=("Front",), definition=("Back",))},
        )
        note = normalize_for_config(_note(Front="語", Gloss="緊張"), config)
        self.assertIn("緊張", note.passage)


class AnkiClientTests(unittest.TestCase):
    def test_deck_query_quotes_names(self) -> None:
        self.assertEqual(deck_query(["Japanese"]), 'deck:"Japanese"')
        self.assertEqual(
            deck_query(['Core "2k"', "Extra"]),
            r'(deck:"Core \"2k\"" OR deck:"Extra")',
        )

    def test_fetch_notes_uses_the_earliest_review(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            self.assertEqual(body["version"], 6)
            self.assertEqual(body["key"], "secret")
            action = body["action"]
            calls.append(action)
            if action == "findNotes":
                result = [1_700_000_000_000]
            elif action == "notesInfo":
                result = [
                    {
                        "noteId": 1_700_000_000_000,
                        "modelName": "Basic",
                        "tags": ["vocab"],
                        "fields": {
                            "Front": {"value": "そわそわ", "order": 0},
                            "Back": {"value": "nervous", "order": 1},
                        },
                        "cards": [50],
                    }
                ]
            elif action == "cardsInfo":
                result = [{"cardId": 50, "deckName": "Japanese"}]
            elif action == "getReviewsOfCards":
                self.assertEqual(body["params"]["cards"], ["50"])
                result = {
                    "50": [
                        {"id": 1_800_000_000_000, "ease": 3},
                        {"id": 1_750_000_000_000, "ease": 2},
                    ]
                }
            else:
                raise AssertionError(action)
            return httpx.Response(200, json={"result": result, "error": None})

        with AnkiClient(
            "http://127.0.0.1:8765",
            "secret",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        ) as client:
            notes = client.fetch_notes(["Japanese"])

        self.assertEqual(calls, ["findNotes", "notesInfo", "cardsInfo", "getReviewsOfCards"])
        self.assertEqual(len(notes), 1)
        note = notes[0]
        self.assertEqual(note.fields["Front"], "そわそわ")
        self.assertEqual(note.deck_names, ("Japanese",))
        self.assertEqual(note.introduced_at, datetime.fromtimestamp(1_750_000_000, tz=timezone.utc))
        normalized = normalize_note(note, FIELDS)
        self.assertEqual(normalized.word, "そわそわ")
        self.assertEqual(normalized.definition, "nervous")
        self.assertEqual(normalized.introduced_at, note.introduced_at)

    def test_api_error_is_raised(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(200, json={"result": None, "error": "collection is not open"})

        client = AnkiClient("http://127.0.0.1:8765", client=httpx.Client(transport=httpx.MockTransport(handler)))
        with self.assertRaises(AnkiError):
            client.fetch_notes(["Japanese"])

    def test_connection_error_names_anki(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            del request
            raise httpx.ConnectError("refused")

        client = AnkiClient("http://127.0.0.1:8765", client=httpx.Client(transport=httpx.MockTransport(handler)))
        with self.assertRaises(AnkiError) as caught:
            client.invoke("version")
        self.assertIn("AnkiConnect", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
