# Anki Semantic Search

Search Japanese Anki notes by meaning, then let ChatGPT answer from the matches. The deck and the vectors stay on this machine. ChatGPT only receives the notes the search tool returns.

An input card is one row: the Japanese word on the front, and a definition in Japanese or English on the back. An English question such as "feeling nervous" is embedded with the same local model as those definitions, and the closest notes come back.

Reopening Anki does not update the index. `anki-search sync` takes a snapshot while Anki is open. Search keeps working after Anki is closed.

## Setup

Install the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on, then open Anki.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

`config.toml` is already filled in from `config.example.toml`. Edit it if your deck name is not `Japanese`:

- `decks` lists the decks to index. A name matches that deck and its subdecks.
- `[fields]` maps your note type onto the word and the definition. The first matching field name wins. Other text fields are still indexed. Audio, images, and URL-only fields are skipped.

The default embedding model is `BAAI/bge-m3`. The first sync downloads it. `intfloat/multilingual-e5-base` is the smaller option in the config file.

## Desktop window

The Electron window edits the same `config.toml`: which decks to index, and a field map for each note type you customize. Note types without a map keep using `[fields]`. It also shows the last sync, compares the index with Anki while Anki is open, and starts or stops the local MCP server.

```powershell
cd desktop
npm install
npm start
```

## Sync

With Anki open:

```powershell
.\.venv\Scripts\anki-search.exe sync
```

A later sync re-embeds a note only when its word, definition, or embedding model changed. `--rebuild` re-embeds every note. `list_decks` reports `last_synced_at`.

## Serve

```powershell
.\.venv\Scripts\anki-search.exe serve
```

This listens on `http://127.0.0.1:8000/mcp` and refuses any other host. Leave this process running while you use ChatGPT.

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
