/**
 * The documentation table of contents.
 *
 * Order matters: the sidebar renders it as written, and the previous/next pager
 * walks the flattened list, so this array is also the reading order for someone
 * going through the docs front to back.
 */
export const GH = 'https://github.com/assevra/assevra';
export const PYPI = 'https://pypi.org/project/assevra/';
export const DOI = 'https://doi.org/10.5281/zenodo.21200852';

export interface NavItem {
  label: string;
  href: string;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const NAV: NavSection[] = [
  {
    title: 'Start here',
    items: [
      { label: 'Overview', href: '/docs' },
      { label: 'Getting started', href: '/docs/getting-started' },
      { label: 'Concepts', href: '/docs/concepts' },
    ],
  },
  {
    title: 'What it measures',
    items: [
      { label: 'Dimensions', href: '/docs/dimensions' },
      { label: 'Methodology', href: '/docs/methodology' },
      { label: 'Judge calibration', href: '/docs/calibration' },
    ],
  },
  {
    title: 'Using it',
    items: [
      { label: 'Configuration', href: '/docs/configuration' },
      { label: 'CLI reference', href: '/docs/cli' },
      { label: 'Python SDK', href: '/docs/sdk' },
      { label: 'Integrations', href: '/docs/integrations' },
      { label: 'CI & the GitHub Action', href: '/docs/ci' },
    ],
  },
  {
    title: 'The artifact',
    items: [
      { label: 'Schemas', href: '/docs/schemas' },
      { label: 'Security & signing', href: '/docs/security' },
      { label: 'Governance mapping', href: '/docs/governance' },
    ],
  },
  {
    title: 'Help',
    items: [
      { label: 'FAQ', href: '/docs/faq' },
      { label: 'Troubleshooting', href: '/docs/troubleshooting' },
    ],
  },
];
