<script lang="ts">
	import { onMount } from 'svelte';
	import Card from '$lib/admin/Card.svelte';
	import ShowLog from '$lib/admin/ShowLog.svelte';
	import {
		bluetoothCommand,
		finishPairing,
		getSessions,
		getShows,
		getStatus,
		imageUrl,
		searchLibrary,
		startPairing,
		startShow,
		subscribe,
		triggerLibrarySync,
		updateSettings,
		type JellyfinSession,
		type SampleItem,
		type Show,
		type Status
	} from '$lib/api';

	let status = $state<Status | null>(null);
	let sessions = $state<JellyfinSession[]>([]);
	let shows = $state<Show[]>([]);
	let error = $state<string | null>(null);

	let pairingCode = $state('');
	let pairingError = $state<string | null>(null);
	let btBusy = $state(false);
	let btError = $state<string | null>(null);
	let query = $state('');
	let results = $state<SampleItem[]>([]);

	const jellyfin = $derived(status?.jellyfin);
	const projector = $derived(status?.projector);
	const session = $derived(status?.session);
	const media = $derived(status?.media);
	const ha = $derived(status?.home_assistant);
	const syncing = $derived(jellyfin?.sync?.running ?? false);
	const bt = $derived(projector?.bluetooth);

	async function refresh() {
		try {
			[status, sessions] = await Promise.all([getStatus(), getSessions().catch(() => [])]);
			error = null;
		} catch (e) {
			error = (e as Error).message;
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

	async function btCommand(action: 'pair' | 'stop' | 'unpair' | 'wake' | 'key', key?: string) {
		if (action === 'pair' && bt?.paired && !confirm('Forget the current pairing and pair again?')) return;
		if (action === 'unpair' && !confirm('Forget the pairing with the projector?')) return;
		btBusy = true;
		btError = null;
		try {
			await bluetoothCommand(action, key);
		} catch (e) {
			btError = (e as Error).message;
		}
		btBusy = false;
		await refresh();
	}

	// While pairing, follow the pairing window more closely than the regular refresh.
	$effect(() => {
		if (!bt?.pairing) return;
		const timer = setInterval(refresh, 3_000);
		return () => clearInterval(timer);
	});

	async function setProjector(changes: { projector_device_id?: string; projector_address?: string }) {
		await updateSettings(changes);
		await refresh();
	}

	async function syncNow() {
		await triggerLibrarySync();
		await refresh();
	}

	let searchTimer: ReturnType<typeof setTimeout>;
	function onSearch() {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(async () => {
			results = query.trim() ? await searchLibrary(query) : [];
		}, 250);
	}

	function upsertShow(show: Show) {
		const index = shows.findIndex((s) => s.id === show.id);
		if (index >= 0) shows[index] = show;
		else shows = [show, ...shows].slice(0, 10);
	}

	const formatTime = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : 'never');

	onMount(() => {
		refresh();
		getShows().then((s) => (shows = s)).catch(() => {});
		const unsubscribe = subscribe({
			show: (show) => {
				upsertShow(show);
				if (show.state !== 'running') refresh();
			}
		});
		const timer = setInterval(refresh, 15_000);
		return () => {
			clearInterval(timer);
			unsubscribe();
		};
	});
</script>

<svelte:head><title>Dashboard · tarantino</title></svelte:head>

{#if error}<p class="error">Backend unreachable: {error}</p>{/if}

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
				<button class="ghost" onclick={syncNow} disabled={syncing}>
					{syncing ? 'Syncing…' : 'Sync library now'}
				</button>
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
				<button class="ghost" onclick={() => pair('start')}>Pair Android TV remote</button>
			{/if}
			{#if pairingError}<p class="error">{pairingError}</p>{/if}
		{:else}
			<p class="muted">Set the address under <a href="/admin/settings">Settings</a> or pick a session below.</p>
		{/if}
		{#if bt}
			<h3>Bluetooth remote</h3>
			{#if !bt.available}
				<p class="muted">Service not running (tarantino-btremote.service).</p>
			{:else}
				<dl>
					<dt>Paired</dt><dd>{bt.paired ? (bt.name ?? 'yes') : 'no'}</dd>
					{#if bt.paired}<dt>Connected</dt><dd>{bt.connected ? 'yes' : 'no (standby?)'}</dd>{/if}
				</dl>
				{#if bt.pairing}
					<p class="muted">
						Pairing… On the projector: Settings → Remotes &amp; Accessories, forget an old "Tarantino Remote",
						then Add accessory → "Tarantino Remote".
					</p>
					<button class="ghost" onclick={() => btCommand('stop')} disabled={btBusy}>Stop pairing</button>
				{:else}
					<div class="buttons">
						{#if bt.paired}
							<button class="ghost" onclick={() => btCommand('wake')} disabled={btBusy}>Wake</button>
							<button class="ghost" onclick={() => btCommand('key', 'star')} disabled={btBusy || !bt.connected}>
								Shortcut key
							</button>
							<button class="ghost" onclick={() => btCommand('key', 'power')} disabled={btBusy || !bt.connected}>
								Power
							</button>
							<button class="ghost" onclick={() => btCommand('unpair')} disabled={btBusy}>Unpair</button>
						{/if}
						<button class="ghost" onclick={() => btCommand('pair')} disabled={btBusy}>
							{bt.paired ? 'Pair again' : 'Pair'}
						</button>
					</div>
				{/if}
			{/if}
			{#if btError}<p class="error">{btError}</p>{/if}
		{/if}
	</Card>

	<Card title="Projector session" state={session?.state} message={session?.message}>
		{#if session?.device_name}
			<dl>
				<dt>Device</dt><dd>{session.device_name}</dd>
				<dt>Now playing</dt><dd>{session.now_playing ?? 'nothing'}{session.paused ? ' (paused)' : ''}</dd>
			</dl>
		{/if}
	</Card>

	<Card title="Media (NFS)" state={media?.state} message={media?.message}>
		{#if media?.mounts.length}
			<dl>
				{#each media.mounts as mount}
					<dt class="mono">{mount.path}</dt><dd>{mount.ok ? '✓' : '✕'} {mount.message}</dd>
				{/each}
			</dl>
		{/if}
	</Card>

	<Card title="Home Assistant" state={ha?.state} message={ha?.message}>
		{#if ha?.url}<dl><dt>URL</dt><dd>{ha.url}</dd></dl>{/if}
	</Card>
</section>

<section class="two-col">
	<div>
		<h2>Recent shows</h2>
		<ShowLog {shows} />
	</div>
	<div>
		<h2>Test play</h2>
		<input class="search" placeholder="Search movies and series…" bind:value={query} oninput={onSearch} />
		<ul class="results">
			{#each results as item (item.id)}
				<li>
					<img src={imageUrl(item.id, 'Primary', item.poster_tag, 80)} alt="" loading="lazy" />
					<span>
						{item.name}{item.year ? ` (${item.year})` : ''}
						<small class="muted">{item.type}{item.played ? ' · watched' : ''}</small>
					</span>
					<button onclick={async () => upsertShow(await startShow(item.id))}>Play</button>
				</li>
			{/each}
		</ul>
	</div>
</section>

<section>
	<h2>Jellyfin sessions</h2>
	<p class="muted">Open Jellyfin on the projector, then mark its session as the projector.</p>
	{#if sessions.length === 0}
		<p class="muted">No active sessions.</p>
	{:else}
		<div class="table-wrap">
			<table>
				<thead>
					<tr><th>Device</th><th>Client</th><th>Address</th><th>Last activity</th><th></th></tr>
				</thead>
				<tbody>
					{#each sessions as s (s.device_id)}
						<tr class:selected={s.selected}>
							<td>{s.device_name}{s.now_playing ? ` · ▶ ${s.now_playing}` : ''}</td>
							<td>{s.client} {s.version}</td>
							<td class="mono">{s.host ?? '–'}</td>
							<td>{formatTime(s.last_activity)}</td>
							<td class="actions">
								{#if s.selected}
									<span class="tag">projector</span>
								{:else if s.remote_control}
									<button class="ghost" onclick={() => setProjector({ projector_device_id: s.device_id })}>
										This is the projector
									</button>
								{/if}
								{#if s.host && s.host !== projector?.address}
									<button class="ghost" onclick={() => setProjector({ projector_address: s.host! })}>
										Use address
									</button>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</section>

<style>
	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(19rem, 1fr));
		gap: 1rem;
	}
	.two-col {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(22rem, 1fr));
		gap: 2rem;
	}
	h3 {
		margin: 1rem 0 0.4rem;
		font-size: 0.95rem;
	}
	.buttons {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}
	form.inline {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}
	form.inline input {
		flex: 1;
	}
	.search {
		width: 100%;
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
	}
	.table-wrap {
		overflow-x: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.9rem;
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
</style>
