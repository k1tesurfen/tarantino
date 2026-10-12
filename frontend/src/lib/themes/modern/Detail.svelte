<script lang="ts">
	import { imageUrl } from '$lib/api';
	import { formatRuntime, franchiseLine, trailerEmbedUrl, type TitleDetail } from '$lib/cinema/api';
	import { cinema } from '$lib/cinema/state.svelte';
	import Showtimes from './Showtimes.svelte';

	let { title }: { title: TitleDetail } = $props();

	let trailerStarted = $state(false);
	let error = $state<string | null>(null);

	const directors = $derived(title.people.filter((p) => p.type === 'Director'));
	const cast = $derived(title.people.filter((p) => p.type === 'Actor'));
	const screening = $derived(title.screenings[0]);
	const isSeries = $derived(title.type === 'series');

	async function playNow() {
		if (!screening) return;
		error = null;
		try {
			await cinema.play(screening.room, screening.next);
		} catch (e) {
			error = (e as Error).message;
		}
	}
</script>

<svelte:head><title>{title.name} · {cinema.name}</title></svelte:head>

<article>
	<div class="banner">
		{#if title.backdrop_tag}
			<img src={imageUrl(title.id, 'Backdrop', title.backdrop_tag, 1920)} alt="" />
		{/if}
		<div class="shade"></div>
	</div>

	<div class="body">
		<div class="poster">
			{#if title.poster_tag}
				<img src={imageUrl(title.id, 'Primary', title.poster_tag, 600)} alt={title.name} />
			{/if}
		</div>

		<div class="info">
			<a class="back" href="/">← Today's programme</a>
			{#if title.franchise}<p class="franchise">{franchiseLine(title.franchise)}</p>{/if}
			<h1>{title.name}</h1>
			{#if title.original_title && title.original_title !== title.name}
				<p class="original">{title.original_title}</p>
			{/if}
			<ul class="facts">
				{#if title.year}<li>{title.year}</li>{/if}
				{#if title.runtime_minutes && !isSeries}<li>{formatRuntime(title.runtime_minutes)}</li>{/if}
				{#if isSeries && title.episode_count}
					<li>{title.unplayed_count ?? 0} of {title.episode_count} episodes to go</li>
				{/if}
				{#if title.official_rating}<li class="age">{title.official_rating}</li>{/if}
				{#if title.community_rating}<li class="rating">★ {title.community_rating.toFixed(1)}</li>{/if}
				{#if title.critic_rating}<li class="critics">🍅 {Math.round(title.critic_rating)}%</li>{/if}
			</ul>
			<p class="genres">{title.genres.join(' · ')}</p>
			{#if title.tagline}<p class="tagline">“{title.tagline}”</p>{/if}
			{#if title.overview}<p class="overview">{title.overview}</p>{/if}

			<section class="tickets">
				{#if screening}
					<p class="where">
						{screening.next ? 'Up next' : 'Today'} in {isSeries ? 'Lounge' : 'Auditorium'} {screening.room} · {screening.name}
						{#if screening.sold_out && !screening.next}<span class="sold">Sold out</span>{/if}
					</p>
					{#if cinema.programme && !screening.next}
						<Showtimes date={cinema.programme.date} times={screening.showtimes} href="/tickets/{screening.room}" />
					{/if}
					<div class="actions">
						<a class="btn primary" href="/tickets/{screening.room}{screening.next ? '?next=1' : ''}">Get tickets</a>
						<button class="btn" onclick={playNow}>{isSeries ? 'Play next episode' : 'Skip the queue · play now'}</button>
					</div>
					{#if error}<p class="error">{error}</p>{/if}
				{:else}
					<p class="where">Not on today's programme. Maybe tomorrow.</p>
				{/if}
			</section>
		</div>
	</div>

	{#if title.trailers.length}
		<section class="trailer">
			<h2>Trailer</h2>
			<div class="player">
				{#if trailerStarted}
					<iframe
						src={trailerEmbedUrl(title.trailers[0])}
						title="Trailer: {title.name}"
						allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
						allowfullscreen
					></iframe>
				{:else}
					<button class="play-trailer" onclick={() => (trailerStarted = true)} aria-label="Play trailer">
						{#if title.backdrop_tag}<img src={imageUrl(title.id, 'Backdrop', title.backdrop_tag, 1280)} alt="" />{/if}
						<span class="play-icon">▶</span>
					</button>
				{/if}
			</div>
		</section>
	{/if}

	{#if directors.length || cast.length}
		<section class="people">
			{#if directors.length}
				<h2>Directed by</h2>
				<p class="directors">{directors.map((d) => d.name).join(', ')}</p>
			{/if}
			{#if cast.length}
				<h2>Cast</h2>
				<ul class="cast">
					{#each cast as person}
						<li><strong>{person.name}</strong>{#if person.role}<span>{person.role}</span>{/if}</li>
					{/each}
				</ul>
			{/if}
			{#if title.studios.length}<p class="studios">{title.studios.join(' · ')}</p>{/if}
		</section>
	{/if}
</article>

<style>
	article {
		padding-bottom: 3rem;
	}
	.banner {
		position: relative;
		height: min(60vh, 34rem);
		margin-top: -4.25rem;
		overflow: hidden;
		background: var(--surface);
	}
	.banner img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.shade {
		position: absolute;
		inset: 0;
		background: linear-gradient(to top, var(--bg) 3%, rgb(11 11 16 / 0.4) 55%, rgb(11 11 16 / 0.7));
	}
	.body {
		position: relative;
		display: grid;
		grid-template-columns: minmax(12rem, 18rem) 1fr;
		gap: clamp(1.5rem, 4vw, 3rem);
		padding: 0 clamp(1rem, 4vw, 3rem);
		margin-top: -14rem;
	}
	.poster img {
		width: 100%;
		aspect-ratio: 2 / 3; /* reserve the space while the poster loads */
		object-fit: cover;
		border-radius: 0.75rem;
		box-shadow: 0 2rem 4rem rgb(0 0 0 / 0.6);
	}
	.info {
		padding-top: 6rem;
		max-width: 46rem;
	}
	.back {
		color: var(--muted);
		text-decoration: none;
		font-size: 0.9rem;
	}
	h1 {
		font-family: var(--display);
		text-transform: uppercase;
		font-size: clamp(2.4rem, 6vw, 4.5rem);
		line-height: 0.95;
		margin: 0.75rem 0 0.25rem;
	}
	.original {
		color: var(--muted);
		font-style: italic;
		margin: 0;
	}
	.facts {
		list-style: none;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin: 1rem 0 0.5rem;
	}
	.facts li {
		padding: 0.25rem 0.65rem;
		border-radius: 0.3rem;
		background: var(--surface-2);
		font-size: 0.85rem;
		font-weight: 600;
	}
	.facts .age {
		border: 1px solid var(--muted);
		background: none;
	}
	.facts .rating {
		color: var(--gold);
	}
	.genres {
		color: var(--muted);
	}
	.franchise {
		margin: 0.6rem 0 -0.2rem;
		color: var(--gold);
		font-weight: 600;
		letter-spacing: 0.04em;
	}
	.tagline {
		font-size: 1.15rem;
		font-style: italic;
		color: #dcdce6;
	}
	.overview {
		line-height: 1.65;
		color: #d4d4de;
	}
	.tickets {
		margin-top: 2rem;
		padding: 1.25rem 1.5rem;
		border-radius: 0.75rem;
		background: var(--surface);
		border: 1px solid var(--line);
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}
	.where {
		margin: 0;
		font-weight: 600;
	}
	.sold {
		margin-left: 0.5rem;
		color: var(--accent);
		text-transform: uppercase;
		font-size: 0.8rem;
		letter-spacing: 0.1em;
	}
	.actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}
	.btn {
		padding: 0.7rem 1.3rem;
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
	.error {
		color: #ff8a9b;
		margin: 0;
	}
	.trailer,
	.people {
		padding: 2.5rem clamp(1rem, 4vw, 3rem) 0;
		max-width: 72rem;
	}
	h2 {
		font-family: var(--display);
		text-transform: uppercase;
		font-size: 1.4rem;
		margin: 0 0 1rem;
	}
	.player {
		aspect-ratio: 16 / 9;
		border-radius: 0.75rem;
		overflow: hidden;
		background: #000;
	}
	.player iframe {
		width: 100%;
		height: 100%;
		border: 0;
	}
	.play-trailer {
		position: relative;
		width: 100%;
		height: 100%;
		border: 0;
		padding: 0;
		background: #000;
		cursor: pointer;
	}
	.play-trailer img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		opacity: 0.6;
	}
	.play-icon {
		position: absolute;
		inset: 0;
		margin: auto;
		width: 5rem;
		height: 5rem;
		display: grid;
		place-items: center;
		border-radius: 50%;
		background: var(--accent);
		color: #fff;
		font-size: 1.8rem;
		box-shadow: 0 0 0 0.6rem rgb(255 59 92 / 0.25);
	}
	.directors {
		margin: 0 0 2rem;
	}
	.cast {
		list-style: none;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(13rem, 1fr));
		gap: 0.9rem 1.5rem;
	}
	.cast li {
		display: flex;
		flex-direction: column;
	}
	.cast span {
		color: var(--muted);
		font-size: 0.9rem;
	}
	.studios {
		color: var(--muted);
		font-size: 0.85rem;
		margin-top: 2rem;
	}
	@media (max-width: 720px) {
		.body {
			grid-template-columns: 1fr;
			margin-top: -8rem;
		}
		.poster {
			width: 10rem;
		}
		.info {
			padding-top: 0;
		}
	}
</style>
