# Contributing

Setup for working on the Python package and the Electron window. For what the app does and how to connect ChatGPT, see [README.md](README.md).

## Python

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Copy `config.example.toml` to `config.toml` if you do not already have one.

- `decks` lists the decks to index. A name matches that deck and its subdecks.
- `[fields]` maps a note type onto the word and the definition. The first matching field name wins. Other text fields are still indexed. Audio, images, and URL-only fields are skipped.
- `[note_types]` holds custom maps saved from the desktop window. Note types absent from that table keep using `[fields]`.

The default embedding model is `BAAI/bge-m3`. The first sync downloads it. `intfloat/multilingual-e5-base` is the smaller option in the config file. Changing the model re-embeds the index on the next sync.

With Anki open:

```powershell
.\.venv\Scripts\anki-search.exe sync
.\.venv\Scripts\anki-search.exe sync --rebuild
.\.venv\Scripts\anki-search.exe serve
```

A later sync re-embeds a note only when its word, definition, or embedding model changed. `--rebuild` re-embeds every note. `serve` listens on `http://127.0.0.1:8000/mcp` and refuses any other host.

Tests use a fake embedder and do not download a model or require Anki:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Desktop

The window is a Svelte app in `desktop/`. Electron starts the Python commands above; it does not index or search on its own.

```powershell
cd desktop
npm install
npm start
```

`npm start` builds the UI, then opens the window. `npm run dev` serves the UI and reloads the window while you edit it.

`desktop/src` is the Svelte UI. `desktop/main.js` is the Electron process. `desktop/preload.js` is the bridge the UI calls.
