// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

// Custom domain at root (GitHub Pages, CNAME = assevra.ai).
const SITE = process.env.SITE_URL ?? 'https://assevra.ai';

export default defineConfig({
  site: SITE,
  trailingSlash: 'ignore',
  integrations: [sitemap()],
  vite: {
    plugins: [tailwindcss()],
  },
});
