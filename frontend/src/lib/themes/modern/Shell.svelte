<script lang="ts">
	import '@fontsource-variable/inter';
	import '@fontsource-variable/oswald';
	import type { Snippet } from 'svelte';
	import { formatCinemaDate } from '$lib/cinema/api';
	import { AVAILABLE_THEMES, cinema } from '$lib/cinema/state.svelte';
	import ShowOverlay from './ShowOverlay.svelte';

	let { children }: { children: Snippet } = $props();

	const programme = $derived(cinema.programme);
	const nowPlaying = $derived(cinema.now?.now_playing);
</script>

<svelte:head><title>{cinema.name || 'Cinema'}</title></svelte:head>

<div class="aplex">
	<header>
		<a class="logo" href="/" aria-label="{cinema.name} home">
			<span class="mark" aria-hidden="true"></span>
			<span class="wordmark">{cinema.name}</span>
		</a>
		<nav>
			<a href="/#today">Today</a>
			<a href="/#lounge">Series lounge</a>
		</nav>
		<div class="right">
			{#if programme}<span class="date">{formatCinemaDate(programme.date)}</span>{/if}
			{#if AVAILABLE_THEMES.length > 1}
				<select
					aria-label="Cinema"
					value={cinema.theme}
					onchange={(e) => cinema.setTheme((e.currentTarget as HTMLSelectElement).value as typeof cinema.theme)}
				>
					{#each AVAILABLE_THEMES as theme}
						<option value={theme}>{programme?.cinema.names[theme] ?? theme}</option>
					{/each}
				</select>
			{/if}
		</div>
	</header>

	<main>
		{#if cinema.error && !programme}
			<p class="offline">The box office is closed right now ({cinema.error}).</p>
		{:else}
			{@render children()}
		{/if}
	</main>

	<footer>
		<span>{cinema.name} · a tarantino cinema</span>
		<span>Members only · Popcorn self-service · <a href="/admin">Staff</a></span>
	</footer>

	{#if nowPlaying}
		<div class="now" role="status">
			<span class="pulse" aria-hidden="true"></span>
			Now showing: <strong>{nowPlaying}</strong>{cinema.now?.paused ? ' (intermission)' : ''}
		</div>
	{/if}

	<ShowOverlay />
</div>

<style>
	.aplex {
		--bg: #0b0b10;
		--surface: #14141c;
		--surface-2: #1d1d29;
		--line: #2a2a38;
		--text: #f4f4f7;
		--muted: #9898aa;
		--accent: #ff3b5c;
		--gold: #ffb547;
		--display: 'Oswald Variable', 'Arial Narrow', sans-serif;
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		background: var(--bg);
		color: var(--text);
		font-family: 'Inter Variable', system-ui, sans-serif;
		-webkit-font-smoothing: antialiased;
	}
	/* :where() keeps this at zero specificity, so components can colour their own links. */
	:where(.aplex) :global(a) {
		color: inherit;
	}
	header {
		position: sticky;
		top: 0;
		z-index: 20;
		display: flex;
		align-items: center;
		gap: 2rem;
		padding: 0.9rem clamp(1rem, 4vw, 3rem);
		background: linear-gradient(to bottom, rgb(11 11 16 / 0.95), rgb(11 11 16 / 0.75));
		backdrop-filter: blur(12px);
		border-bottom: 1px solid rgb(255 255 255 / 0.05);
	}
	.logo {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		text-decoration: none;
	}
	.mark {
		width: 0;
		height: 0;
		border-left: 0.9rem solid var(--accent);
		border-top: 0.55rem solid transparent;
		border-bottom: 0.55rem solid transparent;
	}
	.wordmark {
		font-family: var(--display);
		font-weight: 700;
		font-size: 1.6rem;
		letter-spacing: 0.02em;
	}
	nav {
		display: flex;
		gap: 1.5rem;
	}
	nav a {
		text-decoration: none;
		color: var(--muted);
		font-weight: 500;
		font-size: 0.95rem;
	}
	nav a:hover {
		color: var(--text);
	}
	.right {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 1rem;
	}
	.date {
		color: var(--muted);
		font-size: 0.9rem;
	}
	select {
		background: var(--surface);
		color: var(--text);
		border: 1px solid var(--line);
		border-radius: 999px;
		padding: 0.35rem 0.8rem;
		font: inherit;
		font-size: 0.85rem;
	}
	main {
		flex: 1;
	}
	.offline {
		padding: 6rem 1rem;
		text-align: center;
		color: var(--muted);
	}
	footer {
		display: flex;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 0.5rem;
		padding: 2rem clamp(1rem, 4vw, 3rem) 4.5rem;
		color: var(--muted);
		font-size: 0.8rem;
		border-top: 1px solid var(--line);
	}
	.now {
		position: fixed;
		left: 50%;
		bottom: 1rem;
		transform: translateX(-50%);
		z-index: 30;
		display: flex;
		align-items: center;
		gap: 0.6rem;
		max-width: calc(100vw - 2rem);
		padding: 0.55rem 1.1rem;
		border-radius: 999px;
		background: rgb(20 20 28 / 0.92);
		border: 1px solid var(--line);
		backdrop-filter: blur(10px);
		box-shadow: 0 0.75rem 2rem rgb(0 0 0 / 0.5);
		font-size: 0.9rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.pulse {
		flex: none;
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 50%;
		background: var(--accent);
		animation: pulse 1.6s ease-in-out infinite;
	}
	@keyframes pulse {
		50% {
			box-shadow: 0 0 0 0.4rem rgb(255 59 92 / 0);
			opacity: 0.6;
		}
	}
	@media (max-width: 640px) {
		header {
			gap: 1rem;
			flex-wrap: wrap;
		}
		.date {
			display: none;
		}
	}
</style>
