<script>
  let { decks, deck, dirty, onChoose } = $props();

</script>

<section>
  <h2>1. Deck</h2>
  <p class="hint">Includes nested decks. Other decks are left out.</p>
  {#if decks.length === 0}
    <p>Open Anki and refresh.</p>
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
    {#if dirty}<p class="snapshot">Unsaved.</p>{/if}
  {/if}
</section>
