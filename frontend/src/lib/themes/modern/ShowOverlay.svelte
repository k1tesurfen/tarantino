<script lang="ts">
	import { cinema } from '$lib/cinema/state.svelte';

	const STEPS: Record<string, string> = {
		resolve: 'Fetching the reels',
		projector: 'Warming up the projector',
		session: 'Dimming the lights',
		play: 'Rolling film'
	};

	const show = $derived(cinema.show);
	const done = $derived(show?.state === 'playing');
	const failed = $derived(show?.state === 'failed' || show?.state === 'cancelled');

	$effect(() => {
		if (!done) return;
		const timer = setTimeout(() => cinema.dismissShow(), 8000);
		return () => clearTimeout(timer);
	});
</script>

{#if show}
	<div class="overlay" role="status" aria-live="polite">
		<div class="panel" class:done class:failed>
			<p class="eyebrow">{done ? 'Now showing' : failed ? 'Technical difficulties' : 'Your show is starting'}</p>
			<h2>{show.item_name}</h2>

			{#if done}
				<p class="big">Enjoy the show 🍿</p>
				<p class="hint">Please switch off your phone. Or at least dim it.</p>
			{:else if failed}
				<p class="error">{show.error}</p>
				<p class="hint">The projectionist has been informed (it's you).</p>
			{:else}
				<ol>
					{#each Object.entries(STEPS) as [step, label]}
						{@const s = show.steps.find((x) => x.step === step)}
						<li class={s?.status ?? 'waiting'}>{label}</li>
					{/each}
				</ol>
			{/if}

			{#if done || failed}
				<button onclick={() => cinema.dismissShow()}>Close</button>
			{/if}
		</div>
	</div>
{/if}

<style>
	.overlay {
		position: fixed;
		inset: 0;
		z-index: 40;
		background: radial-gradient(circle at center, rgb(10 10 16 / 0.85), rgb(0 0 0 / 0.97));
		display: grid;
		place-items: center;
		padding: 1rem;
		animation: fade 0.4s ease-out;
	}
	@keyframes fade {
		from {
			opacity: 0;
		}
	}
	.panel {
		width: min(30rem, 100%);
		text-align: center;
	}
	.eyebrow {
		text-transform: uppercase;
		letter-spacing: 0.25em;
		font-size: 0.75rem;
		color: var(--accent);
	}
	h2 {
		font-family: var(--display);
		text-transform: uppercase;
		font-size: clamp(2rem, 6vw, 3.25rem);
		line-height: 1;
		margin: 0.5rem 0 1.5rem;
	}
	ol {
		list-style: none;
		padding: 0;
		margin: 0 auto;
		display: inline-flex;
		flex-direction: column;
		gap: 0.6rem;
		text-align: left;
	}
	li {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		color: var(--muted);
		transition: color 0.3s;
	}
	li::before {
		content: '';
		width: 0.65rem;
		height: 0.65rem;
		border-radius: 50%;
		border: 2px solid var(--line);
	}
	li.running {
		color: var(--text);
	}
	li.running::before {
		border-color: var(--gold);
		border-top-color: transparent;
		animation: spin 0.8s linear infinite;
	}
	li.done {
		color: var(--text);
	}
	li.done::before {
		background: var(--accent);
		border-color: var(--accent);
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.big {
		font-size: 1.5rem;
		font-weight: 600;
	}
	.hint {
		color: var(--muted);
		font-size: 0.9rem;
	}
	.error {
		color: #ff8a9b;
	}
	button {
		margin-top: 1.5rem;
		background: none;
		color: var(--text);
		border: 1px solid var(--line);
		border-radius: 999px;
		padding: 0.5rem 1.5rem;
		font: inherit;
		cursor: pointer;
	}
</style>
