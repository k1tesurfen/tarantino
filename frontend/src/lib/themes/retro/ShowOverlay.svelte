<script lang="ts">
	import { cinema } from '$lib/cinema/state.svelte';

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
		<div class="card sheet">
			{#if failed}
				<p class="title missing">Missing reel</p>
				<p class="film">{show.item_name}</p>
				<p class="note">{show.error}</p>
				<p class="note small">The projectionist apologizes. Try again in a minute.</p>
			{:else}
				<p class="kicker">{done ? 'Now showing' : 'Projection booth'}</p>
				<p class="title">{show.item_name}</p>
				{#if done}
					<p class="note">Enjoy the picture. Positively no talking.</p>
				{:else}
					<ul>
						{#each Object.entries(STEPS) as [step, label]}
							{@const status = show.steps.find((s) => s.step === step)?.status}
							<li class={status ?? 'waiting'}>
								<span class="box">{status === 'done' ? '✕' : status === 'running' ? '…' : ''}</span>
								{label}
							</li>
						{/each}
					</ul>
				{/if}
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
		background: rgb(15 9 7 / 0.92);
	}
	.card {
		width: min(28rem, 100%);
		padding: 1.75rem 2rem;
		text-align: center;
		transform: rotate(-1deg);
	}
	.kicker {
		margin: 0;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.3em;
		font-size: 0.8rem;
		color: var(--red);
	}
	.title {
		margin: 0.5rem 0 1.25rem;
		font-family: var(--display);
		text-transform: uppercase;
		font-size: clamp(1.8rem, 6vw, 2.6rem);
		line-height: 1;
	}
	.title.missing {
		color: var(--red);
		border: 4px solid var(--red);
		display: inline-block;
		padding: 0.2rem 0.8rem;
		transform: rotate(-4deg);
	}
	.film {
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.1em;
	}
	ul {
		list-style: none;
		padding: 0;
		margin: 0 auto;
		display: inline-flex;
		flex-direction: column;
		gap: 0.5rem;
		text-align: left;
	}
	li {
		display: flex;
		align-items: center;
		gap: 0.7rem;
		color: var(--ink-soft);
	}
	li.done,
	li.running {
		color: var(--ink);
		font-weight: 700;
	}
	.box {
		width: 1.1rem;
		height: 1.1rem;
		display: grid;
		place-items: center;
		border: 2px solid currentColor;
		font-size: 0.75rem;
		line-height: 1;
	}
	li.done .box {
		color: var(--red);
	}
	.note {
		margin: 0.5rem 0;
	}
	.note.small {
		font-size: 0.85rem;
		color: var(--ink-soft);
	}
	button {
		margin-top: 1.25rem;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.18em;
		background: var(--ink);
		color: var(--paper);
		border: 0;
		padding: 0.6rem 1.2rem;
		cursor: pointer;
	}
</style>
