import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		// During `npm run dev`, forward API calls to a backend on :8000.
		proxy: { '/api': 'http://localhost:8000' }
	}
});
