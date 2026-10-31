# Anki Semantic Search

This is a local MCP server for your Japanese Anki deck. You ask ChatGPT something like "what's a word I recently learned that means feeling nervous," and it looks the word up in your cards instead of guessing.

An input card is one word: Japanese on the front, and a definition in Japanese or English on the back. The server embeds that word and definition on your machine. ChatGPT only receives the closest matches. The deck and the vectors stay local.

Reopening Anki does not refresh the index. Sync from the desktop window while Anki is open. Search keeps working after you close Anki.

To install the app and work on it, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Desktop window

Install the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on and open Anki, then open the desktop window.

- **Decks.** Check the decks to search. A checked name includes its subdecks. Save writes those names into `config.toml`.
- **Fields.** Pick a note type and, if you want, assign each field a role: word, reading, definition, extra, or skip. A note type without a custom map uses the shared field names in `config.toml`. The sample passage shows the text that will be embedded.
- **Sync.** Check sync compares the index with Anki. Sync updates the index. Rebuild re-embeds every note. The window shows when the index was last taken.
- **MCP server.** Start leaves a local server running for ChatGPT. Stop shuts down the server this window started. The address is `http://127.0.0.1:8000/mcp`.

Field editing, the live comparison, and Sync need Anki open. The server can stay up after Anki is closed.

## Connect ChatGPT

ChatGPT cannot call localhost. Use [OpenAI's Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels), which makes an outbound connection from this PC.

1. Create a tunnel in the OpenAI Platform account and associate it with the ChatGPT account, not only the Platform org.
2. Run `tunnel-client` against `http://127.0.0.1:8000/mcp`.
3. In ChatGPT, open Plugins, add a custom MCP server, choose Tunnel, pick this tunnel, and set authentication to none.

In a chat, invoke the plugin with `@` and ask for a word you learned. The server tells ChatGPT to call `search_notes`, and to use `learned_within_days=30` when you say "recently."

## Tools

- `list_decks` returns indexed deck names and the last sync time.
- `search_notes` returns the word, the definition in the language on the card, the deck, tags, when you first studied it, and a score.

Both tools are read-only.
