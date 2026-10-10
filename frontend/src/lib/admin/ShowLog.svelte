<script lang="ts">
	import type { Show } from '$lib/api';

	let { shows }: { shows: Show[] } = $props();

	const formatTime = (iso: string) => new Date(iso).toLocaleString();
</script>

{#if shows.length === 0}<p class="muted">No shows yet.</p>{/if}
{#each shows as show (show.id)}
	<article class="show {show.state}">
		<div class="head">
			<strong>{show.item_name}</strong>
			<span class="state">{show.state}</span>
		</div>
		<small class="muted">#{show.id} · {show.trigger} · {formatTime(show.created_at)}</small>
		<ol>
			{#each show.steps as step}
				<li class={step.status}>
					<span class="step">{step.step}</span>
					<span>{step.message ?? (step.status === 'running' ? '…' : '')}</span>
				</li>
			{/each}
		</ol>
		{#if show.error}<p class="error">{show.error}</p>{/if}
	</article>
{/each}

<style>
	.show {
		background: var(--panel);
		border: 1px solid var(--line);
		border-left: 3px solid var(--muted);
		border-radius: 0.35rem;
		padding: 0.6rem 0.9rem;
		margin-bottom: 0.6rem;
	}
	.show.playing {
		border-left-color: #6fcf8a;
	}
	.show.failed {
		border-left-color: #e57373;
	}
	.show.running {
		border-left-color: var(--accent);
	}
	.head {
		display: flex;
		justify-content: space-between;
	}
	.state {
		font-size: 0.8rem;
		text-transform: uppercase;
		color: var(--muted);
	}
	ol {
		list-style: none;
		padding: 0;
		margin: 0.4rem 0 0;
		font-size: 0.85rem;
	}
	li {
		display: flex;
		gap: 0.6rem;
		padding: 0.1rem 0;
	}
	li::before {
		content: '○';
		color: var(--muted);
	}
	li.done::before {
		content: '✓';
		color: #6fcf8a;
	}
	li.failed::before {
		content: '✕';
		color: #e57373;
	}
	li.running::before {
		content: '◐';
		color: var(--accent);
	}
	.step {
		width: 5.5rem;
		flex: none;
		color: var(--muted);
	}
	.error {
		margin: 0.4rem 0 0;
	}
</style>
