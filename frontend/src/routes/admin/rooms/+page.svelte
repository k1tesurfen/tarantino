<script lang="ts">
	import { onMount } from 'svelte';
	import ChipPicker from '$lib/admin/ChipPicker.svelte';
	import {
		createRoom,
		deleteRoom,
		getFacets,
		getPresets,
		getRooms,
		previewFilters,
		updateRoom,
		type Facets,
		type MovieFilters,
		type Room
	} from '$lib/api';

	const emptyFilters: MovieFilters = {
		watched: 'any',
		favorite: 'any',
		genres_any: [],
		genres_none: [],
		tags_any: [],
		tags_none: [],
		official_ratings: [],
		year_min: null,
		year_max: null,
		min_community_rating: null,
		min_critic_rating: null,
		runtime_min: null,
		runtime_max: null
	};
	const emptyWeights = { community_rating: 0, critic_rating: 0, recently_added: 0, never_shown: 0 };
	const weightLabels: Record<keyof typeof emptyWeights, string> = {
		community_rating: 'Prefer high audience rating',
		critic_rating: 'Prefer high critic rating',
		recently_added: 'Prefer recently added',
		never_shown: 'Prefer never shown before'
	};

	let rooms = $state<Room[]>([]);
	let facets = $state<Facets>({ genres: [], tags: [], official_ratings: [] });
	let presets = $state<Record<string, MovieFilters>>({});

	let editing = $state<Room | null>(null);
	let originalNumber = $state<number | null>(null); // null: creating a new room
	let pool = $state<{ count: number; sample: string[] } | null>(null);
	let error = $state<string | null>(null);
	let notice = $state<string | null>(null);

	async function load() {
		rooms = await getRooms();
	}

	function edit(room: Room) {
		editing = structuredClone($state.snapshot(room));
		originalNumber = room.number;
		error = notice = null;
	}

	function create(kind: 'movie' | 'series') {
		const number = Math.max(0, ...rooms.map((r) => r.number)) + 1;
		editing = {
			number,
			name: kind === 'movie' ? `Auditorium ${number}` : `Series Lounge ${number}`,
			kind,
			filters: structuredClone(kind === 'movie' ? presets.unwatched ?? emptyFilters : emptyFilters),
			weights: { ...emptyWeights },
			active: true
		};
		originalNumber = null;
		error = notice = null;
	}

	function applyPreset(name: string) {
		if (editing && presets[name]) editing.filters = structuredClone($state.snapshot(presets[name]));
	}

	// Live pool size while editing movie filters.
	let poolTimer: ReturnType<typeof setTimeout>;
	$effect(() => {
		const filters = editing?.kind === 'movie' ? $state.snapshot(editing.filters) : null;
		clearTimeout(poolTimer);
		if (!filters) {
			pool = null;
			return;
		}
		poolTimer = setTimeout(async () => {
			pool = await previewFilters(filters).catch(() => null);
		}, 300);
	});

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (!editing) return;
		error = notice = null;
		try {
			const room = $state.snapshot(editing) as Room;
			if (originalNumber === null) await createRoom(room);
			else await updateRoom(originalNumber, room);
			notice = `Saved ${room.name}. Changes apply from the next re-roll or cinema day.`;
			editing = null;
			await load();
		} catch (e) {
			error = (e as Error).message;
		}
	}

	async function remove() {
		if (!editing || originalNumber === null) return;
		if (!confirm(`Delete ${editing.name}? Its programme history and cassette link are removed too.`)) return;
		try {
			await deleteRoom(originalNumber);
			editing = null;
			await load();
		} catch (e) {
			error = (e as Error).message;
		}
	}

	const nullableNumber = (value: string) => (value === '' ? null : Number(value));

	onMount(async () => {
		[rooms, facets, presets] = await Promise.all([getRooms(), getFacets(), getPresets()]);
	});
</script>

<svelte:head><title>Rooms · tarantino</title></svelte:head>

<div class="section-head">
	<h2>Rooms</h2>
	<div class="buttons">
		<button class="ghost" onclick={() => create('movie')}>+ Auditorium</button>
		<button class="ghost" onclick={() => create('series')}>+ Series lounge</button>
	</div>
