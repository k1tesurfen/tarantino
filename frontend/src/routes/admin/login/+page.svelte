<script lang="ts">
	import { login } from '$lib/api';

	let password = $state('');
	let error = $state<string | null>(null);
	let busy = $state(false);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = null;
		try {
			await login(password);
			location.href = '/admin'; // full load, so the layout re-checks the session
		} catch (e) {
			error = (e as Error).message;
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Login · tarantino</title></svelte:head>

<form class="login" onsubmit={submit}>
	<h1>Admin login</h1>
	<!-- svelte-ignore a11y_autofocus -->
	<input type="password" placeholder="Password" bind:value={password} autofocus autocomplete="current-password" />
	<button type="submit" disabled={busy || !password}>{busy ? 'Checking…' : 'Log in'}</button>
	{#if error}<p class="error">{error}</p>{/if}
</form>

<style>
	.login {
		max-width: 20rem;
		margin: 4rem auto;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
	h1 {
		font-size: 1.3rem;
	}
</style>
