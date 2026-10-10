import { showtimeStates, type CinemaRoom, type ShowtimeState } from './api';
import { seededRandom } from './random';

export const SEAT_ROWS = 'ABCDEFGH'.split('');
export const SEATS_PER_ROW = 14;
export const AISLES_AFTER = new Set([3, 11]);
export const MAX_SEATS = 6;
const BOOKED_SHARE = 0.38;
const HOUSE_SEAT = 'E7'; // a sold-out room always keeps this one for you

/** "Booked" seats: stable for the cinema day; a sold-out room keeps one seat free. */
export function bookedSeats(cinemaDate: string, room: CinemaRoom): Set<string> {
	const random = seededRandom(`${cinemaDate}/${room.number}`);
	const taken = new Set<string>();
	for (const row of SEAT_ROWS) {
		for (let seat = 1; seat <= SEATS_PER_ROW; seat++) {
			if (room.sold_out || random() < BOOKED_SHARE) taken.add(`${row}${seat}`);
		}
	}
	if (room.sold_out) taken.delete(HOUSE_SEAT);
	return taken;
}

/** The showtime a ticket is printed for: the next one, or "Now" after the last show. */
export function ticketTime(cinemaDate: string, room: CinemaRoom): string {
	const states = showtimeStates(cinemaDate, room.showtimes);
	const next = states.indexOf('next');
	return next >= 0 ? room.showtimes[next] : 'Now';
}

export function ticketNumber(cinemaDate: string, room: number, seats: string[]): string {
	return `${cinemaDate.replaceAll('-', '')}-${String(room).padStart(2, '0')}-${seats.join('')}`;
}

export type Chip = { label: string; state: ShowtimeState };

/** Showtime chips; after the last show a "Late show" chip, because the reel always waits. */
export function showtimeChips(cinemaDate: string, times: string[], lateLabel = 'Late show'): Chip[] {
	const states = showtimeStates(cinemaDate, times);
	const chips = times.map((label, i) => ({ label, state: states[i] }));
	if (times.length && !states.includes('next')) chips.push({ label: lateLabel, state: 'next' });
	return chips;
}
