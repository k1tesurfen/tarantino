<script lang="ts">
	import '@fontsource/alfa-slab-one';
	import '@fontsource/courier-prime';
	import '@fontsource/courier-prime/700.css';
	import '@fontsource/yellowtail';
	import '@fontsource-variable/oswald';
	import type { Snippet } from 'svelte';
	import { formatCinemaDate } from '$lib/cinema/api';
	import { AVAILABLE_THEMES, cinema } from '$lib/cinema/state.svelte';
	import { marqueeLines } from './bills';
	import BulbFrame from './BulbFrame.svelte';
	import BulbSign from './BulbSign.svelte';
	import LetterBoard from './LetterBoard.svelte';
	import ShowOverlay from './ShowOverlay.svelte';

	let { children }: { children: Snippet } = $props();

	const programme = $derived(cinema.programme);
	const nowPlaying = $derived(cinema.now?.now_playing);
	const board = $derived(programme ? marqueeLines(programme.rooms) : ['Tonight', 'Threading the reels']);
</script>

<svelte:head><title>{cinema.name || 'Cinema'}</title></svelte:head>

<div class="redapple">
	<div class="topbar">
		<span>{programme ? formatCinemaDate(programme.date) : ''}</span>
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

	<header class="facade">
		<a href="/" class="sign" aria-label="{cinema.name} home">
			{#if cinema.name}<BulbSign text={cinema.name} />{/if}
		</a>
		<p class="neon tagline">Double features nightly</p>
		<div class="canopy">
			<BulbFrame step={28}>
				<LetterBoard lines={board} />
			</BulbFrame>
		</div>
		<nav>
			<a href="/#bills">Now showing</a>
			<a href="/#serials">Serials</a>
			<a href="/#concessions">Concessions</a>
		</nav>
	</header>

	<main>
		{#if cinema.error && !programme}
			<p class="offline">The lights are out. Come back after the intermission. ({cinema.error})</p>
		{:else}
			{@render children()}
		{/if}
	</main>

	<footer>
		<p class="neon small">No smoking in the auditorium</p>
		<p>Except Red Apples · {cinema.name} · a tarantino picture palace · <a href="/admin">Projection booth</a></p>
	</footer>

	{#if nowPlaying}
		<div class="now" role="status">
			<span class="neon small">Now showing</span>
			<strong>{nowPlaying}</strong>{cinema.now?.paused ? ' · intermission' : ''}
		</div>
	{/if}

	<ShowOverlay />
</div>

<style>
	.redapple {
		--night: #0c0a10;
		--wood: #2a1a10;
		--gold: #e7b75a;
		--gold-light: #ffe39a;
		--neon: #ff3a4c;
		--neon-pink: #ff6fae;
		--cream: #f6ecd2;
		--text: #f3e9d7;
		--muted: #b9a88c;
		--red: #b5202b;
		--display: 'Alfa Slab One', Georgia, serif;
		--condensed: 'Oswald Variable', 'Arial Narrow', sans-serif;
		--type: 'Courier Prime', 'Courier New', monospace;
		--script: 'Yellowtail', cursive;
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		color: var(--text);
		font-family: var(--type);
		/* A night street lit warm from the marquee above. */
		background:
			radial-gradient(ellipse 80% 45% at 50% 18rem, rgb(255 170 70 / 0.18), transparent 70%),
			linear-gradient(to bottom, #120c14, var(--night) 40rem);
		background-color: var(--night);
	}
	/* Zero-specificity defaults, so components can style their own links. */
	:where(.redapple) :global(a) {
		color: inherit;
	}
	/* Neon tube lettering, usable by every component of this theme. */
	.redapple :global(.neon) {
		font-family: var(--script);
		font-weight: 400;
		color: #ffe9ee;
		text-shadow:
			0 0 2px #fff,
			0 0 6px var(--neon),
			0 0 14px var(--neon),
			0 0 30px var(--neon),
			0 0 60px rgb(255 58 76 / 0.6);
	}
	.redapple :global(.neon.pink) {
		text-shadow:
			0 0 2px #fff,
			0 0 6px var(--neon-pink),
			0 0 14px var(--neon-pink),
			0 0 30px var(--neon-pink);
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
		padding: 0.5rem clamp(1rem, 4vw, 3rem);
		color: var(--muted);
		font-size: 0.8rem;
		letter-spacing: 0.15em;
		text-transform: uppercase;
	}
	select {
		background: var(--night);
		color: var(--text);
		border: 1px solid #4a3a2a;
		font: inherit;
		letter-spacing: 0.05em;
		padding: 0.2rem 0.5rem;
	}
	.facade {
		text-align: center;
		padding: 0.5rem clamp(0.75rem, 3vw, 2.5rem) 0;
	}
	.sign {
		display: block;
		text-decoration: none;
	}
	.tagline {
		margin: 0.2rem 0 1.4rem;
		font-size: clamp(1.8rem, 4vw, 2.8rem);
		transform: rotate(-3deg);
	}
	.canopy {
		max-width: 60rem;
		margin: 0 auto;
	}
	nav {
		display: flex;
		justify-content: center;
		flex-wrap: wrap;
		gap: 0.75rem;
		margin: 1.5rem 0 0.5rem;
	}
	nav a {
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.2em;
		text-decoration: none;
		padding: 0.45rem 1.2rem;
		color: var(--gold-light);
		border: 2px solid var(--gold);
		border-radius: 999px;
		box-shadow:
			0 0 0.5rem rgb(231 183 90 / 0.5),
			inset 0 0 0.5rem rgb(231 183 90 / 0.3);
		text-shadow: 0 0 0.4rem rgb(255 227 154 / 0.7);
	}
	nav a:hover {
		background: rgb(231 183 90 / 0.15);
	}
	main {
		flex: 1;
		width: min(92rem, 100%);
		margin: 0 auto;
		padding: 2rem clamp(0.75rem, 3vw, 2.5rem) 2rem;
		box-sizing: border-box;
	}
	.offline {
		text-align: center;
		padding: 5rem 1rem;
		color: var(--muted);
	}
	footer {
		text-align: center;
		color: var(--muted);
		font-size: 0.8rem;
		padding: 2rem 1rem 4.5rem;
		border-top: 1px solid rgb(231 183 90 / 0.15);
	}
	footer p {
		margin: 0.3rem 0;
	}
	footer .neon.small {
		font-size: 1.6rem;
	}
	.now {
		position: fixed;
		left: 50%;
		bottom: 1rem;
		transform: translateX(-50%);
		z-index: 30;
		display: flex;
		gap: 0.9rem;
		align-items: center;
		max-width: calc(100vw - 2rem);
		padding: 0.4rem 1.3rem 0.5rem;
		background: rgb(12 10 16 / 0.92);
		border: 2px solid var(--gold);
		border-radius: 999px;
		box-shadow: 0 0 1.2rem rgb(231 183 90 / 0.35);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.now .neon {
		font-size: 1.4rem;
	}
</style>
