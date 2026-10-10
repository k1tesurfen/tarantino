<script lang="ts">
	import { showtimeChips } from '$lib/cinema/tickets';

	let { date, times, href }: { date: string; times: string[]; href?: string } = $props();

	const chips = $derived(showtimeChips(date, times));
</script>

<div class="times">
	{#each chips as chip}
		{#if href}
			<a class="time {chip.state}" {href} title={chip.state === 'past' ? 'Already started, but the reel waits for you' : 'Get tickets'}>{chip.label}</a>
		{:else}
			<span class="time {chip.state}">{chip.label}</span>
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
		opacity: 0.6;
	}
</style>
