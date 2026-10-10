<script lang="ts">
	import { getHealth } from '$lib/api';
</script>

<svelte:head><title>tarantino</title></svelte:head>

<main>
	<h1>tarantino</h1>
	<p>Tonight's programme is being prepared.</p>
	{#await getHealth()}
		<p class="muted">Connecting…</p>
	{:then health}
		<p class="muted">Server {health.status} · v{health.version}</p>
	{:catch}
		<p class="muted">Server unreachable</p>
	{/await}
	<a href="/admin">Admin</a>
</main>

<style>
	:global(body) {
		margin: 0;
		background: #0d0d0f;
		color: #f2efe9;
		font-family: system-ui, sans-serif;
	}
	main {
		padding: 3rem 1rem;
		max-width: 40rem;
		margin: 0 auto;
	}
	.muted {
		color: #8a8790;
	}
	a {
		color: #e8c46a;
	}
</style>
