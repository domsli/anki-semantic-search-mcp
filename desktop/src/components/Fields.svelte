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
</script>

<section>
  <h2>2. Fields</h2>
  <p class="hint">These boxes are what distance uses. Unset card types use Front, Expression, or Meaning.</p>
  {#if loadingTypes}
    <p class="status" role="status"><Spinner /><span>Loading card types…</span></p>
  {:else}
    <label>
      Card type
      <select bind:value={noteTypeName} onchange={() => onChange()}>
        {#each noteTypes as item (item.name)}
          <option value={item.name}>{item.mapped ? `${item.name} (set up)` : item.name}</option>
        {/each}
      </select>
    </label>
    <label class="check">
      <input
        type="checkbox"
        checked={Boolean(current?.mapped)}
        disabled={!current || !ankiOpen}
        onchange={(event) => {
          if (!current) return;
          current.mapped = event.currentTarget.checked;
          onEdit();
        }}
      />
      Set up this card type
    </label>
    <div>
      {#if current}
        {#each current.fields as field (field)}
          <label class="field">
            {field}
            <select
              value={current.roles[field] || "unassigned"}
              disabled={!current.mapped || !ankiOpen}
              onchange={(event) => {
                current.roles[field] = event.currentTarget.value;
                onEdit();
              }}
            >
              {#each ROLES as role (role)}
                <option value={role}>{roleLabels[role]}</option>
              {/each}
            </select>
          </label>
        {/each}
      {/if}
    </div>
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
