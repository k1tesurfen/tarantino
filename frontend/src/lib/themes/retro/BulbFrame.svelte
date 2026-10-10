<script lang="ts">
	import type { Snippet } from 'svelte';

	/**
	 * A box framed by marquee bulbs. Three phase-shifted bulb layers light up in turn,
	 * which reads as the classic "chasing lights". `chase={false}` keeps them steady.
	 */
	let {
		step = 26,
		chase = true,
		children
	}: { step?: number; chase?: boolean; children: Snippet } = $props();
</script>

<div class="frame" class:chase style="--step: {step}px">
	{#each [0, 1, 2] as phase}
		<span class="bulbs" style="--phase: {phase}" aria-hidden="true"></span>
	{/each}
	<div class="inner">{@render children()}</div>
</div>

<style>
	.frame {
		position: relative;
		padding: var(--step);
		background: linear-gradient(#2a1a10, #1a100a);
		border-radius: 0.4rem;
		box-shadow:
			0 0 0 2px #6b4a1e,
			0 0 2.5rem rgb(255 190 80 / 0.25),
			inset 0 0 1.5rem rgb(0 0 0 / 0.6);
	}
	.inner {
		position: relative;
		z-index: 1;
	}
	.bulbs {
		--bulb: radial-gradient(
			circle,
			#fffdf2 0 16%,
			#ffe39a 28%,
			rgb(255 176 50 / 0.75) 40%,
			rgb(255 150 30 / 0.18) 55%,
			transparent 66%
		);
		--offset: calc(var(--step) * var(--phase) / 3);
		position: absolute;
		inset: 0;
		pointer-events: none;
		/* One row of bulbs along each edge, shifted by a third of a step per phase. */
		background:
			var(--bulb) var(--offset) 0 / var(--step) var(--step) repeat-x,
			var(--bulb) var(--offset) 100% / var(--step) var(--step) repeat-x,
			var(--bulb) 0 var(--offset) / var(--step) var(--step) repeat-y,
			var(--bulb) 100% var(--offset) / var(--step) var(--step) repeat-y;
		background-clip: border-box;
	}
	.chase .bulbs {
		animation: chase 1.8s infinite;
		animation-delay: calc(var(--phase) * -0.6s);
	}
	@keyframes chase {
		0%,
		33% {
			opacity: 1;
		}
		34%,
		100% {
			opacity: 0.22;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.chase .bulbs {
			animation: none;
		}
	}
</style>
