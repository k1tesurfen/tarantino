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
	remote?: 'connected' | 'disconnected' | 'connecting' | 'unreachable' | 'unpaired' | 'pairing' | 'unconfigured';
	adb?: 'device' | 'unavailable';
	power?: 'on' | 'standby' | 'unknown';
	foreground?: string | null;
	jellyfin_in_front?: boolean;
	bluetooth?: BluetoothStatus | null;
};

export type BluetoothStatus = {
	available: boolean;
	paired: boolean;
	connected: boolean;
	pairing: boolean;
	name?: string | null;
	address?: string | null;
};

export type SessionStatus = {
	state: SubsystemState;
	message: string | null;
	device_name?: string;
	now_playing?: string | null;
	paused?: boolean;
};

export type MediaStatus = {
	state: SubsystemState;
	message: string | null;
	mounts: { path: string; ok: boolean; message: string }[];
};

export type HomeAssistantStatus = { state: SubsystemState; message: string | null; url?: string };

export type Status = {
	jellyfin: JellyfinStatus;
	projector: ProjectorStatus;
	session: SessionStatus;
	media: MediaStatus;
	home_assistant: HomeAssistantStatus;
};

export type AppSettings = {
	projector_address: string | null;
	projector_device_id: string | null;
	rollover_hour: number;
	movie_cooldown_days: number;
	series_cooldown_days: number;
	franchise_continue_chance: number;
	franchise_rest_days: number;
	franchise_stall_days: number;
	theme_modern_name: string;
	theme_retro_name: string;
	default_theme: 'modern' | 'retro';
	ha_url: string | null;
	media_paths: string[];
};

export type AdminSession = { password_set: boolean; authenticated: boolean };

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
	franchise: { name: string; part: number | null; parts: number; ordered: boolean } | null;
};

