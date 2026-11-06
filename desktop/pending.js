// Count Anki changes made since the last Update decks, without Python or the index.
//
// The last sync left sync_meta.json with `anki_snapshot_at` (when Anki was read)
// and `seen_note_ids` (the notes each tracked deck had then). Comparing those
// with Anki now gives exact counts:
//   new      notes in a deck now that were not there at the snapshot
//   deleted  notes that were in a deck at the snapshot and are gone now
//   edited   notes whose modification time is after the snapshot
//   reviewed notes with a card answered after the snapshot
// Anki's edited:N and rated:N searches only count whole days, so they are used
// to find a few candidates, and exact timestamps decide.

const DAY_MS = 24 * 60 * 60 * 1000;
const BATCH = 100;

function deckQuery(name) {
  return `deck:"${name.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function anyDeckQuery(decks) {
  const parts = decks.map(deckQuery);
  return parts.length === 1 ? parts[0] : `(${parts.join(" OR ")})`;
}

function batches(items) {
  const out = [];
  for (let start = 0; start < items.length; start += BATCH) out.push(items.slice(start, start + BATCH));
  return out;
}

function emptyCounts() {
  return { new: 0, edited: 0, reviewed: 0, deleted: 0 };
}

// `invoke(action, params)` calls AnkiConnect. `meta` is the parsed sync_meta.json.
async function countPending({ invoke, meta, decks, now = Date.now() }) {
  const since = Date.parse(meta?.anki_snapshot_at || "");
  const seenByDeck = meta?.seen_note_ids;
  if (!Number.isFinite(since) || !seenByDeck) return { ok: false, reason: "no-baseline" };
  const tracked = decks.filter(Boolean);
  if (!tracked.length) return { ok: true, total: emptyCounts(), decks: {} };

  const liveByDeck = {};
  for (const deck of tracked) {
    liveByDeck[deck] = new Set((await invoke("findNotes", { query: deckQuery(deck) })) || []);
  }
  const live = new Set(tracked.flatMap((deck) => [...liveByDeck[deck]]));
  const seen = new Set(tracked.flatMap((deck) => seenByDeck[deck] || []));

  // Search a day further back than the gap, so Anki's day boundary never hides a change.
  const days = Math.max(1, Math.ceil((now - since) / DAY_MS) + 1);
  const scope = anyDeckQuery(tracked);
  // A new note is already counted as new, so only notes present at the snapshot can be edited or reviewed.
  const known = (id) => live.has(id) && seen.has(id);

  const edited = new Set();
  const editCandidates = ((await invoke("findNotes", { query: `${scope} edited:${days}` })) || []).filter(known);
  for (const batch of batches(editCandidates)) {
    for (const info of (await invoke("notesInfo", { notes: batch })) || []) {
      if (info && Number(info.mod) * 1000 > since) edited.add(Number(info.noteId));
    }
  }

  const reviewed = new Set();
  const cards = (await invoke("findCards", { query: `${scope} rated:${days}` })) || [];
  for (const batch of batches(cards)) {
    const noteOf = new Map();
    for (const card of (await invoke("cardsInfo", { cards: batch })) || []) {
      if (card) noteOf.set(String(card.cardId), Number(card.note));
    }
    // Integer ids: AnkiConnect answers string ids with empty histories.
    const history = (await invoke("getReviewsOfCards", { cards: batch })) || {};
    for (const [cardId, entries] of Object.entries(history)) {
      const noteId = noteOf.get(String(cardId));
      if (noteId === undefined || !known(noteId)) continue;
      // Ease 0 is a manual reschedule, not a review.
      if ((entries || []).some((entry) => Number(entry.id) > since && Number(entry.ease ?? 1) !== 0)) {
        reviewed.add(noteId);
      }
    }
  }

  const perDeck = {};
  for (const deck of tracked) {
    const current = liveByDeck[deck];
    const before = new Set(seenByDeck[deck] || []);
    perDeck[deck] = {
      new: [...current].filter((id) => !before.has(id)).length,
      deleted: [...before].filter((id) => !current.has(id)).length,
      edited: [...edited].filter((id) => current.has(id)).length,
      reviewed: [...reviewed].filter((id) => current.has(id)).length,
    };
  }
  return {
    ok: true,
    total: {
      new: [...live].filter((id) => !seen.has(id)).length,
      deleted: [...seen].filter((id) => !live.has(id)).length,
      edited: edited.size,
      reviewed: reviewed.size,
    },
    decks: perDeck,
  };
}

// AnkiConnect over HTTP, the same request shape the Python client sends.
function ankiInvoker(url, apiKey) {
  return async (action, params) => {
    const body = { action, version: 6, params };
    if (apiKey) body.key = apiKey;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });
    const payload = await response.json();
    if (payload.error) throw new Error(String(payload.error));
    return payload.result;
  };
}

module.exports = { countPending, ankiInvoker, deckQuery };
