export type Health = { status: string; version: string };

export type SubsystemState = 'ok' | 'warning' | 'error' | 'unconfigured';

export type JellyfinStatus = {
	state: SubsystemState;
	message: string | null;
	version?: string;
	server_name?: string;
	user?: string | null;
	counts?: Record<string, number>;
	sync?: { running: boolean; last_sync_at: string | null; last_error: string | null };
};

export type ProjectorStatus = {
	state: SubsystemState;
	message: string | null;
	address?: string;
	remote?: 'connected' | 'connecting' | 'unreachable' | 'unpaired' | 'pairing' | 'unconfigured';
	adb?: 'device' | 'unavailable';
	power?: 'on' | 'standby' | 'unknown';
	foreground?: string | null;
	jellyfin_in_front?: boolean;
};

export type SessionStatus = {
	state: SubsystemState;
	message: string | null;
	device_name?: string;
	now_playing?: string | null;
	paused?: boolean;
};

export type Status = { jellyfin: JellyfinStatus; projector: ProjectorStatus; session: SessionStatus };

export type AppSettings = { projector_address: string | null; projector_device_id: string | null };

export type JellyfinSession = {
	device_id: string;
	device_name: string;
	client: string;
	version: string;
	user: string | null;
	host: string | null;
	last_activity: string;
	remote_control: boolean;
	now_playing: string | null;
	selected: boolean;
	is_projector: boolean;
};

export type ShowStep = { step: string; status: 'running' | 'done' | 'failed' | 'cancelled'; message: string | null; at: string };

export type Show = {
	id: number;
	trigger: string;
	item_id: string;
	item_name: string;
	state: 'running' | 'playing' | 'failed' | 'cancelled';
	steps: ShowStep[];
	error: string | null;
	created_at: string;
	finished_at: string | null;
};

export type ProgrammeItem = {
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
	trailer_urls: string[];
};

export type ProgrammeRoom = {
	number: number;
	name: string;
	kind: 'movie' | 'series';
	item: ProgrammeItem | null;
	showtimes: string[];
	source: 'generated' | 'override' | null;
	sold_out: boolean;
	sticky: boolean;
};

export type Programme = { date: string; rooms: ProgrammeRoom[] };

export type SampleItem = {
	id: string;
	type: string;
	name: string;
	year: number | null;
	poster_tag: string | null;
	played: boolean;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(path, init);
	if (!response.ok) {
		const detail = await response.json().then((b) => b?.detail).catch(() => null);
		throw new Error(typeof detail === 'string' ? detail : `${init?.method ?? 'GET'} ${path} failed: ${response.status}`);
	}
	return response.json();
}

export const getHealth = () => request<Health>('/api/health');
export const getStatus = () => request<Status>('/api/admin/status');
export const triggerLibrarySync = () => request<{ started: boolean }>('/api/admin/library/sync', { method: 'POST' });
export const getLibrarySample = (count = 12) => request<SampleItem[]>(`/api/admin/library/sample?count=${count}`);

export const searchLibrary = (q: string) =>
	request<SampleItem[]>(`/api/admin/library/search?q=${encodeURIComponent(q)}`);
export const getSettings = () => request<AppSettings>('/api/admin/settings');
export const updateSettings = (changes: Partial<AppSettings>) =>
	request<AppSettings>('/api/admin/settings', {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(changes)
	});
export const getSessions = () => request<JellyfinSession[]>('/api/admin/sessions');
export const getShows = () => request<Show[]>('/api/admin/shows');
export const startShow = (itemId: string) =>
	request<Show>('/api/admin/shows', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ item_id: itemId })
	});

const post = <T>(path: string, body?: unknown) =>
	request<T>(path, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body)
	});

export const startPairing = () => post<{ state: string }>('/api/admin/projector/pairing/start');
export const finishPairing = (code: string) =>
	post<{ state: string }>('/api/admin/projector/pairing/finish', { code });

export const getProgramme = () => request<Programme>('/api/admin/programme');
export const rerollRoom = (room?: number) => post<Programme>('/api/admin/programme/reroll', { room: room ?? null });
export const dropSeries = (room: number) => post<Programme>(`/api/admin/rooms/${room}/drop-series`);
export const playRoom = (room: number) => post<Show>(`/api/admin/rooms/${room}/play`);

type EventHandlers = { show?: (show: Show) => void; programme?: () => void };

/** Subscribe to server-sent events; returns an unsubscribe function. */
export function subscribe(handlers: EventHandlers): () => void {
	const source = new EventSource('/api/events');
	const { show, programme } = handlers;
	if (show) source.addEventListener('show', (e) => show(JSON.parse((e as MessageEvent).data)));
	if (programme) source.addEventListener('programme', () => programme());
	return () => source.close();
}

export function imageUrl(
	itemId: string,
	type: 'Primary' | 'Backdrop' | 'Logo' | 'Thumb',
	tag?: string | null,
	width?: number
) {
	const params = new URLSearchParams();
	if (tag) params.set('tag', tag);
	if (width) params.set('w', String(width));
	const query = params.toString();
	return `/api/img/${itemId}/${type}${query ? `?${query}` : ''}`;
}
