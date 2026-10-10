<script lang="ts">
	import { imageUrl } from '$lib/api';
	import { formatCinemaDate, formatRuntime } from '$lib/cinema/api';
	import { cinema } from '$lib/cinema/state.svelte';
	import {
		AISLES_AFTER,
		MAX_SEATS,
		SEAT_ROWS,
		SEATS_PER_ROW,
		bookedSeats,
		ticketNumber as makeTicketNumber,
		ticketTime
	} from '$lib/cinema/tickets';

	let { room: roomNumber }: { room: number } = $props();

	const programme = $derived(cinema.programme);
	const room = $derived(programme?.rooms.find((r) => r.number === roomNumber));
	const item = $derived(room?.item);

	const booked = $derived(programme && room ? bookedSeats(programme.date, room) : new Set<string>());

	let selected = $state<string[]>([]);
	let step = $state<'seats' | 'ticket'>('seats');
	let error = $state<string | null>(null);
	let starting = $state(false);

	const showtime = $derived(programme && room ? ticketTime(programme.date, room) : 'Now');

	function toggle(seat: string) {
		if (booked.has(seat)) return;
		if (selected.includes(seat)) selected = selected.filter((s) => s !== seat);
		else if (selected.length < MAX_SEATS) selected = [...selected, seat].sort();
	}

	async function startShow() {
		starting = true;
		error = null;
		try {
			await cinema.play(roomNumber);
		} catch (e) {
			error = (e as Error).message;
		} finally {
			starting = false;
		}
	}

	const ticketNumber = $derived(programme ? makeTicketNumber(programme.date, roomNumber, selected) : '');
</script>

<svelte:head><title>Tickets · {cinema.name}</title></svelte:head>

