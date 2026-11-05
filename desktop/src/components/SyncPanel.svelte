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
    deck,
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
      <li>Deck: {indexed.decks.join(", ") || "None"}</li>
      {#if indexed.types.length === 0}
        <li>No card type set up.</li>
      {:else}
        {#each indexed.types as type (type.name)}
          <li>
            {type.name}
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
  <div class="row">
    <button type="button" class="primary" onclick={onSync} disabled={!deck || syncing || comparing || saving}>Update search</button>
    <button type="button" onclick={onCompare} disabled={!deck || syncing || comparing || saving}>See what changed</button>
    <button type="button" onclick={onRebuild} disabled={!deck || syncing || comparing || saving}>Measure every card again</button>
  </div>
</section>
