<script lang="ts">
	import { showtimeStates } from '$lib/cinema/api';

	let { date, times, href }: { date: string; times: string[]; href?: string } = $props();

	const states = $derived(showtimeStates(date, times));
</script>

<div class="times">
	{#each times as time, i}
		{#if href}
			<a class="time {states[i]}" {href} title={states[i] === 'past' ? 'Already started, but we hold the reel for you' : 'Get tickets'}>{time}</a>
		{:else}
			<span class="time {states[i]}">{time}</span>
		{/if}
	{/each}
</div>

<style>
	.times {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}
	.time {
		font-variant-numeric: tabular-nums;
		font-weight: 600;
		font-size: 0.85rem;
		padding: 0.3rem 0.6rem;
		border-radius: 0.3rem;
		border: 1px solid var(--line);
		color: var(--text);
		text-decoration: none;
		transition: border-color 0.15s, background 0.15s;
	}
	a.time:hover {
		border-color: var(--gold);
	}
	.time.next {
		background: var(--gold);
		border-color: var(--gold);
		color: #1a1206;
	}
	.time.past {
		color: var(--muted);
		text-decoration: line-through;
		text-decoration-color: color-mix(in srgb, var(--muted) 60%, transparent);
	}
</style>
