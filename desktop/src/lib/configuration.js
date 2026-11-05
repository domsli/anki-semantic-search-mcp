const ROLE_ORDER = ["word", "reading", "definition", "extra", "skip"];

export const ROLE_LABELS = {
  word: "Word",
  reading: "Reading",
  definition: "Definition",
  extra: "Also include",
  skip: "Ignore",
  unassigned: "Leave out",
};

export function fieldRoles(map) {
  const roles = {};
  if (!map) return roles;
  for (const role of ROLE_ORDER) {
    for (const field of map[role] || []) roles[field] = role;
  }
  return roles;
}

export function configurationEntries(config) {
  const decks = (config?.decks || []).filter(Boolean);
  const types = Object.keys(config?.note_types || {})
    .sort()
    .map((name) => {
      const roles = fieldRoles(config.note_types[name]);
      const fields = Object.keys(roles)
        .sort()
        .map((field) => ({ field, label: ROLE_LABELS[roles[field]] }));
      return { name, fields };
    });
  return { decks, types };
}

export function configurationDifferences(previous, next) {
  if (!previous || !next) return [];
  const notes = [];
  const oldDeck = (previous.decks || []).filter(Boolean).join(", ");
  const newDeck = (next.decks || []).filter(Boolean).join(", ");
  if (oldDeck !== newDeck) notes.push(newDeck ? `Deck: ${newDeck}` : "No deck.");

  const oldTypes = previous.note_types || {};
  const newTypes = next.note_types || {};
  const names = [...new Set([...Object.keys(oldTypes), ...Object.keys(newTypes)])].sort();
  for (const name of names) {
    const had = Object.hasOwn(oldTypes, name);
    const has = Object.hasOwn(newTypes, name);
    if (had && !has) {
      notes.push(`${name}: not set up`);
      continue;
    }
    if (!had && has) {
      notes.push(`${name}: set up`);
      continue;
    }
    const before = fieldRoles(oldTypes[name]);
    const after = fieldRoles(newTypes[name]);
    const fields = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort();
    for (const field of fields) {
      const from = before[field] || "unassigned";
      const to = after[field] || "unassigned";
      if (from !== to) notes.push(`${name} / ${field}: ${ROLE_LABELS[to]}`);
    }
  }
  return notes;
}
