<script>
  let {
    snapshot,
    diff,
    diffError,
    progress,
    progressError,
    dirty,
    selected,
    onCompare,
    onSync,
    onRebuild,
    onSave,
  } = $props();
</script>

<section>
  <h2>3. Update search</h2>
  <p class="hint">
    Press Update search. That saves the checked decks and reads them from Anki.
    Checking a box, or adding cards in Anki, does not update search on its own.
    Anki needs to be open.
  </p>
  {#if dirty}
    <p class="snapshot">
      {selected.length === 0
        ? "Check at least one deck before updating search."
        : "Your checks are waiting. Update search will include them."}
    </p>
  {/if}
  <p class="snapshot">{snapshot}</p>
  <p class="diff" class:error={diffError}>{diff}</p>
  <p class="progress" class:error={progressError}>{progress}</p>
  <div class="row">
    <button type="button" class="primary" onclick={onSync}>Update search</button>
    <button type="button" onclick={onCompare}>See what changed</button>
    <button type="button" onclick={onRebuild}>Update everything</button>
    <button type="button" onclick={() => onSave()}>Save without updating</button>
  </div>
  <p class="hint">
    See what changed previews the next update. Update everything rereads every card and takes longer.
    Save without updating remembers the checks for later.
  </p>
</section>
