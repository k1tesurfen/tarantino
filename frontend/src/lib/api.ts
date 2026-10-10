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

export type Status = { jellyfin: JellyfinStatus };

export type SampleItem = { id: string; type: string; name: string; year: number | null; poster_tag: string };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(path, init);
	if (!response.ok) throw new Error(`${init?.method ?? 'GET'} ${path} failed: ${response.status}`);
	return response.json();
}

export const getHealth = () => request<Health>('/api/health');
export const getStatus = () => request<Status>('/api/admin/status');
export const triggerLibrarySync = () => request<{ started: boolean }>('/api/admin/library/sync', { method: 'POST' });
export const getLibrarySample = (count = 12) => request<SampleItem[]>(`/api/admin/library/sample?count=${count}`);

export function imageUrl(itemId: string, type: 'Primary' | 'Backdrop' | 'Logo' | 'Thumb', tag?: string, width?: number) {
	const params = new URLSearchParams();
	if (tag) params.set('tag', tag);
	if (width) params.set('w', String(width));
	const query = params.toString();
	return `/api/img/${itemId}/${type}${query ? `?${query}` : ''}`;
}
