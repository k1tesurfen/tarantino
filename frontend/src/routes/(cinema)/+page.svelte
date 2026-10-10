<script lang="ts">
	import { cinema } from '$lib/cinema/state.svelte';
	import { themeFor } from '$lib/themes';

	const theme = $derived(themeFor(cinema.theme));
</script>

<theme.Home />