{#if !programme}
	<p class="loading">Opening the box office…</p>
{:else if !room || !item}
	<div class="empty">
		<h1>No screening</h1>
		<p>Auditorium {roomNumber} has nothing on today's programme.</p>
		<a class="btn" href="/">Back to the programme</a>
	</div>
{:else}
	<div class="page">
		<aside class="summary">
			<img src={imageUrl(item.id, 'Primary', item.poster_tag, 400)} alt="" />
			<div>
				<p class="eyebrow">{room.kind === 'movie' ? 'Auditorium' : 'Lounge'} {room.number} · {room.name}</p>
				<h1>{item.name}</h1>
				<p class="muted">{[item.year, formatRuntime(item.runtime_minutes), item.official_rating].filter(Boolean).join(' · ')}</p>
				<p class="muted">{formatCinemaDate(programme.date)} · {showtime}</p>
			</div>
		</aside>

		{#if step === 'seats'}
			<section class="seating">
				<ol class="steps"><li class="active">1 · Seats</li><li>2 · Ticket</li></ol>
				{#if room.sold_out}
					<p class="notice">Sold out — but the house always keeps one seat for you.</p>
				{/if}
				<div class="screen">Screen</div>
				<div class="hall" role="group" aria-label="Seat map">
					{#each SEAT_ROWS as row}
						<div class="row">
							<span class="row-label">{row}</span>
							{#each Array.from({ length: SEATS_PER_ROW }, (_, i) => i + 1) as seat}
								{@const id = `${row}${seat}`}
								<button
									class="seat"
									class:taken={booked.has(id)}
									class:mine={selected.includes(id)}
									class:aisle={AISLES_AFTER.has(seat)}
									disabled={booked.has(id)}
									aria-pressed={selected.includes(id)}
									aria-label="Row {row} seat {seat}{booked.has(id) ? ' (taken)' : ''}"
									onclick={() => toggle(id)}
								></button>
							{/each}
							<span class="row-label">{row}</span>
						</div>
					{/each}
				</div>
				<div class="legend">
					<span><i class="seat"></i> Free</span>
					<span><i class="seat mine"></i> Yours</span>
					<span><i class="seat taken"></i> Taken</span>
				</div>
				<div class="footer">
					<p>{selected.length ? `${selected.length} seat${selected.length > 1 ? 's' : ''}: ${selected.join(', ')}` : 'Pick your seats'}</p>
					<button class="btn primary" disabled={!selected.length} onclick={() => (step = 'ticket')}>Continue</button>
				</div>
			</section>
		{:else}
			<section class="ticket-step">
				<ol class="steps"><li>1 · Seats</li><li class="active">2 · Ticket</li></ol>
				<div class="ticket">
					<div class="stub-main">
						<p class="brand">{cinema.name}</p>
						<h2>{item.name}</h2>
						<dl>
							<div><dt>Date</dt><dd>{formatCinemaDate(programme.date)}</dd></div>
							<div><dt>Time</dt><dd>{showtime}</dd></div>
							<div><dt>{room.kind === 'movie' ? 'Auditorium' : 'Lounge'}</dt><dd>{room.number}</dd></div>
							<div><dt>Seats</dt><dd>{selected.join(', ')}</dd></div>
						</dl>
						<p class="price">€ 0,00 · Members' screening</p>
					</div>
					<div class="stub-tear">
						<span class="admit">Admit {selected.length}</span>
						<span class="barcode" aria-hidden="true"></span>
						<span class="number">{ticketNumber}</span>
					</div>
				</div>
				<div class="footer">
					<button class="btn" onclick={() => (step = 'seats')}>Change seats</button>
					<button class="btn primary big" disabled={starting} onclick={startShow}>
						{starting ? 'Starting…' : room.kind === 'movie' ? 'Start the show' : 'Start next episode'}
					</button>
				</div>
				{#if error}<p class="error">{error}</p>{/if}
			</section>
		{/if}
	</div>
{/if}

<style>
	.loading,
	.empty {
		padding: 6rem 1rem;
		text-align: center;
		color: var(--muted);
	}
	.page {
		display: grid;
		grid-template-columns: minmax(14rem, 20rem) 1fr;
		gap: clamp(1.5rem, 4vw, 3.5rem);
		padding: 2.5rem clamp(1rem, 4vw, 3rem);
		max-width: 80rem;
		margin: 0 auto;
	}
	.summary {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.summary img {
		width: 100%;
		border-radius: 0.6rem;
		box-shadow: 0 1rem 2.5rem rgb(0 0 0 / 0.5);
	}
	.eyebrow {
		text-transform: uppercase;
		letter-spacing: 0.18em;
		font-size: 0.72rem;
		font-weight: 600;
		color: var(--accent);
		margin: 0;
	}
	h1 {
		font-family: var(--display);
		text-transform: uppercase;
		font-size: 2rem;
		line-height: 1;
		margin: 0.4rem 0;
	}
	.muted {
		color: var(--muted);
		margin: 0.2rem 0;
		font-size: 0.9rem;
	}
	.steps {
		list-style: none;
		padding: 0;
		margin: 0 0 1.5rem;
		display: flex;
		gap: 1.5rem;
		color: var(--muted);
		font-weight: 600;
		font-size: 0.9rem;
	}
	.steps .active {
		color: var(--text);
		border-bottom: 2px solid var(--accent);
		padding-bottom: 0.3rem;
	}
	.notice {
		color: var(--gold);
	}
	.screen {
		margin: 0 auto 2.5rem;
		width: 80%;
		text-align: center;
		text-transform: uppercase;
		letter-spacing: 0.5em;
		font-size: 0.7rem;
		color: var(--muted);
		padding-top: 0.6rem;
		border-top: 4px solid rgb(255 255 255 / 0.5);
		border-radius: 50% 50% 0 0 / 1.2rem 1.2rem 0 0;
		box-shadow: 0 -1.5rem 2.5rem -1rem rgb(255 255 255 / 0.25);
	}
	.hall {
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
		align-items: center;
		overflow-x: auto;
		padding-bottom: 0.5rem;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 0.35rem;
	}
	.row-label {
		width: 1.2rem;
		text-align: center;
		color: var(--muted);
		font-size: 0.75rem;
		font-weight: 600;
	}
	.seat {
		width: 1.7rem;
		height: 1.5rem;
		padding: 0;
		border: 0;
		border-radius: 0.4rem 0.4rem 0.2rem 0.2rem;
		background: #4a4a66;
		box-shadow: inset 0 -3px 0 rgb(0 0 0 / 0.35);
		cursor: pointer;
		transition: background 0.12s, transform 0.12s;
	}
	button.seat:hover:not(:disabled) {
		background: #6b6b8f;
		transform: translateY(-1px);
	}
	.seat.aisle {
		margin-right: 1.2rem;
	}
	.seat.taken {
		background:
			linear-gradient(45deg, transparent 45%, rgb(255 255 255 / 0.12) 45% 55%, transparent 55%),
			#1b1b24;
		box-shadow: none;
		cursor: not-allowed;
	}
	.seat.mine {
		background: var(--accent);
	}
	.legend {
		display: flex;
		justify-content: center;
		gap: 1.5rem;
		margin-top: 1.25rem;
		color: var(--muted);
		font-size: 0.85rem;
	}
	.legend span {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.legend .seat {
		display: inline-block;
		width: 1.1rem;
		height: 0.95rem;
		cursor: default;
	}
	.footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-top: 2rem;
		padding-top: 1.25rem;
		border-top: 1px solid var(--line);
	}
	.footer p {
		margin: 0;
		font-weight: 600;
	}
	.btn {
		padding: 0.7rem 1.4rem;
		border-radius: 999px;
		font: inherit;
		font-weight: 600;
		text-decoration: none;
		color: var(--text);
		background: var(--surface-2);
		border: 1px solid var(--line);
		cursor: pointer;
	}
	.btn.primary {
		background: var(--accent);
		border-color: var(--accent);
	}
	.btn.big {
		padding: 0.9rem 2rem;
		font-size: 1.05rem;
	}
	.btn:disabled {
		opacity: 0.45;
		cursor: default;
	}
	.ticket {
		display: grid;
		grid-template-columns: 1fr 11rem;
		max-width: 44rem;
		border-radius: 0.9rem;
		overflow: hidden;
		background: linear-gradient(135deg, #fdf8ee, #f3ead6);
		color: #1d1a14;
		box-shadow: 0 1.5rem 3rem rgb(0 0 0 / 0.5);
		animation: print 0.6s ease-out;
	}
	@keyframes print {
		from {
			transform: translateY(1rem) rotate(-1deg);
			opacity: 0;
		}
	}
	.stub-main {
		padding: 1.5rem 1.75rem;
	}
	.brand {
		margin: 0;
		font-family: var(--display);
		text-transform: uppercase;
		letter-spacing: 0.2em;
		color: var(--accent);
		font-size: 0.85rem;
	}
	.ticket h2 {
		font-family: var(--display);
		text-transform: uppercase;
		font-size: 2rem;
		line-height: 1;
		margin: 0.5rem 0 1.25rem;
	}
	.ticket dl {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.75rem 1.5rem;
		margin: 0;
	}
	.ticket dt {
		text-transform: uppercase;
		font-size: 0.65rem;
		letter-spacing: 0.15em;
		color: #7a7262;
	}
	.ticket dd {
		margin: 0.15rem 0 0;
		font-weight: 700;
	}
	.price {
		margin: 1.25rem 0 0;
		font-size: 0.8rem;
		color: #7a7262;
	}
	.stub-tear {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		padding: 1.25rem 1rem;
		border-left: 2px dashed #cdbf9f;
	}
	.stub-tear::before,
	.stub-tear::after {
		content: '';
		position: absolute;
		left: -0.75rem;
		width: 1.4rem;
		height: 1.4rem;
		border-radius: 50%;
		background: var(--bg);
	}
	.stub-tear::before {
		top: -0.7rem;
	}
	.stub-tear::after {
		bottom: -0.7rem;
	}
	.admit {
		font-family: var(--display);
		text-transform: uppercase;
		font-size: 1.3rem;
	}
	.barcode {
		width: 100%;
		height: 3.5rem;
		background: repeating-linear-gradient(
			90deg,
			#1d1a14 0 2px,
			transparent 2px 4px,
			#1d1a14 4px 5px,
			transparent 5px 8px,
			#1d1a14 8px 11px,
			transparent 11px 12px
		);
	}
	.number {
		font-family: ui-monospace, monospace;
		font-size: 0.65rem;
		color: #7a7262;
		word-break: break-all;
		text-align: center;
	}
	.error {
		color: #ff8a9b;
	}
	@media (max-width: 760px) {
		.page {
			grid-template-columns: 1fr;
		}
		.summary {
			flex-direction: row;
		}
		.summary img {
			width: 7rem;
		}
		.ticket {
			grid-template-columns: 1fr;
		}
		.stub-tear {
			border-left: 0;
			border-top: 2px dashed #cdbf9f;
		}
		.seat {
			width: 1.2rem;
			height: 1.1rem;
		}
		.seat.aisle {
			margin-right: 0.6rem;
		}
	}
</style>
