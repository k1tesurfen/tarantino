<script lang="ts">
	import { onMount, type Snippet } from 'svelte';
	import { cinema } from '$lib/cinema/state.svelte';
	import { themeFor } from '$lib/themes';

	let { children }: { children: Snippet } = $props();

	const theme = $derived(themeFor(cinema.theme));

	onMount(() => cinema.start());
</script>

<theme.Shell>{@render children()}</theme.Shell>
