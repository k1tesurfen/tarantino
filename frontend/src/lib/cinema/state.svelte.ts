import type { Show } from '$lib/api';
import { getCinemaProgramme, getNow, playRoom, type CinemaProgramme, type NowPlaying, type ThemeId } from './api';

const THEME_KEY = 'tarantino.theme';

/** Themes with a complete layout; the toggle only appears when there is more than one. */
export const AVAILABLE_THEMES: ThemeId[] = ['modern', 'retro'];

function storedTheme(): ThemeId | null {
	try {
		const value = localStorage.getItem(THEME_KEY) as ThemeId | null;
		return value && AVAILABLE_THEMES.includes(value) ? value : null;
	} catch {
		return null;
	}
}

class CinemaState {
	programme = $state<CinemaProgramme | null>(null);
	error = $state<string | null>(null);
	theme = $state<ThemeId>('modern');
	now = $state<NowPlaying | null>(null);
	/** The show started from this browser, followed live until it finishes. */
	show = $state<Show | null>(null);

	#started = false;
	#latest = new Map<number, Show>(); // events may arrive before play() returns

	get name(): string {
		return this.programme?.cinema.names[this.theme] ?? '';
	}

	start() {
		if (this.#started) return;
		this.#started = true;
		this.theme = storedTheme() ?? 'modern';
		this.load();
		this.refreshNow();
		const source = new EventSource('/api/events');
		source.addEventListener('show', (event) => {
			const show: Show = JSON.parse((event as MessageEvent).data);
			this.#latest.set(show.id, show);
			if (this.show?.id === show.id) this.show = show;
			if (show.state !== 'running') this.refreshNow();
		});
		source.addEventListener('programme', () => this.load());
		setInterval(() => this.refreshNow(), 30_000);
	}

	async load() {
		try {
			this.programme = await getCinemaProgramme();
			this.error = null;
			if (!storedTheme() && AVAILABLE_THEMES.includes(this.programme.cinema.default_theme)) {
				this.theme = this.programme.cinema.default_theme;
			}
		} catch (e) {
			this.error = (e as Error).message;
		}
	}

	async refreshNow() {
		this.now = await getNow().catch(() => this.now);
	}

	setTheme(theme: ThemeId) {
		this.theme = theme;
		try {
			localStorage.setItem(THEME_KEY, theme);
		} catch {
			// private mode: the choice just isn't remembered
		}
	}

	async play(room: number): Promise<Show> {
		const started = await playRoom(room);
		this.show = this.#latest.get(started.id) ?? started;
		return this.show;
	}

	dismissShow() {
		this.show = null;
	}
}

export const cinema = new CinemaState();
