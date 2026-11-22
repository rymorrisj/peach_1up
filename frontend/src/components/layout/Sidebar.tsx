import { NavLink, useNavigate } from 'react-router-dom';
import JobsBell from './JobsBell';
import { PLATFORM_LABELS } from '@/generated/constants';
import { PLATFORM_COLOR, PLATFORM_GROUPS, PLATFORM_SHORT_LABEL } from '@/types/platform';

const DOCS_BASE_URL =
  (import.meta.env.VITE_DOCS_BASE_URL as string | undefined) ?? 'http://localhost:3000';

// Side rail chip for a platform: short code, colour, full label.
function platformChip(slug: string) {
  const code = PLATFORM_SHORT_LABEL[slug] ?? slug.toUpperCase();
  return {
    code,
    color: PLATFORM_COLOR[code] ?? 'rgb(var(--fg-3))',
    label: PLATFORM_LABELS[slug] ?? slug,
  };
}

const NAV_ITEMS = [
  { to: '/software', label: 'Software', glyph: '📚' },
  { to: '/emulators', label: 'Emulators', glyph: '🖥️' },
  { to: '/environments', label: 'Environments', glyph: '💻' },
  { to: '/system', label: 'System', glyph: '🩺' },
  { to: '/tags', label: 'Tags', glyph: '🏷️' },
  { to: '/users', label: 'Users', glyph: '👤' },
  {
    to: `${DOCS_BASE_URL}/docs/user-guide`,
    label: 'Guides',
    glyph: '📖',
    external: true,
  },
  { to: '/settings', label: 'Settings', glyph: '⚙️' },
] as const;

export default function Sidebar() {
  const navigate = useNavigate();

  return (
    <aside
      className="flex shrink-0 flex-col"
      style={{
        width: 240,
        background: 'rgb(var(--surface-0))',
        borderRight: '1px solid rgb(var(--border))',
      }}
    >
      {/* Brand */}
      <div className="flex items-center gap-3 px-[18px] pb-3.5 pt-[18px]">
        <img
          src="/app-icon.svg"
          alt="Peach 1UP"
          width={36}
          height={36}
          style={{
            flexShrink: 0,
            filter: 'drop-shadow(0 2px 4px rgb(0 0 0 / 0.4))',
          }}
        />
        <div
          className="flex items-baseline gap-1.5"
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: '1.0625rem',
            letterSpacing: '-0.015em',
            color: 'rgb(var(--fg-1))',
          }}
        >
          Peach
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              fontSize: '0.75rem',
              letterSpacing: '0.12em',
              color: 'rgb(var(--peach-500))',
              padding: '3px 5px',
              border: '1px solid rgb(var(--peach-500) / 0.4)',
              borderRadius: 'var(--r-1)',
              background: 'rgb(var(--peach-500) / 0.08)',
              transform: 'translateY(-1px)',
              display: 'inline-block',
            }}
          >
            1UP
          </span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-1">
        <ul role="list" className="flex flex-col gap-0.5">
          {NAV_ITEMS.map(({ to, label, glyph, ...rest }) => {
            const isExternal = 'external' in rest && rest.external;

            if (isExternal) {
              return (
                <li key={to}>
                  <a
                    href={to}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2.5 rounded-lg px-3 py-[9px] text-sm font-medium transition-colors duration-[120ms] hover:text-fg-1 text-neutral-400"
                    style={{
                      fontFamily: 'var(--font-display)',
                      color: 'rgb(var(--fg-2))',
                      borderLeft: '2px solid transparent',
                    }}
                  >
                    <span
                      className="w-[18px] text-center text-base leading-none"
                      aria-hidden="true"
                    >
                      {glyph}
                    </span>
                    <span className="flex-1">{label}</span>
                  </a>
                </li>
              );
            }

            return (
              <li key={to}>
                <NavLink
                  to={to}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 rounded-lg px-3 py-[9px] text-sm font-medium transition-colors duration-[120ms] ${
                      isActive ? 'text-fg-1' : 'hover:text-fg-1 text-neutral-400'
                    }`
                  }
                  style={({ isActive }) => ({
                    fontFamily: 'var(--font-display)',
                    color: isActive ? 'rgb(var(--fg-1))' : 'rgb(var(--fg-2))',
                    background: isActive ? 'rgb(var(--surface-2))' : 'transparent',
                    borderLeft: isActive
                      ? '2px solid rgb(var(--peach-500))'
                      : '2px solid transparent',
                  })}
                >
                  <span className="w-[18px] text-center text-base leading-none" aria-hidden="true">
                    {glyph}
                  </span>
                  <span className="flex-1">{label}</span>
                </NavLink>
              </li>
            );
          })}
        </ul>

        {/* Background activity (uploads, large scans), hidden when idle */}
        <div className="mt-1 px-1">
          <JobsBell />
        </div>

        {/* Platforms jump-list, PC and Console subgroups */}
        <div
          className="mt-3 px-3.5 pb-1.5 pt-3.5"
          style={{
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            fontSize: '0.6875rem',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            color: 'rgb(var(--fg-3))',
          }}
        >
          Platforms
        </div>
        {PLATFORM_GROUPS.map((group) => (
          <div key={group.kind}>
            <div
              id={`sidebar-platforms-${group.kind}`}
              className="px-3.5 pb-1 pt-2"
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.625rem',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                color: 'rgb(var(--fg-3))',
              }}
            >
              {group.label}
            </div>
            <ul
              role="list"
              aria-labelledby={`sidebar-platforms-${group.kind}`}
              className="flex flex-col gap-0.5"
            >
              {group.platforms.map(({ value: slug }) => {
                const { code, color, label } = platformChip(slug);
                return (
                  <li key={slug}>
                    <button
                      type="button"
                      onClick={() => navigate(`/software/games?platform=${slug}`)}
                      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-[7px] transition-colors duration-[120ms] hover:text-neutral-200"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                      }}
                    >
                      <span
                        className="inline-block rounded"
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 600,
                          fontSize: '0.6875rem',
                          letterSpacing: '0.08em',
                          padding: '3px 5px',
                          border: `1px solid ${color}`,
                          color,
                          minWidth: 44,
                          textAlign: 'center',
                        }}
                      >
                        {code}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'rgb(var(--fg-3))' }}>
                        {label}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Sidebar bottom */}
      <div
        className="mt-auto px-4 py-3"
        style={{
          borderTop: '1px solid rgb(var(--border))',
          fontFamily: 'var(--font-mono)',
          fontSize: '0.6875rem',
          lineHeight: 1.4,
          color: 'rgb(var(--fg-3))',
        }}
      >
        <span style={{ color: 'rgb(var(--fg-2))', display: 'block', fontWeight: 600 }}>
          Peach 1UP
        </span>
        Retro Game Launcher
      </div>
    </aside>
  );
}
