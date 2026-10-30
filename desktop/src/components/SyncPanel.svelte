<script>
  let {
    snapshot,
    diff,
    diffError,
    progress,
    progressError,
    onCompare,
    onSync,
    onRebuild,
    onSave,
  } = $props();
</script>

<section>
  <h2>Sync</h2>
  <p class="snapshot">{snapshot}</p>
  <p class="diff" class:error={diffError}>{diff}</p>
  <p class="progress" class:error={progressError}>{progress}</p>
  <div class="row">
    <button type="button" onclick={onCompare}>Check sync</button>
    <button type="button" onclick={onSync}>Sync</button>
    <button type="button" onclick={onRebuild}>Rebuild</button>
    <button type="button" onclick={onSave}>Save config</button>
  </div>
</section>