export type ProgrammeRoom = {
	number: number;
	name: string;
	kind: 'movie' | 'series';
	item: ProgrammeItem | null;
	next: ProgrammeItem | null;
	marathon: number;
	showtimes: string[];
	source: 'generated' | 'franchise' | 'override' | null;
	started: boolean;
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

export class Unauthorized extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(path, init);
	if (response.status === 401 && !path.endsWith('/login')) {
		window.dispatchEvent(new CustomEvent('tarantino:unauthorized'));
		throw new Unauthorized('Login required');
	}
	if (response.status === 204) return undefined as T;
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

export const bluetoothCommand = (action: 'pair' | 'stop' | 'unpair' | 'wake' | 'key', key?: string) =>
	post<BluetoothStatus>('/api/admin/projector/bluetooth', { action, key });

export const getSession = () => request<AdminSession>('/api/admin/session');
export const login = (password: string) => post<{ authenticated: boolean }>('/api/admin/login', { password });
export const logout = () => post<{ authenticated: boolean }>('/api/admin/logout');
export const swapRoom = (room: number, itemId: string) =>
	post<Programme>('/api/admin/programme/swap', { room, item_id: itemId });

export const getProgramme = () => request<Programme>('/api/admin/programme');
export const rerollRoom = (room?: number) => post<Programme>('/api/admin/programme/reroll', { room: room ?? null });
export const dropSeries = (room: number) => post<Programme>(`/api/admin/rooms/${room}/drop-series`);
export const playRoom = (room: number, next = false) =>
	post<Show>(`/api/admin/rooms/${room}/play${next ? '?next=true' : ''}`);

type EventHandlers = { show?: (show: Show) => void; programme?: () => void; vhs?: (update: VhsUpdate) => void };

/** Subscribe to server-sent events; returns an unsubscribe function. */
export function subscribe(handlers: EventHandlers): () => void {
	const source = new EventSource('/api/events');
	const { show, programme, vhs } = handlers;
	if (show) source.addEventListener('show', (e) => show(JSON.parse((e as MessageEvent).data)));
	if (programme) source.addEventListener('programme', () => programme());
	if (vhs) source.addEventListener('vhs', (e) => vhs(JSON.parse((e as MessageEvent).data)));
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

// -- rooms ---------------------------------------------------------------

export type MovieFilters = {
	watched: 'any' | 'unwatched' | 'watched';
	favorite: 'any' | 'yes' | 'no';
	genres_any: string[];
	genres_none: string[];
	tags_any: string[];
	tags_none: string[];
	official_ratings: string[];
	year_min: number | null;
	year_max: number | null;
	min_community_rating: number | null;
	min_critic_rating: number | null;
	runtime_min: number | null;
	runtime_max: number | null;
};

export type Weights = {
	community_rating: number;
	critic_rating: number;
	recently_added: number;
	never_shown: number;
};

export type Room = {
	number: number;
	name: string;
	kind: 'movie' | 'series';
	filters: MovieFilters;
	weights: Weights;
	active: boolean;
};

export type Facets = { genres: string[]; tags: string[]; official_ratings: string[] };

const send = <T>(method: string, path: string, body?: unknown) =>
	request<T>(path, {
		method,
		headers: { 'Content-Type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body)
	});

export const getRooms = () => request<Room[]>('/api/admin/rooms');
export const getPresets = () => request<Record<string, MovieFilters>>('/api/admin/rooms/presets');
export const getFacets = () => request<Facets>('/api/admin/library/facets');
export const createRoom = (room: Room) => send<Room>('POST', '/api/admin/rooms', room);
export const updateRoom = (number: number, room: Room) => send<Room>('PUT', `/api/admin/rooms/${number}`, room);
export const deleteRoom = (number: number) => send<void>('DELETE', `/api/admin/rooms/${number}`);
export const previewFilters = (filters: MovieFilters) =>
	send<{ count: number; sample: string[] }>('POST', '/api/admin/rooms/preview', { filters });

// -- config export / import / backups -------------------------------------

export type ImportPreview = {
	settings_changed: Record<string, { from: unknown; to: unknown }>;
	rooms_added: string[];
	rooms_removed: string[];
	rooms_changed: string[];
	cassettes_changed: string[];
	franchises_changed: string[];
	state_included: boolean;
	series_assignments: number;
	programme_entries: number;
	franchise_runs: number;
	unresolved_titles: string[];
	remapped_titles: number;
	exported_at: string;
	tarantino_version: string;
};

export type BackupInfo = { name: string; reason: string; created_at: string; size: number };

export const exportUrl = (state = true) => `/api/admin/config/export?state=${state}`;
export const previewImport = (document: unknown) => send<ImportPreview>('POST', '/api/admin/config/import/preview', document);
export const importConfig = (document: unknown) =>
	send<{ imported: boolean; backup: string }>('POST', '/api/admin/config/import', document);
export const listBackups = () => request<BackupInfo[]>('/api/admin/backups');
export const createBackup = () => send<BackupInfo>('POST', '/api/admin/backups');
export const backupUrl = (name: string) => `/api/admin/backups/${encodeURIComponent(name)}`;
export const previewBackup = (name: string) => send<ImportPreview>('POST', `${backupUrl(name)}/preview`);
export const restoreBackup = (name: string) =>
	send<{ imported: boolean; backup: string }>('POST', `${backupUrl(name)}/restore`);

// -- cassettes -----------------------------------------------------------

export type LearnState = {
	target: 'room' | 'franchise';
	room: number | null;
	room_name: string;
	expires_at: string;
	seconds_left: number;
};

export type VhsEvent = {
	id: number;
	action: 'insert' | 'eject';
	uid: string | null;
	room: number | null;
	outcome: 'played' | 'learned' | 'unknown' | 'failed' | 'ignored';
	message: string | null;
	show_id: number | null;
	at: string;
};

export type CassetteRoom = {
	number: number;
	name: string;
	kind: 'movie' | 'series';
	active: boolean;
	cassettes: { uid: string; learned_at: string }[];
};

export type Cassette = { uid: string; learned_at: string };

export type CassetteOverview = {
	rooms: CassetteRoom[];
	franchise: Cassette[];
	learn: LearnState | null;
	events: VhsEvent[];
};

export type VhsUpdate = { event: VhsEvent | null; learn: LearnState | null };

/** A room number, or 'franchise' for the franchise cassette. */
export type CassetteTarget = number | 'franchise';
const targetBody = (target: CassetteTarget) => (target === 'franchise' ? { franchise: true } : { room: target });

export const getCassettes = () => request<CassetteOverview>('/api/admin/cassettes');
export const armLearnMode = (target: CassetteTarget) =>
	send<LearnState>('POST', '/api/admin/cassettes/learn', targetBody(target));
export const cancelLearnMode = () => send<void>('DELETE', '/api/admin/cassettes/learn');
export const assignCassette = (uid: string, target: CassetteTarget) =>
	send<CassetteOverview>('PUT', `/api/admin/cassettes/${encodeURIComponent(uid)}`, targetBody(target));
export const removeCassette = (uid: string) =>
	send<CassetteOverview>('DELETE', `/api/admin/cassettes/${encodeURIComponent(uid)}`);

// -- franchises ----------------------------------------------------------

export type FranchisePart = {
	key: string;
	item_id: string;
	name: string;
	year: number | null;
	premiere_date: string | null;
	poster_tag: string | null;
	played: boolean;
	copies: number;
	started: boolean;
	next: boolean;
	today: number | null;
};

export type FranchiseState = 'started' | 'resting' | 'fresh' | 'off';

export type Franchise = {
	collection_id: string;
	name: string;
	default_name: string;
	any_order: boolean;
	custom_order: boolean;
	ordered: boolean;
	state: FranchiseState;
	progress: number;
	started_at: string | null;
	last_advanced_at: string | null;
	resting_until: string | null;
	parts: FranchisePart[];
	excluded: FranchisePart[];
};

export type FranchiseChanges = { name?: string; any_order?: boolean; order?: string[]; excluded?: string[] };

const franchisePath = (id: string) => `/api/admin/franchises/${encodeURIComponent(id)}`;
export const getFranchises = () => request<Franchise[]>('/api/admin/franchises');
export const updateFranchise = (id: string, changes: FranchiseChanges) =>
	send<Franchise>('PATCH', franchisePath(id), changes);
export const resetFranchise = (id: string) => send<Franchise>('POST', `${franchisePath(id)}/reset`);
export const setNextPart = (id: string, key: string) => send<Franchise>('POST', `${franchisePath(id)}/next`, { key });
