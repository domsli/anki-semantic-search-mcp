import io
import json
import sys
import unittest

from anki_semantic_search.cli import _emit, _stdin_json


class StdioEncodingTests(unittest.TestCase):
    def test_japanese_names_stay_utf8_when_the_console_encoding_is_legacy(self) -> None:
        raw_out = io.BytesIO()
        raw_in = io.BytesIO(json.dumps({"decks": ["日本語"]}).encode("utf-8"))
        old_out, old_in = sys.stdout, sys.stdin
        sys.stdout = io.TextIOWrapper(raw_out, encoding="cp932")
        sys.stdin = io.TextIOWrapper(raw_in, encoding="cp932")
        try:
            self.assertEqual(_stdin_json()["decks"], ["日本語"])
            _emit({"decks": ["日本語::単語"]})
            written = json.loads(raw_out.getvalue().decode("utf-8"))
            self.assertEqual(written["decks"], ["日本語::単語"])
        finally:
            sys.stdout = old_out
            sys.stdin = old_in


if __name__ == "__main__":
    unittest.main()
