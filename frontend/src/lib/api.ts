export type Health = { status: string; version: string };

export async function getHealth(fetchFn: typeof fetch = fetch): Promise<Health> {
	const response = await fetchFn('/api/health');
	if (!response.ok) throw new Error(`Health check failed: ${response.status}`);
	return response.json();
}
