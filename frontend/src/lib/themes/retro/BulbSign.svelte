<script lang="ts">
	/**
	 * Big sign letters outlined with light bulbs: a dotted stroke with round caps
	 * along the letter contour forms the bulbs; the painted faces sit crisp on top.
	 */
	let { text, chase = true }: { text: string; chase?: boolean } = $props();

	const label = $derived(text.toUpperCase());
	const width = $derived(Math.max(420, label.length * 74 + 60));
	const uid = `glow-${Math.random().toString(36).slice(2, 8)}`;
</script>

<svg class="sign" class:chase viewBox="0 0 {width} 150" role="img" aria-label={text}>
	<defs>
		<filter id={uid} x="-10%" y="-30%" width="120%" height="160%">
			<feGaussianBlur stdDeviation="3.5" result="blur" />
			<feMerge>
				<feMergeNode in="blur" />
				<feMergeNode in="blur" />
				<feMergeNode in="SourceGraphic" />
			</feMerge>
		</filter>
	</defs>
	<!-- three phase-shifted bulb strings, behind the letters so their glow cannot blur them -->
	{#each [0, 1, 2] as phase}
		<text
			class="bulbs"
			style="--phase: {phase}; filter: url(#{uid})"
			x={width / 2}
			y="112"
			textLength={width - 50}
			lengthAdjust="spacingAndGlyphs">{label}</text
		>
	{/each}
	<!-- crisp painted letter faces on top -->
	<text class="face" x={width / 2} y="112" textLength={width - 50} lengthAdjust="spacingAndGlyphs">{label}</text>
</svg>

<style>
	.sign {
		display: block;
		width: 100%;
		max-width: 64rem;
		margin: 0 auto;
		overflow: visible;
	}
	text {
		font-family: 'Alfa Slab One', Georgia, serif;
		font-size: 112px;
		text-anchor: middle;
	}
	.face {
		fill: #c01a28;
		stroke: #2a0508;
		stroke-width: 2.5;
		paint-order: stroke;
	}
	.bulbs {
		fill: none;
		stroke: #ffe7a3;
		stroke-width: 9;
		stroke-linecap: round;
		stroke-dasharray: 0 21;
		stroke-dashoffset: calc(var(--phase) * -7px);
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
