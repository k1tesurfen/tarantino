<script lang="ts">
	import { onMount } from 'svelte';
	import {
		dropSeries,
		getProgramme,
		imageUrl,
		playRoom,
		rerollRoom,
		searchLibrary,
		subscribe,
		swapRoom,
		type Programme,
		type ProgrammeRoom,
		type SampleItem
	} from '$lib/api';

	let programme = $state<Programme | null>(null);
	let error = $state<string | null>(null);
	let notice = $state<string | null>(null);

	let swapping = $state<ProgrammeRoom | null>(null);
	let query = $state('');
	let results = $state<SampleItem[]>([]);

	async function load() {
		programme = await getProgramme().catch(() => programme);
	}

	async function act(action: () => Promise<unknown>, message?: string) {
		error = notice = null;
		try {
			const result = await action();
			if (result && typeof result === 'object' && 'rooms' in result) programme = result as Programme;
			if (message) notice = message;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	let searchTimer: ReturnType<typeof setTimeout>;
	function onSearch() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(async () => {
			const kind = swapping?.kind;
			results = query.trim() ? (await searchLibrary(query)).filter((i) => i.type === kind) : [];
		}, 250);
	}

	function openSwap(room: ProgrammeRoom) {
		swapping = room;
		query = '';
		results = [];
	}

	async function swap(item: SampleItem) {
		if (!swapping) return;
		const room = swapping;
		swapping = null;
		await act(() => swapRoom(room.number, item.id));
	}

	const movieRooms = $derived(programme?.rooms.filter((r) => r.kind === 'movie') ?? []);
	const seriesRooms = $derived(programme?.rooms.filter((r) => r.kind === 'series') ?? []);

	onMount(() => {
		load();
		return subscribe({ programme: load });
	});
</script>

<svelte:head><title>Programme · tarantino</title></svelte:head>

<div class="section-head">
	<h2>Programme {programme ? `· ${new Date(programme.date).toLocaleDateString()}` : ''}</h2>
	<button class="ghost" onclick={() => act(() => rerollRoom())}>Re-roll whole day</button>
</div>
{#if error}<p class="error">{error}</p>{/if}
{#if notice}<p class="muted">{notice}</p>{/if}

{#snippet roomCard(room: ProgrammeRoom)}
	<article class="room" class:closed={!room.item}>
		{#if room.item}
			<img src={imageUrl(room.item.id, 'Primary', room.item.poster_tag, 160)} alt="" loading="lazy" />
		{:else}
			<div class="poster-placeholder"></div>
		{/if}
		<div class="body">
			<small class="muted">{room.number} · {room.name}</small>
			<strong>{room.item ? room.item.name : 'Closed today'}</strong>
			{#if room.item?.franchise}
				<small class="franchise">
					{room.item.franchise.name}{room.item.franchise.part
						? ` · part ${room.item.franchise.part} of ${room.item.franchise.parts}`
						: ''}
				</small>
			{/if}
			{#if room.next}<small class="franchise">Next: {room.next.name}</small>{/if}
			{#if room.item}
				<small class="muted">
					{room.item.year ?? ''}
					{room.item.runtime_minutes ? `· ${room.item.runtime_minutes} min` : ''}
					{room.item.unplayed_count != null ? `· ${room.item.unplayed_count} unwatched episodes` : ''}
				</small>
				<small class="times">{room.showtimes.join(' · ')}</small>
			{/if}
			<div class="badges">
				{#if room.sold_out}<span class="badge sold">sold out</span>{/if}
				{#if room.next}<span class="badge marathon">marathon{room.marathon ? ` · ${room.marathon + 1} parts` : ''}</span>{/if}
				{#if room.sticky}<span class="badge sticky">sticky</span>{/if}
				{#if room.source === 'override'}<span class="badge">override</span>{/if}
				{#if room.source === 'franchise'}<span class="badge marathon">continued</span>{/if}
			</div>
			<div class="actions">
				{#if room.item}
					<button onclick={() => act(() => playRoom(room.number), `Starting ${room.item?.name}…`)}>Play</button>
				{/if}
				{#if room.next}
					<button onclick={() => act(() => playRoom(room.number, true), `Starting ${room.next?.name}…`)}>Play next</button>
				{/if}
				<button class="ghost" onclick={() => act(() => rerollRoom(room.number))}>Re-roll</button>
				<button class="ghost" onclick={() => openSwap(room)}>Swap</button>
				{#if room.sticky}
					<button class="ghost" onclick={() => act(() => dropSeries(room.number))}>Drop</button>
				{/if}
			</div>
		</div>
	</article>
{/snippet}

{#if !programme}
	<p class="muted">Loading…</p>
{:else}
	<h3>Auditoriums</h3>
	<div class="grid">
		{#each movieRooms as room (room.number)}{@render roomCard(room)}{/each}
	</div>
	<h3>Series lounges</h3>
	<div class="grid">
		{#each seriesRooms as room (room.number)}{@render roomCard(room)}{/each}
	</div>
{/if}

{#if swapping}
	<div class="overlay" role="presentation" onclick={() => (swapping = null)}>
		<div class="dialog" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.key === 'Escape' && (swapping = null)}>
			<h3>Swap {swapping.name}</h3>
			<!-- svelte-ignore a11y_autofocus -->
			<input placeholder="Search {swapping.kind === 'movie' ? 'movies' : 'series'}…" bind:value={query} oninput={onSearch} autofocus />
			<ul>
				{#each results as item (item.id)}
					<li>
						<button class="pick" onclick={() => swap(item)}>
							<img src={imageUrl(item.id, 'Primary', item.poster_tag, 80)} alt="" />
							<span>{item.name}{item.year ? ` (${item.year})` : ''}{item.played ? ' · watched' : ''}</span>
						</button>
					</li>
				{/each}
			</ul>
			<button class="ghost" onclick={() => (swapping = null)}>Cancel</button>
		</div>
	</div>
{/if}

<style>
	h3 {
		font-size: 0.95rem;
		color: var(--muted);
		font-weight: 500;
		margin: 1.25rem 0 0.6rem;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(21rem, 1fr));
		gap: 0.75rem;
	}
	.room {
		display: flex;
		gap: 0.8rem;
		background: var(--panel);
		border: 1px solid var(--line);
		border-radius: 0.4rem;
		padding: 0.6rem;
	}
	.room.closed {
		opacity: 0.6;
	}
	.room img,
	.poster-placeholder {
		width: 4.5rem;
		aspect-ratio: 2 / 3;
		object-fit: cover;
		border-radius: 0.25rem;
		background: var(--bg);
		flex: none;
	}
	.body {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		min-width: 0;
	}
	.times {
		color: var(--accent);
	}
	.badges {
		display: flex;
		gap: 0.3rem;
	}
	.badge {
		font-size: 0.7rem;
		text-transform: uppercase;
		border: 1px solid #3a3c42;
		border-radius: 999px;
		padding: 0 0.45rem;
		color: var(--muted);
	}
	.badge.sold {
		border-color: #e57373;
		color: #f3a1a1;
	}
	.badge.sticky {
		border-color: var(--accent);
		color: var(--accent);
	}
	.badge.marathon {
		border-color: #4f8fb0;
		color: #8fd0ef;
	}
	.franchise {
		color: #8fd0ef;
	}
	.badges {
		flex-wrap: wrap;
	}
	.actions {
		display: flex;
		gap: 0.4rem;
		flex-wrap: wrap;
		margin-top: auto;
		padding-top: 0.3rem;
	}
	.actions button {
		padding: 0.25rem 0.6rem;
		font-size: 0.85rem;
	}
	.overlay {
		position: fixed;
		inset: 0;
		background: rgb(0 0 0 / 0.6);
		display: grid;
		place-items: start center;
		padding-top: 10vh;
		z-index: 10;
	}
	.dialog {
		background: var(--panel);
		border: 1px solid var(--line);
		border-radius: 0.5rem;
		padding: 1rem 1.25rem;
		width: min(32rem, calc(100vw - 2rem));
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}
	.dialog h3 {
		margin: 0;
		color: var(--text);
	}
	.dialog ul {
		list-style: none;
		padding: 0;
		margin: 0;
		max-height: 50vh;
		overflow-y: auto;
	}
	.pick {
		all: unset;
		display: flex;
		align-items: center;
		gap: 0.6rem;
		width: 100%;
		padding: 0.3rem;
		border-radius: 0.3rem;
		cursor: pointer;
		box-sizing: border-box;
	}
	.pick:hover,
	.pick:focus-visible {
		background: var(--bg);
	}
	.pick img {
		width: 2.2rem;
		aspect-ratio: 2 / 3;
		object-fit: cover;
		border-radius: 0.2rem;
	}
</style>
