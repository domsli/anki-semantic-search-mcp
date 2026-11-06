# Anki Semantic Search

This is a local MCP server for your Japanese Anki deck. You ask ChatGPT something like "what's a word I recently learned that means feeling nervous," and it looks the word up in your cards instead of guessing.

An input card is one word: Japanese on the front, and a definition in Japanese or English on the back. The server embeds that word and definition on your machine. ChatGPT only receives the closest matches. The deck and the vectors stay local.

Reopening Anki does not refresh the index. Sync from the desktop window while Anki is open. Search keeps working after you close Anki.

To install the app and work on it, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Desktop window

Install the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on and open Anki, then open the desktop window.

The window does four things, in order:

1. **Choose a deck.** Search updates one deck at a time. A deck includes the decks inside it. Updating adds the deck to search, and decks you updated before stay searchable. The choice waits until you update search.
2. **Check the fields.** Optional. For each card type, the window shows which box is used as the word, the definition, and so on. Every card type starts with the default fields, matched by usual names such as Front, Expression, or Meaning. Change any box and that card type becomes custom. Only its marked boxes are used. Reset to default undoes that.
3. **Update search.** This is the button that applies the checks and reads Anki. Anki needs to be open. See what changed previews that update. Update everything rereads every card. Save without updating remembers the checks for later.
4. **Start MCP server.** Start it after the vector database is updated. The address is `http://127.0.0.1:8000/mcp`. ChatGPT can keep searching after you close Anki, as long as the server stays on.

## Connect ChatGPT

ChatGPT runs on OpenAI's servers and cannot reach `localhost`. [OpenAI's Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) fixes that. A small program, `tunnel-client`, runs on this PC, opens an outbound connection to OpenAI, and passes ChatGPT's requests to `http://127.0.0.1:8000/mcp`. You do not open any ports.

You set this up once. After that, each session only needs steps 5 and 6.

### 1. Create the tunnel

1. Sign in to the [OpenAI Platform](https://platform.openai.com) with the same login you use for ChatGPT. For a personal ChatGPT account, use your personal Platform organization.
2. Open [Settings → Tunnels](https://platform.openai.com/settings/organization/tunnels) and create a tunnel.
3. Associate the tunnel with your **ChatGPT workspace**. A tunnel that belongs only to the Platform organization does not appear in ChatGPT.
4. Copy the tunnel ID. It looks like `tunnel_` followed by 32 letters and digits.

If the page says you need tunnel access, the organization owner must give you the **Tunnels Read, Use and Manage** permissions. A new permission can take up to 30 minutes to apply.

### 2. Create a runtime API key

Open [Settings → API keys](https://platform.openai.com/settings/organization/api-keys) and create a **runtime** key. `tunnel-client` uses it to connect. Do not use an admin key here.

### 3. Download tunnel-client

Download `tunnel-client-<version>-windows-amd64.zip` from the [tunnel-client releases](https://github.com/openai/tunnel-client/releases/latest), or from the download button on the Tunnels page. Unzip it to a folder that stays put, such as `C:\tools\tunnel-client`. It contains `tunnel-client.exe`.

### 4. Create a profile

In PowerShell, in that folder, run the following. Replace the key and the tunnel ID with your own.

```powershell
$env:CONTROL_PLANE_API_KEY = "sk-..."
.\tunnel-client.exe init --sample sample_mcp_remote_no_auth --profile anki `
  --tunnel-id tunnel_0123456789abcdef0123456789abcdef `
  --mcp-server-url http://127.0.0.1:8000/mcp
```

This saves a profile named `anki`. You do not run it again.

To avoid pasting the key in every session, store it for your Windows user with `setx CONTROL_PLANE_API_KEY "sk-..."`, then open a new terminal. The key is saved in plain text in your user environment.

### 5. Start the MCP server, then the tunnel

1. Start the MCP server, from the desktop window or with `anki-search serve`.
2. In PowerShell, in the tunnel-client folder:

   ```powershell
   .\tunnel-client.exe doctor --profile anki --explain
   .\tunnel-client.exe run --profile anki
   ```

   `doctor` checks the key, the tunnel, and the MCP server, and explains any failure. `run` connects. Leave that window open. ChatGPT loses the tunnel when it closes.

Open http://127.0.0.1:8080/ui to see the tunnel's status. Port 8080 is the tunnel's own local page, not the MCP server.

### 6. Add the server in ChatGPT

Do this once, while `run` is connected.

1. Open [chatgpt.com/plugins](https://chatgpt.com/plugins), select **+**, then **Add custom MCP server**.
2. Name it, for example `Anki`.
3. Under **Connection**, choose **Tunnel** and pick your tunnel. If it is missing, check the workspace association from step 1.
4. Set authentication to **No authentication**. Only your tunnel reaches the server.
5. Accept the warning, select **Create as a plugin**, then **install** the plugin.

### If it does not work

- **ChatGPT cannot find tools, or calls fail.** Check that the MCP server and `tunnel-client run` are both still running, then run `doctor --explain` again.
- **The tunnel is not in ChatGPT's list.** The tunnel is not associated with your ChatGPT workspace, or your account lacks the Tunnels Use permission.
- **Searches return nothing.** Ask ChatGPT to call `list_decks`. An empty list means search has not been updated yet.

In a chat, invoke the plugin with `@` and ask for a word you learned. The server tells ChatGPT to call `search_notes`, and to use `learned_within_days=30` when you say "recently."

## Tools

- `list_decks` returns indexed deck names and the last sync time.
- `search_notes` returns the word, the definition in the language on the card, the deck, tags, when you first studied it, and a score.

Both tools are read-only.
