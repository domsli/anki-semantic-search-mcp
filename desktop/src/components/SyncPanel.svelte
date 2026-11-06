<script>
  import Spinner from "./Spinner.svelte";
  import { configurationEntries } from "../lib/configuration.js";

  let {
    snapshot,
    diff,
    diffError,
    progress,
    progressError,
    syncing,
    comparing,
    saving,
    hasDecks,
    indexedConfiguration,
    vectorUpdated,
    configDifferences,
    onCompare,
    onSync,
    onRebuild,
  } = $props();

  let indexed = $derived(indexedConfiguration ? configurationEntries(indexedConfiguration) : null);
</script>

<section>
  <h2>3. Vector database</h2>
  <h3>Stored configuration</h3>
  {#if indexed}
    <ul class="config-list">
      {#if indexed.types.length === 0}
        <li>Every card type uses the default fields.</li>
      {:else}
        <li>Other card types use the default fields.</li>
        {#each indexed.types as type (type.name)}
          <li>
            {type.name} (custom)
            {#if type.fields.length === 0}
              <ul><li>None.</li></ul>
            {:else}
              <ul>
                {#each type.fields as row (row.field)}
                  <li>{row.field}: {row.label}</li>
                {/each}
              </ul>
            {/if}
          </li>
        {/each}
      {/if}
    </ul>
  {:else if vectorUpdated}
    <p class="snapshot">Not recorded.</p>
  {:else}
    <p class="snapshot">None yet.</p>
  {/if}
  {#if configDifferences.length}
    <p class="snapshot">Different from above.</p>
    <ul class="config-list">
      {#each configDifferences as line, index (index)}
        <li>{line}</li>
      {/each}
    </ul>
  {/if}
  <p class="snapshot">{snapshot}</p>
  <p class="diff" class:status={comparing} class:error={diffError} role="status">
    {#if comparing}<Spinner /><span>Comparing…</span>{:else}{diff}{/if}
  </p>
  {#if progress || syncing}
    <p class="progress" class:status={syncing || saving} class:error={progressError} role="status">
      {#if syncing || saving}<Spinner />{/if}
      <span>{progress}</span>
    </p>
  {/if}
  <p class="hint">
    The vector database does not follow Anki on its own. Cards you add, edit, delete, or review appear in search
    only after Update decks.
  </p>
  <div class="row">
    <button type="button" class="primary" onclick={onSync} disabled={!hasDecks || syncing || comparing || saving}>Update decks</button>
    <button type="button" onclick={onCompare} disabled={!hasDecks || syncing || comparing || saving}>See missed updates</button>
    <button type="button" onclick={onRebuild} disabled={!hasDecks || syncing || comparing || saving}>Re-index decks</button>
  </div>
</section>
