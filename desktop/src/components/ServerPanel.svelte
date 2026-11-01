<script>
  let { state, url, error, onStart, onStop } = $props();
</script>

<section>
  <h2>4. Turn on ChatGPT</h2>
  <p class="hint">
    Start this after search is updated. Paste the address into the ChatGPT connection.
    Stop turns it off. ChatGPT can keep searching after you close Anki, as long as this stays on.
  </p>
  <p class="server-state" class:error>{state}</p>
  <p>{url}</p>
  <div class="row">
    <button type="button" onclick={onStart}>Start</button>
    <button type="button" onclick={onStop}>Stop</button>
  </div>
</section>
