// Run with: npm test (node's built-in test runner).
const test = require("node:test");
const assert = require("node:assert/strict");
const { countPending, deckQuery } = require("./pending");

const SNAPSHOT = Date.parse("2026-11-05T12:00:00.000Z");
const BEFORE = SNAPSHOT - 60_000;
const AFTER = SNAPSHOT + 60_000;

// A tiny AnkiConnect: notes with decks, modification times (seconds), and card review logs.
function fakeAnki(notes) {
  const calls = [];
  const cardsOf = (note) => note.cards.map((card) => card.id);
  const inDeck = (note, query) => {
    const decks = [...query.matchAll(/deck:"((?:[^"\\]|\\.)*)"/g)].map((m) => m[1].replace(/\\(.)/g, "$1"));
    return decks.some((deck) => note.deck === deck || note.deck.startsWith(`${deck}::`));
  };
  const invoke = async (action, params) => {
    calls.push({ action, params });
    if (action === "findNotes") {
      // edited:N and rated:N return every candidate; exact timestamps must decide.
      return notes.filter((note) => inDeck(note, params.query)).map((note) => note.id);
    }
    if (action === "findCards") {
      return notes.filter((note) => inDeck(note, params.query)).flatMap(cardsOf);
    }
    if (action === "notesInfo") {
      return params.notes.map((id) => {
        const note = notes.find((item) => item.id === id);
        return { noteId: id, mod: Math.floor(note.mod / 1000) };
      });
    }
    if (action === "cardsInfo") {
      return params.cards.map((cardId) => ({ cardId, note: notes.find((note) => cardsOf(note).includes(cardId)).id }));
    }
    if (action === "getReviewsOfCards") {
      for (const card of params.cards) assert.equal(typeof card, "number", "card ids must be integers");
      const out = {};
      for (const cardId of params.cards) {
        const card = notes.flatMap((note) => note.cards).find((item) => item.id === cardId);
        out[String(cardId)] = card.reviews.map(([at, ease]) => ({ id: at, ease }));
      }
      return out;
    }
    throw new Error(`unexpected ${action}`);
  };
  return { invoke, calls };
}

function note(id, deck, { mod = BEFORE, reviews = [] } = {}) {
  return { id, deck, mod, cards: [{ id: id * 10, reviews }] };
}

const META = {
  anki_snapshot_at: new Date(SNAPSHOT).toISOString(),
  seen_note_ids: { Mining: [1, 2, 3, 4, 5], Core: [6] },
};

test("counts each kind of change since the snapshot exactly", async () => {
  const anki = fakeAnki([
    note(1, "Mining"), // untouched
    note(2, "Mining", { mod: AFTER }), // edited after
    note(3, "Mining", { reviews: [[BEFORE, 3], [AFTER, 3]] }), // reviewed after
    note(4, "Mining::Sub", { mod: BEFORE + 1000, reviews: [[BEFORE, 2]] }), // changed only before
    // 5 was deleted
    note(7, "Mining", { mod: AFTER }), // new: edited and reviewed do not count it twice
    note(6, "Core", { reviews: [[AFTER, 0]] }), // a manual reschedule is not a review
  ]);
  const result = await countPending({ invoke: anki.invoke, meta: META, decks: ["Mining", "Core"], now: AFTER });
  assert.deepEqual(result.total, { new: 1, edited: 1, reviewed: 1, deleted: 1 });
  assert.deepEqual(result.decks.Mining, { new: 1, deleted: 1, edited: 1, reviewed: 1 });
  assert.deepEqual(result.decks.Core, { new: 0, deleted: 0, edited: 0, reviewed: 0 });
});

test("a deck that was never synced counts every note as new", async () => {
  const anki = fakeAnki([note(1, "Mining"), note(8, "Output"), note(9, "Output")]);
  const result = await countPending({ invoke: anki.invoke, meta: META, decks: ["Mining", "Output"], now: AFTER });
  assert.equal(result.decks.Output.new, 2);
  assert.equal(result.total.new, 2);
});

test("searches reach back past Anki's day boundary", async () => {
  const anki = fakeAnki([note(1, "Mining")]);
  await countPending({ invoke: anki.invoke, meta: META, decks: ["Mining"], now: SNAPSHOT + 3 * 24 * 3600_000 + 5 });
  const queries = anki.calls.map((call) => call.params.query).filter(Boolean);
  assert.ok(queries.includes('deck:"Mining" edited:5'), queries.join(" | "));
  assert.ok(queries.includes('deck:"Mining" rated:5'), queries.join(" | "));
});

test("without a snapshot it asks for an update first", async () => {
  const anki = fakeAnki([]);
  const result = await countPending({ invoke: anki.invoke, meta: { last_synced_at: "x" }, decks: ["Mining"] });
  assert.deepEqual(result, { ok: false, reason: "no-baseline" });
  assert.equal(anki.calls.length, 0);
});

test("deck names are quoted like the Python client", () => {
  assert.equal(deckQuery('My "deck"\\x'), 'deck:"My \\"deck\\"\\\\x"');
});
