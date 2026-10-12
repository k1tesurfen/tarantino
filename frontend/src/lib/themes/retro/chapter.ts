import { roman, type FranchiseBadge } from '$lib/cinema/api';

/** "Chapter II · Terminator" on the retro bill (just the name when the franchise has no order). */
export function chapterLine(badge: FranchiseBadge): string {
	return badge.part ? `Chapter ${roman(badge.part)} · ${badge.name}` : badge.name;
}