</div>
<p class="muted">The room number is also the number of the VHS cassette that plays it.</p>
{#if notice}<p class="muted">{notice}</p>{/if}

<div class="layout">
	<ul class="list">
		{#each rooms as room (room.number)}
			<li>
				<button class="item" class:selected={originalNumber === room.number && editing} onclick={() => edit(room)}>
					<span class="number">{room.number}</span>
					<span>
						{room.name}
						<small class="muted">{room.kind === 'movie' ? 'auditorium' : 'series lounge'}{room.active ? '' : ' · inactive'}</small>
					</span>
				</button>
			</li>
		{/each}
	</ul>

	{#if editing}
		<form class="editor" onsubmit={save}>
			<div class="row">
				<label class="narrow">Number <input type="number" min="1" max="99" bind:value={editing.number} required /></label>
				<label class="grow">Name <input bind:value={editing.name} maxlength="60" required /></label>
				<label class="check"><input type="checkbox" bind:checked={editing.active} /> Active</label>
			</div>

			{#if editing.kind === 'series'}
				<p class="muted">Series lounges pick random unfinished series. A series started here stays until it is finished or dropped.</p>
			{:else}
				<fieldset>
					<legend>Which films</legend>
					<div class="row">
						<label>
							Preset
							<select onchange={(e) => applyPreset((e.target as HTMLSelectElement).value)}>
								<option value="">Apply a preset…</option>
								{#each Object.keys(presets) as name}<option value={name}>{name.replace('_', ' ')}</option>{/each}
							</select>
						</label>
						<label>
							Watched
							<select bind:value={editing.filters.watched}>
								<option value="any">any</option>
								<option value="unwatched">unwatched only</option>
								<option value="watched">watched only</option>
							</select>
						</label>
						<label>
							Favourite ❤️
							<select bind:value={editing.filters.favorite}>
								<option value="any">any</option>
								<option value="yes">favourites only</option>
								<option value="no">no favourites</option>
							</select>
						</label>
					</div>
					<ChipPicker label="At least one of these genres" options={facets.genres} bind:selected={editing.filters.genres_any} />
					<ChipPicker label="None of these genres" options={facets.genres} bind:selected={editing.filters.genres_none} />
					{#if facets.tags.length}
						<ChipPicker label="At least one of these tags" options={facets.tags} bind:selected={editing.filters.tags_any} />
						<ChipPicker label="None of these tags" options={facets.tags} bind:selected={editing.filters.tags_none} />
					{/if}
					<ChipPicker label="Only these age ratings (empty: all)" options={facets.official_ratings} bind:selected={editing.filters.official_ratings} />
					<div class="row">
						<label>Year from <input type="number" value={editing.filters.year_min ?? ''} oninput={(e) => editing && (editing.filters.year_min = nullableNumber(e.currentTarget.value))} /></label>
						<label>Year to <input type="number" value={editing.filters.year_max ?? ''} oninput={(e) => editing && (editing.filters.year_max = nullableNumber(e.currentTarget.value))} /></label>
						<label>Runtime min <input type="number" min="0" value={editing.filters.runtime_min ?? ''} oninput={(e) => editing && (editing.filters.runtime_min = nullableNumber(e.currentTarget.value))} /></label>
						<label>Runtime max <input type="number" min="0" value={editing.filters.runtime_max ?? ''} oninput={(e) => editing && (editing.filters.runtime_max = nullableNumber(e.currentTarget.value))} /></label>
					</div>
					<div class="row">
						<label>Min. audience rating (0–10) <input type="number" min="0" max="10" step="0.1" value={editing.filters.min_community_rating ?? ''} oninput={(e) => editing && (editing.filters.min_community_rating = nullableNumber(e.currentTarget.value))} /></label>
						<label>Min. critic rating (0–100) <input type="number" min="0" max="100" value={editing.filters.min_critic_rating ?? ''} oninput={(e) => editing && (editing.filters.min_critic_rating = nullableNumber(e.currentTarget.value))} /></label>
					</div>
					<p class="pool">
						{#if pool}
							<strong>{pool.count}</strong> films match{pool.count ? `, e.g. ${pool.sample.slice(0, 4).join(', ')}` : ' — this room would be closed'}
						{:else}…{/if}
					</p>
				</fieldset>

				<fieldset>
					<legend>Pick bias</legend>
					{#each Object.entries(weightLabels) as [key, label]}
						<label class="slider">
							<span>{label}</span>
							<input type="range" min="0" max="10" step="1" bind:value={editing.weights[key as keyof typeof emptyWeights]} />
							<span class="value">{editing.weights[key as keyof typeof emptyWeights]}</span>
						</label>
					{/each}
				</fieldset>
			{/if}

			<div class="footer">
				<button type="submit">{originalNumber === null ? 'Create room' : 'Save room'}</button>
				<button type="button" class="ghost" onclick={() => (editing = null)}>Cancel</button>
				{#if originalNumber !== null}<button type="button" class="ghost danger" onclick={remove}>Delete</button>{/if}
				{#if error}<span class="error">{error}</span>{/if}
			</div>
		</form>
	{:else}
		<p class="muted hint">Select a room to edit it.</p>
	{/if}
</div>

<style>
	.buttons {
		display: flex;
		gap: 0.5rem;
	}
	.layout {
		display: grid;
		grid-template-columns: minmax(14rem, 18rem) 1fr;
		gap: 1.5rem;
		align-items: start;
	}
	@media (max-width: 760px) {
		.layout {
			grid-template-columns: 1fr;
		}
	}
	.list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.item {
		all: unset;
		box-sizing: border-box;
		display: flex;
		gap: 0.75rem;
		align-items: center;
		width: 100%;
		padding: 0.5rem 0.7rem;
		border-radius: 0.35rem;
		cursor: pointer;
		background: var(--panel);
		border: 1px solid var(--line);
	}
	.item.selected,
	.item:hover {
		border-color: var(--accent);
	}
	.item small {
		display: block;
	}
	.number {
		font-weight: 700;
		font-size: 1.1rem;
		color: var(--accent);
		width: 1.6rem;
		text-align: center;
	}
	.editor {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	fieldset {
		border: 1px solid var(--line);
		border-radius: 0.5rem;
		padding: 0.75rem 1.25rem 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}
	legend {
		padding: 0 0.4rem;
		font-weight: 600;
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem 1rem;
		align-items: end;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		font-size: 0.9rem;
	}
	label.grow {
		flex: 1;
		min-width: 12rem;
	}
	label.narrow input {
		width: 5rem;
	}
	label.check {
		flex-direction: row;
		align-items: center;
		padding-bottom: 0.5rem;
	}
	.row input[type='number'] {
		width: 8rem;
	}
	.slider {
		display: grid;
		grid-template-columns: 14rem 1fr 2rem;
		align-items: center;
	}
	.value {
		text-align: right;
		color: var(--accent);
	}
	.pool {
		margin: 0;
		font-size: 0.9rem;
	}
	.footer {
		display: flex;
		gap: 0.6rem;
		align-items: center;
		flex-wrap: wrap;
	}
	.footer .danger {
		color: #f3a1a1;
		border-color: #5c1f1f;
	}
	.hint {
		padding-top: 0.5rem;
	}
</style>
