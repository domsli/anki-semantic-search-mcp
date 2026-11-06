<script>
  import { onMount } from "svelte";
  import Decks from "./components/Decks.svelte";
  import Fields from "./components/Fields.svelte";
  import ServerPanel from "./components/ServerPanel.svelte";
  import Spinner from "./components/Spinner.svelte";
  import SyncPanel from "./components/SyncPanel.svelte";
  import { configurationDifferences } from "./lib/configuration.js";
  import { roleLists } from "./lib/roles.js";

  let ankiOpen = $state(false);
  let decks = $state([]);
  let deck = $state("");
  let dirty = $state(false);
  let noteTypes = $state([]);
  let noteTypeName = $state("");
  let serverPort = $state(8000);

  let ready = $state(false);
  let refreshing = $state(true);
  let loadingTypes = $state(false);
  let previewing = $state(false);
  let syncing = $state(false);
  let comparing = $state(false);
  let saving = $state(false);
  let serverBusy = $state(false);
  let serverBusyLabel = $state("");
  let ankiState = $state("Reading your last update…");
  let ankiError = $state(false);
  let snapshot = $state("Not updated yet.");
  let diff = $state("Open Anki to compare.");
  let diffError = $state(false);
  let progress = $state("");
  let progressError = $state(false);
  let saveProgress = $state("");
  let saveError = $state(false);
  let savedConfiguration = $state({ decks: [], note_types: {} });
  let indexedConfiguration = $state(null);
  let vectorUpdated = $state(false);
  let typesReady = $state(false);
  let preview = $state("Open Anki.");
  let previewError = $state(false);
  let serverRunning = $state(false);
  let serverOwned = $state(false);
  let serverMessage = $state("");
  let serverError = $state(false);
  let serverUrl = $state("");

  let current = $derived(noteTypes.find((item) => item.name === noteTypeName) ?? null);

  function chosenDecks() {
    return deck ? [deck] : [];
  }

  function draftConfiguration() {
    return {
      decks: chosenDecks(),
      note_types: Object.fromEntries(
        noteTypes.filter((item) => item.mapped).map((item) => [item.name, roleLists(item)]),
      ),
    };
  }

  let activeConfiguration = $derived(
    typesReady ? draftConfiguration() : { decks: savedConfiguration.decks || [], note_types: savedConfiguration.note_types || {} },
  );
  let configDifferences = $derived(configurationDifferences(indexedConfiguration, activeConfiguration));

  function markDirty() {
    if (!ankiOpen) {
      dirty = false;
      return;
    }
    const savedDecks = savedConfiguration.decks || [];
    if (!typesReady) {
      dirty = savedDecks.length !== 1 || savedDecks[0] !== deck;
      return;
    }
    dirty = configurationDifferences(savedConfiguration, draftConfiguration()).length > 0;
  }

  function applyStatus(status) {
    snapshot = snapshotText(status);
    serverPort = status.port || 8000;
    vectorUpdated = Boolean(status.last_synced_at);
    savedConfiguration = { decks: status.decks || [], note_types: status.note_types || {} };
    indexedConfiguration = status.indexed_configuration || null;
  }

  async function chooseDeck(name) {
    if (name === deck) return;
    deck = name;
    refreshing = true;
    try {
      await loadCardTypes();
    } finally {
      markDirty();
      refreshing = false;
      if (!ankiError) {
        ankiState = ankiOpen
          ? "Anki is open."
          : "Anki is closed.";
      }
    }
  }

  function onFieldsChange() {
    markDirty();
    refreshPreview();
  }

  function formatWhen(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  }

  function snapshotText(status) {
    if (!status || !status.last_synced_at) {
      return "Not updated yet.";
    }
    const parts = [];
    if (status.embedded) parts.push(`${status.embedded} added`);
    if (status.updated) parts.push(`${status.updated} refreshed`);
    if (status.removed) parts.push(`${status.removed} removed`);
    const detail = parts.length ? ` ${parts.join(", ")}.` : "";
    const count = status.note_count ?? 0;
    const cards = count === 1 ? "1 card" : `${count} cards`;
    return `Updated ${formatWhen(status.last_synced_at)}. ${cards}.${detail}`;
  }

  function applyServer(server) {
    serverUrl = server.url || `http://127.0.0.1:${serverPort || 8000}/mcp`;
    serverRunning = Boolean(server.running);
    serverOwned = Boolean(server.owned);
    serverError = Boolean(server.error);
    serverMessage = server.error || "";
  }

  async function toggleServer() {
    const action = serverRunning ? "stop" : "start";
    serverBusy = true;
    serverBusyLabel = action === "start" ? "Starting…" : "Stopping…";
    try {
      applyServer(await window.anki.server(action));
    } finally {
      serverBusy = false;
    }
  }

  async function refreshPreview(item = current) {
    if (!item || !ankiOpen) {
      preview = "Open Anki.";
      previewError = false;
      previewing = false;
      return;
    }
    previewing = true;
    try {
      const result = await window.anki.api("preview", {
        note_type: item.name,
        decks: chosenDecks(),
        explicit: item.mapped,
        roles: item.mapped ? roleLists(item) : null,
      });
      preview = result.passage || result.message || result.error || "";
      previewError = Boolean(result.error);
    } finally {
      previewing = false;
    }
  }

  function keepNoteType(types) {
    const previous = new Map(noteTypes.map((item) => [item.name, item]));
    noteTypes = types.map((item) => {
      const prior = previous.get(item.name);
      const roles = { ...(item.roles || {}) };
      if (!prior) return { ...item, roles };
      for (const field of item.fields || []) {
        if (prior.roles?.[field]) roles[field] = prior.roles[field];
      }
      return { ...item, mapped: prior.mapped, roles };
    });
    if (!noteTypes.some((item) => item.name === noteTypeName)) {
      noteTypeName = noteTypes[0]?.name || "";
    }
  }

  async function loadCardTypes() {
    if (!ankiOpen || !deck) {
      loadingTypes = false;
      typesReady = false;
      noteTypes = [];
      noteTypeName = "";
      previewError = false;
      preview = ankiOpen ? "Choose a deck." : "Open Anki.";
      return;
    }
    loadingTypes = true;
    typesReady = false;
    ankiState = "Loading card types…";
    try {
      const types = await window.anki.api("note-types", { decks: chosenDecks() });
      ankiOpen = Boolean(types.anki_open);
      if (!ankiOpen) {
        typesReady = false;
        noteTypes = [];
        noteTypeName = "";
        return;
      }
      keepNoteType(types.note_types || []);
      typesReady = true;
    } finally {
      loadingTypes = false;
    }
    const active = noteTypes.find((item) => item.name === noteTypeName) ?? null;
    if (active && ankiOpen) {
      ankiState = "Loading an example…";
      await refreshPreview(active);
      return;
    }
    previewError = false;
    if (ankiOpen) preview = "No card types.";
    else preview = "Open Anki.";
  }

  async function refresh() {
    refreshing = true;
    ankiError = false;
    try {
      ankiState = "Reading the last update…";
      const status = await window.anki.api("status");
      if (!status.ok) {
        ankiState = status.error || "Couldn't open your settings.";
        ankiError = true;
        return;
      }
      applyStatus(status);
      ankiState = "Checking Anki…";
      const deckResult = await window.anki.api("decks");
      ankiOpen = Boolean(deckResult.anki_open);
      decks = deckResult.decks || [];
      deck = deckResult.selected?.[0] || "";
      ready = true;
      await loadCardTypes();
      markDirty();
      ankiState = "Checking the MCP server…";
      applyServer(await window.anki.server("status"));
      ankiState = ankiOpen
        ? "Anki is open."
        : "Anki is closed.";
    } finally {
      refreshing = false;
      ready = true;
    }
  }

  async function save({ announce = true } = {}) {
    saving = true;
    if (announce) {
      saveError = false;
      saveProgress = "Saving…";
    }
    try {
      const payload = { decks: chosenDecks() };
      if (ankiOpen) {
        payload.note_types = {};
        for (const item of noteTypes) {
          if (item.mapped) payload.note_types[item.name] = roleLists(item);
        }
      }
      const result = await window.anki.api("save", payload);
      if (!result.ok) {
        const message = result.error || "Couldn't save.";
        if (announce) {
          saveProgress = message;
          saveError = true;
        } else {
          progress = message;
          progressError = true;
        }
        return false;
      }
      applyStatus(result);
      markDirty();
      if (announce) {
        saveError = false;
        saveProgress = "Saved.";
      }
      return true;
    } finally {
      saving = false;
    }
  }

  async function compare() {
    comparing = true;
    try {
      if (dirty && !(await save({ announce: false }))) return;
      const result = await window.anki.api("diff");
      if (!result) {
        diff = "Open Anki to compare.";
        diffError = false;
        return;
      }
      if (!result.ok) {
        diff = result.error || "Couldn't compare.";
        diffError = true;
        return;
      }
      diffError = false;
      const examples = result.examples || {};
      const labels = { embed: "New or changed", update: "Review details", remove: "Removed" };
      const sample = Object.entries(labels)
        .filter(([key]) => (examples[key] || []).length)
        .map(([key, label]) => `${label}: ${examples[key].join(", ")}`)
        .join(" · ");
      diff = `${result.would_embed} new or changed, ${result.would_update} review details, ${result.unchanged} current, ${result.would_remove} removed.${sample ? ` ${sample}` : ""}`;
    } finally {
      comparing = false;
    }
  }

  async function runSync(rebuild) {
    if (rebuild && !window.confirm("Re-index every card in this deck? This can take a while.")) return;
    syncing = true;
    progressError = false;
      progress = "Saving…";
    try {
      if (!(await save({ announce: false }))) return;
      progress = rebuild ? "Re-indexing the deck…" : "Updating the deck…";
      const result = await window.anki.sync(rebuild);
      if (!result.ok) {
        progress = result.error || "Update failed.";
        progressError = true;
        return;
      }
      progress = `Done. ${result.embedded} added, ${result.updated} refreshed, ${result.unchanged} already current, ${result.removed} removed.`;
      await refresh();
      await compare();
    } finally {
      syncing = false;
    }
  }

  onMount(() => {
    if (!window.anki) {
      ankiState = "Open this from the Anki search app.";
      ankiError = true;
      refreshing = false;
      ready = true;
      return;
    }
    const stopProgress = window.anki.onSyncProgress((event) => {
      progress = event.message || `Updating card ${event.embedded} of ${event.total}…`;
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
    <h1>Anki Semantic Search MCP</h1>
    <p class="lede">Run the MCP server, and update your Anki decks in the vector database.</p>
    {#if refreshing && !ready}
      <p class="loading" role="status"><Spinner large /><span>{ankiState}</span></p>
    {:else}
      <p class="anki-state" class:status={refreshing} class:error={ankiError} role="status">
        {#if refreshing}<Spinner />{/if}
        <span>{ankiState}</span>
      </p>
    {/if}
  </div>
  <button type="button" onclick={refresh} disabled={refreshing}>Refresh</button>
</header>
{#if ready}
<main>
  <ServerPanel
    running={serverRunning}
    owned={serverOwned}
    url={serverUrl}
    message={serverMessage}
    error={serverError}
    busy={serverBusy}
    busyLabel={serverBusyLabel}
    onToggle={toggleServer}
  />
  <Decks {decks} {deck} {dirty} onChoose={chooseDeck} />
  <Fields
    {noteTypes}
    bind:noteTypeName
    {ankiOpen}
    {preview}
    {previewError}
    {previewing}
    {loadingTypes}
    {deck}
    {saving}
    {syncing}
    {comparing}
    {saveProgress}
    {saveError}
    onChange={refreshPreview}
    onEdit={onFieldsChange}
    onSave={save}
  />
  <SyncPanel
    {snapshot}
    {diff}
    {diffError}
    {progress}
    {progressError}
    {syncing}
    {comparing}
    {saving}
    {deck}
    {indexedConfiguration}
    {vectorUpdated}
    {configDifferences}
    onCompare={compare}
    onSync={() => runSync(false)}
    onRebuild={() => runSync(true)}
  />
</main>
{/if}
