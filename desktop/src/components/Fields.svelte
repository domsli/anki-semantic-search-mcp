<script>
  import Spinner from "./Spinner.svelte";
  import { ROLE_LABELS } from "../lib/configuration.js";
  import { ROLES } from "../lib/roles.js";

  // One tab per card type in the tracked decks. Settings belong to the card type, in every deck.
  let {
    hasDecks,
    noteTypes,
    noteTypeName,
    ankiOpen,
    preview,
    previewError,
    previewing,
    loadingTypes,
    dirty,
    saving,
    syncing,
    comparing,
    saveError,
    onType,
    onEdit,
    onSave,
  } = $props();

  let tabs = $derived(noteTypes);
  let current = $derived(tabs.find((item) => item.name === noteTypeName) ?? null);

  function resetToDefault() {
    if (!current) return;
    current.roles = { ...(current.default_roles || {}) };
    current.mapped = false;
    onEdit();
  }

  // Arrow keys move between tabs, as in a native tab strip.
  function onTabKey(event, index) {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!step || !tabs.length) return;
    event.preventDefault();
    const next = tabs[(index + step + tabs.length) % tabs.length];
    onType(next.name);
    document.getElementById(`tab-${next.name}`)?.focus();
  }
</script>

<section>
  <h2><span class="step">2</span>Card indexing configuration</h2>
  <p class="hint">
    The marked fields are combined into the text stored in the vector database. Search measures the distance
    between your question and that text. Ignored fields are left out.
  </p>
  {#if !hasDecks}
    <p class="snapshot">Add a deck first.</p>
  {:else}
    {#if loadingTypes}
      <p class="status" role="status"><Spinner /><span>Loading card types…</span></p>
    {:else if !ankiOpen}
      <p class="snapshot">Open Anki to see card types.</p>
    {:else if tabs.length === 0}
      <p class="snapshot">No card types in these decks.</p>
    {:else}
      <div class="tabs" role="tablist" aria-label="Card types">
        {#each tabs as item, index (item.name)}
          <button
            type="button"
            role="tab"
            id={`tab-${item.name}`}
            aria-selected={item.name === noteTypeName}
            tabindex={item.name === noteTypeName ? 0 : -1}
            class:selected={item.name === noteTypeName}
            onclick={() => onType(item.name)}
            onkeydown={(event) => onTabKey(event, index)}
          >
            {item.name}
            <span class="tab-mode">{item.mapped ? "custom" : "default"}</span>
          </button>
        {/each}
      </div>
      {#if current}
        <div class="tab-panel" role="tabpanel" aria-labelledby={`tab-${current.name}`}>
          {#if current.mapped}
            <div class="mode row">
              <button type="button" onclick={resetToDefault}>Reset to default</button>
            </div>
          {/if}
          {#each current.fields as field (field)}
            {@const fallback = current.default_roles?.[field] || "unassigned"}
            <label class="field">
              <span class="field-name">{field}</span>
              <select
                value={current.roles[field] || "unassigned"}
                onchange={(event) => {
                  current.roles[field] = event.currentTarget.value;
                  current.mapped = true;
                  onEdit();
                }}
              >
                {#each ROLES as role (role)}
                  <option value={role}>{ROLE_LABELS[role]}</option>
                {/each}
              </select>
              {#if current.mapped && (current.roles[field] || "unassigned") !== fallback}
                <span class="default-note">Default: {ROLE_LABELS[fallback]}</span>
              {/if}
            </label>
          {/each}
          <h3>Example</h3>
          {#if previewing}
            <p class="status" role="status"><Spinner /><span>Loading an example…</span></p>
          {:else}
            <pre class:error={previewError}>{preview}</pre>
          {/if}
        </div>
      {/if}
    {/if}
  {/if}
  {#if saveError}
    <p class="progress error" role="status">{saveError}</p>
  {/if}
  <button
    type="button"
    class="save primary"
    onclick={() => onSave()}
    disabled={!dirty || saving || syncing || comparing}
  >
    {#if saving}<Spinner />Saving…{:else}Save changes{/if}
  </button>
</section>
