<script>
  import Spinner from "./Spinner.svelte";

  let {
    snapshot,
    diff,
    diffError,
    progress,
    progressError,
    syncing,
    comparing,
    saving,
    dirty,
    deck,
    onCompare,
    onSync,
    onRebuild,
    onSave,
  } = $props();
</script>

<section>
  <h2>3. Update search</h2>
  <p class="hint">
    Press Update search. That saves this deck and reads it from Anki.
    Picking a different deck, or adding cards in Anki, does not update search on its own.
    Anki needs to be open.
  </p>
  {#if dirty}
    <p class="snapshot">
      {deck
        ? `Update search will read ${deck}.`
        : "Choose a deck before updating search."}
    </p>
  {/if}
  <p class="snapshot">{snapshot}</p>
  <p class="diff" class:status={comparing} class:error={diffError} role="status">
    {#if comparing}<Spinner /><span>Checking what changed…</span>{:else}{diff}{/if}
  </p>
  {#if progress || syncing || saving}
    <p class="progress" class:status={syncing || saving} class:error={progressError} role="status">
      {#if syncing || saving}<Spinner />{/if}
      <span>{progress}</span>
    </p>
  {/if}
  <div class="row">
    <button type="button" class="primary" onclick={onSync} disabled={!deck || syncing || comparing || saving}>Update search</button>
    <button type="button" onclick={onCompare} disabled={!deck || syncing || comparing || saving}>See what changed</button>
    <button type="button" onclick={onRebuild} disabled={!deck || syncing || comparing || saving}>Update everything</button>
    <button type="button" onclick={() => onSave()} disabled={!deck || syncing || comparing || saving}>Save without updating</button>
  </div>
  <p class="hint">
    See what changed previews the next update. Update everything rereads every card and takes longer.
    Save without updating remembers this deck for later.
  </p>
</section>
