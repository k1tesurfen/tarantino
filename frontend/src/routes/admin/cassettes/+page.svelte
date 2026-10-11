<script lang="ts">
	import { onMount } from 'svelte';
	import {
		armLearnMode,
		assignCassette,
		cancelLearnMode,
		getCassettes,
		removeCassette,
		subscribe,
		type CassetteOverview,
		type VhsEvent
	} from '$lib/api';

	let overview = $state<CassetteOverview | null>(null);
	let error = $state<string | null>(null);
	let secondsLeft = $state(0);
	let assignTo = $state<Record<string, number>>({});

	const learn = $derived(overview?.learn ?? null);
	const knownUids = $derived(new Set((overview?.rooms ?? []).flatMap((r) => r.cassettes.map((c) => c.uid))));

	async function load() {
		try {
			overview = await getCassettes();
			secondsLeft = overview.learn?.seconds_left ?? 0;
			error = null;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	async function run(action: () => Promise<unknown>) {
		error = null;
		try {
			await action();
		} catch (e) {
			error = (e as Error).message;
		}
		await load();
	}

	function remove(uid: string, room: number) {
		if (confirm(`Remove cassette ${uid} from room ${room}?`)) run(() => removeCassette(uid));
	}

	const outcomeLabel: Record<VhsEvent['outcome'], string> = {
		played: 'started',
		learned: 'learned',
		unknown: 'unknown',
		failed: 'failed',
		ignored: 'ignored'
	};
	const formatTime = (iso: string) => new Date(iso).toLocaleString();

	onMount(() => {
		load();
		const unsubscribe = subscribe({ vhs: () => load() });
		const timer = setInterval(() => {
			if (secondsLeft > 0 && --secondsLeft === 0) load();
		}, 1000);
		return () => {
			clearInterval(timer);
			unsubscribe();
		};
	});
</script>

<svelte:head><title>Cassettes · tarantino</title></svelte:head>

<p class="muted">
	Each room is bound to one or more RFID-tagged cassettes. Inserting a cassette into the VHS recorder starts whatever
	its room shows today. To bind a cassette, press <strong>Learn</strong> next to a room and insert the cassette within
	two minutes. Learning never starts a film.
</p>

{#if learn}
	<div class="learn">
		<span class="dot"></span>
		<div>
			<strong>Insert the cassette for room {learn.room} · {learn.room_name} now</strong>
			<div class="muted">The next cassette the recorder reads is bound to this room ({secondsLeft} s left).</div>
		</div>
		<button class="ghost" onclick={() => run(cancelLearnMode)}>Cancel</button>
	</div>
{/if}

{#if error}<p class="error">{error}</p>{/if}

{#if overview}
	<table>
		<thead><tr><th>Room</th><th>Name</th><th>Cassettes</th><th></th></tr></thead>
		<tbody>
			{#each overview.rooms as room (room.number)}
				<tr class:armed={learn?.room === room.number} class:inactive={!room.active}>
					<td class="num">{room.number}</td>
					<td>{room.name}{#if !room.active} <span class="muted">(inactive)</span>{/if}</td>
					<td>
						{#each room.cassettes as cassette (cassette.uid)}
							<span class="chip mono" title="Learned {formatTime(cassette.learned_at)}">
								{cassette.uid}
								<button class="x" aria-label="Remove {cassette.uid}" onclick={() => remove(cassette.uid, room.number)}
									>×</button
								>
							</span>
						{:else}
							<span class="muted">none</span>
						{/each}
					</td>
					<td class="actions">
						{#if learn?.room === room.number}
							<span class="muted">waiting…</span>
						{:else}
							<button class="ghost" onclick={() => run(() => armLearnMode(room.number))}>Learn</button>
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>

	<h2>Recorder log</h2>
	<p class="muted">
		Every insert and eject the recorder reports, newest first. Unknown cassettes are ignored; you can bind them to a
		room here.
	</p>
	{#if overview.events.length === 0}
		<p class="muted">Nothing yet. Test without the recorder: <code>tarantino vhs insert FAKE0001</code></p>
	{:else}
		<table>
			<thead><tr><th>Time</th><th>Event</th><th>Cassette</th><th>Room</th><th>Result</th><th></th></tr></thead>
			<tbody>
				{#each overview.events as event (event.id)}
					<tr>
						<td>{formatTime(event.at)}</td>
						<td>{event.action}</td>
						<td class="mono">{event.uid ?? '—'}</td>
						<td>{event.room ?? '—'}</td>
						<td>
							<span class="outcome {event.outcome}">{outcomeLabel[event.outcome]}</span>
							{#if event.message}<span class="muted">{event.message}</span>{/if}
						</td>
						<td class="actions">
							{#if event.outcome === 'unknown' && event.uid && !knownUids.has(event.uid)}
								{@const uid = event.uid}
								<select bind:value={assignTo[uid]} aria-label="Room for {uid}">
									<option value={undefined}>Room…</option>
									{#each overview.rooms as room}<option value={room.number}>{room.number} · {room.name}</option>{/each}
								</select>
								<button
									class="ghost"
									disabled={!assignTo[uid]}
									onclick={() => run(() => assignCassette(uid, assignTo[uid]))}>Bind</button
								>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
{/if}

<style>
	.learn {
		display: flex;
		align-items: center;
		gap: 1rem;
		background: #3d3212;
		border: 1px solid #5a4614;
		border-radius: 0.5rem;
		padding: 0.75rem 1rem;
		margin: 1rem 0;
	}
	.learn button {
		margin-left: auto;
	}
	.dot {
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 50%;
		background: var(--accent);
		flex: none;
		animation: pulse 1.2s ease-in-out infinite;
	}
	@keyframes pulse {
		50% {
			opacity: 0.25;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.dot {
			animation: none;
		}
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.9rem;
	}
	th,
	td {
		text-align: left;
		padding: 0.45rem 0.6rem;
		border-bottom: 1px solid var(--line);
		vertical-align: middle;
	}
	th {
		color: var(--muted);
		font-weight: 500;
	}
	td.num {
		font-weight: 700;
		width: 3rem;
	}
	td.actions {
		text-align: right;
		white-space: nowrap;
	}
	td.actions select {
		margin-right: 0.4rem;
	}
	tr.armed {
		background: #2a2414;
	}
	tr.inactive td {
		opacity: 0.6;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		background: var(--bg);
		border: 1px solid var(--line);
		border-radius: 999px;
		padding: 0.1rem 0.25rem 0.1rem 0.6rem;
		margin: 0.1rem 0.3rem 0.1rem 0;
	}
	.chip .x {
		background: transparent;
		color: var(--muted);
		padding: 0 0.35rem;
		font-weight: 400;
	}
	.chip .x:hover {
		color: #f3a1a1;
	}
	.outcome {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 0.1rem 0.45rem;
		border-radius: 999px;
		background: var(--line);
		margin-right: 0.4rem;
	}
	.outcome.played,
	.outcome.learned {
		background: #1e4d2b;
		color: #9be3ae;
	}
	.outcome.unknown {
		background: #5a4614;
		color: #f3d27a;
	}
	.outcome.failed {
		background: #5c1f1f;
		color: #f3a1a1;
	}
	@media (max-width: 40rem) {
		td.actions select {
			max-width: 7rem;
		}
	}
</style>
