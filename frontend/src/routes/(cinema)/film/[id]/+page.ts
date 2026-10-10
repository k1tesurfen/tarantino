import { error } from '@sveltejs/kit';
import { getTitle } from '$lib/cinema/api';

export async function load({ params }) {
	try {
		return { title: await getTitle(params.id) };
	} catch {
		error(404, 'This title is not in our programme.');
	}
}
