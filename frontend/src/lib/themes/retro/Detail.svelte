<script lang="ts">
	import { imageUrl } from '$lib/api';
	import type { TitleDetail } from '$lib/cinema/api';
	import { cinema } from '$lib/cinema/state.svelte';
	import { showtimeChips } from '$lib/cinema/tickets';
	import TrailerModal from '../modern/TrailerModal.svelte';
	import BulbFrame from './BulbFrame.svelte';
	import LetterBoard from './LetterBoard.svelte';
	import { chapterLine } from './chapter';

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
			await cinema.play(screening.room, screening.next);
		} catch (e) {
			error = (e as Error).message;
		}
	}
</script>

<svelte:head><title>{title.name} · {cinema.name}</title></svelte:head>

<a class="back" href="/">◂ Back to tonight's bill</a>

<article>
	<div class="poster-col">
		<BulbFrame step={20} chase={false}>
			<div class="poster">
				{#if title.poster_tag}
					<img src={imageUrl(title.id, 'Primary', title.poster_tag, 700)} alt={title.name} />
				{/if}
			</div>
		</BulbFrame>
		{#if title.trailers.length}
			<button class="coming" onclick={() => (trailerOpen = true)}><span class="neon pink">Coming attractions</span></button>
		{/if}
	</div>

	<div class="info">
		<p class="kicker">
			{#if screening}
				{isSeries ? 'Serial' : screening.next ? 'Held over, up next' : 'Now playing'} · {isSeries ? 'Lounge' : 'Auditorium'} {screening.room}
			{:else}
				Not on tonight's bill
			{/if}
		</p>
		<LetterBoard lines={[title.name]} />
		{#if title.franchise}<p class="chapter neon pink">{chapterLine(title.franchise)}</p>{/if}
		{#if title.tagline}<p class="tagline neon">“{title.tagline}”</p>{/if}

		<div class="facts">
			{#if title.official_rating}
				<div class="certificate"><strong>{title.official_rating}</strong><span>Certificate</span></div>
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
				{#if !screening.next}
					<p class="shows">
						{#each showtimeChips(cinema.programme?.date ?? '', screening.showtimes) as chip}
							<span class="tile {chip.state}">{chip.label}</span>
						{/each}
						{#if screening.sold_out}<span class="sold">Sold out</span>{/if}
					</p>
				{/if}
				<div class="actions">
					<a class="admit" href="/tickets/{screening.room}{screening.next ? '?next=1' : ''}">Admit one</a>
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
		color: var(--gold-light);
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.15em;
		text-decoration: none;
		font-size: 0.85rem;
	}
	article {
		display: grid;
		grid-template-columns: minmax(14rem, 24rem) 1fr;
		gap: clamp(1.5rem, 4vw, 3.5rem);
		padding: clamp(1.25rem, 3vw, 2.5rem);
		border-radius: 0.75rem;
		background:
			linear-gradient(rgb(255 200 120 / 0.06), transparent 40%),
			repeating-linear-gradient(90deg, #22150d 0 3px, #1c110b 3px 90px);
		border: 1px solid rgb(231 183 90 / 0.25);
	}
	.poster-col {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}
	.poster {
		position: relative;
		aspect-ratio: 2 / 3;
		background: #000;
	}
	.poster img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
		filter: brightness(1.08) saturate(1.1);
	}
	.poster::after {
		content: '';
		position: absolute;
		inset: 0;
		background: linear-gradient(115deg, rgb(255 255 255 / 0.18), transparent 30% 65%, rgb(255 255 255 / 0.06));
	}
	.coming {
		background: none;
		border: 2px solid var(--neon-pink);
		border-radius: 0.5rem;
		padding: 0.4rem 1rem 0.6rem;
		cursor: pointer;
		box-shadow:
			0 0 0.8rem rgb(255 111 174 / 0.5),
			inset 0 0 0.8rem rgb(255 111 174 / 0.3);
	}
	.coming .neon {
		font-size: 1.9rem;
	}
	.kicker {
		margin: 0 0 0.75rem;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.2em;
		color: var(--gold);
	}
	.chapter {
		margin: 0.6rem 0 0;
		font-size: 1.6rem;
		line-height: 1.1;
	}
	.tagline {
		margin: 1.25rem 0;
		font-size: clamp(1.5rem, 3vw, 2.1rem);
		line-height: 1.2;
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
		border: 3px solid var(--gold);
		color: var(--gold-light);
		padding: 0.4rem 0.8rem;
		min-width: 4rem;
		box-shadow: 0 0 0.8rem rgb(231 183 90 / 0.35);
	}
	.certificate strong {
		font-family: var(--display);
		font-weight: 400;
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
		color: var(--gold);
	}
	dd {
		margin: 0;
		font-weight: 700;
		color: var(--cream);
	}
	.overview {
		line-height: 1.65;
		margin: 1.5rem 0;
	}
	.box-office {
		border: 1px solid rgb(231 183 90 / 0.4);
		border-radius: 0.5rem;
		padding: 1rem 1.25rem;
		margin-bottom: 1.75rem;
		background: rgb(0 0 0 / 0.25);
	}
	.shows {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.3rem;
		margin: 0 0 1rem;
	}
	.tile {
		font-family: var(--condensed);
		font-weight: 700;
		letter-spacing: 0.08em;
		font-size: 0.9rem;
		padding: 0.15rem 0.5rem;
		background: var(--cream);
		color: #121010;
	}
	.tile.past {
		opacity: 0.4;
	}
	.tile.next {
		background: var(--gold-light);
		box-shadow: 0 0 0.8rem rgb(255 227 154 / 0.8);
	}
	.sold {
		margin-left: 0.6rem;
		color: var(--neon);
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.15em;
		text-shadow: 0 0 0.6rem rgb(255 58 76 / 0.8);
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
		padding: 0.6rem 1.2rem;
		border-radius: 999px;
		text-decoration: none;
		cursor: pointer;
	}
	.admit {
		color: #1b1006;
		background: linear-gradient(#ffe7a3, var(--gold));
		box-shadow: 0 0 1rem rgb(231 183 90 / 0.5);
	}
	.sneak {
		background: none;
		border: 2px solid var(--gold);
		color: var(--gold-light);
	}
	.error {
		color: var(--neon);
	}
	.billing {
		border-top: 1px solid rgb(231 183 90 / 0.4);
		padding-top: 1rem;
		text-align: center;
		font-family: var(--condensed);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--cream);
	}
	.billing p {
		margin: 0.4rem 0;
		font-size: 1.05rem;
	}
	.billing small {
		display: block;
		font-size: 0.65rem;
		letter-spacing: 0.3em;
		color: var(--gold);
	}
	.billing .studios {
		font-size: 0.75rem;
		color: var(--muted);
	}
	@media (max-width: 760px) {
		article {
			grid-template-columns: 1fr;
		}
		.poster-col {
			max-width: 17rem;
		}
	}
</style>
