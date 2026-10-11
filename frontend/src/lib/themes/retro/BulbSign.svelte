<script lang="ts">
	/**
	 * Big sign letters outlined with light bulbs, like a marquee sign: each letter has
	 * a dark backing (the sign box), a red face inset from the outline, and bulbs on
	 * the outline itself, so they sit in the gap between face and box edge.
	 */
	let { text, chase = true }: { text: string; chase?: boolean } = $props();

	// In sign units. The letters are large relative to bulbs and inset, so the
	// red faces stay solid even with a ring of bulbs around every stroke.
	const PER_LETTER = 176; // glyph width plus generous spacing
	const FONT_SIZE = 220;
	const BASELINE = 226;
	const HEIGHT = 290;

	const label = $derived(text.toUpperCase());
	const width = $derived(Math.max(800, label.length * PER_LETTER + 120));
	const uid = Math.random().toString(36).slice(2, 8);
</script>

<svg class="sign" class:chase viewBox="0 0 {width} {HEIGHT}" role="img" aria-label={text}>
	<defs>
		<!-- shrink the red faces inward, leaving the outline free for the bulbs -->
		<filter id="inset-{uid}" x="-5%" y="-20%" width="110%" height="140%">
			<feMorphology operator="erode" radius="12" />
		</filter>
		<filter id="glow-{uid}" x="-5%" y="-20%" width="110%" height="140%">
			<feGaussianBlur stdDeviation="2.5" result="blur" />
			<feMerge>
				<feMergeNode in="blur" />
				<feMergeNode in="SourceGraphic" />
			</feMerge>
		</filter>
	</defs>

	{#snippet letters(cls: string, style = '')}
		<text class={cls} {style} x={width / 2} y={BASELINE} font-size={FONT_SIZE} textLength={width - 120} lengthAdjust="spacing"
			>{label}</text
		>
	{/snippet}

	<!-- the sign box behind each letter -->
	{@render letters('box')}
	<!-- painted face, inset from the outline -->
	{@render letters('face', `filter: url(#inset-${uid})`)}
	<!-- three phase-shifted bulb strings on the outline -->
	{#each [0, 1, 2] as phase}
		{@render letters('bulbs', `--phase: ${phase}; filter: url(#glow-${uid})`)}
	{/each}
</svg>

<style>
	.sign {
		display: block;
		width: 100%;
		max-width: 85rem;
		margin: 0 auto;
		overflow: visible;
	}
	text {
		font-family: 'Alfa Slab One', Georgia, serif;
		text-anchor: middle;
	}
	.box {
		fill: #1c0b0c;
		stroke: #1c0b0c;
		stroke-width: 38;
		stroke-linejoin: round;
	}
	.face {
		fill: #c81c2a;
	}
	.bulbs {
		fill: none;
		stroke: #ffe7a3;
		stroke-width: 12.5;
		stroke-linecap: round;
		stroke-dasharray: 0 31;
		stroke-dashoffset: calc(var(--phase) * -10.33px);
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
			opacity: 0.25;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.chase .bulbs {
			animation: none;
		}
	}
</style>
