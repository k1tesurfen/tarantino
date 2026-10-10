<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/admin/Card.svelte';
	import {
		getLibrarySample,
		getSessions,
		getSettings,
		getShows,
		getStatus,
		imageUrl,
		searchLibrary,
		startShow,
		subscribe,
		dropSeries,
		finishPairing,
		getProgramme,
		playRoom,
		rerollRoom,
		startPairing,
		triggerLibrarySync,
		updateSettings,
		type AppSettings,
		type JellyfinSession,
		type Programme,
		type SampleItem,
		type Show,
		type Status
	} from '$lib/api';

	let status = $state<Status | null>(null);
	let programme = $state<Programme | null>(null);
	let programmeError = $state<string | null>(null);
	let settings = $state<AppSettings | null>(null);
	let sessions = $state<JellyfinSession[]>([]);
	let shows = $state<Show[]>([]);
	let sample = $state<SampleItem[]>([]);
	let error = $state<string | null>(null);

	let addressInput = $state('');
	let pairingCode = $state('');
	let pairingError = $state<string | null>(null);
	let query = $state('');
	let results = $state<SampleItem[]>([]);

	const jellyfin = $derived(status?.jellyfin);
	const projector = $derived(status?.projector);
	const session = $derived(status?.session);
	const syncing = $derived(jellyfin?.sync?.running ?? false);

	async function refresh() {
		try {
			[status, sessions] = await Promise.all([getStatus(), getSessions().catch(() => [])]);
			error = null;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	async function loadSettings() {
		settings = await getSettings();
		addressInput = settings.projector_address ?? '';
	}

	async function saveSettings(changes: Partial<AppSettings>) {
		settings = await updateSettings(changes);
		addressInput = settings.projector_address ?? '';
		await refresh();
	}

	async function loadProgramme() {
		programme = await getProgramme().catch(() => programme);
	}

	async function programmeAction(action: () => Promise<unknown>) {
		programmeError = null;
		try {
			const result = await action();
			if (result && typeof result === 'object' && 'rooms' in result) programme = result as Programme;
			else if (result && typeof result === 'object' && 'steps' in result) upsertShow(result as Show);
		} catch (e) {
			programmeError = (e as Error).message;
		}
	}

	async function pair(step: 'start' | 'finish') {
		pairingError = null;
		try {
			if (step === 'start') await startPairing();
			else {
				await finishPairing(pairingCode);
				pairingCode = '';
			}
		} catch (e) {
			pairingError = (e as Error).message;
		}
		await refresh();
	}

	async function syncNow() {
		await triggerLibrarySync();
		await refresh();
		sample = await getLibrarySample(12);
	}

	let searchTimer: ReturnType<typeof setTimeout>;
	function onSearch() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(async () => {
			results = query.trim() ? await searchLibrary(query) : [];
		}, 250);
	}

	async function play(item: SampleItem) {
		upsertShow(await startShow(item.id));
	}

	function upsertShow(show: Show) {
		const index = shows.findIndex((s) => s.id === show.id);
		if (index >= 0) shows[index] = show;
		else shows = [show, ...shows].slice(0, 10);
	}

	const formatTime = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : 'never');

	onMount(() => {
		refresh();
		loadSettings();
		getShows().then((s) => (shows = s)).catch(() => {});
		getLibrarySample(12).then((s) => (sample = s)).catch(() => {});
		loadProgramme();
		const unsubscribe = subscribe({
			programme: loadProgramme,
			show: (show) => {
				upsertShow(show);
				if (show.state !== 'running') refresh();
			}
		});
		const timer = setInterval(refresh, 10_000);
		return () => {
			clearInterval(timer);
			unsubscribe();
		};
	});
</script>

<svelte:head><title>Admin · tarantino</title></svelte:head>

