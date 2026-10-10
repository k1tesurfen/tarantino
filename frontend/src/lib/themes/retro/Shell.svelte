<script lang="ts">
	import '@fontsource/alfa-slab-one';
	import '@fontsource/courier-prime';
	import '@fontsource/courier-prime/700.css';
	import '@fontsource-variable/oswald';
	import type { Snippet } from 'svelte';
	import { formatCinemaDate } from '$lib/cinema/api';
	import { AVAILABLE_THEMES, cinema } from '$lib/cinema/state.svelte';
	import Apple from './Apple.svelte';
	import ShowOverlay from './ShowOverlay.svelte';

	let { children }: { children: Snippet } = $props();

	const programme = $derived(cinema.programme);
	const nowPlaying = $derived(cinema.now?.now_playing);
</script>

<svelte:head><title>{cinema.name || 'Cinema'}</title></svelte:head>

<div class="redapple">
	<div class="topbar">
		<span>{programme ? `Tonight · ${formatCinemaDate(programme.date)}` : 'Tonight'}</span>
		{#if AVAILABLE_THEMES.length > 1}
			<label>
				<span class="sr">Cinema</span>
				<select
					value={cinema.theme}
					onchange={(e) => cinema.setTheme((e.currentTarget as HTMLSelectElement).value as typeof cinema.theme)}
				>
					{#each AVAILABLE_THEMES as theme}
						<option value={theme}>{programme?.cinema.names[theme] ?? theme}</option>
					{/each}
				</select>
			</label>
		{/if}
	</div>

	<header class="masthead">
		<a href="/" class="brand" aria-label="{cinema.name} home">
			<Apple size={64} />
			<span class="name">{cinema.name}</span>
		</a>
		<p class="strap">Double features nightly · Air-conditioned · Est. 1974</p>
		<nav>
			<a href="/#bills">Tonight's double bills</a>
			<a href="/#serials">Serials</a>
			<a href="/#concessions">Concessions</a>
		</nav>
	</header>

	<main>
		{#if cinema.error && !programme}
			<p class="offline">The box office is closed. Come back after the intermission. ({cinema.error})</p>
		{:else}
			{@render children()}
		{/if}
	</main>

	<footer>
		<p>Positively no smoking in the auditorium. Except Red Apples.</p>
		<p>{cinema.name} · a tarantino picture house · <a href="/admin">Projection booth</a></p>
	</footer>

	{#if nowPlaying}
		<div class="now" role="status">
			<span class="label">Now showing</span>
			<strong>{nowPlaying}</strong>{cinema.now?.paused ? ' · intermission' : ''}
		</div>
	{/if}

	<ShowOverlay />
</div>

<style>
	.redapple {
		--paper: #efe2c4;
		--paper-dark: #e0cc9f;
		--ink: #1e1712;
		--ink-soft: #5a4632;
		--red: #b5202b;
		--mustard: #dba21d;
		--teal: #2c6b67;
		--lobby: #1b120e;
		--display: 'Alfa Slab One', Georgia, serif;
		--condensed: 'Oswald Variable', 'Arial Narrow', sans-serif;
		--type: 'Courier Prime', 'Courier New', monospace;
		/* Printed paper: fractal noise grain plus darkened, aged edges. */
		--grain: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 .3  0 0 0 0 .2  0 0 0 0 .1  0 0 0 .22 0'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>");
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		color: var(--ink);
		font-family: var(--type);
		background:
			repeating-linear-gradient(90deg, rgb(0 0 0 / 0.12) 0 2px, transparent 2px 14px),
			radial-gradient(ellipse at top, #3a1b14, var(--lobby) 70%);
		background-color: var(--lobby);
	}
	.redapple :global(.sheet) {
		background-color: var(--paper);
		background-image: var(--grain), radial-gradient(ellipse at center, transparent 55%, rgb(120 80 30 / 0.28));
		box-shadow: 0 0.6rem 1.8rem rgb(0 0 0 / 0.55);
	}
	.redapple :global(a) {
		color: inherit;
	}
	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
	}
	.topbar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.4rem clamp(1rem, 4vw, 3rem);
		color: var(--paper-dark);
		font-size: 0.8rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
	}
	select {
		background: var(--lobby);
		color: var(--paper);
		border: 1px solid var(--ink-soft);
		font: inherit;
		letter-spacing: 0.05em;
		padding: 0.2rem 0.5rem;
	}
	.masthead {
		text-align: center;
		padding: 1.5rem 1rem 0.5rem;
		color: var(--paper);
	}
	.brand {
		display: inline-flex;
		align-items: center;
		gap: 0.9rem;
		text-decoration: none;
	}
	.name {
		font-family: var(--display);
		font-size: clamp(2.2rem, 7vw, 4.6rem);
		line-height: 1;
		text-transform: uppercase;
		color: var(--paper);
		text-shadow:
			0.18rem 0.18rem 0 var(--red),
			0.36rem 0.36rem 0 rgb(0 0 0 / 0.5);
	}
	.strap {
		margin: 0.9rem 0 1.1rem;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.35em;
		font-size: 0.85rem;
		color: var(--mustard);
	}
	nav {
		display: inline-flex;
		flex-wrap: wrap;
		justify-content: center;
		border-top: 2px solid var(--mustard);
		border-bottom: 2px solid var(--mustard);
	}
	nav a {
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.15em;
		text-decoration: none;
		padding: 0.5rem 1.2rem;
		color: var(--paper);
	}
	nav a:hover {
		background: var(--red);
	}
	main {
		flex: 1;
		width: min(92rem, 100%);
		margin: 0 auto;
		padding: 1.5rem clamp(0.75rem, 3vw, 2.5rem) 2rem;
		box-sizing: border-box;
	}
	.offline {
		color: var(--paper);
		text-align: center;
		padding: 5rem 1rem;
	}
	footer {
		text-align: center;
		color: var(--paper-dark);
		font-size: 0.8rem;
		padding: 1.5rem 1rem 4.5rem;
		border-top: 1px solid rgb(239 226 196 / 0.15);
	}
	footer p {
		margin: 0.3rem 0;
	}
	.now {
		position: fixed;
		left: 50%;
		bottom: 1rem;
		transform: translateX(-50%) rotate(-1deg);
		z-index: 30;
		display: flex;
		gap: 0.75rem;
		align-items: center;
		max-width: calc(100vw - 2rem);
		padding: 0.5rem 1.2rem;
		background-color: var(--paper);
		background-image: var(--grain);
		box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 0.6);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.now .label {
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.2em;
		background: var(--red);
		color: var(--paper);
		padding: 0.1rem 0.5rem;
		font-size: 0.8rem;
	}
</style>
