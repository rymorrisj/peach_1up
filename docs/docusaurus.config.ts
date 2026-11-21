import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

// Full URL this docs site is reachable at. Set DOCS_BASE_URL in the
// environment when building (defaults to the local dev server).
const DOCS_BASE_URL = process.env.DOCS_BASE_URL ?? 'http://localhost:3000';

const config: Config = {
  title: 'Peach 1UP',
  tagline: 'Documentation',
  favicon: 'img/favicon.ico',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Set the production url of your site here
  url: DOCS_BASE_URL,
  // Set the /<baseUrl>/ pathname under which your site is served. Requires
  // both a leading and trailing slash (confirmed directly against
  // @docusaurus/core's own config schema, BaseUrlSchema in
  // configValidation.js, which normalizes every value through
  // addLeadingSlash(addTrailingSlash(value)) regardless of what is typed
  // here). Backend serves this build under app.mount("/docs", ...)
  // (backend/main.py), so the site's own baseUrl must match that mount path
  // for its emitted asset/script paths to resolve under the mount instead of
  // falling through to the SPA catch-all. The docs plugin below uses
  // routeBasePath '/', so pages live directly under baseUrl
  // (/docs/user-guide, not /docs/docs/user-guide).
  baseUrl: '/docs/',

  onBrokenLinks: 'throw',

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang. For example, if your site is Chinese, you
  // may want to replace "en" with "zh-Hans".
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          // Docs-only mode: serve docs at the site root so the full URL is
          // baseUrl + slug. The root route is the doc with `slug: /`
          // (docs/intro.md), which replaces the old src/pages/index.tsx.
          routeBasePath: '/',
          docItemComponent: '@theme/ApiItem',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  plugins: [
    [
      'docusaurus-plugin-openapi-docs',
      {
        id: 'api',
        docsPluginId: 'classic',
        config: {
          api: {
            specPath: '../shared/openapi.json',
            outputDir: 'docs/api',
            label: 'API Reference',
            sidebarOptions: {
              groupPathsBy: 'tag',
            },
          },
        },
      },
    ],
  ],

  themes: [
    [
      '@easyops-cn/docusaurus-search-local',
      {
        hashed: true,
        // Must match the docs plugin's routeBasePath. The plugin defaults to
        // 'docs' and would otherwise index no pages.
        docsRouteBasePath: '/',
      },
    ],
    'docusaurus-theme-openapi-docs',
  ],

  themeConfig: {
    // Replace with your project's social card
    image: 'img/docusaurus-social-card.jpg',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Peach 1UP Docs',
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Docs',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            // Site-relative paths: baseUrl ('/docs/') is prepended
            // automatically, so these resolve to /docs/getting-started etc.
            // Do not write the baseUrl into `to`; addBaseUrl skips the
            // prepend whenever `to` already starts with it.
            {
              label: 'Getting Started',
              to: '/getting-started',
            },
            {
              label: 'User Guide',
              to: '/user-guide',
            },
            {
              label: 'Contributor Guide',
              to: '/contributor-guide',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Peach 1UP.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