<div class="admin">
	<header>
		<h1>tarantino <span>admin</span></h1>
		<a href="/">← Cinema</a>
	</header>

	{#if error}<p class="banner">Backend unreachable: {error}</p>{/if}

	<section class="cards">
		<Card title="Jellyfin" state={jellyfin?.state} message={jellyfin?.message}>
			{#if jellyfin}
				<dl>
					{#if jellyfin.version}<dt>Server</dt><dd>{jellyfin.server_name} · {jellyfin.version}</dd>{/if}
					{#if jellyfin.user}<dt>User</dt><dd>{jellyfin.user}</dd>{/if}
					{#if jellyfin.counts}
						<dt>Library</dt><dd>{jellyfin.counts.movie ?? 0} movies · {jellyfin.counts.series ?? 0} series</dd>
					{/if}
					{#if jellyfin.sync}
						<dt>Last sync</dt><dd>{syncing ? 'running…' : formatTime(jellyfin.sync.last_sync_at)}</dd>
					{/if}
				</dl>
				{#if jellyfin.state !== 'unconfigured'}
					<button onclick={syncNow} disabled={syncing}>{syncing ? 'Syncing…' : 'Sync library now'}</button>
				{/if}
			{/if}
		</Card>

		<Card title="Projector" state={projector?.state} message={projector?.message}>
			{#if projector?.address}
				<dl>
					<dt>Address</dt><dd>{projector.address}</dd>
					<dt>Power</dt><dd>{projector.power ?? '–'}</dd>
					<dt>Remote</dt><dd>{projector.remote ?? '–'}</dd>
					<dt>ADB</dt><dd>{projector.adb ?? '–'}</dd>
					<dt>Foreground</dt><dd class="mono">{projector.foreground ?? '–'}</dd>
				</dl>
				{#if projector.remote === 'pairing'}
					<form
						class="inline"
						onsubmit={(e) => {
							e.preventDefault();
							pair('finish');
						}}
					>
						<input placeholder="Code shown on the projector" bind:value={pairingCode} maxlength="6" />
						<button type="submit" disabled={pairingCode.trim().length < 6}>Pair</button>
					</form>
				{:else if projector.remote !== 'connected'}
					<button class="ghost spaced" onclick={() => pair('start')}>Pair Android TV remote</button>
				{/if}
				{#if pairingError}<p class="error">{pairingError}</p>{/if}
			{/if}
			<form
				class="inline"
				onsubmit={(e) => {
					e.preventDefault();
					saveSettings({ projector_address: addressInput });
				}}
			>
				<input placeholder="Projector IP or hostname" bind:value={addressInput} />
				<button type="submit">Save</button>
			</form>
		</Card>

		<Card title="Projector session" state={session?.state} message={session?.message}>
			{#if session?.device_name}
				<dl>
					<dt>Device</dt><dd>{session.device_name}</dd>
					<dt>Now playing</dt><dd>{session.now_playing ?? 'nothing'}{session.paused ? ' (paused)' : ''}</dd>
				</dl>
			{/if}
		</Card>
	</section>

	<section>
		<div class="section-head">
			<h2>Today's programme {programme ? `· ${new Date(programme.date).toLocaleDateString()}` : ''}</h2>
			<button class="ghost" onclick={() => programmeAction(() => rerollRoom())}>Re-roll whole day</button>
		</div>
		{#if programmeError}<p class="error">{programmeError}</p>{/if}
		{#if !programme}
			<p class="muted">Loading…</p>
		{:else}
			<div class="programme">
				{#each programme.rooms as room (room.number)}
					<article class="room" class:closed={!room.item}>
						{#if room.item}
							<img src={imageUrl(room.item.id, 'Primary', room.item.poster_tag, 160)} alt="" loading="lazy" />
						{:else}
							<div class="poster-placeholder"></div>
						{/if}
						<div class="room-body">
							<small class="muted">{room.number} · {room.name}</small>
							<strong>{room.item ? room.item.name : 'Closed today'}</strong>
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
								{#if room.sticky}<span class="badge sticky">sticky</span>{/if}
								{#if room.source === 'override'}<span class="badge">override</span>{/if}
							</div>
							<div class="room-actions">
								{#if room.item}
									<button onclick={() => programmeAction(() => playRoom(room.number))}>Play</button>
								{/if}
								<button class="ghost" onclick={() => programmeAction(() => rerollRoom(room.number))}>Re-roll</button>
								{#if room.sticky}
									<button class="ghost" onclick={() => programmeAction(() => dropSeries(room.number))}>Drop</button>
								{/if}
							</div>
						</div>
					</article>
				{/each}
			</div>
		{/if}
	</section>

	<section>
		<h2>Jellyfin sessions</h2>
		<p class="muted">Open the Jellyfin app on the projector, then mark its session as the projector.</p>
		{#if sessions.length === 0}
			<p class="muted">No active sessions.</p>
		{:else}
			<table>
				<thead>
					<tr><th>Device</th><th>Client</th><th>Address</th><th>Last activity</th><th>Remote</th><th></th></tr>
				</thead>
				<tbody>
					{#each sessions as s (s.device_id)}
						<tr class:selected={s.selected}>
							<td>{s.device_name}{s.now_playing ? ` · ▶ ${s.now_playing}` : ''}</td>
							<td>{s.client} {s.version}</td>
							<td class="mono">{s.host ?? '–'}</td>
							<td>{formatTime(s.last_activity)}</td>
							<td>{s.remote_control ? 'yes' : 'no'}</td>
							<td class="actions">
								{#if s.selected}
									<span class="tag">projector</span>
								{:else if s.remote_control}
									<button class="ghost" onclick={() => saveSettings({ projector_device_id: s.device_id })}>
										This is the projector
									</button>
								{/if}
								{#if s.host && s.host !== settings?.projector_address}
									<button class="ghost" onclick={() => saveSettings({ projector_address: s.host })}>
										Use address
									</button>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</section>

	<section class="two-col">
		<div>
			<h2>Test play</h2>
			<input class="search" placeholder="Search movies and series…" bind:value={query} oninput={onSearch} />
			<ul class="results">
				{#each results as item (item.id)}
					<li>
						<img src={imageUrl(item.id, 'Primary', item.poster_tag, 80)} alt="" loading="lazy" />
						<span>
							{item.name}{item.year ? ` (${item.year})` : ''}
							<small>{item.type}{item.played ? ' · watched' : ''}</small>
						</span>
						<button onclick={() => play(item)}>Play</button>
					</li>
				{/each}
			</ul>
		</div>

		<div>
			<h2>Recent shows</h2>
			{#if shows.length === 0}<p class="muted">No shows yet.</p>{/if}
			{#each shows as show (show.id)}
				<article class="show {show.state}">
					<div class="show-head">
						<strong>{show.item_name}</strong>
						<span class="state">{show.state}</span>
					</div>
					<small class="muted">#{show.id} · {show.trigger} · {formatTime(show.created_at)}</small>
					<ol>
						{#each show.steps as step}
							<li class={step.status}>
								<span class="step">{step.step}</span>
								<span>{step.message ?? (step.status === 'running' ? '…' : '')}</span>
							</li>
						{/each}
					</ol>
					{#if show.error}<p class="error">{show.error}</p>{/if}
				</article>
			{/each}
		</div>
	</section>

	{#if sample.length}
		<section>
			<div class="section-head">
				<h2>Library sample</h2>
				<button class="ghost" onclick={async () => (sample = await getLibrarySample(12))}>Shuffle</button>
			</div>
			<div class="posters">
				{#each sample as item (item.id)}
					<figure>
						<img src={imageUrl(item.id, 'Primary', item.poster_tag, 240)} alt={item.name} loading="lazy" />
						<figcaption>{item.name}{item.year ? ` (${item.year})` : ''}</figcaption>
					</figure>
				{/each}
			</div>
		</section>
	{/if}
</div>

<style>
	:global(body) {
		--bg: #121316;
		--panel: #1b1c20;
		--line: #2a2c31;
		--text: #e9e7e2;
		--muted: #8a8790;
		--accent: #e8c46a;
		margin: 0;
		background: var(--bg);
		color: var(--text);
		font-family: system-ui, sans-serif;
	}
	.admin {
		max-width: 76rem;
		margin: 0 auto;
		padding: 1.5rem 1rem 4rem;
	}
	header {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		border-bottom: 1px solid var(--line);
		margin-bottom: 1.5rem;
	}
	h1 span {
		color: var(--muted);
		font-weight: 400;
	}
	h2 {
		font-size: 1.1rem;
		margin: 2rem 0 0.5rem;
	}
	a {
		color: var(--accent);
	}
	section {
		margin-bottom: 1rem;
	}
	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(20rem, 1fr));
		gap: 1rem;
	}
	.two-col {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(22rem, 1fr));
		gap: 2rem;
	}
	dl {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.3rem 1rem;
		font-size: 0.9rem;
	}
	dt {
		color: var(--muted);
	}
	dd {
		margin: 0;
		overflow-wrap: anywhere;
	}
	.mono {
		font-family: ui-monospace, monospace;
		font-size: 0.85em;
	}
	button {
		background: var(--accent);
		color: var(--bg);
		border: 0;
		border-radius: 0.35rem;
		padding: 0.45rem 0.9rem;
		font-weight: 600;
		cursor: pointer;
		white-space: nowrap;
	}
	button:disabled {
		opacity: 0.6;
		cursor: default;
	}
	button.ghost {
		background: transparent;
		color: var(--accent);
		border: 1px solid #3a3c42;
		padding: 0.3rem 0.6rem;
		font-weight: 500;
	}
	input {
		background: var(--bg);
		color: var(--text);
		border: 1px solid #3a3c42;
		border-radius: 0.35rem;
		padding: 0.45rem 0.6rem;
		font: inherit;
		min-width: 0;
	}
	form.inline {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}
	form.inline input {
		flex: 1;
	}
	.muted {
		color: var(--muted);
		font-size: 0.9rem;
	}
	.banner {
		background: #5c1f1f;
		padding: 0.6rem 1rem;
		border-radius: 0.35rem;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.9rem;
		display: block;
		overflow-x: auto;
	}
	th,
	td {
		text-align: left;
		padding: 0.45rem 0.6rem;
		border-bottom: 1px solid var(--line);
	}
	th {
		color: var(--muted);
		font-weight: 500;
	}
	tr.selected td {
		background: #23241f;
	}
	td.actions {
		display: flex;
		gap: 0.4rem;
	}
	.tag {
		color: var(--accent);
		font-size: 0.8rem;
		text-transform: uppercase;
	}
	.search {
		width: 100%;
		box-sizing: border-box;
	}
	.results {
		list-style: none;
		padding: 0;
	}
	.results li {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.35rem 0;
		border-bottom: 1px solid var(--line);
	}
	.results img {
		width: 2.5rem;
		aspect-ratio: 2 / 3;
		object-fit: cover;
		border-radius: 0.2rem;
		background: var(--panel);
	}
	.results span {
		flex: 1;
	}
	.results small {
		display: block;
		color: var(--muted);
	}
	.show {
		background: var(--panel);
		border: 1px solid var(--line);
		border-left: 3px solid var(--muted);
		border-radius: 0.35rem;
		padding: 0.6rem 0.9rem;
		margin-bottom: 0.6rem;
	}
	.show.playing {
		border-left-color: #6fcf8a;
	}
	.show.failed {
		border-left-color: #e57373;
	}
	.show.running {
		border-left-color: var(--accent);
	}
	.show-head {
		display: flex;
		justify-content: space-between;
	}
	.state {
		font-size: 0.8rem;
		text-transform: uppercase;
		color: var(--muted);
	}
	.show ol {
		list-style: none;
		padding: 0;
		margin: 0.4rem 0 0;
		font-size: 0.85rem;
	}
	.show li {
		display: flex;
		gap: 0.6rem;
		padding: 0.1rem 0;
	}
	.show li::before {
		content: '○';
		color: var(--muted);
	}
	.show li.done::before {
		content: '✓';
		color: #6fcf8a;
	}
	.show li.failed::before {
		content: '✕';
		color: #e57373;
	}
	.show li.running::before {
		content: '◐';
		color: var(--accent);
	}
	.step {
		width: 5.5rem;
		color: var(--muted);
	}
	.error {
		color: #f3a1a1;
		font-size: 0.85rem;
		margin: 0.4rem 0 0;
	}
	.programme {
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
	.room-body {
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
	.room-actions {
		display: flex;
		gap: 0.4rem;
		margin-top: auto;
		padding-top: 0.3rem;
	}
	.room-actions button {
		padding: 0.25rem 0.6rem;
		font-size: 0.85rem;
	}
	.spaced {
		margin-top: 0.5rem;
	}
	.section-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	.posters {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
		gap: 1rem;
	}
	figure {
		margin: 0;
	}
	figure img {
		width: 100%;
		aspect-ratio: 2 / 3;
		object-fit: cover;
		border-radius: 0.35rem;
		background: var(--panel);
	}
	figcaption {
		font-size: 0.8rem;
		color: #b5b2ab;
		margin-top: 0.3rem;
	}
</style>
