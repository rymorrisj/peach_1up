import { Link } from 'react-router-dom'
import TopBar from '@/components/layout/TopBar'

export default function Box86HardwareGuide() {
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
        <span style={{ flex: 1 }} />
      </TopBar>

      <div className="p-6">
      <h1 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        86Box Hardware Profiles
      </h1>
      <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">
        86Box emulates real PC hardware at the component level. Choosing the right hardware
        configuration is the difference between a game running perfectly and not running at all.
      </p>

      <section aria-labelledby="what-is-profile" className="mb-10">
        <h2
          id="what-is-profile"
          className="mb-3 text-lg font-semibold text-neutral-900 dark:text-neutral-100"
        >
          What is a hardware profile?
        </h2>
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">
          86Box emulates specific physical components — the motherboard chipset, CPU, graphics
          card, and sound card. Unlike a typical emulator that abstracts hardware, 86Box loads
          actual firmware and ROM data for each component. A hardware profile is a curated set
          of components that work well together for a particular category of software.
        </p>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Peach 1UP provides four profiles that cover the most common compatibility scenarios
          for Windows 95 and 98 software. For most cases, Standard is the right starting point.
        </p>
      </section>

      <section aria-labelledby="profiles-table" className="mb-10">
        <h2
          id="profiles-table"
          className="mb-3 text-lg font-semibold text-neutral-900 dark:text-neutral-100"
        >
          Profiles at a glance
        </h2>

        <div className="overflow-x-auto rounded-md" style={{ border: '1px solid var(--border)' }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)', background: 'var(--surface-2)' }}>
                <th className="px-4 py-2.5 text-left font-medium text-neutral-700 dark:text-neutral-300">Profile</th>
                <th className="px-4 py-2.5 text-left font-medium text-neutral-700 dark:text-neutral-300">Graphics</th>
                <th className="px-4 py-2.5 text-left font-medium text-neutral-700 dark:text-neutral-300">Sound</th>
                <th className="px-4 py-2.5 text-left font-medium text-neutral-700 dark:text-neutral-300">Example software</th>
              </tr>
            </thead>
            <tbody style={{ borderTop: '1px solid var(--border)' }}>
              <tr>
                <td className="px-4 py-2.5 font-medium text-neutral-900 dark:text-neutral-100">Standard</td>
                <td className="px-4 py-2.5 text-neutral-600 dark:text-neutral-400">S3 ViRGE/DX</td>
                <td className="px-4 py-2.5 text-neutral-600 dark:text-neutral-400">Sound Blaster 16 PnP</td>
                <td className="px-4 py-2.5 text-neutral-500 dark:text-neutral-500">Most Win95/98 software, Office, browsers</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 font-medium text-neutral-900 dark:text-neutral-100">3D / Glide</td>
                <td className="px-4 py-2.5 text-neutral-600 dark:text-neutral-400">Voodoo 3 3500</td>
                <td className="px-4 py-2.5 text-neutral-600 dark:text-neutral-400">Sound Blaster 16 PnP</td>
                <td className="px-4 py-2.5 text-neutral-500 dark:text-neutral-500">Tomb Raider II, Need for Speed III, Quake II</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 font-medium text-neutral-900 dark:text-neutral-100">DOS / FM Music</td>
                <td className="px-4 py-2.5 text-neutral-600 dark:text-neutral-400">S3 ViRGE/DX</td>
                <td className="px-4 py-2.5 text-neutral-600 dark:text-neutral-400">Sound Blaster 16 (OPL3)</td>
                <td className="px-4 py-2.5 text-neutral-500 dark:text-neutral-500">Doom, Duke Nukem 3D, Warcraft I</td>
              </tr>
              <tr>
                <td className="px-4 py-2.5 font-medium text-neutral-900 dark:text-neutral-100">MIDI Music</td>
                <td className="px-4 py-2.5 text-neutral-600 dark:text-neutral-400">S3 ViRGE/DX</td>
                <td className="px-4 py-2.5 text-neutral-600 dark:text-neutral-400">AWE32 + Roland SC-55 (emulated)</td>
                <td className="px-4 py-2.5 text-neutral-500 dark:text-neutral-500">Command &amp; Conquer, X-COM, Baldur's Gate</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 dark:border-amber-800/40 dark:bg-amber-900/10">
          <p className="text-xs text-amber-700 dark:text-amber-300">
            The 3D / Glide profile requires Voodoo3 drivers to be installed inside the Windows
            environment before 3D acceleration will work. After installing Windows, boot the
            environment and install the drivers from the Voodoo3 driver disc before loading
            any 3D game.
          </p>
        </div>
      </section>

      <section aria-labelledby="machine-override" className="mb-10">
        <h2
          id="machine-override"
          className="mb-3 text-lg font-semibold text-neutral-900 dark:text-neutral-100"
        >
          Advanced: choosing your own machine
        </h2>
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">
          Each hardware profile uses a fixed motherboard. If you need a specific chipset for
          compatibility — for example, a title that requires an ISA slot or a specific VGA
          BIOS — you can override the machine using the Advanced section of the environment
          form.
        </p>
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">
          Machine identifiers are the folder names inside your 86Box ROM pack's{' '}
          <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs dark:bg-surface-700">
            machines/
          </code>{' '}
          directory. Browse to that directory in the machine picker and select a folder — the
          folder name is the identifier 86Box will use.
        </p>
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">
          The machine must exist in your installed ROM pack. If the ROM files for the selected
          machine are missing, 86Box will fail to start. Reference the full list of supported
          machines at{' '}
          <a
            href="https://86box.net"
            target="_blank"
            rel="noreferrer"
            className="text-[#ff8a5c] underline hover:opacity-80"
          >
            86box.net
          </a>
          .
        </p>
        <div className="rounded-md p-3" style={{ border: '1px solid var(--border)', background: 'var(--surface-1)' }}>
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
            Example: Win98 with 3dfx custom machine
          </p>
          <pre className="overflow-x-auto font-mono text-xs text-neutral-700 dark:text-neutral-300">
{`[Machine]
machine         = p2b
cpu_family      = pentium2_deschutes
cpu_speed       = 350000000
mem_size        = 131072
cpu_use_dynarec = 1
fpu_type        = internal

[Video]
gfxcard         = voodoo3_3500_si_agp
vid_renderer    = qt_software

[Sound]
sndcard         = sb16_pnp`}
          </pre>
        </div>
      </section>

      <section aria-labelledby="tip" className="mb-4">
        <div className="rounded-md p-4" style={{ border: '1px solid var(--border)', background: 'var(--surface-1)' }}>
          <p className="text-sm font-medium text-neutral-800 dark:text-neutral-200">
            When in doubt, start with Standard.
          </p>
          <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
            You can always delete the environment and recreate it with a different profile.
            The config file is regenerated each time — no data is lost unless you have saved
            games inside the Windows environment itself.
          </p>
        </div>
      </section>
      </div>
    </div>
  )
}
