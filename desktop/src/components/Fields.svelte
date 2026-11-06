<script>
  import Spinner from "./Spinner.svelte";
  import { ROLES } from "../lib/roles.js";

  let {
    noteTypes,
    noteTypeName = $bindable(""),
    ankiOpen,
    preview,
    previewError,
    previewing,
    loadingTypes,
    deck,
    saving,
    syncing,
    comparing,
    saveProgress,
    saveError,
    onChange,
    onEdit,
    onSave,
  } = $props();

  let current = $derived(noteTypes.find((item) => item.name === noteTypeName) ?? null);

  const roleLabels = {
    word: "Word",
    reading: "Reading",
    definition: "Definition",
    extra: "Also include",
    skip: "Ignore",
    unassigned: "Leave out",
  };

  function resetToDefault() {
    if (!current) return;
    current.roles = { ...(current.default_roles || {}) };
    current.mapped = false;
    onEdit();
  }
</script>

<section>
  <h2>2. Fields</h2>
  <p class="hint">
    The marked fields are combined into the text stored in the vector database. Search measures the distance
    between your question and that text. Ignored fields are left out.
  </p>
  {#if loadingTypes}
    <p class="status" role="status"><Spinner /><span>Loading card types…</span></p>
  {:else}
    <label>
      Card type
      <select bind:value={noteTypeName} onchange={() => onChange()}>
        {#each noteTypes as item (item.name)}
          <option value={item.name}>{item.mapped ? `${item.name} (custom)` : `${item.name} (default)`}</option>
        {/each}
      </select>
    </label>
    {#if current}
      {#if current.mapped}
        <div class="mode row">
          <button type="button" onclick={resetToDefault} disabled={!ankiOpen}>Reset to default</button>
        </div>
      {/if}
      <div>
        {#each current.fields as field (field)}
          {@const fallback = current.default_roles?.[field] || "unassigned"}
          <label class="field">
            {field}
            <select
              value={current.roles[field] || "unassigned"}
              disabled={!ankiOpen}
              onchange={(event) => {
                current.roles[field] = event.currentTarget.value;
                current.mapped = true;
                onEdit();
              }}
            >
              {#each ROLES as role (role)}
                <option value={role}>{roleLabels[role]}</option>
              {/each}
            </select>
            {#if current.mapped && (current.roles[field] || "unassigned") !== fallback}
              <span class="default-note">Default: {roleLabels[fallback]}</span>
            {/if}
          </label>
        {/each}
      </div>
    {/if}
    <h3>Example</h3>
    {#if previewing}
      <p class="status" role="status"><Spinner /><span>Loading an example…</span></p>
    {:else}
      <pre class:error={previewError}>{preview}</pre>
    {/if}
  {/if}
  <h3>Save configuration</h3>
  <p class="hint">Does not update the vector database.</p>
  {#if saveProgress || saving}
    <p class="progress" class:status={saving} class:error={saveError} role="status">
      {#if saving}<Spinner />{/if}
      <span>{saveProgress}</span>
    </p>
  {/if}
  <button type="button" onclick={() => onSave()} disabled={!deck || saving || syncing || comparing}>Save configuration</button>
</section>
