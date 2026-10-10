<script lang="ts">
	import { cinema } from '$lib/cinema/state.svelte';
	import BulbFrame from './BulbFrame.svelte';
	import LetterBoard from './LetterBoard.svelte';

	const STEPS: Record<string, string> = {
		resolve: 'Threading the reel',
		projector: 'Warming the bulb',
		session: 'House lights down',
		play: 'Roll it'
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
	<div class="booth" role="status" aria-live="polite">
		<div class="card">
			<p class="headline neon" class:pink={!failed}>
				{failed ? 'Missing reel' : done ? 'Now showing' : 'Coming right up'}
			</p>
			<BulbFrame step={22} chase={!failed}>
				<LetterBoard lines={[show.item_name]} />
			</BulbFrame>

			{#if failed}
				<p class="note">{show.error}</p>
				<p class="note small">The projectionist apologizes. Try again in a minute.</p>
			{:else if done}
				<p class="note">Enjoy the picture. Positively no talking.</p>
			{:else}
				<ul>
					{#each Object.entries(STEPS) as [step, label]}
						{@const status = show.steps.find((s) => s.step === step)?.status}
						<li class={status ?? 'waiting'}><span class="lamp" aria-hidden="true"></span>{label}</li>
					{/each}
				</ul>
			{/if}
			{#if done || failed}
				<button onclick={() => cinema.dismissShow()}>Back to the lobby</button>
			{/if}
		</div>
	</div>
{/if}

<style>
	.booth {
		position: fixed;
		inset: 0;
		z-index: 40;
		display: grid;
		place-items: center;
		padding: 1rem;
		background: radial-gradient(ellipse at center, rgb(30 18 14 / 0.94), rgb(5 4 6 / 0.98));
	}
	.card {
		width: min(36rem, 100%);
		text-align: center;
	}
	.headline {
		margin: 0 0 1rem;
		font-size: clamp(2.5rem, 7vw, 3.6rem);
		line-height: 1.1;
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 1.75rem auto 0;
		display: inline-flex;
		flex-direction: column;
		gap: 0.55rem;
		text-align: left;
		color: var(--muted);
	}
	li {
		display: flex;
		align-items: center;
		gap: 0.8rem;
	}
	li.done,
	li.running {
		color: var(--cream);
	}
	.lamp {
		width: 0.8rem;
		height: 0.8rem;
		border-radius: 50%;
		background: #3a2c22;
	}
	li.running .lamp {
		background: var(--gold);
		box-shadow: 0 0 0.6rem var(--gold);
	}
	li.done .lamp {
		background: #fff6d0;
		box-shadow: 0 0 0.8rem 0.2rem rgb(255 227 154 / 0.9);
	}
	.note {
		margin: 1.25rem 0 0;
		color: var(--cream);
	}
	.note.small {
		margin-top: 0.4rem;
		font-size: 0.85rem;
		color: var(--muted);
	}
	button {
		margin-top: 1.5rem;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.18em;
		background: none;
		color: var(--gold-light);
		border: 2px solid var(--gold);
		border-radius: 999px;
		padding: 0.55rem 1.3rem;
		cursor: pointer;
	}
</style>
