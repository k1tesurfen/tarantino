<script lang="ts">
	import { showtimeStates } from '$lib/cinema/api';

	let { date, times, href }: { date: string; times: string[]; href?: string } = $props();

	const states = $derived(showtimeStates(date, times));
	// Fake showtimes, but the reel always waits: after the last one there is a late show.
	const lateShow = $derived(times.length > 0 && !states.includes('next'));
</script>

<div class="times">
	{#each times as time, i}
		{#if href}
			<a class="time {states[i]}" {href} title={states[i] === 'past' ? 'Already started, but the reel waits for you' : 'Get tickets'}>{time}</a>
		{:else}
			<span class="time {states[i]}">{time}</span>
		{/if}
	{/each}
	{#if lateShow}
		{#if href}<a class="time next" {href}>Late show</a>{:else}<span class="time next">Late show</span>{/if}
	{/if}
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
		opacity: 0.6;
	}
</style>
