<script lang="ts">
	import { page } from '$app/state';
	import { cinema } from '$lib/cinema/state.svelte';
	import { themeFor } from '$lib/themes';

	const theme = $derived(themeFor(cinema.theme));
	const room = $derived(Number(page.params.room));
	const next = $derived(page.url.searchParams.has('next'));
</script>

<theme.Tickets {room} {next} />
