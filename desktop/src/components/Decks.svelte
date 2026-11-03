<script>
  let { decks, deck, dirty, onChoose } = $props();

  let summary = $derived.by(() => {
    if (!deck) return "No deck chosen yet. Pick one, then press Update search.";
    if (dirty) return `Chosen: ${deck}. Press Update search to use this deck. Choosing a deck does not update search by itself.`;
    return `Saved: ${deck}. Press Update search to read new and edited cards from this deck.`;
  });
</script>

<section>
  <h2>1. Choose a deck</h2>
  <p class="hint">
    Search updates one deck at a time. A deck includes the decks inside it.
    The choice does nothing until you press Update search.
  </p>
  <p class="snapshot">{summary}</p>
  {#if decks.length === 0}
    <p>Open Anki, then refresh, to see your decks.</p>
  {:else}
    <label class="deck-pick">
      Deck
      <select value={deck} onchange={(event) => onChoose(event.currentTarget.value)}>
        {#if !deck}
          <option value="">Choose a deck…</option>
        {/if}
        {#each decks as name (name)}
          <option value={name}>{name}</option>
        {/each}
      </select>
    </label>
  {/if}
</section>
