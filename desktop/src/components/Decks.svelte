<script>
  let { decks, selected, onToggle } = $props();
</script>

<section>
  <h2>Decks</h2>
  <p class="hint">Checked decks are written to config.toml. A name includes its subdecks.</p>
  <div>
    {#if decks.length === 0}
      No decks yet.
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
