<script lang="ts">
	import { imageUrl } from '$lib/api';
	import { formatRuntime, type CinemaRoom } from '$lib/cinema/api';
	import { cinema } from '$lib/cinema/state.svelte';
	import Showtimes from './Showtimes.svelte';
	import TrailerModal from './TrailerModal.svelte';

	const programme = $derived(cinema.programme);
	const movieRooms = $derived(programme?.rooms.filter((r) => r.kind === 'movie') ?? []);
	const lounges = $derived(programme?.rooms.filter((r) => r.kind === 'series') ?? []);
	const featured = $derived(movieRooms.filter((r) => r.item?.backdrop_tag));

	let index = $state(0);
	let paused = $state(false);
	let trailer = $state<{ id: string; title: string } | null>(null);
	const hero = $derived(featured.length ? featured[index % featured.length] : null);

	$effect(() => {
		if (featured.length < 2 || paused) return;
		const timer = setInterval(() => (index = (index + 1) % featured.length), 9000);
		return () => clearInterval(timer);
	});

	const meta = (room: CinemaRoom) =>
		[room.item?.year, formatRuntime(room.item?.runtime_minutes ?? null), room.item?.official_rating]
			.filter(Boolean)
			.join(' · ');
</script>

{#if !programme}
	<div class="hero skeleton"></div>
{:else}
	{#if hero?.item}
		<section
			class="hero"
			onmouseenter={() => (paused = true)}
			onmouseleave={() => (paused = false)}
			aria-label="Featured"
		>
			{#key hero.number}
				<img class="backdrop" src={imageUrl(hero.item.id, 'Backdrop', hero.item.backdrop_tag, 1920)} alt="" />
			{/key}
			<div class="shade"></div>
			<div class="hero-content">
				<p class="eyebrow">Auditorium {hero.number} · {hero.name}</p>
				{#if hero.item.logo_tag}
					<img class="title-logo" src={imageUrl(hero.item.id, 'Logo', hero.item.logo_tag, 800)} alt={hero.item.name} />
				{:else}
					<h1>{hero.item.name}</h1>
				{/if}
				<p class="meta">
					{meta(hero)}
					{#if hero.item.community_rating}<span class="rating">★ {hero.item.community_rating.toFixed(1)}</span>{/if}
				</p>
				{#if hero.item.tagline || hero.item.overview}
					<p class="blurb">{hero.item.tagline ?? hero.item.overview}</p>
				{/if}
				<div class="actions">
					<a class="btn primary" href="/tickets/{hero.number}">Get tickets</a>
					<a class="btn" href="/film/{hero.item.id}">Details</a>
					{#if hero.item.trailers.length}
						<button class="btn" onclick={() => (trailer = { id: hero.item!.trailers[0], title: hero.item!.name })}>
							▶ Trailer
						</button>
					{/if}
				</div>
			</div>
			{#if featured.length > 1}
				<div class="dots">
					{#each featured as room, i (room.number)}
						<button class:active={i === index % featured.length} onclick={() => (index = i)} aria-label="Show {room.item?.name}"></button>
					{/each}
				</div>
			{/if}
		</section>
	{/if}

	<section id="today" class="section">
		<div class="section-head">
			<h2>Today at {cinema.name}</h2>
			<p>{movieRooms.length} auditoriums · one film each · the reel waits for you</p>
		</div>
		<div class="grid">
			{#each movieRooms as room (room.number)}
				<article class="card" class:closed={!room.item}>
					{#if room.item}
						<a class="poster" href="/film/{room.item.id}">
							<img src={imageUrl(room.item.id, 'Primary', room.item.poster_tag, 500)} alt={room.item.name} loading="lazy" />
							<span class="badge">{room.number}</span>
							{#if room.sold_out}<span class="ribbon">Sold out</span>{/if}
						</a>
						<div class="card-body">
							<p class="room-name">{room.name}</p>
							<h3><a href="/film/{room.item.id}">{room.item.name}</a></h3>
							<p class="card-meta">{meta(room)}</p>
							<p class="genres">{room.item.genres.slice(0, 3).join(' · ')}</p>
							<Showtimes date={programme.date} times={room.showtimes} href="/tickets/{room.number}" />
						</div>
					{:else}
						<div class="poster empty"><span class="badge">{room.number}</span><span>Closed</span></div>
						<div class="card-body">
							<p class="room-name">{room.name}</p>
							<h3>Closed today</h3>
							<p class="card-meta">The projectionist found nothing that fits this room's taste.</p>
						</div>
					{/if}
				</article>
			{/each}
		</div>
	</section>

	{#if lounges.length}
		<section id="lounge" class="section lounge">
			<div class="section-head">
				<h2>Series lounge</h2>
				<p>Start a series here and it keeps its lounge until the finale.</p>
			</div>
			<div class="lounges">
				{#each lounges as room (room.number)}
					<article class="lounge-card" class:closed={!room.item}>
						{#if room.item}
							<img
								class="lounge-bg"
								src={imageUrl(room.item.id, room.item.backdrop_tag ? 'Backdrop' : 'Primary', room.item.backdrop_tag ?? room.item.poster_tag, 900)}
								alt=""
								loading="lazy"
							/>
							<div class="lounge-shade"></div>
							<div class="lounge-content">
								<p class="room-name">
									Lounge {room.number} · {room.name}
									{#if room.sticky}<span class="running">Now running</span>{/if}
								</p>
								<h3><a href="/film/{room.item.id}">{room.item.name}</a></h3>
								<p class="card-meta">
									{room.item.year ?? ''}
									{#if room.item.unplayed_count != null}· {room.item.unplayed_count} episodes to go{/if}
								</p>
								<div class="lounge-actions">
									<Showtimes date={programme.date} times={room.showtimes} />
									<a class="btn small primary" href="/tickets/{room.number}">Continue</a>
								</div>
							</div>
						{:else}
							<div class="lounge-content">
								<p class="room-name">Lounge {room.number} · {room.name}</p>
								<h3>Closed today</h3>
							</div>
						{/if}
					</article>
				{/each}
			</div>
		</section>
	{/if}
{/if}

{#if trailer}
	<TrailerModal youtubeId={trailer.id} title={trailer.title} onclose={() => (trailer = null)} />
{/if}

<style>
	.hero {
		position: relative;
		min-height: min(78vh, 46rem);
		display: flex;
		align-items: flex-end;
		overflow: hidden;
		margin-top: -4.25rem; /* slide under the translucent header */
	}
	.hero.skeleton {
		background: linear-gradient(90deg, var(--surface), var(--surface-2), var(--surface));
		background-size: 200% 100%;
		animation: shimmer 1.5s infinite;
	}
	@keyframes shimmer {
		to {
			background-position: -200% 0;
		}
	}
	.backdrop {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
		animation: kenburns 12s ease-out both;
	}
	@keyframes kenburns {
		from {
			transform: scale(1.08);
			opacity: 0;
		}
		15% {
			opacity: 1;
		}
		to {
			transform: scale(1);
		}
	}
	.shade {
		position: absolute;
		inset: 0;
		background:
			linear-gradient(to top, var(--bg) 2%, rgb(11 11 16 / 0.55) 40%, rgb(11 11 16 / 0.2) 70%, rgb(11 11 16 / 0.7)),
			linear-gradient(to right, rgb(11 11 16 / 0.85), transparent 65%);
	}
	.hero-content {
		position: relative;
		padding: 0 clamp(1rem, 4vw, 3rem) clamp(2.5rem, 7vh, 4.5rem);
		max-width: 44rem;
	}
	.eyebrow,
	.room-name {
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
		font-size: clamp(2.6rem, 7vw, 5.5rem);
		line-height: 0.95;
		margin: 0.6rem 0;
	}
	.title-logo {
		display: block;
		max-width: min(32rem, 80vw);
		max-height: 10rem;
		margin: 1rem 0;
		filter: drop-shadow(0 0.5rem 1.5rem rgb(0 0 0 / 0.6));
	}
	.meta {
		color: #d8d8e2;
		font-weight: 500;
		display: flex;
		gap: 1rem;
		align-items: center;
	}
	.rating {
		color: var(--gold);
	}
	.blurb {
		color: #cfcfdb;
		line-height: 1.55;
		max-width: 38rem;
		display: -webkit-box;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
		margin-top: 1.5rem;
	}
	.btn {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.75rem 1.4rem;
		border-radius: 999px;
		font: inherit;
		font-weight: 600;
		text-decoration: none;
		color: var(--text);
		background: rgb(255 255 255 / 0.1);
		border: 1px solid rgb(255 255 255 / 0.15);
		backdrop-filter: blur(6px);
		cursor: pointer;
		transition: transform 0.15s, background 0.15s;
	}
	.btn:hover {
		transform: translateY(-1px);
		background: rgb(255 255 255 / 0.18);
	}
	.btn.primary {
		background: var(--accent);
		border-color: var(--accent);
	}
	.btn.primary:hover {
		background: #ff5574;
	}
	.btn.small {
		padding: 0.4rem 1rem;
		font-size: 0.85rem;
	}
	.dots {
		position: absolute;
		right: clamp(1rem, 4vw, 3rem);
		bottom: 2rem;
		display: flex;
		gap: 0.45rem;
	}
	.dots button {
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 999px;
		border: 0;
		padding: 0;
		background: rgb(255 255 255 / 0.35);
		cursor: pointer;
		transition: width 0.3s, background 0.3s;
	}
	.dots button.active {
		width: 1.6rem;
		background: var(--text);
	}

	.section {
		padding: 3rem clamp(1rem, 4vw, 3rem) 1rem;
		scroll-margin-top: 4rem;
	}
	.section-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 0.5rem 2rem;
		margin-bottom: 1.5rem;
	}
	h2 {
		font-family: var(--display);
		text-transform: uppercase;
		font-size: 2rem;
		margin: 0;
	}
	.section-head p {
		color: var(--muted);
		margin: 0;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
		gap: 2rem 1.5rem;
	}
	.card {
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}
	.poster {
		position: relative;
		display: block;
		aspect-ratio: 2 / 3;
		border-radius: 0.6rem;
		overflow: hidden;
		background: var(--surface);
		box-shadow: 0 1rem 2rem rgb(0 0 0 / 0.35);
	}
	.poster img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		transition: transform 0.4s ease;
	}
	.poster:hover img {
		transform: scale(1.04);
	}
	.poster.empty {
		display: grid;
		place-items: center;
		color: var(--muted);
		font-family: var(--display);
		text-transform: uppercase;
		letter-spacing: 0.2em;
		border: 1px dashed var(--line);
		box-shadow: none;
	}
	.badge {
		position: absolute;
		top: 0.7rem;
		left: 0.7rem;
		min-width: 2.2rem;
		height: 2.2rem;
		display: grid;
		place-items: center;
		border-radius: 0.4rem;
		background: rgb(11 11 16 / 0.85);
		border: 1px solid rgb(255 255 255 / 0.15);
		font-family: var(--display);
		font-weight: 700;
		font-size: 1.15rem;
	}
	.ribbon {
		position: absolute;
		top: 1.4rem;
		right: -2.6rem;
		transform: rotate(35deg);
		background: var(--accent);
		color: #fff;
		padding: 0.3rem 3rem;
		font-family: var(--display);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		font-size: 0.85rem;
		box-shadow: 0 0.3rem 1rem rgb(0 0 0 / 0.4);
	}
	.card-body {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	h3 {
		font-size: 1.1rem;
		margin: 0;
		line-height: 1.25;
	}
	h3 a {
		text-decoration: none;
	}
	h3 a:hover {
		color: var(--accent);
	}
	.card-meta,
	.genres {
		color: var(--muted);
		font-size: 0.85rem;
		margin: 0;
	}
	.genres {
		margin-bottom: 0.4rem;
	}
	.closed h3 {
		color: var(--muted);
	}

	.lounges {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(26rem, 100%), 1fr));
		gap: 1.25rem;
	}
	.lounge-card {
		position: relative;
		min-height: 15rem;
		border-radius: 0.75rem;
		overflow: hidden;
		background: var(--surface);
		display: flex;
		align-items: flex-end;
	}
	.lounge-bg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.lounge-shade {
		position: absolute;
		inset: 0;
		background: linear-gradient(to top, rgb(11 11 16 / 0.96) 15%, rgb(11 11 16 / 0.25));
	}
	.lounge-content {
		position: relative;
		padding: 1.25rem;
		width: 100%;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}
	.lounge-content h3 {
		font-family: var(--display);
		text-transform: uppercase;
		font-size: 1.6rem;
	}
	.running {
		margin-left: 0.5rem;
		padding: 0.1rem 0.5rem;
		border-radius: 999px;
		background: var(--gold);
		color: #1a1206;
		letter-spacing: 0.08em;
	}
	.lounge-actions {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		flex-wrap: wrap;
		margin-top: 0.5rem;
	}
</style>
