<script lang="ts">
	import { imageUrl } from '$lib/api';
	import type { CinemaRoom } from '$lib/cinema/api';
	import { cinema } from '$lib/cinema/state.svelte';
	import { showtimeChips } from '$lib/cinema/tickets';

	const BILL_LINES = [
		'Two features. One ticket. No refunds.',
		'Stay for the second picture. That is where it gets good.',
		'Positively no talking during the picture.',
		'Mind the cigarette burns. They are part of the show.',
		'Bring a date. Or a briefcase. Do not open the briefcase.',
		'Sit anywhere. Except the projectionist’s seat.'
	];

	const programme = $derived(cinema.programme);
	const movieRooms = $derived(programme?.rooms.filter((r) => r.kind === 'movie') ?? []);
	const serials = $derived(programme?.rooms.filter((r) => r.kind === 'series') ?? []);
	// Auditoriums 1+2, 3+4, ... become double bills.
	const bills = $derived(
		Array.from({ length: Math.ceil(movieRooms.length / 2) }, (_, i) => movieRooms.slice(i * 2, i * 2 + 2))
	);

	const minutes = (room: CinemaRoom) => (room.item?.runtime_minutes ? `${room.item.runtime_minutes} min` : '');
</script>

{#snippet feature(room: CinemaRoom)}
	<div class="feature">
		{#if room.item}
			<a class="poster" href="/film/{room.item.id}">
				<img src={imageUrl(room.item.id, 'Primary', room.item.poster_tag, 500)} alt={room.item.name} loading="lazy" />
				{#if room.sold_out}<span class="stamp">Sold out</span>{/if}
			</a>
			<div class="text">
			<p class="room">Auditorium {room.number} · {room.name}</p>
			<h3><a href="/film/{room.item.id}">{room.item.name}</a></h3>
			<p class="facts">{[room.item.year, minutes(room), room.item.official_rating].filter(Boolean).join(' · ')}</p>
			<p class="shows">
				Shows
				{#each showtimeChips(programme!.date, room.showtimes) as chip, i}
					{#if i}·{/if}
					<span class={chip.state}>{chip.label}</span>
				{/each}
			</p>
			<a class="admit" href="/tickets/{room.number}">Admit one ▸</a>
			</div>
		{:else}
			<div class="poster missing">
				<span>Missing reel</span>
				<small>The projectionist is looking into it.</small>
			</div>
			<div class="text">
				<p class="room">Auditorium {room.number} · {room.name}</p>
				<h3>Dark tonight</h3>
			</div>
		{/if}
	</div>
{/snippet}

{#if !programme}
	<p class="loading">Threading the reels…</p>
{:else}
	<section id="bills">
		{#each bills as bill, i}
			<article class="bill sheet" class:single={bill.length === 1}>
				<header>
					<span class="ribbon">{bill.length === 2 ? 'Double feature' : 'Special engagement'}</span>
				</header>
				<div class="features">
					{@render feature(bill[0])}
					{#if bill[1]}
						<span class="plus" aria-hidden="true">Plus!</span>
						{@render feature(bill[1])}
					{/if}
				</div>
				<p class="line">{BILL_LINES[i % BILL_LINES.length]}</p>
			</article>
		{/each}
	</section>

	{#if serials.length}
		<section id="serials">
			<h2>Serials · a new chapter every night</h2>
			<div class="serials">
				{#each serials as room (room.number)}
					<article class="serial sheet">
						{#if room.item}
							<a class="lobby" href="/film/{room.item.id}">
								<img
									src={imageUrl(room.item.id, room.item.backdrop_tag ? 'Backdrop' : 'Primary', room.item.backdrop_tag ?? room.item.poster_tag, 700)}
									alt=""
									loading="lazy"
								/>
								{#if room.sticky}<span class="stamp small">Now serialized</span>{/if}
							</a>
							<div class="serial-body">
								<p class="room">Lounge {room.number} · {room.name}</p>
								<h3><a href="/film/{room.item.id}">{room.item.name}</a></h3>
								<p class="facts">
									{room.item.unplayed_count != null ? `${room.item.unplayed_count} chapters to go` : 'A serial'}
								</p>
								<a class="admit" href="/tickets/{room.number}">Next chapter ▸</a>
							</div>
						{:else}
							<div class="serial-body">
								<p class="room">Lounge {room.number} · {room.name}</p>
								<h3>Dark tonight</h3>
							</div>
						{/if}
					</article>
				{/each}
			</div>
		</section>
	{/if}

	<section id="concessions" class="concessions sheet">
		<h2>Concession stand</h2>
		<ul>
			<li><span>Royale with Cheese</span><i></i><span>$2.50</span></li>
			<li><span>Big Kahuna Burger</span><i></i><span>$3.00</span></li>
			<li><span>Five-dollar shake</span><i></i><span>$5.00</span></li>
			<li><span>Buttered popcorn, large</span><i></i><span>$1.25</span></li>
			<li><span>Red Apple tobacco</span><i></i><span>props only</span></li>
		</ul>
		<p>Twist contest at Jack Rabbit Slim’s · Fridays after the late show</p>
	</section>
{/if}

<style>
	.loading {
		color: var(--paper);
		text-align: center;
		padding: 4rem;
	}
	section {
		scroll-margin-top: 1rem;
	}
	#bills {
		display: grid;
		gap: 2.5rem;
	}
	.bill {
		padding: 1.25rem clamp(1rem, 3vw, 2.5rem) 1.5rem;
		transform: rotate(-0.4deg);
	}
	.bill:nth-child(even) {
		transform: rotate(0.5deg);
	}
	.bill header {
		text-align: center;
		margin-bottom: 1.25rem;
	}
	.ribbon {
		display: inline-block;
		font-family: var(--display);
		text-transform: uppercase;
		font-size: clamp(1.4rem, 3.5vw, 2.4rem);
		color: var(--paper);
		background: var(--red);
		padding: 0.25rem 1.5rem;
		box-shadow: 0.25rem 0.25rem 0 var(--ink);
	}
	.features {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		gap: 1.5rem;
		align-items: start;
	}
	.single .features {
		grid-template-columns: minmax(0, 28rem);
		justify-content: center;
	}
	.plus {
		align-self: center;
		width: 4.5rem;
		height: 4.5rem;
		display: grid;
		place-items: center;
		border-radius: 50%;
		background: var(--mustard);
		color: var(--ink);
		font-family: var(--display);
		text-transform: uppercase;
		font-size: 0.95rem;
		transform: rotate(-12deg);
		box-shadow: 0.2rem 0.2rem 0 var(--ink);
	}
	.feature {
		display: grid;
		grid-template-columns: minmax(8rem, 13rem) 1fr;
		gap: 1.1rem;
		align-items: start;
		min-width: 0;
	}
	.text {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		min-width: 0;
	}
	.poster {
		position: relative;
		display: block;
		aspect-ratio: 2 / 3;
		overflow: hidden;
		border: 6px solid var(--ink);
		background: var(--ink);
	}
	/* Screen-printed look: warm, slightly crushed colours plus a halftone dot screen. */
	.poster img,
	.lobby img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		filter: sepia(0.35) saturate(0.9) contrast(1.12);
	}
	.poster::after,
	.lobby::after {
		content: '';
		position: absolute;
		inset: 0;
		background: radial-gradient(rgb(30 23 18 / 0.35) 0.9px, transparent 1.4px) 0 0 / 4px 4px;
		mix-blend-mode: multiply;
		pointer-events: none;
	}
	.poster.missing {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		text-align: center;
		color: var(--paper);
		background: repeating-linear-gradient(45deg, #2b211a 0 14px, #231a14 14px 28px);
	}
	.missing span {
		font-family: var(--display);
		text-transform: uppercase;
		font-size: 1.15rem;
		border: 3px solid var(--paper);
		padding: 0.3rem 0.9rem;
		transform: rotate(-6deg);
	}
	.missing small {
		font-size: 0.8rem;
		max-width: 14rem;
	}
	.stamp {
		position: absolute;
		top: 40%;
		left: 50%;
		transform: translate(-50%, -50%) rotate(-14deg);
		z-index: 1;
		font-family: var(--display);
		text-transform: uppercase;
		font-size: 1.3rem;
		color: var(--red);
		border: 4px solid var(--red);
		padding: 0.2rem 0.8rem;
		background: rgb(239 226 196 / 0.85);
		white-space: nowrap;
	}
	.stamp.small {
		font-size: 1rem;
		top: 1rem;
		left: auto;
		right: 0.75rem;
		transform: rotate(6deg);
		border-width: 3px;
	}
	.room {
		margin: 0;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.18em;
		font-size: 0.75rem;
		color: var(--red);
	}
	h3 {
		margin: 0;
		font-family: var(--display);
		text-transform: uppercase;
		font-size: clamp(1.3rem, 2.4vw, 1.9rem);
		line-height: 1.05;
	}
	h3 a {
		text-decoration: none;
	}
	.facts {
		margin: 0;
		color: var(--ink-soft);
		font-size: 0.9rem;
	}
	.shows {
		margin: 0.2rem 0;
		font-size: 0.9rem;
	}
	.shows .past {
		color: var(--ink-soft);
		opacity: 0.6;
	}
	.shows .next {
		font-weight: 700;
		background: var(--mustard);
		padding: 0 0.3rem;
	}
	.admit {
		align-self: flex-start;
		margin-top: 0.4rem;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.2em;
		font-size: 0.9rem;
		text-decoration: none;
		color: var(--paper);
		background: var(--ink);
		padding: 0.45rem 0.9rem;
	}
	.admit:hover {
		background: var(--red);
	}
	.line {
		margin: 1.5rem 0 0;
		text-align: center;
		font-style: italic;
		color: var(--ink-soft);
		border-top: 2px dashed var(--ink-soft);
		padding-top: 0.9rem;
	}
	h2 {
		font-family: var(--display);
		text-transform: uppercase;
		color: var(--paper);
		text-align: center;
		font-size: clamp(1.5rem, 3vw, 2.2rem);
		margin: 3.5rem 0 1.5rem;
		text-shadow: 0.15rem 0.15rem 0 var(--red);
	}
	.serials {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(19rem, 100%), 1fr));
		gap: 1.5rem;
	}
	.serial {
		padding: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}
	.lobby {
		position: relative;
		display: block;
		aspect-ratio: 16 / 9;
		overflow: hidden;
		border: 4px solid var(--ink);
	}
	.serial-body {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		padding: 0 0.25rem 0.25rem;
	}
	.concessions {
		margin-top: 3.5rem;
		max-width: 34rem;
		margin-inline: auto;
		padding: 1rem 2rem 1.5rem;
		transform: rotate(0.6deg);
	}
	.concessions h2 {
		color: var(--ink);
		text-shadow: none;
		margin: 0.5rem 0 1rem;
	}
	.concessions ul {
		list-style: none;
		padding: 0;
		margin: 0;
	}
	.concessions li {
		display: flex;
		gap: 0.5rem;
		padding: 0.25rem 0;
	}
	.concessions i {
		flex: 1;
		border-bottom: 2px dotted var(--ink-soft);
		margin-bottom: 0.3rem;
	}
	.concessions p {
		text-align: center;
		margin: 1.25rem 0 0;
		font-size: 0.85rem;
		color: var(--red);
	}
	@media (max-width: 1000px) {
		.features {
			grid-template-columns: 1fr;
		}
	}
	@media (max-width: 480px) {
		.feature {
			grid-template-columns: 7rem 1fr;
		}
	}
	@media (max-width: 1000px) {
		.plus {
			justify-self: center;
		}
	}
</style>
