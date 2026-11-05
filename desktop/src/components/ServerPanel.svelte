<script>
  import Spinner from "./Spinner.svelte";

  let { state, url, error, busy, busyLabel, onStart, onStop } = $props();
</script>

<section>
  <h2>4. MCP server</h2>
  <p class="server-state" class:status={busy} class:error role="status">
    {#if busy}<Spinner /><span>{busyLabel}</span>{:else}{state}{/if}
  </p>
  <p>{url}</p>
  <div class="row">
    <button type="button" onclick={onStart} disabled={busy}>Start MCP server</button>
    <button type="button" onclick={onStop} disabled={busy}>Stop MCP server</button>
  </div>
</section>
