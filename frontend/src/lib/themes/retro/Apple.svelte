<script lang="ts">
	let { size = 48 }: { size?: number } = $props();
</script>

<!-- A red apple with a bite taken out, in flat screen-print colours. -->
<svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
	<path d="M33 14c1-5 5-9 11-10-1 6-5 10-11 10z" fill="#2c6b67" />
	<path d="M32 16c-2-4-3-7-3-10" stroke="#1e1712" stroke-width="2.5" stroke-linecap="round" fill="none" />
	<path
		d="M32 18c-6-4-17-4-21 6-4 10 0 24 7 31 4 4 9 5 14 3 5 2 10 1 14-3 2-2 4-5 5-8-4 1-8-2-8-6s4-7 8-6c0-1 0-2-1-3 1-2 0-5-2-7-4-9-11-11-16-7z"
		fill="#b5202b"
	/>
	<path d="M19 26c-2 4-2 9 0 13" stroke="#efe2c4" stroke-width="2.5" stroke-linecap="round" fill="none" opacity="0.7" />
</svg>
