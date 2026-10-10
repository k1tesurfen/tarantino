<script lang="ts">
	import { imageUrl } from '$lib/api';
	import type { TitleDetail } from '$lib/cinema/api';
	import { cinema } from '$lib/cinema/state.svelte';
	import { showtimeChips } from '$lib/cinema/tickets';
	import TrailerModal from '../modern/TrailerModal.svelte';

	let { title }: { title: TitleDetail } = $props();

	let trailerOpen = $state(false);
	let error = $state<string | null>(null);

	const directors = $derived(title.people.filter((p) => p.type === 'Director').map((p) => p.name));
	const stars = $derived(title.people.filter((p) => p.type === 'Actor').map((p) => p.name));
	const screening = $derived(title.screenings[0]);
	const isSeries = $derived(title.type === 'series');

	async function playNow() {
		if (!screening) return;
		error = null;
		try {
			await cinema.play(screening.room);
		} catch (e) {
			error = (e as Error).message;
		}
	}
</script>

<svelte:head><title>{title.name} · {cinema.name}</title></svelte:head>

<a class="back" href="/">◂ Back to tonight's bill</a>

<article class="sheet">
	<div class="poster-col">
		<div class="poster">
			{#if title.poster_tag}
				<img src={imageUrl(title.id, 'Primary', title.poster_tag, 700)} alt={title.name} />
			{/if}
			<span class="tape left" aria-hidden="true"></span>
			<span class="tape right" aria-hidden="true"></span>
		</div>
		{#if title.trailers.length}
			<button class="coming" onclick={() => (trailerOpen = true)}>▶ Coming attractions</button>
		{/if}
	</div>

	<div class="info">
		<p class="kicker">
			{#if screening}
				{isSeries ? 'Serial' : 'Now playing'} · {isSeries ? 'Lounge' : 'Auditorium'} {screening.room}
			{:else}
				Not on tonight's bill
			{/if}
		</p>
		<h1>{title.name}</h1>
		{#if title.tagline}<p class="tagline">“{title.tagline}”</p>{/if}

		<div class="facts">
			{#if title.official_rating}
				<div class="certificate">
					<strong>{title.official_rating}</strong>
					<span>Certificate</span>
				</div>
			{/if}
			<dl>
				{#if title.year}<div><dt>Year</dt><dd>{title.year}</dd></div>{/if}
				{#if title.runtime_minutes && !isSeries}<div><dt>Running time</dt><dd>{title.runtime_minutes} min</dd></div>{/if}
				{#if isSeries && title.episode_count}
					<div><dt>Chapters</dt><dd>{title.unplayed_count ?? 0} of {title.episode_count} to go</dd></div>
				{/if}
				{#if title.community_rating}<div><dt>Audience</dt><dd>★ {title.community_rating.toFixed(1)}</dd></div>{/if}
				{#if title.critic_rating}<div><dt>Critics</dt><dd>{Math.round(title.critic_rating)}%</dd></div>{/if}
				{#if title.genres.length}<div><dt>Genre</dt><dd>{title.genres.slice(0, 3).join(' / ')}</dd></div>{/if}
			</dl>
		</div>

		{#if title.overview}<p class="overview">{title.overview}</p>{/if}

		{#if screening}
			<div class="box-office">
				<p class="shows">
					Shows tonight:
					{#each showtimeChips(cinema.programme?.date ?? '', screening.showtimes) as chip, i}
						{#if i}<span class="sep">·</span>{/if}<span class={chip.state}>{chip.label}</span>
					{/each}
					{#if screening.sold_out}<span class="sold">Sold out</span>{/if}
				</p>
				<div class="actions">
					<a class="admit" href="/tickets/{screening.room}">Admit one ▸</a>
					<button class="sneak" onclick={playNow}>{isSeries ? 'Roll the next chapter' : 'Sneak in · play now'}</button>
				</div>
				{#if error}<p class="error">{error}</p>{/if}
			</div>
		{/if}

		{#if directors.length || stars.length}
			<div class="billing">
				{#if directors.length}<p><small>A picture by</small> {directors.join(' & ')}</p>{/if}
				{#if stars.length}<p><small>Starring</small> {stars.slice(0, 8).join(' · ')}</p>{/if}
				{#if title.studios.length}<p class="studios">{title.studios.join(' · ')}</p>{/if}
			</div>
		{/if}
	</div>
</article>

{#if trailerOpen && title.trailers.length}
	<TrailerModal youtubeId={title.trailers[0]} title={title.name} onclose={() => (trailerOpen = false)} />
{/if}

<style>
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
	article {
		display: grid;
		grid-template-columns: minmax(14rem, 24rem) 1fr;
		gap: clamp(1.5rem, 4vw, 3rem);
		padding: clamp(1.25rem, 3vw, 2.5rem);
	}
	.poster-col {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}
	.poster {
		position: relative;
		transform: rotate(-1.5deg);
		border: 8px solid #fff8e8;
		box-shadow: 0 0.5rem 1.5rem rgb(0 0 0 / 0.35);
	}
	.poster img {
		display: block;
		width: 100%;
		aspect-ratio: 2 / 3; /* reserve the space while the poster loads */
		object-fit: cover;
		filter: sepia(0.3) saturate(0.9) contrast(1.1);
	}
	.poster::after {
		content: '';
		position: absolute;
		inset: 0;
		background: radial-gradient(rgb(30 23 18 / 0.3) 0.9px, transparent 1.4px) 0 0 / 4px 4px;
		mix-blend-mode: multiply;
	}
	.tape {
		position: absolute;
		top: -0.9rem;
		width: 5.5rem;
		height: 1.6rem;
		background: rgb(219 200 150 / 0.75);
		z-index: 1;
	}
	.tape.left {
		left: -1.2rem;
		transform: rotate(-35deg);
	}
	.tape.right {
		right: -1.2rem;
		transform: rotate(35deg);
	}
	.coming {
		font-family: var(--display);
		text-transform: uppercase;
		font-size: 1.05rem;
		background: var(--ink);
		color: var(--mustard);
		border: 0;
		padding: 0.8rem 1rem;
		cursor: pointer;
	}
	.coming:hover {
		color: var(--paper);
		background: var(--red);
	}
	.kicker {
		margin: 0;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.2em;
		color: var(--red);
	}
	h1 {
		margin: 0.4rem 0;
		font-family: var(--display);
		text-transform: uppercase;
		font-size: clamp(2.2rem, 5.5vw, 4rem);
		line-height: 1;
	}
	.tagline {
		margin: 0.5rem 0 1.25rem;
		font-size: 1.15rem;
		font-style: italic;
		color: var(--red);
	}
	.facts {
		display: flex;
		gap: 1.5rem;
		align-items: flex-start;
		flex-wrap: wrap;
	}
	.certificate {
		display: flex;
		flex-direction: column;
		align-items: center;
		border: 3px solid var(--ink);
		padding: 0.4rem 0.8rem;
		min-width: 4rem;
	}
	.certificate strong {
		font-family: var(--display);
		font-size: 1.8rem;
		line-height: 1;
	}
	.certificate span {
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.15em;
	}
	dl {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
		gap: 0.6rem 1.25rem;
		margin: 0;
		flex: 1;
	}
	dt {
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.15em;
		font-size: 0.7rem;
		color: var(--ink-soft);
	}
	dd {
		margin: 0;
		font-weight: 700;
	}
	.overview {
		line-height: 1.65;
		margin: 1.5rem 0;
	}
	.box-office {
		border: 3px double var(--ink);
		padding: 1rem 1.25rem;
		margin-bottom: 1.5rem;
	}
	.shows {
		margin: 0 0 0.9rem;
	}
	.sep {
		margin: 0 0.35rem;
	}
	.shows .past {
		opacity: 0.55;
	}
	.shows .next {
		font-weight: 700;
		background: var(--mustard);
		padding: 0 0.3rem;
	}
	.sold {
		margin-left: 0.5rem;
		color: var(--red);
		font-weight: 700;
		text-transform: uppercase;
	}
	.actions {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}
	.admit,
	.sneak {
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.18em;
		font-size: 0.95rem;
		padding: 0.6rem 1.1rem;
		text-decoration: none;
		cursor: pointer;
	}
	.admit {
		background: var(--red);
		color: var(--paper);
	}
	.sneak {
		background: none;
		border: 2px solid var(--ink);
		color: var(--ink);
	}
	.error {
		color: var(--red);
	}
	.billing {
		border-top: 2px solid var(--ink);
		padding-top: 1rem;
		text-align: center;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.billing p {
		margin: 0.35rem 0;
		font-size: 1.05rem;
	}
	.billing small {
		display: block;
		font-size: 0.65rem;
		letter-spacing: 0.3em;
		color: var(--ink-soft);
	}
	.billing .studios {
		font-size: 0.75rem;
		color: var(--ink-soft);
	}
	@media (max-width: 760px) {
		article {
			grid-template-columns: 1fr;
		}
		.poster-col {
			max-width: 16rem;
		}
	}
</style>
