<script>
  import { ROLES } from "../lib/roles.js";

  let {
    noteTypes,
    noteTypeName = $bindable(""),
    ankiOpen,
    preview,
    previewError,
    onChange,
  } = $props();

  let current = $derived(noteTypes.find((item) => item.name === noteTypeName) ?? null);
</script>

<section>
  <h2>Fields</h2>
  <p class="hint">A custom map indexes only the fields you assign. Other note types keep the shared field names.</p>
  <label>
    Note type
    <select bind:value={noteTypeName} onchange={() => onChange()}>
      {#each noteTypes as item (item.name)}
        <option value={item.name}>{item.mapped ? `${item.name} (custom)` : item.name}</option>
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
        onChange();
      }}
    />
    Use a custom field map for this note type
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
              onChange();
            }}
          >
            {#each ROLES as role (role)}
              <option value={role}>{role}</option>
            {/each}
          </select>
        </label>
      {/each}
    {/if}
  </div>
  <h3>Sample passage</h3>
  <pre class:error={previewError}>{preview}</pre>
</section>
