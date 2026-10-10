<script lang="ts">
	import { imageUrl } from '$lib/api';
	import { formatCinemaDate } from '$lib/cinema/api';
	import { cinema } from '$lib/cinema/state.svelte';
	import {
		AISLES_AFTER,
		MAX_SEATS,
		SEAT_ROWS,
		SEATS_PER_ROW,
		bookedSeats,
		ticketNumber,
		ticketTime
	} from '$lib/cinema/tickets';

	let { room: roomNumber }: { room: number } = $props();

	let selected = $state<string[]>([]);
	let step = $state<'seats' | 'ticket'>('seats');
	let starting = $state(false);
	let error = $state<string | null>(null);

	const programme = $derived(cinema.programme);
	const room = $derived(programme?.rooms.find((r) => r.number === roomNumber));
	const item = $derived(room?.item);
	const booked = $derived(programme && room ? bookedSeats(programme.date, room) : new Set<string>());
	const time = $derived(programme && room ? ticketTime(programme.date, room) : 'Now');
	const serial = $derived(programme ? ticketNumber(programme.date, roomNumber, selected).replaceAll('-', ' ') : '');

	function toggle(seat: string) {
		if (booked.has(seat)) return;
		if (selected.includes(seat)) selected = selected.filter((s) => s !== seat);
		else if (selected.length < MAX_SEATS) selected = [...selected, seat].sort();
	}

	async function roll() {
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
</script>

<svelte:head><title>Box office · {cinema.name}</title></svelte:head>

{#if !programme}
	<p class="loading">Opening the box office…</p>
{:else if !room || !item}
	<div class="sheet closed">
		<h1>Dark tonight</h1>
		<p>Auditorium {roomNumber} has nothing on the bill. Missing reel, probably.</p>
		<a href="/">◂ Back to tonight's bill</a>
	</div>
{:else}
	<a class="back" href="/">◂ Back to tonight's bill</a>
	<div class="box-office sheet">
		<header>
			<img src={imageUrl(item.id, 'Primary', item.poster_tag, 300)} alt="" />
			<div>
				<p class="kicker">Box office · {room.kind === 'movie' ? 'Auditorium' : 'Lounge'} {room.number}</p>
				<h1>{item.name}</h1>
				<p>{formatCinemaDate(programme.date)} · {time}</p>
			</div>
		</header>

		{#if step === 'seats'}
			{#if room.sold_out}<p class="notice">Sold out. The house keeps one seat for its best customer. That’s you.</p>{/if}
			<div class="curtain"><span>Screen</span></div>
			<div class="hall" role="group" aria-label="Seat map">
				{#each SEAT_ROWS as row}
					<div class="row">
						<span class="label">{row}</span>
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
							>{seat}</button>
						{/each}
						<span class="label">{row}</span>
					</div>
				{/each}
			</div>
			<p class="legend"><i class="seat"></i> free <i class="seat mine"></i> yours <i class="seat taken"></i> taken</p>
			<div class="footer">
				<p>{selected.length ? `Seats ${selected.join(', ')}` : 'Pick your seats, then step up to the window.'}</p>
				<button class="go" disabled={!selected.length} onclick={() => (step = 'ticket')}>Print ticket ▸</button>
			</div>
		{:else}
			<div class="ticket" aria-label="Your ticket">
				<p class="house">{cinema.name}</p>
				<p class="admit">Admit {selected.length === 1 ? 'one' : selected.length}</p>
				<p class="film">{item.name}</p>
				<p class="detail">{formatCinemaDate(programme.date)} · {time} · Aud. {room.number} · Seats {selected.join(' ')}</p>
				<p class="serial">No. {serial}</p>
				<p class="keep">Keep this coupon · Not transferable · No refunds</p>
			</div>
			<div class="footer">
				<button class="ghost" onclick={() => (step = 'seats')}>◂ Other seats</button>
				<button class="go" disabled={starting} onclick={roll}>
					{starting ? 'Threading…' : room.kind === 'movie' ? 'Roll the film ▸' : 'Roll the next chapter ▸'}
				</button>
			</div>
			{#if error}<p class="error">{error}</p>{/if}
		{/if}
	</div>
{/if}

<style>
	.loading {
		color: var(--paper);
		text-align: center;
		padding: 4rem;
	}
	.back {
		display: inline-block;
		margin-bottom: 1rem;
		color: var(--paper);
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.15em;
		text-decoration: none;
		font-size: 0.85rem;
	}
	.closed,
	.box-office {
		max-width: 56rem;
		margin: 0 auto;
		padding: clamp(1rem, 3vw, 2rem);
	}
	.closed {
		text-align: center;
	}
	header {
		display: flex;
		gap: 1.25rem;
		align-items: center;
		border-bottom: 3px double var(--ink);
		padding-bottom: 1rem;
		margin-bottom: 1.5rem;
	}
	header img {
		width: 5rem;
		border: 4px solid var(--ink);
		filter: sepia(0.3) contrast(1.1);
	}
	.kicker {
		margin: 0;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.2em;
		font-size: 0.8rem;
		color: var(--red);
	}
	h1 {
		margin: 0.2rem 0;
		font-family: var(--display);
		text-transform: uppercase;
		font-size: clamp(1.6rem, 4vw, 2.6rem);
		line-height: 1;
	}
	header p {
		margin: 0.2rem 0 0;
	}
	.notice {
		text-align: center;
		color: var(--red);
		font-weight: 700;
	}
	.curtain {
		height: 2.2rem;
		margin: 0 auto 2rem;
		width: 85%;
		display: grid;
		place-items: center;
		background: repeating-linear-gradient(90deg, #8e1820 0 10px, #b5202b 10px 20px);
		box-shadow: 0 0.4rem 0 var(--ink);
	}
	.curtain span {
		font-family: var(--display);
		text-transform: uppercase;
		letter-spacing: 0.4em;
		color: var(--paper);
		font-size: 0.85rem;
	}
	.hall {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.35rem;
		overflow-x: auto;
		padding-bottom: 0.5rem;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}
	.label {
		width: 1.2rem;
		text-align: center;
		font-weight: 700;
		font-size: 0.8rem;
	}
	.seat {
		width: 1.75rem;
		height: 1.75rem;
		padding: 0;
		border: 2px solid var(--ink);
		border-radius: 0.6rem 0.6rem 0.25rem 0.25rem;
		background: var(--red);
		color: rgb(239 226 196 / 0.75);
		font-family: var(--type);
		font-size: 0.6rem;
		cursor: pointer;
	}
	button.seat:hover:not(:disabled) {
		background: #d8323d;
	}
	.seat.aisle {
		margin-right: 1.1rem;
	}
	.seat.taken {
		background: #6d5a49;
		color: transparent;
		cursor: not-allowed;
		opacity: 0.55;
	}
	.seat.mine {
		background: var(--mustard);
		color: var(--ink);
		font-weight: 700;
	}
	.legend {
		display: flex;
		justify-content: center;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.8rem;
	}
	.legend .seat {
		display: inline-block;
		width: 1rem;
		height: 1rem;
		margin-left: 0.75rem;
		cursor: default;
	}
	.footer {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
		margin-top: 1.5rem;
		border-top: 2px dashed var(--ink-soft);
		padding-top: 1rem;
	}
	.footer p {
		margin: 0;
		font-weight: 700;
	}
	.go,
	.ghost {
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.18em;
		font-size: 1rem;
		padding: 0.7rem 1.3rem;
		cursor: pointer;
	}
	.go {
		background: var(--red);
		color: var(--paper);
		border: 0;
		box-shadow: 0.2rem 0.2rem 0 var(--ink);
	}
	.go:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.ghost {
		background: none;
		border: 2px solid var(--ink);
		color: var(--ink);
	}
	/* The classic red roll ticket. */
	.ticket {
		position: relative;
		max-width: 26rem;
		margin: 0.5rem auto;
		padding: 1.5rem 2rem;
		text-align: center;
		color: #fff4dc;
		background: #c22a33;
		border: 3px solid #fff4dc;
		outline: 6px solid #c22a33;
		transform: rotate(-2deg);
		box-shadow: 0.6rem 0.8rem 0 rgb(0 0 0 / 0.25);
		mask: radial-gradient(circle at 0 50%, transparent 0.8rem, #000 0.85rem) left / 51% 100% no-repeat,
			radial-gradient(circle at 100% 50%, transparent 0.8rem, #000 0.85rem) right / 51% 100% no-repeat;
	}
	.ticket p {
		margin: 0.25rem 0;
	}
	.house {
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.3em;
		font-size: 0.8rem;
	}
	.admit {
		font-family: var(--display);
		text-transform: uppercase;
		font-size: 2.8rem;
		line-height: 1;
	}
	.film {
		font-family: var(--condensed);
		text-transform: uppercase;
		font-size: 1.2rem;
		letter-spacing: 0.08em;
	}
	.detail,
	.keep {
		font-size: 0.75rem;
	}
	.serial {
		font-weight: 700;
		letter-spacing: 0.2em;
	}
	.error {
		color: var(--red);
		font-weight: 700;
	}
	@media (max-width: 640px) {
		.seat {
			width: 1.25rem;
			height: 1.25rem;
			font-size: 0;
		}
		.seat.aisle {
			margin-right: 0.5rem;
		}
	}
</style>
