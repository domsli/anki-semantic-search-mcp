const ASSIGNED = ["word", "reading", "definition", "extra", "skip"];

export const ROLES = [...ASSIGNED, "unassigned"];

export function roleLists(item) {
  const lists = { word: [], reading: [], definition: [], extra: [], skip: [] };
  for (const field of item.fields) {
    const role = item.roles?.[field] || "unassigned";
    if (lists[role]) lists[role].push(field);
  }
  return lists;
}
