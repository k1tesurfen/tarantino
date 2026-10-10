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
	reachable?: boolean;
	adb?: string;
	screen_on?: boolean | null;
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
	if (!response.ok) throw new Error(`${init?.method ?? 'GET'} ${path} failed: ${response.status}`);
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

/** Subscribe to server-sent events; returns an unsubscribe function. */
export function subscribe(handlers: { show?: (show: Show) => void }): () => void {
	const source = new EventSource('/api/events');
	if (handlers.show) {
		const onShow = handlers.show;
		source.addEventListener('show', (e) => onShow(JSON.parse((e as MessageEvent).data)));
	}
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
