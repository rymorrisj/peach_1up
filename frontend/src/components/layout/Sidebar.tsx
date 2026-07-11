import { NavLink, useNavigate } from "react-router-dom";
import JobsBell from "./JobsBell";

const DOCS_BASE_URL =
  (import.meta.env.VITE_DOCS_BASE_URL as string | undefined) ??
  "http://localhost:3000";

const ERA_ITEMS = [
  { label: "DOS", slug: "dos", color: "var(--era-dos)" },
  { label: "WIN95", slug: "win95", color: "var(--era-win95)" },
  { label: "WIN98", slug: "win98", color: "var(--era-win98)" },
  { label: "WINXP", slug: "winxp", color: "var(--era-winxp)" },
];

const CONSOLE_ERA_ITEMS = [
  { label: "PS1", slug: "ps1", color: "#a9a0d6" },
  { label: "PS2", slug: "ps2", color: "#6090d0" },
  { label: "XBOX", slug: "xbox", color: "#6db36d" },
  { label: "NES", slug: "nes", color: "#d06060" },
  { label: "SNES", slug: "snes", color: "#d4a0c0" },
  { label: "N64", slug: "n64", color: "#60a0d0" },
  { label: "DREAMCAST", slug: "dreamcast", color: "#d0a060" },
];

const NAV_ITEMS = [
  { to: "/software", label: "Software", glyph: "📚" },
  { to: "/emulators", label: "Emulators", glyph: "🖥️" },
  { to: "/environments", label: "Environments", glyph: "💻" },
  { to: "/platform-health", label: "Platform Health", glyph: "🩺" },
  { to: "/tags", label: "Tags", glyph: "🏷️" },
  { to: "/users", label: "Users", glyph: "👤" },
  {
    to: `${DOCS_BASE_URL}/docs/user-guide`,
    label: "Guides",
    glyph: "📖",
    external: true,
  },
  { to: "/settings", label: "Settings", glyph: "⚙️" },
] as const;

export default function Sidebar() {
  const navigate = useNavigate();

  return (
    <aside
      className="flex shrink-0 flex-col"
      style={{
        width: 240,
        background: "var(--surface-0)",
        borderRight: "1px solid var(--border)",
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
            filter: "drop-shadow(0 2px 4px rgb(0 0 0 / 0.4))",
          }}
        />
        <div
          className="flex items-baseline gap-1.5"
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: 17,
            letterSpacing: "-0.015em",
            color: "var(--fg-1)",
          }}
        >
          Peach
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontWeight: 700,
              fontSize: 12,
              letterSpacing: "0.12em",
              color: "var(--peach-500)",
              padding: "3px 5px",
              border: "1px solid rgb(255 138 92 / 0.4)",
              borderRadius: "var(--r-1)",
              background: "rgb(255 138 92 / 0.08)",
              transform: "translateY(-1px)",
              display: "inline-block",
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
            const isExternal = "external" in rest && rest.external;

            if (isExternal) {
              return (
                <li key={to}>
                  <a
                    href={to}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2.5 rounded-lg px-3 py-[9px] text-sm font-medium transition-colors duration-[120ms] hover:text-fg-1 text-neutral-400"
                    style={{
                      fontFamily: "var(--font-display)",
                      color: "var(--fg-2)",
                      borderLeft: "2px solid transparent",
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
                      isActive
                        ? "text-fg-1"
                        : "hover:text-fg-1 text-neutral-400"
                    }`
                  }
                  style={({ isActive }) => ({
                    fontFamily: "var(--font-display)",
                    color: isActive ? "var(--fg-1)" : "var(--fg-2)",
                    background: isActive ? "var(--surface-2)" : "transparent",
                    borderLeft: isActive
                      ? "2px solid var(--peach-500)"
                      : "2px solid transparent",
                  })}
                >
                  <span
                    className="w-[18px] text-center text-base leading-none"
                    aria-hidden="true"
                  >
                    {glyph}
                  </span>
                  <span className="flex-1">{label}</span>
                </NavLink>
              </li>
            );
          })}
        </ul>

        {/* Background activity (uploads, large scans) — hidden when idle */}
        <div className="mt-1 px-1">
          <JobsBell />
        </div>

        {/* Eras jump-list */}
        <div
          className="mt-3 px-3.5 pb-1.5 pt-3.5"
          style={{
            fontFamily: "var(--font-mono)",
            fontWeight: 600,
            fontSize: 11,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--fg-3)",
          }}
        >
          Eras
        </div>
        <ul role="list" className="flex flex-col gap-0.5">
          {ERA_ITEMS.map(({ label, slug, color }) => (
            <li key={slug}>
              <button
                type="button"
                onClick={() => navigate(`/software/games?era=${slug}`)}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-[7px] transition-colors duration-[120ms] hover:text-neutral-200"
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                <span
                  className="inline-block rounded"
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontWeight: 600,
                    fontSize: 11,
                    letterSpacing: "0.08em",
                    padding: "3px 5px",
                    border: `1px solid ${color}`,
                    color,
                    minWidth: 44,
                    textAlign: "center",
                  }}
                >
                  {label}
                </span>
                <span style={{ fontSize: 12, color: "var(--fg-3)" }}>
                  {label === "DOS" && "DOS 6.22"}
                  {label === "WIN95" && "Windows 95"}
                  {label === "WIN98" && "Windows 98"}
                  {label === "WINXP" && "Windows XP"}
                </span>
              </button>
            </li>
          ))}
        </ul>

        {/* Consoles jump-list */}
        <div
          className="mt-3 px-3.5 pb-1.5 pt-3.5"
          style={{
            fontFamily: "var(--font-mono)",
            fontWeight: 600,
            fontSize: 11,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--fg-3)",
          }}
        >
          Consoles
        </div>
        <ul role="list" className="flex flex-col gap-0.5">
          {CONSOLE_ERA_ITEMS.map(({ label, slug, color }) => (
            <li key={slug}>
              <button
                type="button"
                onClick={() => navigate(`/software/games?era=${slug}`)}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-[7px] transition-colors duration-[120ms] hover:text-neutral-200"
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                <span
                  className="inline-block rounded"
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontWeight: 600,
                    fontSize: 11,
                    letterSpacing: "0.08em",
                    padding: "3px 5px",
                    border: `1px solid ${color}`,
                    color,
                    minWidth: 44,
                    textAlign: "center",
                  }}
                >
                  {label}
                </span>
                <span style={{ fontSize: 12, color: "var(--fg-3)" }}>
                  {label === "PS1" && "PlayStation 1"}
                  {label === "PS2" && "PlayStation 2"}
                  {label === "XBOX" && "Xbox OG"}
                  {label === "NES" && "Nintendo NES"}
                  {label === "SNES" && "Super Nintendo"}
                  {label === "N64" && "Nintendo 64"}
                  {label === "DREAMCAST" && "Sega Dreamcast"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </nav>

      {/* Sidebar bottom */}
      <div
        className="mt-auto px-4 py-3"
        style={{
          borderTop: "1px solid var(--border)",
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          lineHeight: 1.4,
          color: "var(--fg-3)",
        }}
      >
        <span
          style={{ color: "var(--fg-2)", display: "block", fontWeight: 600 }}
        >
          Peach 1UP
        </span>
        Retro Game Launcher
      </div>
    </aside>
  );
}
