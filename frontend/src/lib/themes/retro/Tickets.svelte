<script lang="ts">
	import { imageUrl } from '$lib/api';
	import { formatCinemaDate, type CinemaItem } from '$lib/cinema/api';
	import { cinema } from '$lib/cinema/state.svelte';
	import { chapterLine } from './chapter';
	import {
		AISLES_AFTER,
		MAX_SEATS,
		SEAT_ROWS,
		SEATS_PER_ROW,
		bookedSeats,
		ticketNumber,
		ticketTime
	} from '$lib/cinema/tickets';

	let { room: roomNumber, next = false }: { room: number; next?: boolean } = $props();

	let selected = $state<string[]>([]);
	let step = $state<'seats' | 'ticket'>('seats');
	let starting = $state(false);
	let error = $state<string | null>(null);

	const programme = $derived(cinema.programme);
	const room = $derived(programme?.rooms.find((r) => r.number === roomNumber));
	/** Once the reel rolls, the room moves on to the following part: keep this ticket as printed. */
	let frozen = $state<CinemaItem | null>(null);
	const item = $derived(frozen ?? (next ? room?.next : room?.item));
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
		frozen = item ?? null;
		try {
			await cinema.play(roomNumber, next);
		} catch (e) {
			error = (e as Error).message;
			frozen = null;
		} finally {
			starting = false;
		}
	}
</script>

<svelte:head><title>Box office · {cinema.name}</title></svelte:head>

