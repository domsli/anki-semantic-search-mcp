<script>
  let { state, url, error, onStart, onStop } = $props();
</script>

<section>
  <h2>MCP server</h2>
  <p class="server-state" class:error>{state}</p>
  <p>{url}</p>
  <div class="row">
    <button type="button" onclick={onStart}>Start</button>
    <button type="button" onclick={onStop}>Stop</button>
  </div>
</section>
