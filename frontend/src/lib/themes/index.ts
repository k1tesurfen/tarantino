import type { Component, Snippet } from 'svelte';
import type { ThemeId, TitleDetail } from '$lib/cinema/api';
import * as modern from './modern';
import * as retro from './retro';

/** A cinema theme provides a complete layout for every cinema page. */
export type Theme = {
	Shell: Component<{ children: Snippet }>;
	Home: Component;
	Detail: Component<{ title: TitleDetail }>;
	Tickets: Component<{ room: number }>;
};

const themes: Record<ThemeId, Theme> = { modern, retro };

export const themeFor = (id: ThemeId): Theme => themes[id] ?? modern;
