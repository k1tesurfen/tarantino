<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { SubsystemState } from '$lib/api';

	let {
		title,
		state,
		message = null,
		children
	}: { title: string; state?: SubsystemState; message?: string | null; children?: Snippet } = $props();
</script>

<article class="card">
	<div class="head">
		<h2>{title}</h2>
		{#if state}<span class="pill {state}">{state}</span>{/if}
	</div>
	{#if message}<p class="message">{message}</p>{/if}
	{@render children?.()}
</article>

<style>
	.card {
		background: var(--panel);
		border: 1px solid var(--line);
		border-radius: 0.5rem;
		padding: 1rem 1.25rem;
	}
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	h2 {
		font-size: 1.05rem;
		margin: 0.25rem 0;
	}
	.pill {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 0.15rem 0.5rem;
		border-radius: 999px;
		background: var(--line);
	}
	.pill.ok {
		background: #1e4d2b;
		color: #9be3ae;
	}
	.pill.warning {
		background: #5a4614;
		color: #f3d27a;
	}
	.pill.error {
		background: #5c1f1f;
		color: #f3a1a1;
	}
	.message {
		color: #f3d27a;
		font-size: 0.9rem;
	}
</style>
