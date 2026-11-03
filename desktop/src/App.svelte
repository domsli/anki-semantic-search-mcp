<script>
  import { onMount } from "svelte";
  import Decks from "./components/Decks.svelte";
  import Fields from "./components/Fields.svelte";
  import ServerPanel from "./components/ServerPanel.svelte";
  import Spinner from "./components/Spinner.svelte";
  import SyncPanel from "./components/SyncPanel.svelte";
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
  let snapshot = $state("Search has not been updated yet.");
  let diff = $state("Open Anki to see whether search is up to date.");
  let diffError = $state(false);
  let progress = $state("");
  let progressError = $state(false);
  let preview = $state("Open Anki to see an example.");
  let previewError = $state(false);
  let serverState = $state("Stopped");
  let serverError = $state(false);
  let serverUrl = $state("");

  let current = $derived(noteTypes.find((item) => item.name === noteTypeName) ?? null);

  function chosenDecks() {
    return deck ? [deck] : [];
  }

  async function chooseDeck(name) {
    if (name === deck) return;
    deck = name;
    dirty = true;
    refreshing = true;
    try {
      await loadCardTypes();
    } finally {
      refreshing = false;
      if (!ankiError) {
        ankiState = ankiOpen
          ? "Anki is open."
          : "Anki is closed. Open it to choose a deck, set up card fields, and update search.";
      }
    }
  }

  function onFieldsChange() {
    dirty = true;
    refreshPreview();
  }

  function formatWhen(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  }

  function snapshotText(status) {
    if (!status || !status.last_synced_at) {
      return "Search has not been updated yet. Open Anki and update search so your cards can be found.";
    }
    const parts = [];
    if (status.embedded) parts.push(`${status.embedded} added`);
    if (status.updated) parts.push(`${status.updated} refreshed`);
    if (status.removed) parts.push(`${status.removed} removed`);
    const detail = parts.length ? ` ${parts.join(", ")}.` : "";
    const count = status.note_count ?? 0;
    const cards = count === 1 ? "1 card is searchable" : `${count} cards are searchable`;
    return `Last updated ${formatWhen(status.last_synced_at)}. ${cards}.${detail}`;
  }

  function applyServer(server) {
    serverUrl = server.url || `http://127.0.0.1:${serverPort || 8000}/mcp`;
    serverError = Boolean(server.error);
    if (server.error) serverState = server.error;
    else serverState = server.running ? "On. ChatGPT can search your cards." : "Off.";
  }

  async function refreshPreview(item = current) {
    if (!item || !ankiOpen) {
      preview = "Open Anki to see an example.";
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
      noteTypes = [];
      noteTypeName = "";
      previewError = false;
      preview = ankiOpen ? "Choose a deck to see its card types." : "Open Anki to choose a deck and see its card types.";
      return;
    }
    loadingTypes = true;
    ankiState = "Loading card types in this deck…";
    try {
      const types = await window.anki.api("note-types", { decks: chosenDecks() });
      ankiOpen = Boolean(types.anki_open);
      keepNoteType(types.note_types || []);
    } finally {
      loadingTypes = false;
    }
    const active = noteTypes.find((item) => item.name === noteTypeName) ?? null;
    if (active && ankiOpen) {
      ankiState = "Loading an example card…";
      await refreshPreview(active);
      return;
    }
    previewError = false;
    if (ankiOpen) preview = "No card types found in this deck.";
    else preview = "Open Anki to see card types.";
  }

  async function refresh() {
    refreshing = true;
    ankiError = false;
    try {
      ankiState = "Reading your last update…";
      const status = await window.anki.api("status");
      if (!status.ok) {
        ankiState = status.error || "Couldn't open your settings.";
        ankiError = true;
        return;
      }
      snapshot = snapshotText(status);
      serverPort = status.port || 8000;
      ankiState = "Checking whether Anki is open…";
      const deckResult = await window.anki.api("decks");
      ankiOpen = Boolean(deckResult.anki_open);
      decks = deckResult.decks || [];
      deck = deckResult.selected?.[0] || "";
      const saved = status.decks || [];
      dirty = ankiOpen && (saved.length !== 1 || saved[0] !== deck);
      ready = true;
      await loadCardTypes();
      ankiState = "Checking whether ChatGPT is on…";
      applyServer(await window.anki.server("status"));
      ankiState = ankiOpen
        ? "Anki is open."
        : "Anki is closed. Open it to choose a deck, set up card fields, and update search.";
    } finally {
      refreshing = false;
      ready = true;
    }
  }

  async function save({ announce = true } = {}) {
    saving = true;
    if (announce) {
      progressError = false;
      progress = "Saving…";
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
        progress = result.error || "Couldn't save.";
        progressError = true;
        return false;
      }
      dirty = false;
      progressError = false;
      if (announce) progress = "Saved. Press Update search when you want this deck included.";
      snapshot = snapshotText(result);
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
        diff = "Open Anki to see whether search is up to date.";
        diffError = false;
        return;
      }
      if (!result.ok) {
        diff = result.error || "Couldn't compare with Anki.";
        diffError = true;
        return;
      }
      diffError = false;
      const examples = result.examples || {};
      const labels = { embed: "New or changed", update: "Review dates only", remove: "No longer in this deck" };
      const sample = Object.entries(labels)
        .filter(([key]) => (examples[key] || []).length)
        .map(([key, label]) => `${label}: ${examples[key].join(", ")}`)
        .join(" · ");
      diff = `${result.would_embed} new or changed, ${result.would_update} with only a newer review, ${result.unchanged} already current, ${result.would_remove} no longer in this deck.${sample ? ` ${sample}` : ""}`;
    } finally {
      comparing = false;
    }
  }

  async function runSync(rebuild) {
    if (rebuild && !window.confirm("This rereads every card. It can take a while. Continue?")) return;
    syncing = true;
    progressError = false;
    progress = "Saving your choices…";
    try {
      if (!(await save({ announce: false }))) return;
      progress = rebuild ? "Updating every card…" : "Updating search…";
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
      progress = `Updating card ${event.embedded} of ${event.total}…`;
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
    <h1>Search your cards</h1>
    <p class="lede">
      Choose one deck for ChatGPT to search, mark the word and the definition, then press Update search.
      Start ChatGPT after that.
    </p>
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
  <Decks {decks} {deck} {dirty} onChoose={chooseDeck} />
  <Fields
    {noteTypes}
    bind:noteTypeName
    {ankiOpen}
    {preview}
    {previewError}
    {previewing}
    {loadingTypes}
    onChange={refreshPreview}
    onEdit={onFieldsChange}
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
    {dirty}
    {deck}
    onCompare={compare}
    onSync={() => runSync(false)}
    onRebuild={() => runSync(true)}
    onSave={save}
  />
  <ServerPanel
    state={serverState}
    url={serverUrl}
    error={serverError}
    busy={serverBusy}
    busyLabel={serverBusyLabel}
    onStart={async () => {
      serverBusy = true;
      serverBusyLabel = "Turning ChatGPT on…";
      try {
        applyServer(await window.anki.server("start"));
      } finally {
        serverBusy = false;
      }
    }}
    onStop={async () => {
      serverBusy = true;
      serverBusyLabel = "Turning ChatGPT off…";
      try {
        applyServer(await window.anki.server("stop"));
      } finally {
        serverBusy = false;
      }
    }}
  />
</main>
{/if}
