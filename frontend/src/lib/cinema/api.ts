import type { Show } from '$lib/api';

export type ThemeId = 'modern' | 'retro';

/** "Terminator · Part 2 of 6"; `part` is null when the franchise has no order. */
export type FranchiseBadge = { name: string; part: number | null; parts: number; ordered: boolean };

export type CinemaItem = {
	id: string;
	type: 'movie' | 'series';
	name: string;
	year: number | null;
	runtime_minutes: number | null;
	genres: string[];
	overview: string | null;
	tagline: string | null;
	official_rating: string | null;
	community_rating: number | null;
	poster_tag: string | null;
	backdrop_tag: string | null;
	logo_tag: string | null;
	played: boolean;
	favorite: boolean;
	unplayed_count: number | null;
	trailers: string[];
	franchise: FranchiseBadge | null;
};

export type CinemaRoom = {
	number: number;
	name: string;
	kind: 'movie' | 'series';
	item: CinemaItem | null;
	/** Same-day marathon: the next franchise part, offered once `item` started today. */
	next: CinemaItem | null;
	marathon: number;
	showtimes: string[];
	source: 'generated' | 'franchise' | 'override' | null;
	started: boolean;
	sold_out: boolean;
	sticky: boolean;
};

export type CinemaProgramme = {
	date: string;
	cinema: { names: Record<ThemeId, string>; default_theme: ThemeId };
	rooms: CinemaRoom[];
};

export type Person = { name: string; role: string | null; type: 'Director' | 'Actor' | string };

export type TitleDetail = {
	id: string;
	type: 'movie' | 'series';
	name: string;
	original_title: string | null;
	year: number | null;
	premiere_date: string | null;
	overview: string | null;
	tagline: string | null;
	genres: string[];
	studios: string[];
	people: Person[];
	official_rating: string | null;
	community_rating: number | null;
	critic_rating: number | null;
	runtime_minutes: number | null;
	unplayed_count: number | null;
	episode_count: number | null;
	poster_tag: string | null;
	backdrop_tag: string | null;
	logo_tag: string | null;
	trailers: string[];
	franchise: FranchiseBadge | null;
	screenings: { room: number; name: string; showtimes: string[]; sold_out: boolean; next: boolean }[];
};

export type NowPlaying = { show: Show | null; now_playing: string | null; paused: boolean | null };

async function get<T>(path: string): Promise<T> {
	const response = await fetch(path);
	if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
	return response.json();
}

export const getCinemaProgramme = () => get<CinemaProgramme>('/api/cinema/programme');
export const getTitle = (id: string) => get<TitleDetail>(`/api/cinema/titles/${id}`);
export const getNow = () => get<NowPlaying>('/api/cinema/now');

export async function playRoom(number: number, next = false): Promise<Show> {
	const response = await fetch(`/api/cinema/rooms/${number}/play${next ? '?next=true' : ''}`, { method: 'POST' });
	const body = await response.json().catch(() => null);
	if (!response.ok) throw new Error(body?.detail ?? `HTTP ${response.status}`);
	return body;
}

export const trailerEmbedUrl = (youtubeId: string) =>
	`https://www.youtube-nocookie.com/embed/${youtubeId}?autoplay=1&rel=0&modestbranding=1`;

export type ShowtimeState = 'past' | 'next' | 'later';

/** Showtimes of a cinema day relative to now (the day may have started yesterday evening). */
export function showtimeStates(cinemaDate: string, times: string[], now = new Date()): ShowtimeState[] {
	let nextFound = false;
	return times.map((time) => {
		const at = new Date(`${cinemaDate}T${time}:00`);
		if (at < now) return 'past';
		if (!nextFound) {
			nextFound = true;
			return 'next';
		}
		return 'later';
	});
}

const ROMAN: [number, string][] = [
	[1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'], [100, 'C'], [90, 'XC'],
	[50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']
];

export function roman(n: number): string {
	let out = '';
	for (const [value, numeral] of ROMAN) {
		while (n >= value) {
			out += numeral;
			n -= value;
		}
	}
	return out;
}

/** "Terminator · Part 2 of 6" (or just the name when the franchise has no order). */
export function franchiseLine(badge: FranchiseBadge): string {
	return badge.part ? `${badge.name} · Part ${badge.part} of ${badge.parts}` : badge.name;
}

export function formatRuntime(minutes: number | null): string {
	if (!minutes) return '';
	const h = Math.floor(minutes / 60);
	const m = minutes % 60;
	return h ? `${h} h ${m.toString().padStart(2, '0')} min` : `${m} min`;
}

export function formatCinemaDate(cinemaDate: string): string {
	return new Date(`${cinemaDate}T12:00:00`).toLocaleDateString('en-GB', {
		weekday: 'long',
		day: 'numeric',
		month: 'long'
	});
}
