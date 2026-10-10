<script lang="ts">
	import { trailerEmbedUrl } from '$lib/cinema/api';

	let { youtubeId, title, onclose }: { youtubeId: string; title: string; onclose: () => void } = $props();
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<div class="backdrop" role="presentation" onclick={onclose}>
	<div class="frame" role="dialog" aria-modal="true" aria-label="Trailer: {title}">
		<iframe
			src={trailerEmbedUrl(youtubeId)}
			title="Trailer: {title}"
			allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
			allowfullscreen
		></iframe>
		<button class="close" onclick={onclose} aria-label="Close trailer">✕</button>
	</div>
</div>

<style>
	.backdrop {
		position: fixed;
		inset: 0;
		z-index: 50;
		background: rgb(0 0 0 / 0.85);
		display: grid;
		place-items: center;
		padding: 1rem;
	}
	.frame {
		position: relative;
		width: min(72rem, 100%);
		aspect-ratio: 16 / 9;
		box-shadow: 0 2rem 6rem rgb(0 0 0 / 0.7);
	}
	iframe {
		width: 100%;
		height: 100%;
		border: 0;
		border-radius: 0.5rem;
		background: #000;
	}
	.close {
		position: absolute;
		top: -2.6rem;
		right: 0;
		background: none;
		border: 0;
		color: #fff;
		font-size: 1.5rem;
		cursor: pointer;
	}
</style>
