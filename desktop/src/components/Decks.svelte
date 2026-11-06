<script>
  import Spinner from "./Spinner.svelte";

  // decks: every deck in Anki. tracked: decks kept in the vector database.
  // indexed: tracked decks that an update has already put in the database.
  let { decks, tracked, indexed, ankiOpen, busy, removing, onAdd, onRemove } = $props();

  let choice = $state("");
  let addable = $derived(decks.filter((name) => !tracked.includes(name)));

  function status(name) {
    if (ankiOpen && !decks.includes(name)) return "Not in Anki";
    return indexed.includes(name) ? "In search" : "Not in search yet";
  }

  function add() {
    if (!choice) return;
    onAdd(choice);
    choice = "";
  }
</script>

<section>
  <h2>1. Decks</h2>
  <p class="hint">Each deck includes the decks inside it. Update decks reads every deck listed here.</p>
  {#if tracked.length === 0}
    <p class="snapshot">No decks yet.</p>
  {:else}
    <ul class="deck-list">
      {#each tracked as name (name)}
        <li>
          <span class="deck-name">{name}</span>
          <span class="deck-status" class:pending={status(name) !== "In search"}>{status(name)}</span>
          <button type="button" onclick={() => onRemove(name)} disabled={busy}>
            {#if removing === name}<Spinner />{/if}
            Remove
          </button>
        </li>
      {/each}
    </ul>
  {/if}
  {#if !ankiOpen}
    <p>Open Anki and refresh to add a deck.</p>
  {:else if addable.length}
    <div class="deck-pick">
      <select bind:value={choice} aria-label="Deck to add">
        <option value="">Choose a deck…</option>
        {#each addable as name (name)}
          <option value={name}>{name}</option>
        {/each}
      </select>
      <button type="button" onclick={add} disabled={!choice || busy}>Add deck</button>
    </div>
  {/if}
</section>
