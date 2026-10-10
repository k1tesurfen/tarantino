<script lang="ts">
	import { imageUrl } from '$lib/api';
	import type { CinemaRoom } from '$lib/cinema/api';
	import { cinema } from '$lib/cinema/state.svelte';
	import { showtimeChips } from '$lib/cinema/tickets';
	import Apple from './Apple.svelte';
	import BulbFrame from './BulbFrame.svelte';
	import { doubleBills } from './bills';

	const BILL_LINES = [
		'Two features. One ticket. No refunds.',
		'Stay for the second picture. That is where it gets good.',
		'Positively no talking during the picture.',
		'Bring a date. Or a briefcase. Do not open the briefcase.',
		'Sit anywhere. Except the projectionist’s seat.'
	];

	const programme = $derived(cinema.programme);
	const bills = $derived(programme ? doubleBills(programme.rooms) : []);
	const serials = $derived(programme?.rooms.filter((r) => r.kind === 'series') ?? []);

	const facts = (room: CinemaRoom) =>
		[room.item?.year, room.item?.runtime_minutes ? `${room.item.runtime_minutes} min` : null, room.item?.official_rating]
			.filter(Boolean)
			.join(' · ');
</script>

{#snippet feature(room: CinemaRoom)}
	<div class="feature">
		<div class="case">
			<BulbFrame step={18} chase={false}>
				{#if room.item}
					<a class="poster" href="/film/{room.item.id}">
						<img src={imageUrl(room.item.id, 'Primary', room.item.poster_tag, 500)} alt={room.item.name} loading="lazy" />
						{#if room.sold_out}<span class="sold">Sold out</span>{/if}
					</a>
				{:else}
					<div class="poster missing">
						<span class="neon">Missing reel</span>
						<small>The projectionist is looking into it.</small>
					</div>
				{/if}
			</BulbFrame>
		</div>
		<div class="info">
			<p class="room">Auditorium {room.number} · {room.name}</p>
			{#if room.item}
				<h3><a href="/film/{room.item.id}">{room.item.name}</a></h3>
				<p class="facts">{facts(room)}</p>
				<p class="shows">
					{#each showtimeChips(programme!.date, room.showtimes) as chip}
						<span class="tile {chip.state}">{chip.label}</span>
					{/each}
				</p>
				<a class="admit" href="/tickets/{room.number}">Admit one</a>
			{:else}
				<h3>Dark tonight</h3>
			{/if}
		</div>
	</div>
{/snippet}

{#if !programme}
	<p class="loading">Warming up the bulbs…</p>
{:else}
	<section id="bills">
		{#each bills as bill, i}
			<article class="bill" class:single={bill.length === 1}>
				<p class="bill-title neon pink">{bill.length === 2 ? 'Double Feature' : 'Special Engagement'}</p>
				<div class="features">
					{@render feature(bill[0])}
					{#if bill[1]}
						<span class="and neon" aria-hidden="true">&amp;</span>
						{@render feature(bill[1])}
					{/if}
				</div>
				<p class="line">{BILL_LINES[i % BILL_LINES.length]}</p>
			</article>
		{/each}
	</section>

	{#if serials.length}
		<section id="serials">
			<h2 class="neon">Serials</h2>
			<p class="sub">A new chapter every night in the lounge</p>
			<div class="serials">
				{#each serials as room (room.number)}
					<article class="serial">
						{#if room.item}
							<a class="lobby" href="/film/{room.item.id}">
								<img
									src={imageUrl(room.item.id, room.item.backdrop_tag ? 'Backdrop' : 'Primary', room.item.backdrop_tag ?? room.item.poster_tag, 700)}
									alt=""
									loading="lazy"
								/>
								{#if room.sticky}<span class="running">Now serialized</span>{/if}
							</a>
							<p class="room">{room.number} · {room.name}</p>
							<h3><a href="/film/{room.item.id}">{room.item.name}</a></h3>
							<p class="facts">
								{room.item.unplayed_count != null ? `${room.item.unplayed_count} chapters to go` : 'A serial'}
							</p>
							<a class="admit small" href="/tickets/{room.number}">Next chapter</a>
						{:else}
							<div class="lobby dark"><span class="neon">Dark tonight</span></div>
							<p class="room">{room.number} · {room.name}</p>
						{/if}
					</article>
				{/each}
			</div>
		</section>
	{/if}

	<section id="concessions">
		<h2 class="neon">Concessions</h2>
		<div class="menu">
			<Apple size={44} />
			<ul>
				<li><span>Royale with Cheese</span><i></i><span>$2.50</span></li>
				<li><span>Big Kahuna Burger</span><i></i><span>$3.00</span></li>
				<li><span>Five-dollar shake</span><i></i><span>$5.00</span></li>
				<li><span>Buttered popcorn, large</span><i></i><span>$1.25</span></li>
				<li><span>Red Apple tobacco</span><i></i><span>props only</span></li>
			</ul>
			<p>Twist contest at Jack Rabbit Slim’s · Fridays after the late show</p>
		</div>
	</section>
{/if}

<style>
	.loading {
		text-align: center;
		padding: 4rem;
		color: var(--muted);
	}
	section {
		scroll-margin-top: 1rem;
	}
	#bills {
		display: grid;
		gap: 3.5rem;
	}
	.bill {
		padding: 1.5rem clamp(1rem, 3vw, 2.5rem) 1.75rem;
		border-radius: 0.75rem;
		/* the theatre front: dark wood panelling under the warm glow */
		background:
			linear-gradient(rgb(255 200 120 / 0.06), transparent 40%),
			repeating-linear-gradient(90deg, #22150d 0 3px, #1c110b 3px 90px);
		border: 1px solid rgb(231 183 90 / 0.25);
		box-shadow: 0 1.5rem 3rem rgb(0 0 0 / 0.6);
	}
	.bill-title {
		text-align: center;
		margin: 0 0 1.5rem;
		font-size: clamp(2.2rem, 5vw, 3.4rem);
		line-height: 1;
	}
	.features {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		gap: 1.5rem;
		align-items: center;
	}
	.single .features {
		grid-template-columns: minmax(0, 36rem);
		justify-content: center;
	}
	.and {
		font-size: 4.5rem;
		line-height: 1;
	}
	.feature {
		display: grid;
		grid-template-columns: minmax(9rem, 14rem) 1fr;
		gap: 1.25rem;
		align-items: center;
		min-width: 0;
	}
	.poster {
		position: relative;
		display: block;
		aspect-ratio: 2 / 3;
		overflow: hidden;
		background: #000;
	}
	/* Backlit one-sheet behind glass: bright, warm, with a sheen across the glass. */
	.poster img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		filter: brightness(1.08) saturate(1.1) contrast(1.05);
	}
	.poster::after {
		content: '';
		position: absolute;
		inset: 0;
		background: linear-gradient(115deg, rgb(255 255 255 / 0.18), transparent 30% 65%, rgb(255 255 255 / 0.06));
		pointer-events: none;
	}
	.poster.missing {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		padding: 1rem;
		text-align: center;
		background: radial-gradient(#1d1418, #0a080b);
	}
	.missing .neon {
		font-size: 2.2rem;
		line-height: 1;
	}
	.missing small {
		color: var(--muted);
		font-size: 0.75rem;
	}
	.sold {
		position: absolute;
		top: 1.6rem;
		right: -3rem;
		z-index: 1;
		width: 12rem;
		text-align: center;
		transform: rotate(35deg);
		background: var(--red);
		color: var(--cream);
		font-family: var(--condensed);
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.15em;
		padding: 0.3rem 0;
		box-shadow: 0 0 1rem rgb(255 58 76 / 0.6);
	}
	.info {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		min-width: 0;
	}
	.room {
		margin: 0;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.2em;
		font-size: 0.75rem;
		color: var(--gold);
	}
	h3 {
		margin: 0;
		font-family: var(--display);
		font-weight: 400;
		text-transform: uppercase;
		font-size: clamp(1.3rem, 2.2vw, 1.9rem);
		line-height: 1.05;
		color: var(--cream);
		text-shadow: 0 0 1.2rem rgb(255 210 140 / 0.35);
	}
	h3 a {
		text-decoration: none;
	}
	.facts {
		margin: 0;
		color: var(--muted);
		font-size: 0.9rem;
	}
	.shows {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		margin: 0.3rem 0;
	}
	/* Showtimes as little letter-board tiles. */
	.tile {
		font-family: var(--condensed);
		font-weight: 700;
		letter-spacing: 0.08em;
		font-size: 0.85rem;
		padding: 0.15rem 0.45rem;
		background: var(--cream);
		color: #121010;
		box-shadow: inset 0 0 0.4rem rgb(255 230 170 / 0.9);
	}
	.tile.past {
		opacity: 0.4;
	}
	.tile.next {
		background: var(--gold-light);
		box-shadow: 0 0 0.8rem rgb(255 227 154 / 0.8);
	}
	.admit {
		align-self: flex-start;
		margin-top: 0.4rem;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.2em;
		font-size: 0.95rem;
		text-decoration: none;
		color: #1b1006;
		background: linear-gradient(#ffe7a3, var(--gold));
		padding: 0.5rem 1.1rem;
		border-radius: 999px;
		box-shadow: 0 0 1rem rgb(231 183 90 / 0.5);
	}
	.admit:hover {
		box-shadow: 0 0 1.6rem rgb(255 227 154 / 0.9);
	}
	.admit.small {
		font-size: 0.8rem;
		padding: 0.35rem 0.9rem;
	}
	.line {
		margin: 1.75rem 0 0;
		text-align: center;
		font-style: italic;
		color: var(--muted);
	}
	h2 {
		text-align: center;
		margin: 4rem 0 0;
		font-size: clamp(2.8rem, 6vw, 4rem);
		line-height: 1.1;
	}
	.sub {
		text-align: center;
		color: var(--muted);
		margin: 0.3rem 0 1.75rem;
	}
	.serials {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(19rem, 100%), 1fr));
		gap: 1.75rem;
	}
	.serial {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}
	.lobby {
		position: relative;
		display: block;
		aspect-ratio: 16 / 9;
		overflow: hidden;
		border: 6px solid transparent;
		border-image: linear-gradient(135deg, #f5d27a, #9c6f24, #f5d27a, #7a5418) 1;
		box-shadow: 0 0 1.5rem rgb(255 200 120 / 0.25);
		margin-bottom: 0.4rem;
	}
	.lobby img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.lobby.dark {
		display: grid;
		place-items: center;
		background: #0a080b;
	}
	.lobby.dark .neon {
		font-size: 2rem;
	}
	.running {
		position: absolute;
		top: 0.6rem;
		right: 0.6rem;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.15em;
		font-size: 0.75rem;
		background: var(--gold-light);
		color: #121010;
		padding: 0.2rem 0.5rem;
		box-shadow: 0 0 0.8rem rgb(255 227 154 / 0.8);
	}
	/* A backlit menu board. */
	.menu {
		position: relative;
		max-width: 34rem;
		margin: 1.5rem auto 0;
		padding: 1.5rem 2rem;
		color: #121010;
		background: radial-gradient(ellipse at center, #fffdf5, #f1e4c2 80%);
		border: 4px solid #3a2a14;
		box-shadow:
			inset 0 0 1.5rem rgb(255 230 170 / 0.9),
			0 0 2.5rem rgb(255 240 200 / 0.3);
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 600;
	}
	.menu :global(svg) {
		position: absolute;
		top: -1.4rem;
		right: -1.2rem;
		transform: rotate(12deg);
	}
	.menu ul {
		list-style: none;
		padding: 0;
		margin: 0;
	}
	.menu li {
		display: flex;
		gap: 0.5rem;
		padding: 0.3rem 0;
	}
	.menu i {
		flex: 1;
		border-bottom: 2px dotted #6a5a3a;
		margin-bottom: 0.35rem;
	}
	.menu p {
		margin: 1rem 0 0;
		text-align: center;
		font-size: 0.8rem;
		color: var(--red);
	}
	@media (max-width: 1100px) {
		.features {
			grid-template-columns: 1fr;
		}
		.and {
			justify-self: center;
		}
	}
	@media (max-width: 480px) {
		.feature {
			grid-template-columns: 8rem 1fr;
		}
	}
</style>
