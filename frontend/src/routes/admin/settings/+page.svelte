<script lang="ts">
	import { onMount } from 'svelte';
	import { getSettings, updateSettings, type AppSettings } from '$lib/api';

	let saved = $state<AppSettings | null>(null);
	let form = $state<AppSettings | null>(null);
	let mediaPaths = $state('');
	let error = $state<string | null>(null);
	let notice = $state<string | null>(null);
	let busy = $state(false);

	function load(settings: AppSettings) {
		saved = settings;
		form = structuredClone(settings);
		mediaPaths = settings.media_paths.join('\n');
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (!form || !saved) return;
		const next: AppSettings = {
			...form,
			media_paths: mediaPaths
				.split('\n')
				.map((p) => p.trim())
				.filter(Boolean)
		};
		const changes = Object.fromEntries(
			Object.entries(next).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(saved![key as keyof AppSettings]))
		);
		if (Object.keys(changes).length === 0) {
			notice = 'Nothing changed.';
			return;
		}
		busy = true;
		error = notice = null;
		try {
			load(await updateSettings(changes));
			notice = 'Saved.';
		} catch (e) {
			error = (e as Error).message;
		} finally {
			busy = false;
		}
	}

	onMount(async () => load(await getSettings()));
</script>

<svelte:head><title>Settings · tarantino</title></svelte:head>

{#if form}
	<form onsubmit={save}>
		<fieldset>
			<legend>Cinema</legend>
			<label>Modern theme name <input bind:value={form.theme_modern_name} maxlength="40" required /></label>
			<label>Retro theme name <input bind:value={form.theme_retro_name} maxlength="40" required /></label>
			<label>
				Default theme for new visitors
				<select bind:value={form.default_theme}>
					<option value="modern">{form.theme_modern_name} (modern)</option>
					<option value="retro">{form.theme_retro_name} (retro)</option>
				</select>
			</label>
		</fieldset>

		<fieldset>
			<legend>Programme</legend>
			<label>
				New cinema day starts at
				<select bind:value={form.rollover_hour}>
					{#each Array.from({ length: 24 }, (_, h) => h) as hour}
						<option value={hour}>{String(hour).padStart(2, '0')}:00</option>
					{/each}
				</select>
			</label>
			<label>
				Movie cooldown (days before a film may return)
				<input type="number" min="0" max="365" bind:value={form.movie_cooldown_days} />
			</label>
			<label>
				Series cooldown (days before a non-sticky series may return)
				<input type="number" min="0" max="365" bind:value={form.series_cooldown_days} />
			</label>
		</fieldset>

		<fieldset>
			<legend>Projector</legend>
			<label>Address (IP or hostname) <input bind:value={form.projector_address} placeholder="e.g. 192.0.2.50" /></label>
			<label>
				Jellyfin device id
				<span class="with-button">
					<input value={form.projector_device_id ?? 'not selected'} readonly class="mono" />
					{#if form.projector_device_id}
						<button type="button" class="ghost" onclick={() => form && (form.projector_device_id = null)}>Clear</button>
					{/if}
				</span>
				<small class="muted">Pick it on the dashboard in the Jellyfin sessions table.</small>
			</label>
		</fieldset>

		<fieldset>
			<legend>Home & media</legend>
			<label>
				Home Assistant URL
				<input bind:value={form.ha_url} placeholder="http://homeassistant.local:8123" />
				<small class="muted">The access token lives in the environment file (TARANTINO_HA_TOKEN).</small>
			</label>
			<label>
				Media mounts to monitor (one path per line)
				<textarea rows="3" bind:value={mediaPaths} class="mono"></textarea>
			</label>
		</fieldset>

		<div class="footer">
			<button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save settings'}</button>
			{#if notice}<span class="muted">{notice}</span>{/if}
			{#if error}<span class="error">{error}</span>{/if}
		</div>
	</form>
{:else}
	<p class="muted">Loading…</p>
{/if}

<style>
	form {
		max-width: 44rem;
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}
	fieldset {
		border: 1px solid var(--line);
		border-radius: 0.5rem;
		padding: 0.75rem 1.25rem 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}
	legend {
		padding: 0 0.4rem;
		font-weight: 600;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		font-size: 0.9rem;
	}
	.with-button {
		display: flex;
		gap: 0.5rem;
	}
	.with-button input {
		flex: 1;
	}
	.footer {
		display: flex;
		align-items: center;
		gap: 1rem;
	}
</style>
