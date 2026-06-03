import { Link } from 'react-router-dom'
import TopBar from '@/components/layout/TopBar'

interface ControllerRow {
  emulator: string
  platform: string
  xbox: string
  notes: string
}

const CONTROLLER_ROWS: ControllerRow[] = [
  {
    emulator: 'DOSBox-X',
    platform: 'DOS / Win 3.1',
    xbox: '✅ Supported',
    notes: 'SDL2 gamepad; use the DOSBox-X keymapper (F1 in-game) to remap buttons',
  },
  {
    emulator: '86Box',
    platform: 'Win 95/98/XP/ME',
    xbox: '✅ Supported',
    notes: 'Configure joystick type in 86Box Machine Settings → Input',
  },
  {
    emulator: 'DuckStation',
    platform: 'PS1',
    xbox: '✅ Supported',
    notes: 'Per-port mapping in Settings → Controllers; analogue stick supported',
  },
  {
    emulator: 'PCSX2',
    platform: 'PS2',
    xbox: '✅ Supported',
    notes: 'Per-port mapping in Settings → Controllers; full DualShock 2 mapping',
  },
  {
    emulator: 'Flycast',
    platform: 'Dreamcast',
    xbox: '✅ Supported',
    notes: 'SDL2 gamepad; configure in Settings → Input',
  },
  {
    emulator: 'Mesen',
    platform: 'NES / SNES',
    xbox: '✅ Supported',
    notes: 'Button mapping in Settings → Input; D-pad maps to left stick automatically',
  },
  {
    emulator: 'Project64',
    platform: 'N64',
    xbox: '✅ Supported',
    notes: 'Uses input plugin (default: SDL); configure in Options → Configure Controller',
  },
  {
    emulator: 'xemu',
    platform: 'Xbox OG',
    xbox: '✅ Native',
    notes: 'Xbox 360/One controller maps directly to OG Xbox layout with no configuration',
  },
]

export default function ControllerGuide() {
  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        <Link
          to="/guides"
          style={{
            color: 'var(--fg-2)',
            fontFamily: 'var(--font-display)',
            fontSize: 13,
            fontWeight: 500,
            textDecoration: 'none',
            padding: '6px 10px',
          }}
        >
          ← Guides
        </Link>
      </TopBar>

      <div className="p-6">
        <div className="max-w-2xl space-y-8">

          <section
            className="rounded-xl p-5 space-y-3"
            style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
          >
            <h2
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: 15,
                color: 'var(--fg-1)',
              }}
            >
              Controller support overview
            </h2>
            <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.6 }}>
              All supported emulators accept standard USB and Bluetooth gamepads. An Xbox controller
              (wired or wireless with the USB adapter) works out of the box with every emulator in
              Peach 1UP — no additional drivers required on Windows 10/11.
            </p>
          </section>

          <section
            className="rounded-xl p-5 space-y-3"
            style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
          >
            <h2
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: 15,
                color: 'var(--fg-1)',
              }}
            >
              Per-emulator controller support
            </h2>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-display)', fontSize: 13 }}>
                <thead>
                  <tr>
                    {['Emulator', 'Platform', 'Xbox controller', 'Notes'].map((h) => (
                      <th
                        key={h}
                        style={{
                          textAlign: 'left',
                          padding: '6px 10px 6px 0',
                          color: 'var(--fg-3)',
                          fontWeight: 600,
                          borderBottom: '1px solid var(--border)',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {CONTROLLER_ROWS.map((row) => (
                    <tr key={row.emulator}>
                      <td style={{ padding: '8px 10px 8px 0', color: 'var(--fg-1)', fontWeight: 500, whiteSpace: 'nowrap', borderBottom: '1px solid var(--border)' }}>
                        {row.emulator}
                      </td>
                      <td style={{ padding: '8px 10px 8px 0', color: 'var(--fg-2)', whiteSpace: 'nowrap', borderBottom: '1px solid var(--border)' }}>
                        {row.platform}
                      </td>
                      <td style={{ padding: '8px 10px 8px 0', color: 'var(--fg-2)', whiteSpace: 'nowrap', borderBottom: '1px solid var(--border)' }}>
                        {row.xbox}
                      </td>
                      <td style={{ padding: '8px 10px 8px 0', color: 'var(--fg-3)', borderBottom: '1px solid var(--border)' }}>
                        {row.notes}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section
            className="rounded-xl p-5 space-y-3"
            style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
          >
            <h2
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: 15,
                color: 'var(--fg-1)',
              }}
            >
              NES, SNES and retro controller layouts
            </h2>
            <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.6 }}>
              When mapping a NES or SNES layout to an Xbox controller, note that A and B are swapped
              between Nintendo and Xbox convention. Most emulators default to Nintendo layout, so
              expect B to confirm and A to go back until you remap them — the opposite of what Xbox
              players expect.
            </p>
            <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.6 }}>
              The N64 controller has no right analogue stick. Project64 maps the C-buttons to the
              right stick by default, which is the standard modern convention and works well with an
              Xbox controller out of the box.
            </p>
          </section>

        </div>
      </div>
    </div>
  )
}
