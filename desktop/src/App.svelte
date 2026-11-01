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
  let dirty = $state(false);
  let noteTypes = $state([]);
  let noteTypeName = $state("");
  let serverPort = $state(8000);

  let ankiState = $state("Checking whether Anki is open…");
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

  function toggleDeck(name, checked) {
    const next = new Set(selected);
    if (checked) next.add(name);
    else next.delete(name);
    selected = [...next];
    dirty = true;
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
      ankiState = status.error || "Couldn't open your settings.";
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
    dirty = false;
    const types = await window.anki.api("note-types");
    ankiOpen = Boolean(types.anki_open);
    keepNoteType(types.note_types || []);
    const active = noteTypes.find((item) => item.name === noteTypeName) ?? null;
    ankiState = ankiOpen
      ? "Anki is open."
      : "Anki is closed. Open it to choose decks, set up card fields, and update search.";
    if (!active) {
      preview = ankiOpen ? "No card types found." : "Open Anki to set up card fields.";
      previewError = false;
    } else {
      await refreshPreview(active);
    }
    applyServer(await window.anki.server("status"));
  }

  async function save({ announce = true } = {}) {
    const payload = { decks: [...selected] };
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
    if (announce) progress = "Saved. Press Update search when you want these decks included.";
    snapshot = snapshotText(result);
    return true;
  }

  async function compare() {
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
    const labels = { embed: "New or changed", update: "Review dates only", remove: "No longer in these decks" };
    const sample = Object.entries(labels)
      .filter(([key]) => (examples[key] || []).length)
      .map(([key, label]) => `${label}: ${examples[key].join(", ")}`)
      .join(" · ");
    diff = `${result.would_embed} new or changed, ${result.would_update} with only a newer review, ${result.unchanged} already current, ${result.would_remove} no longer in these decks.${sample ? ` ${sample}` : ""}`;
  }

  async function runSync(rebuild) {
    if (rebuild && !window.confirm("This rereads every card. It can take a while. Continue?")) return;
    progressError = false;
    progress = "Saving your choices…";
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
  }

  onMount(() => {
    if (!window.anki) {
      ankiState = "Open this from the Anki search app.";
      ankiError = true;
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
      Choose which decks ChatGPT can search, mark the word and the definition, then press Update search.
      Start ChatGPT after that.
    </p>
    <p class="anki-state" class:error={ankiError}>{ankiState}</p>
  </div>
  <button type="button" onclick={refresh}>Refresh</button>
</header>
<main>
  <Decks {decks} {selected} {dirty} onToggle={toggleDeck} />
  <Fields
    {noteTypes}
    bind:noteTypeName
    {ankiOpen}
    {preview}
    {previewError}
    onChange={refreshPreview}
    onEdit={onFieldsChange}
  />
  <SyncPanel
    {snapshot}
    {diff}
    {diffError}
    {progress}
    {progressError}
    {dirty}
    {selected}
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
