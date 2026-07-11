import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import TabbedLayout, { buildTabRoutes } from './TabbedLayout'
import type { TabConfig } from './TabbedLayout'

// dev_docs/v2/08_emulator_profiles_navigation.md, Locked decision 4: TabbedLayout
// must be "agnostic — takes its tab/route config entirely as props; zero
// built-in knowledge of 'games', 'profiles', 'controllers', or any domain."
// This is asserted two ways below: statically (the source text itself must not
// contain any real domain's words) and behaviorally (a synthetic, nonsense
// domain exercises every documented behavior identically to a real one would).

const SOURCE_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), 'TabbedLayout.tsx')
const FORBIDDEN_DOMAIN_WORDS = [
  'games', 'media', 'apps', 'profiles', 'profile', 'bios', 'rom-packs', 'rompack',
  'controllers', 'controller', 'health', 'emulator', 'software',
]

function renderTabbed(tabs: TabConfig[], initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/x" element={<TabbedLayout tabs={tabs} title="X" />}>
          {buildTabRoutes(tabs)}
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

function stripComments(source: string): string {
  // Block comments (JSDoc etc.) then line comments. The doc comments in this
  // file legitimately name real consumers ("Games", "Emulators", "Software")
  // as usage examples — that's documentation, not domain knowledge baked into
  // the component's actual logic, so it must not fail this check. Only the
  // executable code below is asserted to be domain-free.
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
}

describe('TabbedLayout — domain-agnostic contract', () => {
  it('contains no hardcoded domain strings in its executable source (comments excluded)', () => {
    const code = stripComments(fs.readFileSync(SOURCE_PATH, 'utf-8')).toLowerCase()
    for (const word of FORBIDDEN_DOMAIN_WORDS) {
      expect(code).not.toContain(word)
    }
  })

  it('renders an arbitrary, non-domain tab set purely from props', () => {
    const tabs: TabConfig[] = [
      { label: 'Widget', segment: 'widget', element: <div>widget-view</div> },
      { label: 'Gadget', segment: 'gadget', element: <div>gadget-view</div> },
    ]
    renderTabbed(tabs, '/x/widget')
    expect(screen.getByRole('link', { name: 'Widget' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Gadget' })).toBeInTheDocument()
    expect(screen.getByText('widget-view')).toBeInTheDocument()
  })

  it('derives the active tab from the URL, not from independent internal state', () => {
    const tabs: TabConfig[] = [
      { label: 'Widget', segment: 'widget', element: <div>widget-view</div> },
      { label: 'Gadget', segment: 'gadget', element: <div>gadget-view</div> },
    ]
    // Two independent mounts at two different URLs — if active-tab tracking
    // were internal useState instead of URL-derived, both mounts would show
    // whatever the default initial state is, not diverge with the route.
    // NavLink sets aria-current="page" on the active link by default (react-
    // router's own active-matching, not anything TabbedLayout implements
    // itself) — checking that attribute avoids any assumption about how the
    // inline active/inactive styles happen to serialize in jsdom.
    const first = renderTabbed(tabs, '/x/widget')
    expect(first.getByRole('link', { name: 'Widget' })).toHaveAttribute('aria-current', 'page')
    expect(first.getByRole('link', { name: 'Gadget' })).not.toHaveAttribute('aria-current')
    first.unmount()

    const second = renderTabbed(tabs, '/x/gadget')
    expect(second.getByRole('link', { name: 'Gadget' })).toHaveAttribute('aria-current', 'page')
    expect(second.getByRole('link', { name: 'Widget' })).not.toHaveAttribute('aria-current')
  })

  it('does not render a tab whose visible is false, and its route is unreachable', () => {
    const tabs: TabConfig[] = [
      { label: 'Widget', segment: 'widget', element: <div>widget-view</div> },
      { label: 'Hidden', segment: 'hidden', element: <div>hidden-view</div>, visible: false },
    ]
    renderTabbed(tabs, '/x/hidden')
    // Not in the tab bar
    expect(screen.queryByRole('link', { name: 'Hidden' })).not.toBeInTheDocument()
    // A deep link to the hidden segment does not mount its element — it lands
    // on the section's default (first visible) tab instead.
    expect(screen.queryByText('hidden-view')).not.toBeInTheDocument()
    expect(screen.getByText('widget-view')).toBeInTheDocument()
  })

  it('redirects a deep link to a nonexistent sub-route to the section index', () => {
    const tabs: TabConfig[] = [
      { label: 'Widget', segment: 'widget', element: <div>widget-view</div> },
      { label: 'Gadget', segment: 'gadget', element: <div>gadget-view</div> },
    ]
    renderTabbed(tabs, '/x/does-not-exist')
    expect(screen.getByText('widget-view')).toBeInTheDocument()
    expect(screen.queryByText('gadget-view')).not.toBeInTheDocument()
  })

  it('redirects the section index (no sub-route at all) to the first visible tab', () => {
    const tabs: TabConfig[] = [
      { label: 'Widget', segment: 'widget', element: <div>widget-view</div> },
      { label: 'Gadget', segment: 'gadget', element: <div>gadget-view</div> },
    ]
    renderTabbed(tabs, '/x')
    expect(screen.getByText('widget-view')).toBeInTheDocument()
  })

  it('consumes title as a prop rather than owning/deriving it', () => {
    const tabs: TabConfig[] = [{ label: 'Widget', segment: 'widget', element: <div>widget-view</div> }]
    render(
      <MemoryRouter initialEntries={['/x/widget']}>
        <Routes>
          <Route path="/x" element={<TabbedLayout tabs={tabs} title="Totally Arbitrary Title" />}>
            {buildTabRoutes(tabs)}
          </Route>
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: 'Totally Arbitrary Title' })).toBeInTheDocument()
  })
})
