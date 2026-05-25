import { Link } from 'react-router-dom'
import TopBar from '@/components/layout/TopBar'

export default function VirtualBoxSetup() {
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
        VirtualBox Environment Setup
      </h1>
      <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">
        How to source a pre-installed HDD image, register it as an Environment, and launch Windows
        software from it. VirtualBox must be installed first — see the Emulators page.
      </p>

      <section aria-labelledby="what-is-image" className="mb-10">
        <h2
          id="what-is-image"
          className="mb-3 text-lg font-semibold text-neutral-900 dark:text-neutral-100"
        >
          What is a pre-installed HDD image?
        </h2>
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">
          A pre-installed HDD image is a virtual hard drive file (.img, .vhd, or .vdi) that contains
          a Windows operating system already set up and ready to run — no installation wizard required.
          The community term for these is "pre-installed images" or "pre-configured VMs". They are the
          primary media path for VirtualBox Environments in Peach 1UP because they eliminate the
          installation step entirely.
        </p>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Peach 1UP registers the image, keeps a locked base copy, and works from a separate working
          copy so your original is never modified. You can reset the working copy to the base at any
          time.
        </p>
      </section>

      <section aria-labelledby="sourcing" className="mb-10">
        <h2
          id="sourcing"
          className="mb-3 text-lg font-semibold text-neutral-900 dark:text-neutral-100"
        >
          Where to source images
        </h2>
        <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">
          You are responsible for sourcing images and for ensuring you own or have the right to use
          any software contained in them. Peach 1UP does not automate or assist with downloading
          OS images. Recommended community sources:
        </p>
        <ul className="mb-4 list-disc space-y-2 pl-5 text-sm text-neutral-600 dark:text-neutral-400">
          <li>
            <a
              href="https://winworldpc.com"
              target="_blank"
              rel="noreferrer"
              className="text-[#ff8a5c] underline hover:opacity-80"
            >
              WinWorld PC
            </a>{' '}
            — abandonware archive for Windows 95, 98, and older versions. Provides original installation
            media, not pre-installed images. You would install Windows yourself inside VirtualBox.
          </li>
          <li>
            The{' '}
            <a
              href="https://archive.org"
              target="_blank"
              rel="noreferrer"
              className="text-[#ff8a5c] underline hover:opacity-80"
            >
              Internet Archive
            </a>{' '}
            hosts various legacy OS collections. Search for the specific Windows version you need.
          </li>
          <li>
            Community forums such as{' '}
            <a
              href="https://www.vogons.org"
              target="_blank"
              rel="noreferrer"
              className="text-[#ff8a5c] underline hover:opacity-80"
            >
              VOGONS
            </a>{' '}
            discuss pre-configured VirtualBox images and share setup guides.
          </li>
        </ul>
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 dark:border-amber-800/40 dark:bg-amber-900/10">
          <p className="text-xs text-amber-700 dark:text-amber-300">
            Windows 95, 98, and XP are no longer sold by Microsoft and are considered abandonware in
            practice, but they are not formally in the public domain. Use images only from sources
            you trust and for software you have a legitimate reason to run.
          </p>
        </div>
      </section>

      <section aria-labelledby="register" className="mb-10">
        <h2
          id="register"
          className="mb-3 text-lg font-semibold text-neutral-900 dark:text-neutral-100"
        >
          Registering an Environment
        </h2>
        <ol className="list-decimal space-y-3 pl-5 text-sm text-neutral-600 dark:text-neutral-400">
          <li>
            Go to the <strong className="text-neutral-800 dark:text-neutral-200">Emulators</strong> page
            and confirm VirtualBox is installed and Expert Mode is set.
          </li>
          <li>
            Go to the <strong className="text-neutral-800 dark:text-neutral-200">Environments</strong>{' '}
            page and click <strong className="text-neutral-800 dark:text-neutral-200">Add Platform</strong>.
          </li>
          <li>
            Enter a name, select the matching era (Windows 95, Windows 98, or Windows XP), and
            provide the path to your base image file.
          </li>
          <li>
            Provide a working image path — this is where Peach 1UP will store the working copy that
            is actually used for launches. It must be a different path from the base image.
          </li>
          <li>
            Click <strong className="text-neutral-800 dark:text-neutral-200">Add Platform</strong>.
            The Environment will appear in the list with a health status.
          </li>
        </ol>
      </section>

      <section aria-labelledby="expert-mode" className="mb-10">
        <h2
          id="expert-mode"
          className="mb-3 text-lg font-semibold text-neutral-900 dark:text-neutral-100"
        >
          VirtualBox Expert Mode
        </h2>
        <p className="text-sm text-neutral-600 dark:text-neutral-400">
          Peach 1UP requires VirtualBox Expert Mode to be enabled for full Environment management
          functionality. When VirtualBox is detected, a one-time prompt will appear on the Emulators
          page to set this automatically via a single VBoxManage command. If you prefer to set it
          manually, run:
        </p>
        <pre className="mt-3 rounded-md px-3 py-2 font-mono text-xs dark:text-neutral-300" style={{ background: 'var(--surface-2)', color: 'var(--fg-2)' }}>
          VBoxManage setextradata global GUI/ExperienceMode Expert
        </pre>
      </section>
      </div>
    </div>
  )
}
