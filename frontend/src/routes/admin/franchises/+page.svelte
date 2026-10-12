<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getFranchises,
		imageUrl,
		resetFranchise,
		setNextPart,
		subscribe,
		updateFranchise,
		type Franchise,
		type FranchiseChanges,
		type FranchiseState
	} from '$lib/api';

	let franchises = $state<Franchise[] | null>(null);
	let error = $state<string | null>(null);
	let query = $state('');
	let filter = $state<FranchiseState | 'all'>('all');
	let open = $state<string | null>(null);
	let names = $state<Record<string, string>>({});

	const counts = $derived(
		(franchises ?? []).reduce(
			(acc, f) => ({ ...acc, [f.state]: (acc[f.state] ?? 0) + 1 }),
			{} as Partial<Record<FranchiseState, number>>
		)
	);
	const shown = $derived(
		(franchises ?? []).filter(
			(f) =>
				(filter === 'all' || f.state === filter) &&
				(!query.trim() ||
					f.name.toLowerCase().includes(query.trim().toLowerCase()) ||
					f.parts.some((p) => p.name.toLowerCase().includes(query.trim().toLowerCase())))
		)
	);

	const FILTERS: { value: FranchiseState | 'all'; label: string }[] = [
		{ value: 'all', label: 'All' },
		{ value: 'started', label: 'Running' },
		{ value: 'resting', label: 'Resting' },
		{ value: 'fresh', label: 'Not started' },
		{ value: 'off', label: 'Any order' }
	];

	async function load() {
		try {
			franchises = await getFranchises();
			error = null;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	async function apply(id: string, action: () => Promise<Franchise>) {
		error = null;
		try {
			const updated = await action();
			franchises = (franchises ?? []).map((f) => (f.collection_id === id ? updated : f));
			names[id] = updated.name;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	const update = (f: Franchise, changes: FranchiseChanges) =>
		apply(f.collection_id, () => updateFranchise(f.collection_id, changes));

	function move(f: Franchise, index: number, delta: number) {
		const keys = f.parts.map((p) => p.key);
		const [key] = keys.splice(index, 1);
		keys.splice(index + delta, 0, key);
		update(f, { order: keys });
	}

	function exclude(f: Franchise, key: string, excluded: boolean) {
		const keys = f.excluded.map((p) => p.key).filter((k) => k !== key);
		update(f, { excluded: excluded ? [...keys, key] : keys });
	}

	function rename(f: Franchise) {
		const name = (names[f.collection_id] ?? f.name).trim();
		if (name !== f.name) update(f, { name });
	}

	function toggle(f: Franchise) {
		open = open === f.collection_id ? null : f.collection_id;
		names[f.collection_id] = f.name;
	}

	function stateLabel(f: Franchise): string {
		if (f.state === 'started') return `Part ${f.progress + 1} of ${f.parts.length} next`;
		if (f.state === 'resting')
			return `Resting until ${f.resting_until ? new Date(f.resting_until).toLocaleDateString() : '…'}`;
		if (f.state === 'off') return f.any_order ? 'Any order' : 'Too few parts';
		return 'Not started';
	}

	const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : '—');

	onMount(() => {
		load();
		return subscribe({ programme: load });
	});
</script>

<svelte:head><title>Franchises · tarantino</title></svelte:head>

<p class="muted intro">
	Movies of a TMDb collection play in order: only the next part can be programmed. Starting a part in a room offers the
	next one there for the rest of the cinema day, and a franchise you are in the middle of comes back on later days at
	the daily chance set in <a href="/admin/settings">Settings</a>. Progress is tarantino's own, so a franchise can be
	watched again and again.
</p>

<div class="toolbar">
	<div class="filters" role="tablist">
		{#each FILTERS as f}
			<button
				role="tab"
				aria-selected={filter === f.value}
				class="ghost"
				class:active={filter === f.value}
				onclick={() => (filter = f.value)}
			>
				{f.label}
				{#if f.value === 'all'}<span class="count">{franchises?.length ?? 0}</span>
				{:else if counts[f.value]}<span class="count">{counts[f.value]}</span>{/if}
			</button>
		{/each}
	</div>
	<input type="search" placeholder="Search franchises or titles…" bind:value={query} />
</div>

{#if error}<p class="error">{error}</p>{/if}

{#if !franchises}
	<p class="muted">Loading…</p>
{:else if franchises.length === 0}
	<p class="muted">
		No franchises yet. They appear after the library sync when two or more movies of a TMDb collection are in Jellyfin.
	</p>
{:else}
	<ul class="list">
		{#each shown as f (f.collection_id)}
			<li class="franchise {f.state}" class:open={open === f.collection_id}>
				<button class="head" onclick={() => toggle(f)} aria-expanded={open === f.collection_id}>
					<span class="title">
						<strong>{f.name}</strong>
						<small class="muted">{f.parts.length} parts{f.excluded.length ? ` · ${f.excluded.length} excluded` : ''}</small>
					</span>
					<span class="track" aria-hidden="true">
						{#each f.parts as part}
							<i class:started={part.started} class:next={part.next} class:today={part.today !== null}></i>
						{/each}
					</span>
					<span class="pill {f.state}">{stateLabel(f)}</span>
				</button>

				{#if open === f.collection_id}
					<div class="editor">
						<div class="settings">
							<label>
								Name
								<span class="with-button">
									<input
										bind:value={names[f.collection_id]}
										placeholder={f.default_name}
										onkeydown={(e) => e.key === 'Enter' && rename(f)}
									/>
									<button class="ghost" onclick={() => rename(f)}>Rename</button>
								</span>
								{#if f.name !== f.default_name}
									<small class="muted">Jellyfin calls it “{f.default_name}”. Clear the field to go back.</small>
								{/if}
							</label>
							<label class="check">
								<input type="checkbox" checked={f.any_order} onchange={(e) => update(f, { any_order: e.currentTarget.checked })} />
								Any order (the parts behave like standalone movies)
							</label>
							<div class="meta muted">
								{#if f.started_at}Started {formatDate(f.started_at)} · last part {formatDate(f.last_advanced_at)}{/if}
							</div>
							<div class="buttons">
								{#if f.custom_order}
									<button class="ghost" onclick={() => update(f, { order: [] })}>Order by premiere date</button>
								{/if}
								{#if f.state === 'started' || f.state === 'resting'}
									<button class="ghost" onclick={() => apply(f.collection_id, () => resetFranchise(f.collection_id))}>
										Start over at part 1
									</button>
								{/if}
							</div>
						</div>

						<ol class="parts">
							{#each f.parts as part, i (part.key)}
								<li class:started={part.started} class:next={part.next}>
									<span class="index">{i + 1}</span>
									<img src={imageUrl(part.item_id, 'Primary', part.poster_tag, 90)} alt="" loading="lazy" />
									<span class="part-info">
										<strong>{part.name}</strong>
										<small class="muted">
											{part.premiere_date ? new Date(part.premiere_date).getFullYear() : (part.year ?? '')}
											{part.copies > 1 ? ` · ${part.copies} copies` : ''}
											{part.played ? ' · watched in Jellyfin' : ''}
										</small>
										<span class="tags">
											{#if part.next}<span class="tag next">next</span>{/if}
											{#if part.started}<span class="tag started">started</span>{/if}
											{#if part.today !== null}<span class="tag today">today in room {part.today}</span>{/if}
										</span>
									</span>
									<span class="part-actions">
										<button class="ghost icon" disabled={i === 0} onclick={() => move(f, i, -1)} aria-label="Move up">↑</button>
										<button class="ghost icon" disabled={i === f.parts.length - 1} onclick={() => move(f, i, 1)} aria-label="Move down"
											>↓</button
										>
										{#if f.ordered && !part.next}
											<button class="ghost" onclick={() => apply(f.collection_id, () => setNextPart(f.collection_id, part.key))}>
												Make next
											</button>
										{/if}
										<button class="ghost" onclick={() => exclude(f, part.key, true)} title="Treat as a standalone movie (e.g. a spin-off)">
											Exclude
										</button>
									</span>
								</li>
							{/each}
						</ol>

						{#if f.excluded.length}
							<h4>Excluded <span class="muted">· programmed like standalone movies</span></h4>
							<ul class="parts excluded">
								{#each f.excluded as part (part.key)}
									<li>
										<span class="index">–</span>
										<img src={imageUrl(part.item_id, 'Primary', part.poster_tag, 90)} alt="" loading="lazy" />
										<span class="part-info">
											<strong>{part.name}</strong>
											<small class="muted">{part.year ?? ''}</small>
										</span>
										<span class="part-actions">
											<button class="ghost" onclick={() => exclude(f, part.key, false)}>Include</button>
										</span>
									</li>
								{/each}
							</ul>
						{/if}
					</div>
				{/if}
			</li>
		{:else}
			<li class="muted empty">Nothing matches.</li>
		{/each}
	</ul>
{/if}

<style>
	.intro {
		max-width: 52rem;
	}
	.toolbar {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: center;
		justify-content: space-between;
		margin: 1rem 0;
	}
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}
	.filters .active {
		border-color: var(--accent);
		color: var(--accent);
	}
	.count {
		margin-left: 0.3rem;
		font-size: 0.75rem;
		color: var(--muted);
	}
	.toolbar input {
		min-width: min(18rem, 100%);
	}
	.list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	.franchise {
		background: var(--panel);
		border: 1px solid var(--line);
		border-radius: 0.5rem;
	}
	.franchise.started {
		border-color: #4f8fb0;
	}
	.franchise .head {
		width: 100%;
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto auto;
		gap: 1rem;
		align-items: center;
		padding: 0.6rem 0.9rem;
		background: transparent;
		color: var(--text);
		font-weight: 400;
		text-align: left;
		border-radius: 0.5rem;
	}
	.franchise .head:hover {
		background: #212329;
	}
	.title {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.title strong {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.track {
		display: flex;
		gap: 0.2rem;
	}
	.track i {
		width: 0.7rem;
		height: 0.7rem;
		border-radius: 50%;
		border: 1px solid #4a4c53;
	}
	.track i.started {
		background: #4f8fb0;
		border-color: #4f8fb0;
	}
	.track i.next {
		border: 2px solid #8fd0ef;
	}
	.track i.today {
		box-shadow: 0 0 0 2px var(--accent);
	}
	.pill {
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		padding: 0.15rem 0.55rem;
		border-radius: 999px;
		background: var(--line);
		white-space: nowrap;
	}
	.pill.started {
		background: #1d3a4a;
		color: #8fd0ef;
	}
	.pill.resting {
		background: #3d3212;
		color: #f3d27a;
	}
	.pill.off {
		color: var(--muted);
	}
	.editor {
		border-top: 1px solid var(--line);
		padding: 0.9rem;
		display: grid;
		grid-template-columns: minmax(14rem, 20rem) 1fr;
		gap: 1.25rem;
	}
	.settings {
		display: flex;
		flex-direction: column;
		gap: 0.8rem;
	}
	.settings label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		font-size: 0.9rem;
	}
	.settings label.check {
		flex-direction: row;
		align-items: flex-start;
		gap: 0.5rem;
	}
	.with-button {
		display: flex;
		gap: 0.4rem;
	}
	.with-button input {
		flex: 1;
		min-width: 0;
	}
	.meta {
		font-size: 0.8rem;
	}
	.buttons {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}
	.parts {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.editor h4 {
		grid-column: 2;
		margin: 0.5rem 0 0;
		font-size: 0.9rem;
	}
	.parts.excluded {
		grid-column: 2;
		opacity: 0.75;
	}
	.parts li {
		display: grid;
		grid-template-columns: 1.6rem 2.4rem minmax(0, 1fr) auto;
		gap: 0.6rem;
		align-items: center;
		padding: 0.3rem 0.4rem;
		border-radius: 0.4rem;
		border: 1px solid transparent;
	}
	.parts li.next {
		border-color: #4f8fb0;
		background: #16252e;
	}
	.parts li.started .part-info strong {
		color: var(--muted);
	}
	.index {
		text-align: center;
		font-weight: 700;
		color: var(--muted);
	}
	.parts img {
		width: 2.4rem;
		aspect-ratio: 2 / 3;
		object-fit: cover;
		border-radius: 0.2rem;
		background: var(--bg);
	}
	.part-info {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.part-info strong {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.tags {
		display: flex;
		gap: 0.3rem;
		flex-wrap: wrap;
	}
	.tag {
		font-size: 0.65rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		border: 1px solid #3a3c42;
		border-radius: 999px;
		padding: 0 0.4rem;
		color: var(--muted);
	}
	.tag.next {
		border-color: #4f8fb0;
		color: #8fd0ef;
	}
	.tag.today {
		border-color: var(--accent);
		color: var(--accent);
	}
	.part-actions {
		display: flex;
		gap: 0.3rem;
		flex-wrap: wrap;
		justify-content: flex-end;
	}
	.icon {
		padding-inline: 0.5rem;
	}
	.empty {
		padding: 1rem;
	}
	@media (max-width: 52rem) {
		.editor {
			grid-template-columns: 1fr;
		}
		.editor h4,
		.parts.excluded {
			grid-column: 1;
		}
		.franchise .head {
			grid-template-columns: minmax(0, 1fr) auto;
		}
		.track {
			display: none;
		}
		.parts li {
			grid-template-columns: 1.4rem 2.2rem minmax(0, 1fr);
		}
		.part-actions {
			grid-column: 2 / -1;
			justify-content: flex-start;
		}
	}
</style>
