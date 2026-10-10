<script lang="ts">
	let {
		label,
		options,
		selected = $bindable()
	}: { label: string; options: string[]; selected: string[] } = $props();

	let adding = $state('');
	const available = $derived(options.filter((o) => !selected.includes(o)));

	function add() {
		if (adding && !selected.includes(adding)) selected = [...selected, adding];
		adding = '';
	}
</script>

<div class="picker">
	<span class="label">{label}</span>
	<div class="chips">
		{#each selected as value (value)}
			<button type="button" class="chip" onclick={() => (selected = selected.filter((v) => v !== value))}>
				{value} ✕
			</button>
		{/each}
		{#if available.length}
			<select bind:value={adding} onchange={add} aria-label="Add to {label}">
				<option value="">+ add</option>
				{#each available as option}<option value={option}>{option}</option>{/each}
			</select>
		{/if}
	</div>
</div>

<style>
	.picker {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		font-size: 0.9rem;
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		align-items: center;
	}
	.chip {
		background: var(--bg);
		color: var(--text);
		border: 1px solid #3a3c42;
		border-radius: 999px;
		padding: 0.15rem 0.6rem;
		font-weight: 400;
		font-size: 0.85rem;
	}
	.chips select {
		padding: 0.2rem 0.4rem;
		font-size: 0.85rem;
	}
</style>
