<script lang="ts">
	/** A backlit attraction board with black changeable letters on rails. */
	let { lines, small = false }: { lines: string[]; small?: boolean } = $props();
</script>

<div class="board" class:small>
	{#each lines as line}
		<p>{line.toUpperCase()}</p>
	{/each}
</div>

<style>
	.board {
		padding: 0.6rem 1.25rem;
		background:
			repeating-linear-gradient(
				to bottom,
				transparent 0 calc(var(--rail, 3.1rem) - 2px),
				rgb(80 60 30 / 0.25) calc(var(--rail, 3.1rem) - 2px) var(--rail, 3.1rem)
			),
			radial-gradient(ellipse at center, #fffdf5, #f6ecd2 75%, #e8d8b0);
		box-shadow:
			inset 0 0 1.5rem rgb(255 230 170 / 0.9),
			0 0 2rem rgb(255 240 200 / 0.35);
		border: 3px solid #3a2a14;
		text-align: center;
	}
	.board.small {
		--rail: 2.2rem;
		padding: 0.35rem 0.75rem;
	}
	p {
		margin: 0;
		height: var(--rail, 3.1rem);
		line-height: var(--rail, 3.1rem);
		font-family: 'Oswald Variable', 'Arial Narrow', sans-serif;
		font-weight: 700;
		font-size: clamp(1.1rem, 2.6vw, 2rem);
		letter-spacing: 0.12em;
		color: #121010;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.small p {
		font-size: clamp(0.9rem, 1.6vw, 1.2rem);
		letter-spacing: 0.1em;
	}
</style>
