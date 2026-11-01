<script>
  import { ROLES } from "../lib/roles.js";

  let {
    noteTypes,
    noteTypeName = $bindable(""),
    ankiOpen,
    preview,
    previewError,
    onChange,
    onEdit,
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
  <h2>2. Mark the word and the definition</h2>
  <p class="hint">
    Optional. For a card type, say which box is the word and which is the definition, and leave out audio and pictures.
    Card types you leave alone still match usual names such as Front, Expression, or Meaning.
    Press Update search after you change this.
  </p>
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
  <h3>Example of what search will use</h3>
  <pre class:error={previewError}>{preview}</pre>
</section>
