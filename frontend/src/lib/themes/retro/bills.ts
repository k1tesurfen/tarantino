import type { CinemaRoom } from '$lib/cinema/api';

/** Auditoriums 1+2, 3+4, ... become double bills; an odd one out is a special engagement. */
export function doubleBills(rooms: CinemaRoom[]): CinemaRoom[][] {
	const movies = rooms.filter((r) => r.kind === 'movie');
	return Array.from({ length: Math.ceil(movies.length / 2) }, (_, i) => movies.slice(i * 2, i * 2 + 2));
}

/** The attraction board: what a theatre would spell out above its entrance tonight. */
export function marqueeLines(rooms: CinemaRoom[]): string[] {
	const bills = doubleBills(rooms)
		.map((bill) => bill.map((r) => r.item?.name).filter(Boolean).join(' & '))
		.filter(Boolean);
	const serials = rooms.filter((r) => r.kind === 'series' && r.item).length;
	const marathons = rooms.flatMap((r) => (r.next?.franchise ? [`${r.next.franchise.name} marathon`] : []));
	return [
		'Tonight · double features',
		...bills,
		...marathons,
		...(serials ? [`+ ${serials} serials in the lounge`] : [])
	];
}
