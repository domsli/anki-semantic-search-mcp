# Anki Semantic Search

This is a local MCP server for your Japanese Anki deck. You ask ChatGPT something like "what's a word I recently learned that means feeling nervous," and it looks the word up in your cards instead of guessing.

An input card is one word: Japanese on the front, and a definition in Japanese or English on the back. The server embeds that word and definition on your machine. ChatGPT only receives the closest matches. The deck and the vectors stay local.

Reopening Anki does not refresh the index. Sync from the desktop window while Anki is open. Search keeps working after you close Anki.

To install the app and work on it, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Desktop window

Install the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on and open Anki, then open the desktop window.

The window does four things, in order:

1. **Choose decks.** A checked deck is included, including decks inside it. An unchecked deck is left out. The check waits until you update search.
2. **Mark the word and the definition.** Optional. Say which box is the word and which is the definition. Card types you leave alone still match usual names such as Front, Expression, or Meaning.
3. **Update search.** This is the button that applies the checks and reads Anki. Anki needs to be open. See what changed previews that update. Update everything rereads every card. Save without updating remembers the checks for later.
4. **Turn on ChatGPT.** Start after search is updated. The address is `http://127.0.0.1:8000/mcp`. ChatGPT can keep searching after you close Anki, as long as this stays on.

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