{#if !programme}
	<p class="loading">Opening the box office…</p>
{:else if room && next && !item}
	<div class="booth closed">
		<h1>No reel to follow</h1>
		<p>{room.name} has nothing held over right now.</p>
		<a href="/tickets/{room.number}">◂ Back to the box office</a>
	</div>
{:else if !room || !item}
	<div class="booth closed">
		<h1>Dark tonight</h1>
		<p>Auditorium {roomNumber} has nothing on the bill. Missing reel, probably.</p>
		<a href="/">◂ Back to tonight's bill</a>
	</div>
{:else}
	<a class="back" href="/">◂ Back to tonight's bill</a>
	<div class="booth">
		<p class="booth-sign">Box Office</p>
		<header>
			<img src={imageUrl(item.id, 'Primary', item.poster_tag, 300)} alt="" />
			<div>
				<p class="kicker">
					{next ? 'Held over · Auditorium' : room.kind === 'movie' ? 'Auditorium' : 'Lounge'} {room.number} · {room.name}
				</p>
				<h1>{item.name}</h1>
				{#if item.franchise}<p class="chapter neon pink">{chapterLine(item.franchise)}</p>{/if}
				<p>{formatCinemaDate(programme.date)} · {time}</p>
			</div>
		</header>

		{#if step === 'seats'}
			{#if next}
				<p class="notice">The marathon rolls on. Keep your seat, the next reel is threading.</p>
			{:else if room.sold_out}
				<p class="notice">Sold out. The house keeps one seat for its best customer. That’s you.</p>
			{/if}
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
				{#if item.franchise?.part}<p class="detail">{chapterLine(item.franchise)}</p>{/if}
				<p class="detail">{formatCinemaDate(programme.date)} · {time} · Aud. {room.number} · Seats {selected.join(' ')}</p>
				<p class="serial">No. {serial}</p>
				<p class="keep">Keep this coupon · Not transferable · No refunds</p>
			</div>
			<div class="footer">
				<button class="ghost" onclick={() => (step = 'seats')}>◂ Other seats</button>
				<button class="go" disabled={starting} onclick={roll}>
					{starting ? 'Threading…' : next ? 'Roll the next reel ▸' : room.kind === 'movie' ? 'Roll the film ▸' : 'Roll the next chapter ▸'}
				</button>
			</div>
			{#if error}<p class="error">{error}</p>{/if}
		{/if}
	</div>
{/if}

<style>
	.loading {
		color: var(--muted);
		text-align: center;
		padding: 4rem;
	}
	.back {
		display: inline-block;
		margin-bottom: 1rem;
		color: var(--gold-light);
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.15em;
		text-decoration: none;
		font-size: 0.85rem;
	}
	/* The box office: a glass booth set in dark wood, lit from inside. */
	.booth {
		max-width: 58rem;
		margin: 0 auto;
		padding: clamp(1rem, 3vw, 2rem);
		border-radius: 1.5rem 1.5rem 0.5rem 0.5rem;
		border: 10px solid #3a2414;
		background:
			linear-gradient(115deg, rgb(255 255 255 / 0.07), transparent 25% 70%, rgb(255 255 255 / 0.04)),
			radial-gradient(ellipse at top, rgb(255 200 120 / 0.14), transparent 60%),
			#120d10;
		box-shadow:
			0 0 0 2px #8a6324,
			0 0 3rem rgb(255 190 80 / 0.15),
			0 1.5rem 3rem rgb(0 0 0 / 0.7);
	}
	.booth.closed {
		text-align: center;
	}
	.booth-sign {
		margin: 0 0 1.25rem;
		text-align: center;
		font-family: var(--display);
		text-transform: uppercase;
		letter-spacing: 0.15em;
		font-size: clamp(1.4rem, 3vw, 2rem);
		/* gold leaf on glass */
		background: linear-gradient(#fff2c2, #e7b75a 45%, #9c6f24 55%, #f5d27a);
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
		filter: drop-shadow(0 0 0.5rem rgb(231 183 90 / 0.35));
	}
	header {
		display: flex;
		gap: 1.25rem;
		align-items: center;
		border-bottom: 1px solid rgb(231 183 90 / 0.35);
		padding-bottom: 1rem;
		margin-bottom: 1.5rem;
	}
	header img {
		width: 5rem;
		border: 3px solid var(--gold);
	}
	.kicker {
		margin: 0;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.2em;
		font-size: 0.8rem;
		color: var(--gold);
	}
	h1 {
		margin: 0.2rem 0;
		font-family: var(--display);
		font-weight: 400;
		text-transform: uppercase;
		font-size: clamp(1.6rem, 4vw, 2.6rem);
		line-height: 1;
		color: var(--cream);
	}
	header p {
		margin: 0.2rem 0 0;
		color: var(--muted);
	}
	.chapter {
		margin: 0.2rem 0 0.4rem;
		font-size: 1.3rem;
		line-height: 1.1;
	}
	.notice {
		text-align: center;
		color: var(--gold-light);
	}
	.curtain {
		height: 2.2rem;
		margin: 0 auto 2rem;
		width: 85%;
		display: grid;
		place-items: center;
		background: repeating-linear-gradient(90deg, #7a141c 0 10px, #a51d27 10px 20px);
		box-shadow:
			0 0.4rem 0 #3a2414,
			0 0 2rem rgb(255 58 76 / 0.25);
	}
	.curtain span {
		font-family: var(--display);
		text-transform: uppercase;
		letter-spacing: 0.4em;
		color: var(--cream);
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
		color: var(--gold);
	}
	.seat {
		width: 1.75rem;
		height: 1.75rem;
		padding: 0;
		border: 2px solid #3a0a0e;
		border-radius: 0.6rem 0.6rem 0.25rem 0.25rem;
		background: linear-gradient(#c62a35, #8e1820);
		color: rgb(246 236 210 / 0.7);
		font-family: var(--type);
		font-size: 0.6rem;
		cursor: pointer;
	}
	button.seat:hover:not(:disabled) {
		background: linear-gradient(#e23b47, #a51d27);
	}
	.seat.aisle {
		margin-right: 1.1rem;
	}
	.seat.taken {
		background: #2b2226;
		border-color: #1a1416;
		color: transparent;
		cursor: not-allowed;
	}
	.seat.mine {
		background: linear-gradient(#ffe7a3, var(--gold));
		color: #1b1006;
		font-weight: 700;
		box-shadow: 0 0 0.8rem rgb(255 227 154 / 0.7);
	}
	.legend {
		display: flex;
		justify-content: center;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.8rem;
		color: var(--muted);
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
		border-top: 1px solid rgb(231 183 90 / 0.35);
		padding-top: 1rem;
	}
	.footer p {
		margin: 0;
		font-weight: 700;
		color: var(--cream);
	}
	.go,
	.ghost {
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.18em;
		font-size: 1rem;
		padding: 0.7rem 1.4rem;
		border-radius: 999px;
		cursor: pointer;
	}
	.go {
		color: #1b1006;
		background: linear-gradient(#ffe7a3, var(--gold));
		border: 0;
		box-shadow: 0 0 1.2rem rgb(231 183 90 / 0.5);
	}
	.go:disabled {
		opacity: 0.45;
		cursor: default;
	}
	.ghost {
		background: none;
		border: 2px solid var(--gold);
		color: var(--gold-light);
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
		box-shadow: 0 0 2.5rem rgb(255 58 76 / 0.35);
		mask:
			radial-gradient(circle at 0 50%, transparent 0.8rem, #000 0.85rem) left / 51% 100% no-repeat,
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
		color: var(--neon);
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
