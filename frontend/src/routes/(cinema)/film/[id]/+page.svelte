<script lang="ts">
	import { cinema } from '$lib/cinema/state.svelte';
	import { themeFor } from '$lib/themes';

	let { data } = $props();

	const theme = $derived(themeFor(cinema.theme));
</script>

<theme.Detail title={data.title} />
