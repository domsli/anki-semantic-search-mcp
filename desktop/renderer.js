const state = {
  ankiOpen: false,
  decks: [],
  selected: new Set(),
  noteTypes: [],
  current: null,
};

const decksEl = document.querySelector("#decks");
const noteTypeEl = document.querySelector("#note-type");
const fieldsEl = document.querySelector("#fields");
const previewEl = document.querySelector("#preview");
const snapshotEl = document.querySelector("#snapshot");
const diffEl = document.querySelector("#diff");
const progressEl = document.querySelector("#progress");
const ankiStateEl = document.querySelector("#anki-state");
const serverStateEl = document.querySelector("#server-state");
const serverUrlEl = document.querySelector("#server-url");
const customMapEl = document.querySelector("#custom-map");

const ROLES = ["word", "reading", "definition", "extra", "skip", "unassigned"];

function currentType() {
  return state.noteTypes.find((item) => item.name === noteTypeEl.value) || null;
}

function renderDecks() {
  decksEl.replaceChildren();
  if (!state.decks.length) {
    decksEl.textContent = "No decks yet.";
    return;
  }
  for (const name of state.decks) {
    const label = document.createElement("label");
    label.className = "deck";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = state.selected.has(name);
    input.addEventListener("change", () => {
      if (input.checked) state.selected.add(name);
      else state.selected.delete(name);
    });
    label.append(input, document.createTextNode(name));
    decksEl.append(label);
  }
}

function renderNoteTypes() {
  const previous = noteTypeEl.value;
  noteTypeEl.replaceChildren();
  for (const item of state.noteTypes) {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = item.mapped ? `${item.name} (custom)` : item.name;
    noteTypeEl.append(option);
  }
  if (state.noteTypes.some((item) => item.name === previous)) noteTypeEl.value = previous;
  renderFields();
}

function renderFields() {
  const item = currentType();
  fieldsEl.replaceChildren();
  customMapEl.disabled = !item || !state.ankiOpen;
  if (!item) {
    customMapEl.checked = false;
    previewEl.textContent = state.ankiOpen ? "No note types found." : "Open Anki to edit field maps.";
    return;
  }
  customMapEl.checked = item.mapped;
  if (!item.roles) item.roles = {};
  for (const field of item.fields) {
    const row = document.createElement("label");
    row.className = "field";
    const select = document.createElement("select");
    select.disabled = !item.mapped || !state.ankiOpen;
    for (const role of ROLES) {
      const option = document.createElement("option");
      option.value = role;
      option.textContent = role;
      select.append(option);
    }
    select.value = item.roles[field] || "unassigned";
    select.addEventListener("change", () => {
      item.roles[field] = select.value;
      refreshPreview();
    });
    row.append(document.createTextNode(field), select);
    fieldsEl.append(row);
  }
  refreshPreview();
}

function roleLists(item) {
  const lists = { word: [], reading: [], definition: [], extra: [], skip: [] };
  for (const field of item.fields) {
    const role = item.roles[field] || "unassigned";
    if (lists[role]) lists[role].push(field);
  }
  return lists;
}

async function refreshPreview() {
  const item = currentType();
  if (!item || !state.ankiOpen) {
    previewEl.textContent = "Open Anki to preview a note.";
    return;
  }
  const result = await window.anki.api("preview", {
    note_type: item.name,
    decks: [...state.selected],
    explicit: item.mapped,
    roles: item.mapped ? roleLists(item) : null,
  });
  previewEl.textContent = result.passage || result.message || result.error || "";
  previewEl.classList.toggle("error", Boolean(result.error));
}

function renderSnapshot(status) {
  if (!status || !status.last_synced_at) {
    snapshotEl.textContent = "No sync yet. The index is empty until you sync with Anki open.";
    return;
  }
  const counts = ["embedded", "updated", "unchanged", "removed"]
    .filter((key) => status[key] !== null && status[key] !== undefined)
    .map((key) => `${key} ${status[key]}`)
    .join(", ");
  snapshotEl.textContent = `Last sync ${status.last_synced_at}. ${status.note_count} notes${counts ? ` (${counts})` : ""}.`;
}

