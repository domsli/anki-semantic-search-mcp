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
    pending,
    pendingChecking,
    indexedConfiguration,
    vectorUpdated,
    configDifferences,
    onCompare,
    onSync,
    onRebuild,
  } = $props();

  let indexed = $derived(indexedConfiguration ? configurationEntries(indexedConfiguration) : null);

  const KINDS = ["new", "edited", "reviewed", "deleted"];

  function describe(counts) {
    return KINDS.filter((kind) => counts[kind]).map((kind) => `${counts[kind]} ${kind}`).join(" · ");
  }

  let pendingTotal = $derived(pending?.ok ? KINDS.reduce((sum, kind) => sum + pending.total[kind], 0) : 0);
  let pendingDecks = $derived(
    pending?.ok ? Object.entries(pending.decks).filter(([, counts]) => KINDS.some((kind) => counts[kind])) : [],
  );
  let pendingNote = $derived.by(() => {
    if (!pending || pending.ok) return "";
    if (pending.reason === "no-baseline") return "Update decks once to start counting changes.";
    if (pending.reason === "anki-closed") return "Anki needs to be open to count changes.";
    return pending.error || "Couldn't count changes.";
  });

  function clock(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString();
  }
</script>

<section>
  <h2>3. Vector database</h2>
  <div class="pending" role="status">
    {#if pending?.ok}
      {#if pendingTotal === 0}
        <p class="snapshot in-sync">In sync with Anki.</p>
      {:else}
        <p class="snapshot"><strong>Not synced:</strong> {describe(pending.total)}</p>
        {#if pendingDecks.length > 1}
          <ul class="config-list">
            {#each pendingDecks as [name, counts] (name)}
              <li>{name}: {describe(counts)}</li>
            {/each}
          </ul>
        {/if}
      {/if}
      <p class="checked">Checked {clock(pending.checkedAt)}{#if pendingChecking}<Spinner />{/if}</p>
    {:else if pendingNote}
      <p class="snapshot">{pendingNote}</p>
    {:else if pendingChecking}
      <p class="status"><Spinner /><span>Counting changes in Anki…</span></p>
    {/if}
  </div>
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
  {#if comparing || diff}
    <p class="diff" class:status={comparing} class:error={diffError} role="status">
      {#if comparing}<Spinner /><span>Comparing…</span>{:else}{diff}{/if}
    </p>
  {/if}
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
