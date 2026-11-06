# Anki Semantic Search MCP

This is a local MCP server for your Japanese Anki decks. You ask ChatGPT something like "what's a word I recently learned that means feeling nervous," and it looks the word up in your cards instead of guessing.

An input card is one word: Japanese on the front, and a definition in Japanese or English on the back. The server embeds that word and definition on your machine. ChatGPT only receives the closest matches. The decks and the vectors stay local.

The vector database does not follow Anki on its own. Cards you add, edit, delete, or review reach search only after you press **Update decks** in the desktop window while Anki is open. Search keeps working after you close Anki.

To install the app and work on it, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Tools

The server exposes two read-only MCP tools at `http://127.0.0.1:8000/mcp`. ChatGPT picks the arguments from how you ask. For example, "words I keep forgetting" sets `min_lapses`.

### `search_notes`

Finds the notes closest to `query` by meaning and by spelling. Filters run before ranking, and every filter you pass must match.

```ts
search_notes(args: {
  query: string;                  // required: a word, phrase, or meaning
  decks?: string[];               // deck names; each includes the decks inside it
  learned_within_days?: number;   // first review in the last N days        (N >= 1)
  reviewed_within_days?: number;  // last review in the last N days         (N >= 1)
  added_within_days?: number;     // card created in the last N days        (N >= 1)
  edited_within_days?: number;    // note edited in the last N days         (N >= 1)
  min_lapses?: number;            // forgotten at least N times             (N >= 0)
  max_interval_days?: number;     // studied, interval at most N days       (N >= 0)
  suspended?: boolean;            // true: only suspended; false: none suspended
  limit?: number;                 // default 8, clamped to 1..25
}): {
  hits: Hit[];
  message?: string;               // why hits is empty, and what to try next
}

type Hit = {
  word: string;
  reading: string;
  definition: string;             // in the language on the card
  extra: string;                  // other included fields
  decks: string[];
  tags: string[];
  added_at: string | null;        // dates are ISO 8601 UTC, e.g. "2026-11-04T08:30:00Z"
  introduced_at: string | null;   // first review
  last_reviewed_at: string | null;
  modified_at: string | null;     // null if AnkiConnect does not report edit times
  review_count: number;           // manual reschedules are not counted
  lapses: number;                 // summed over the note's cards
  interval_days: number;          // longest interval among the note's cards
  suspended: boolean;             // true when every card is suspended
  score: number;                  // higher is closer
};
```

Omitted filters are off. Review data is as of the last Update decks. `max_interval_days` leaves out cards that were never studied.

`message` is set instead of hits when:

- `query` is empty, or a filter value is out of range.
- The index is empty.
- The filters left nothing, but matching notes exist without them. The message names the filters and how to loosen them.
- A filter needs a column the index does not have yet. Press Update decks once to add it.
- No notes match in the given decks, or at all.

### `list_decks`

```ts
list_decks(): {
  decks: string[];                // every deck name in the index, including nested decks
  last_synced_at: string | null;  // last Update decks, ISO 8601 UTC
  note_count: number;
  message?: string;               // set when the index is empty
}
```

## Desktop window

Install the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on and open Anki, then open the desktop window. **Refresh**, at the top right, checks Anki and the server again.

### MCP server

One button starts and stops the server. It shows a spinner while the server starts or stops, and a green dot while it runs. If the server was started outside the window, for example with `anki-search serve`, the button says so and cannot stop it. The address is `http://127.0.0.1:8000/mcp`. ChatGPT can keep searching after you close Anki, as long as the server stays on.

### Put decks in the vector database

1. **Decks.** The list shows every deck kept in the vector database, and whether each one is in search yet. A deck includes the decks inside it. **Add deck** puts a deck on the list; it reaches search at the next Update decks. **Remove** takes a deck off the list and deletes its cards from the vector database right away. Anki is not changed, and a card that is also in another listed deck stays.
2. **Card indexing configuration.** Optional. There is a tab for each card type used in the listed decks. Pick one to see its fields. The marked fields are combined into the text stored in the vector database, and search measures the distance between your question and that text. Set each field to **Word**, **Reading**, **Definition**, **Include**, or **Ignore**. Ignored fields stay out of search.

   Settings belong to the card type, and apply in every deck that uses it. A *default* card type uses fields matched by usual names such as Front, Expression, or Meaning, and the window shows what they matched. Change any field and the card type becomes *custom*: only its marked fields are used, and a grey note shows the default next to each field you changed. **Reset to default** undoes that. **Save changes** stores the settings, and is greyed out when nothing is unsaved. Update decks also saves them.
3. **Vector database.** At the top, the window counts the Anki changes that are not in search yet: new, edited, reviewed, and deleted cards, in total and per deck. It counts when it opens, every 10 seconds while it is visible, and when you switch back to it, so cards you add in Anki show up within seconds. It asks Anki directly and takes well under a second. The counts start after the first Update decks.

   **Update decks** applies the fields and reads every listed deck from Anki. Anki needs to be open. Only new and changed cards are embedded again. **See missed updates** lists what Update decks would pick up. **Re-index decks** embeds every card in every listed deck again, which takes longer.

   This section also lists the field settings the decks were indexed with, and flags a deck or field change that is not in search yet.

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
- **Searches return nothing.** Ask ChatGPT to call `list_decks`. An empty list means no deck has been updated yet. Press Update decks in the window.

In a chat, invoke the plugin with `@` and ask for a word you learned. The server tells ChatGPT to call `search_notes`, and to use `learned_within_days=30` when you say "recently."