function renderDiff(result) {
  if (!result) {
    diffEl.textContent = "Live comparison appears when Anki is open.";
    return;
  }
  if (!result.ok) {
    diffEl.textContent = result.error || "Could not compare with Anki.";
    diffEl.classList.add("error");
    return;
  }
  diffEl.classList.remove("error");
  const examples = result.examples || {};
  const sample = ["embed", "update", "remove"]
    .filter((key) => (examples[key] || []).length)
    .map((key) => `${key}: ${examples[key].join(", ")}`)
    .join(" · ");
  diffEl.textContent = `Would embed ${result.would_embed}, update ${result.would_update}, leave ${result.unchanged} unchanged, remove ${result.would_remove}.${sample ? ` ${sample}` : ""}`;
}

async function refresh() {
  const status = await window.anki.api("status");
  if (!status.ok) {
    ankiStateEl.textContent = status.error || "Could not read config.toml.";
    ankiStateEl.classList.add("error");
    return;
  }
  ankiStateEl.classList.remove("error");
  renderSnapshot(status);
  state.selected = new Set(status.decks || []);
  const decks = await window.anki.api("decks");
  state.ankiOpen = Boolean(decks.anki_open);
  state.decks = decks.decks || status.decks || [];
  state.selected = new Set(decks.selected || status.decks || []);
  renderDecks();
  const types = await window.anki.api("note-types");
  state.ankiOpen = Boolean(types.anki_open);
  state.noteTypes = types.note_types || [];
  ankiStateEl.textContent = state.ankiOpen
    ? "Anki is open. Deck names were checked against the collection."
    : "Anki is closed. Saved decks are shown, but they were not checked against the collection. Field editing, the live comparison, and Sync need Anki.";
  renderNoteTypes();
  const server = await window.anki.server("status");
  renderServer(server, status.port);
}

function renderServer(server, port) {
  serverUrlEl.textContent = server.url || `http://127.0.0.1:${port || 8000}/mcp`;
  serverStateEl.textContent = server.running ? "Running" : "Stopped";
  if (server.error) serverStateEl.textContent += `. ${server.error}`;
  serverStateEl.classList.toggle("error", Boolean(server.error));
}

document.querySelector("#refresh").addEventListener("click", refresh);
noteTypeEl.addEventListener("change", renderFields);
customMapEl.addEventListener("change", () => {
  const item = currentType();
  if (!item) return;
  item.mapped = customMapEl.checked;
  renderFields();
});

document.querySelector("#save").addEventListener("click", async () => {
  const payload = { decks: [...state.selected] };
  if (state.ankiOpen) {
    payload.note_types = {};
    for (const item of state.noteTypes) {
      if (item.mapped) payload.note_types[item.name] = roleLists(item);
    }
  }
  const result = await window.anki.api("save", payload);
  if (!result.ok) {
    progressEl.textContent = result.error || "Could not save config.toml.";
    progressEl.classList.add("error");
    return;
  }
  progressEl.classList.remove("error");
  progressEl.textContent = "Saved config.toml.";
  renderSnapshot(result);
});

document.querySelector("#compare").addEventListener("click", async () => {
  const result = await window.anki.api("diff");
  renderDiff(result);
});

async function runSync(rebuild) {
  if (rebuild && !window.confirm("Rebuild re-embeds every note. Continue?")) return;
  progressEl.classList.remove("error");
  progressEl.textContent = rebuild ? "Rebuilding…" : "Syncing…";
  const result = await window.anki.sync(rebuild);
  if (!result.ok) {
    progressEl.textContent = result.error || "Sync failed.";
    progressEl.classList.add("error");
    return;
  }
  progressEl.textContent = `Embedded ${result.embedded}, updated ${result.updated}, unchanged ${result.unchanged}, removed ${result.removed}.`;
  await refresh();
  renderDiff(await window.anki.api("diff"));
}

document.querySelector("#sync").addEventListener("click", () => runSync(false));
document.querySelector("#rebuild").addEventListener("click", () => runSync(true));
document.querySelector("#server-start").addEventListener("click", async () => {
  renderServer(await window.anki.server("start"));
});
document.querySelector("#server-stop").addEventListener("click", async () => {
  renderServer(await window.anki.server("stop"));
});

window.anki.onSyncProgress((event) => {
  progressEl.textContent = `Embedding ${event.embedded} of ${event.total}…`;
});
window.anki.onServerExit(async (event) => {
  const server = await window.anki.server("status");
  if (event && event.error) server.error = event.error;
  renderServer(server);
});

refresh();
