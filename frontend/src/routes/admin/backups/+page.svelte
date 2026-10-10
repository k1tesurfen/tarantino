<script lang="ts">
	import { onMount } from 'svelte';
	import {
		backupUrl,
		createBackup,
		exportUrl,
		importConfig,
		listBackups,
		previewBackup,
		previewImport,
		restoreBackup,
		type BackupInfo,
		type ImportPreview
	} from '$lib/api';

	let backups = $state<BackupInfo[]>([]);
	let includeState = $state(true);
	let error = $state<string | null>(null);
	let notice = $state<string | null>(null);

	// A pending import: a preview plus the action that applies it.
	let pending = $state<{ source: string; preview: ImportPreview; apply: () => Promise<{ backup: string }> } | null>(
		null
	);

	async function load() {
		backups = await listBackups();
	}

	async function run(action: () => Promise<void>) {
		error = notice = null;
		try {
			await action();
		} catch (e) {
			error = (e as Error).message;
		}
	}

	async function onFile(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		await run(async () => {
			let document: unknown;
			try {
				document = JSON.parse(await file.text());
			} catch {
				throw new Error(`${file.name} is not a JSON file`);
			}
			pending = { source: file.name, preview: await previewImport(document), apply: () => importConfig(document) };
		});
	}

	async function prepareRestore(backup: BackupInfo) {
		await run(async () => {
			pending = { source: backup.name, preview: await previewBackup(backup.name), apply: () => restoreBackup(backup.name) };
		});
	}

	async function confirmImport() {
		if (!pending) return;
		const { apply, source } = pending;
		await run(async () => {
			const result = await apply();
			pending = null;
			notice = `Imported ${source}. The previous configuration was saved as ${result.backup}.`;
			await load();
		});
	}

	const formatSize = (bytes: number) => `${(bytes / 1024).toFixed(1)} KB`;
	const formatValue = (value: unknown) => (value === null ? '—' : JSON.stringify(value));
	const hasChanges = (p: ImportPreview) =>
		Object.keys(p.settings_changed).length + p.rooms_added.length + p.rooms_changed.length + p.rooms_removed.length > 0 ||
		p.state_included;

	onMount(load);
</script>

<svelte:head><title>Backups · tarantino</title></svelte:head>

<h2>Export</h2>
<p class="muted">
	The export contains all admin settings, rooms and cassettes, never passwords or tokens. With state it also contains
	sticky series and the programme history (cooldowns).
</p>
<div class="row">
	<label class="check"><input type="checkbox" bind:checked={includeState} /> Include state</label>
	<a class="button" href={exportUrl(includeState)} download>Download export</a>
</div>

<h2>Import</h2>
<p class="muted">You will see what changes before anything is applied. The current configuration is backed up first.</p>
<input type="file" accept=".json,application/json" onchange={onFile} />

{#if error}<p class="error">{error}</p>{/if}
{#if notice}<p class="notice">{notice}</p>{/if}

{#if pending}
	{@const p = pending.preview}
	<section class="preview">
		<h3>Import {pending.source}</h3>
		<p class="muted">Exported {new Date(p.exported_at).toLocaleString()} by tarantino {p.tarantino_version}</p>
		{#if !hasChanges(p)}
			<p>Nothing would change.</p>
		{/if}
		{#if Object.keys(p.settings_changed).length}
			<h4>Settings</h4>
			<ul>
				{#each Object.entries(p.settings_changed) as [key, change]}
					<li><code>{key}</code>: {formatValue(change.from)} → <strong>{formatValue(change.to)}</strong></li>
				{/each}
			</ul>
		{/if}
		{#if p.rooms_added.length || p.rooms_changed.length || p.rooms_removed.length}
			<h4>Rooms</h4>
			<ul>
				{#each p.rooms_added as room}<li class="added">+ {room}</li>{/each}
				{#each p.rooms_changed as room}<li>~ {room}</li>{/each}
				{#each p.rooms_removed as room}<li class="removed">− {room}</li>{/each}
			</ul>
		{/if}
		{#if p.state_included}
			<h4>State</h4>
			<p>
				Replaces sticky series ({p.series_assignments}) and programme history ({p.programme_entries} entries).
				{#if p.remapped_titles}{p.remapped_titles} titles were matched under a new Jellyfin id.{/if}
			</p>
			{#if p.unresolved_titles.length}
				<p class="error">Not in the library, will be skipped: {p.unresolved_titles.join(', ')}</p>
			{/if}
		{/if}
		<div class="row">
			<button onclick={confirmImport}>Apply import</button>
			<button class="ghost" onclick={() => (pending = null)}>Cancel</button>
		</div>
	</section>
{/if}

<div class="section-head">
	<h2>Backups on the mini-PC</h2>
	<button class="ghost" onclick={() => run(async () => (await createBackup(), await load()))}>Back up now</button>
</div>
<p class="muted">Written nightly, before every update and before every import. The last 14 of each kind are kept.</p>
{#if backups.length === 0}
	<p class="muted">No backups yet.</p>
{:else}
	<table>
		<thead><tr><th>Created</th><th>Reason</th><th>Size</th><th></th></tr></thead>
		<tbody>
			{#each backups as backup (backup.name)}
				<tr>
					<td>{new Date(backup.created_at).toLocaleString()}</td>
					<td>{backup.reason}</td>
					<td>{formatSize(backup.size)}</td>
					<td class="actions">
						<a href={backupUrl(backup.name)} download={backup.name}>Download</a>
						<button class="ghost" onclick={() => prepareRestore(backup)}>Restore…</button>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
{/if}

<style>
	.row {
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
	}
	.check {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	/* Scoped under .row so it outranks the layout's global link colour. */
	.row .button {
		background: var(--accent);
		color: var(--bg);
		border-radius: 0.35rem;
		padding: 0.45rem 0.9rem;
		font-weight: 600;
		text-decoration: none;
	}
	.notice {
		color: #9be3ae;
	}
	.preview {
		margin-top: 1rem;
		background: var(--panel);
		border: 1px solid var(--accent);
		border-radius: 0.5rem;
		padding: 0.5rem 1.25rem 1rem;
	}
	.preview h3 {
		margin-bottom: 0.2rem;
	}
	.preview h4 {
		margin: 1rem 0 0.3rem;
		color: var(--muted);
		font-weight: 500;
	}
	.preview ul {
		margin: 0;
		padding-left: 1.2rem;
		font-size: 0.9rem;
	}
	.added {
		color: #9be3ae;
	}
	.removed {
		color: #f3a1a1;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.9rem;
	}
	th,
	td {
		text-align: left;
		padding: 0.45rem 0.6rem;
		border-bottom: 1px solid var(--line);
	}
	th {
		color: var(--muted);
		font-weight: 500;
	}
	td.actions {
		display: flex;
		gap: 0.75rem;
		align-items: center;
	}
</style>
