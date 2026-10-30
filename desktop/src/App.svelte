<script>
  import { onMount } from "svelte";
  import Decks from "./components/Decks.svelte";
  import Fields from "./components/Fields.svelte";
  import ServerPanel from "./components/ServerPanel.svelte";
  import SyncPanel from "./components/SyncPanel.svelte";
  import { roleLists } from "./lib/roles.js";

  let ankiOpen = $state(false);
  let decks = $state([]);
  let selected = $state([]);
  let noteTypes = $state([]);
  let noteTypeName = $state("");
  let serverPort = $state(8000);

  let ankiState = $state("Checking Anki…");
  let ankiError = $state(false);
  let snapshot = $state("No sync yet.");
  let diff = $state("Live comparison appears when Anki is open.");
  let diffError = $state(false);
  let progress = $state("");
  let progressError = $state(false);
  let preview = $state("Open Anki to preview a note.");
  let previewError = $state(false);
  let serverState = $state("Stopped");
  let serverError = $state(false);
  let serverUrl = $state("");

  let current = $derived(noteTypes.find((item) => item.name === noteTypeName) ?? null);

  function toggleDeck(name, checked) {
    const next = new Set(selected);
    if (checked) next.add(name);
    else next.delete(name);
    selected = [...next];
  }

  function snapshotText(status) {
    if (!status || !status.last_synced_at) {
      return "No sync yet. The index is empty until you sync with Anki open.";
    }
    const counts = ["embedded", "updated", "unchanged", "removed"]
      .filter((key) => status[key] !== null && status[key] !== undefined)
      .map((key) => `${key} ${status[key]}`)
      .join(", ");
    return `Last sync ${status.last_synced_at}. ${status.note_count} notes${counts ? ` (${counts})` : ""}.`;
  }

  function applyServer(server) {
    serverUrl = server.url || `http://127.0.0.1:${serverPort || 8000}/mcp`;
    serverState = server.running ? "Running" : "Stopped";
    if (server.error) serverState += `. ${server.error}`;
    serverError = Boolean(server.error);
  }

  async function refreshPreview(item = current) {
    if (!item || !ankiOpen) {
      preview = "Open Anki to preview a note.";
      previewError = false;
      return;
    }
    const result = await window.anki.api("preview", {
      note_type: item.name,
      decks: [...selected],
      explicit: item.mapped,
      roles: item.mapped ? roleLists(item) : null,
    });
    preview = result.passage || result.message || result.error || "";
    previewError = Boolean(result.error);
  }

  function keepNoteType(types) {
    noteTypes = types.map((item) => ({
      ...item,
      roles: { ...(item.roles || {}) },
    }));
    if (!noteTypes.some((item) => item.name === noteTypeName)) {
      noteTypeName = noteTypes[0]?.name || "";
    }
  }

  async function refresh() {
    const status = await window.anki.api("status");
    if (!status.ok) {
      ankiState = status.error || "Could not read config.toml.";
      ankiError = true;
      return;
    }
    ankiError = false;
    snapshot = snapshotText(status);
    serverPort = status.port || 8000;
    const deckResult = await window.anki.api("decks");
    ankiOpen = Boolean(deckResult.anki_open);
    decks = deckResult.decks || status.decks || [];
    selected = [...(deckResult.selected || status.decks || [])];
    const types = await window.anki.api("note-types");
    ankiOpen = Boolean(types.anki_open);
    keepNoteType(types.note_types || []);
    const active = noteTypes.find((item) => item.name === noteTypeName) ?? null;
    ankiState = ankiOpen
      ? "Anki is open. Deck names were checked against the collection."
      : "Anki is closed. Saved decks are shown, but they were not checked against the collection. Field editing, the live comparison, and Sync need Anki.";
    if (!active) {
      preview = ankiOpen ? "No note types found." : "Open Anki to edit field maps.";
      previewError = false;
    } else {
      await refreshPreview(active);
    }
    applyServer(await window.anki.server("status"));
  }

  async function save() {
    const payload = { decks: [...selected] };
    if (ankiOpen) {
      payload.note_types = {};
      for (const item of noteTypes) {
        if (item.mapped) payload.note_types[item.name] = roleLists(item);
      }
    }
    const result = await window.anki.api("save", payload);
    if (!result.ok) {
      progress = result.error || "Could not save config.toml.";
      progressError = true;
      return;
    }
    progressError = false;
    progress = "Saved config.toml.";
    snapshot = snapshotText(result);
  }

  async function compare() {
    const result = await window.anki.api("diff");
    if (!result) {
      diff = "Live comparison appears when Anki is open.";
      diffError = false;
      return;
    }
    if (!result.ok) {
      diff = result.error || "Could not compare with Anki.";
      diffError = true;
      return;
    }
    diffError = false;
    const examples = result.examples || {};
    const sample = ["embed", "update", "remove"]
      .filter((key) => (examples[key] || []).length)
      .map((key) => `${key}: ${examples[key].join(", ")}`)
      .join(" · ");
    diff = `Would embed ${result.would_embed}, update ${result.would_update}, leave ${result.unchanged} unchanged, remove ${result.would_remove}.${sample ? ` ${sample}` : ""}`;
  }

  async function runSync(rebuild) {
    if (rebuild && !window.confirm("Rebuild re-embeds every note. Continue?")) return;
    progressError = false;
    progress = rebuild ? "Rebuilding…" : "Syncing…";
    const result = await window.anki.sync(rebuild);
    if (!result.ok) {
      progress = result.error || "Sync failed.";
      progressError = true;
      return;
    }
    progress = `Embedded ${result.embedded}, updated ${result.updated}, unchanged ${result.unchanged}, removed ${result.removed}.`;
    await refresh();
    await compare();
  }

  onMount(() => {
    if (!window.anki) {
      ankiState = "This window only works inside the Electron app.";
      ankiError = true;
      return;
    }
    const stopProgress = window.anki.onSyncProgress((event) => {
      progress = `Embedding ${event.embedded} of ${event.total}…`;
    });
    const stopServer = window.anki.onServerExit(async (event) => {
      const server = await window.anki.server("status");
      if (event && event.error) server.error = event.error;
      applyServer(server);
    });
    refresh();
    return () => {
      stopProgress();
      stopServer();
    };
  });
</script>

<header>
  <div>
    <h1>Anki search</h1>
    <p class="anki-state" class:error={ankiError}>{ankiState}</p>
  </div>
  <button type="button" onclick={refresh}>Refresh</button>
</header>
<main>
  <Decks {decks} {selected} onToggle={toggleDeck} />
  <Fields
    {noteTypes}
    bind:noteTypeName
    {ankiOpen}
    {preview}
    {previewError}
    onChange={refreshPreview}
  />
  <SyncPanel
    {snapshot}
    {diff}
    {diffError}
    {progress}
    {progressError}
    onCompare={compare}
    onSync={() => runSync(false)}
    onRebuild={() => runSync(true)}
    onSave={save}
  />
  <ServerPanel
    state={serverState}
    url={serverUrl}
    error={serverError}
    onStart={async () => applyServer(await window.anki.server("start"))}
    onStop={async () => applyServer(await window.anki.server("stop"))}
  />
</main>
