<script lang="ts">
	import { onMount } from 'svelte';
	import {
		getLibrarySample,
		getStatus,
		imageUrl,
		triggerLibrarySync,
		type SampleItem,
		type Status
	} from '$lib/api';

	let status = $state<Status | null>(null);
	let sample = $state<SampleItem[]>([]);
	let error = $state<string | null>(null);

	const jellyfin = $derived(status?.jellyfin);
	const syncing = $derived(jellyfin?.sync?.running ?? false);

	async function refresh() {
		try {
			status = await getStatus();
			error = null;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	async function loadSample() {
		sample = await getLibrarySample(12).catch(() => []);
	}

	async function syncNow() {
		await triggerLibrarySync();
		await refresh();
		await loadSample();
	}

	function formatTime(iso: string | null | undefined) {
		return iso ? new Date(iso).toLocaleString() : 'never';
	}

	onMount(() => {
		refresh();
		loadSample();
		const timer = setInterval(refresh, 10_000);
		return () => clearInterval(timer);
	});
</script>

<svelte:head><title>Admin · tarantino</title></svelte:head>

<div class="admin">
	<header>
		<h1>tarantino <span>admin</span></h1>
		<a href="/">← Cinema</a>
	</header>

	{#if error}
		<p class="banner error">Backend unreachable: {error}</p>
	{/if}

	<section class="cards">
		<article class="card">
			<div class="card-head">
				<h2>Jellyfin</h2>
				{#if jellyfin}
					<span class="pill {jellyfin.state}">{jellyfin.state}</span>
				{/if}
			</div>
			{#if !jellyfin}
				<p class="muted">Loading…</p>
			{:else}
				{#if jellyfin.message}
					<p class="message">{jellyfin.message}</p>
				{/if}
				<dl>
					{#if jellyfin.version}
						<dt>Server</dt>
						<dd>{jellyfin.server_name} · {jellyfin.version}</dd>
					{/if}
					{#if jellyfin.user}
						<dt>User</dt>
						<dd>{jellyfin.user}</dd>
					{/if}
					{#if jellyfin.counts}
						<dt>Library</dt>
						<dd>{jellyfin.counts.movie ?? 0} movies · {jellyfin.counts.series ?? 0} series</dd>
					{/if}
					{#if jellyfin.sync}
						<dt>Last sync</dt>
						<dd>{syncing ? 'running…' : formatTime(jellyfin.sync.last_sync_at)}</dd>
					{/if}
				</dl>
				{#if jellyfin.state !== 'unconfigured'}
					<button onclick={syncNow} disabled={syncing}>{syncing ? 'Syncing…' : 'Sync library now'}</button>
				{/if}
			{/if}
		</article>
	</section>

	{#if sample.length}
		<section>
			<div class="section-head">
				<h2>Library sample</h2>
				<button class="ghost" onclick={loadSample}>Shuffle</button>
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
		margin: 0;
		background: #121316;
		color: #e9e7e2;
		font-family: system-ui, sans-serif;
	}
	.admin {
		max-width: 72rem;
		margin: 0 auto;
		padding: 1.5rem 1rem 4rem;
	}
	header {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		border-bottom: 1px solid #2a2c31;
		margin-bottom: 1.5rem;
	}
	h1 span {
		color: #8a8790;
		font-weight: 400;
	}
	a {
		color: #e8c46a;
	}
	.cards {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
		gap: 1rem;
		margin-bottom: 2rem;
	}
	.card {
		background: #1b1c20;
		border: 1px solid #2a2c31;
		border-radius: 0.5rem;
		padding: 1rem 1.25rem;
	}
	.card-head,
	.section-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	h2 {
		font-size: 1.1rem;
		margin: 0.25rem 0;
	}
	.pill {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		background: #2a2c31;
	}
	.pill.ok {
		background: #1e4d2b;
		color: #9be3ae;
	}
	.pill.warning {
		background: #5a4614;
		color: #f3d27a;
	}
	.pill.error {
		background: #5c1f1f;
		color: #f3a1a1;
	}
	.message {
		color: #f3d27a;
		font-size: 0.9rem;
	}
	dl {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.3rem 1rem;
		font-size: 0.9rem;
	}
	dt {
		color: #8a8790;
	}
	dd {
		margin: 0;
	}
	button {
		background: #e8c46a;
		color: #121316;
		border: 0;
		border-radius: 0.35rem;
		padding: 0.45rem 0.9rem;
		font-weight: 600;
		cursor: pointer;
	}
	button:disabled {
		opacity: 0.6;
		cursor: default;
	}
	button.ghost {
		background: transparent;
		color: #e8c46a;
		border: 1px solid #3a3c42;
	}
	.posters {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
		gap: 1rem;
		margin-top: 1rem;
	}
	figure {
		margin: 0;
	}
	figure img {
		width: 100%;
		aspect-ratio: 2 / 3;
		object-fit: cover;
		border-radius: 0.35rem;
		background: #1b1c20;
	}
	figcaption {
		font-size: 0.8rem;
		color: #b5b2ab;
		margin-top: 0.3rem;
	}
	.muted {
		color: #8a8790;
	}
	.banner.error {
		background: #5c1f1f;
		padding: 0.6rem 1rem;
		border-radius: 0.35rem;
	}
</style>
