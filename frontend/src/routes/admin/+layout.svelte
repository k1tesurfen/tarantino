<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount, type Snippet } from 'svelte';
	import { getSession, logout, type AdminSession } from '$lib/api';

	let { children }: { children: Snippet } = $props();

	let session = $state<AdminSession | null>(null);
	let unreachable = $state(false);
	const onLogin = $derived(page.url.pathname === '/admin/login');

	const nav = [
		{ href: '/admin', label: 'Dashboard' },
		{ href: '/admin/programme', label: 'Programme' },
		{ href: '/admin/rooms', label: 'Rooms' },
		{ href: '/admin/franchises', label: 'Franchises' },
		{ href: '/admin/cassettes', label: 'Cassettes' },
		{ href: '/admin/settings', label: 'Settings' },
		{ href: '/admin/backups', label: 'Backups' }
	];

	async function check() {
		try {
			session = await getSession();
			unreachable = false;
		} catch {
			// tarantino is restarting or down: keep trying
			unreachable = true;
			setTimeout(check, 5000);
			return;
		}
		if (!session.authenticated && !onLogin) goto('/admin/login');
	}

	async function signOut() {
		await logout();
		goto('/admin/login');
	}

	onMount(() => {
		check();
		const onUnauthorized = () => goto('/admin/login');
		window.addEventListener('tarantino:unauthorized', onUnauthorized);
		return () => window.removeEventListener('tarantino:unauthorized', onUnauthorized);
	});
</script>

<div class="admin">
<div class="admin-inner">
	<header>
		<a class="brand" href="/admin">tarantino <span>admin</span></a>
		{#if !onLogin}
			<nav>
				{#each nav as item}
					<a href={item.href} class:active={page.url.pathname === item.href}>{item.label}</a>
				{/each}
			</nav>
			<div class="right">
				<a href="/">Cinema ↗</a>
				{#if session?.password_set}<button class="ghost" onclick={signOut}>Log out</button>{/if}
			</div>
		{/if}
	</header>

	{#if unreachable}
		<p class="banner warn">
			tarantino is not responding. It may be restarting; this page retries every few seconds. On the mini-PC:
			<code>sudo journalctl -u tarantino.service -n 50</code>
		</p>
	{/if}

	{#if session && !session.password_set && !onLogin}
		<p class="banner warn">
			No admin password is set, so this admin is open to everyone on the network. Set
			<code>TARANTINO_ADMIN_PASSWORD</code> in the environment file on the mini-PC.
		</p>
	{/if}

	{#if session?.authenticated || onLogin}
		{@render children()}
	{/if}
</div>
</div>

<style>
	.admin {
		--bg: #121316;
		--panel: #1b1c20;
		--line: #2a2c31;
		--text: #e9e7e2;
		--muted: #8a8790;
		--accent: #e8c46a;
		min-height: 100vh;
		background: var(--bg);
		color: var(--text);
		font-family: system-ui, sans-serif;
	}
	.admin-inner {
		max-width: 78rem;
		margin: 0 auto;
		padding: 1rem 1rem 4rem;
	}
	header {
		display: flex;
		align-items: center;
		gap: 1.5rem;
		flex-wrap: wrap;
		border-bottom: 1px solid var(--line);
		padding-bottom: 0.75rem;
		margin-bottom: 1.25rem;
	}
	.brand {
		font-size: 1.3rem;
		font-weight: 700;
		color: var(--text);
		text-decoration: none;
	}
	.brand span {
		color: var(--muted);
		font-weight: 400;
	}
	nav {
		display: flex;
		gap: 0.25rem;
		flex-wrap: wrap;
	}
	nav a {
		color: var(--muted);
		text-decoration: none;
		padding: 0.35rem 0.7rem;
		border-radius: 0.35rem;
	}
	nav a.active,
	nav a:hover {
		color: var(--text);
		background: var(--panel);
	}
	.right {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 1rem;
	}
	.banner.warn {
		background: #3d3212;
		border: 1px solid #5a4614;
		color: #f3d27a;
		padding: 0.6rem 1rem;
		border-radius: 0.35rem;
	}

	/* Shared admin building blocks */
	.admin :global(a) {
		color: var(--accent);
	}
	.admin :global(h2) {
		font-size: 1.1rem;
		margin: 2rem 0 0.6rem;
	}
	.admin :global(button) {
		background: var(--accent);
		color: var(--bg);
		border: 0;
		border-radius: 0.35rem;
		padding: 0.45rem 0.9rem;
		font: inherit;
		font-weight: 600;
		cursor: pointer;
		white-space: nowrap;
	}
	.admin :global(button:disabled) {
		opacity: 0.55;
		cursor: default;
	}
	.admin :global(button.ghost) {
		background: transparent;
		color: var(--accent);
		border: 1px solid #3a3c42;
		padding: 0.3rem 0.65rem;
		font-weight: 500;
	}
	.admin :global(input),
	.admin :global(select),
	.admin :global(textarea) {
		background: var(--bg);
		color: var(--text);
		border: 1px solid #3a3c42;
		border-radius: 0.35rem;
		padding: 0.45rem 0.6rem;
		font: inherit;
		min-width: 0;
		box-sizing: border-box;
	}
	.admin :global(.muted) {
		color: var(--muted);
		font-size: 0.9rem;
	}
	.admin :global(.error) {
		color: #f3a1a1;
		font-size: 0.9rem;
	}
	.admin :global(.section-head) {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
	}
	.admin :global(.mono) {
		font-family: ui-monospace, monospace;
		font-size: 0.85em;
	}
	.admin :global(dl) {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.3rem 1rem;
		font-size: 0.9rem;
	}
	.admin :global(dt) {
		color: var(--muted);
	}
	.admin :global(dd) {
		margin: 0;
		overflow-wrap: anywhere;
	}
</style>
