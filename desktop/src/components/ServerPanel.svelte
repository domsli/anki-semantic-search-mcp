<script>
  import Spinner from "./Spinner.svelte";

  // running: the port answers. owned: this window started it, so it can stop it.
  let { running, owned, url, message, error, busy, busyLabel, onToggle } = $props();

  let outside = $derived(running && !owned);
  let label = $derived.by(() => {
    if (busy) return busyLabel;
    if (outside) return "Running outside this window";
    return running ? "Running · Stop MCP server" : "Start MCP server";
  });
</script>

<section>
  <h2>MCP server</h2>
  <div class="row">
    <button
      type="button"
      class="server-toggle"
      class:running={running && !busy}
      aria-pressed={running}
      onclick={onToggle}
      disabled={busy || outside}
    >
      {#if busy}
        <Spinner />
      {:else if running}
        <svg class="running-icon" viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="4" /></svg>
      {/if}
      <span>{label}</span>
    </button>
    <code>{url}</code>
  </div>
  {#if message}
    <p class="server-message" class:error role="status">{message}</p>
  {/if}
</section>
