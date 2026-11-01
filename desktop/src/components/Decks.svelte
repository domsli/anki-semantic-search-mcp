<script>
  let { decks, selected, dirty, onToggle } = $props();

  let summary = $derived.by(() => {
    if (selected.length === 0) return "Nothing is checked. Check a deck, then press Update search.";
    const names = selected.join(", ");
    if (dirty) return `Checked: ${names}. Press Update search to use this list. A check by itself does not update search.`;
    return `Saved: ${names}. Press Update search to read new and edited cards from these decks.`;
  });
</script>

<section>
  <h2>1. Choose decks</h2>
  <p class="hint">
    A checked deck is included, along with the decks inside it. An unchecked deck is left out.
    The check does nothing until you press Update search.
  </p>
  <p class="snapshot">{summary}</p>
  <div>
    {#if decks.length === 0}
      Open Anki, then refresh, to see your decks.
    {:else}
      {#each decks as name (name)}
        <label class="deck">
          <input
            type="checkbox"
            checked={selected.includes(name)}
            onchange={(event) => onToggle(name, event.currentTarget.checked)}
          />
          {name}
        </label>
      {/each}
    {/if}
  </div>
</section>
