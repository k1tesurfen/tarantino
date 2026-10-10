<script lang="ts">
	import { page } from '$app/state';
	import { cinema } from '$lib/cinema/state.svelte';
	import { themeFor } from '$lib/themes';

	const theme = $derived(themeFor(cinema.theme));
	const room = $derived(Number(page.params.room));
</script>

<theme.Tickets {room} />
