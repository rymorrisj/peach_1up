import { Link } from 'react-router-dom'
import TopBar from '@/components/layout/TopBar'

interface BiosPlatform {
  id: string
  name: string
  emulator: string
  path: string
  files: { name: string; notes: string }[]
  steps: string[]
  official_url: string
}

const PLATFORMS: BiosPlatform[] = [
  {
    id: 'ps1',
    name: 'PlayStation 1',
    emulator: 'DuckStation',
    path: 'library/system/bios/ps1/',
    files: [
      {
        name: 'scph1001.bin',
        notes: 'NTSC-U BIOS v2.2. Most commonly used for North American titles.',
      },
      {
        name: 'scph5500.bin / scph5501.bin / scph5502.bin',
        notes: 'v3.0 BIOS revisions (JP/US/EU). Required for some later releases.',
      },
    ],
    steps: [
      'Connect your PS1 to a computer using a modchipped unit or a dedicated BIOS dumping tool.',
      'Use a PS1 BIOS dumper (e.g. the open-source caetla or a compatible flash cart) to read the BIOS ROM chip.',
      'Save the output as a .bin file matching one of the expected filenames listed above.',
      'Place the file in library/system/bios/ps1/ inside your Peach 1UP folder.',
      'The Emulators page BIOS section will update automatically once the file is present.',
    ],
    official_url: 'https://www.duckstation.org/wiki/BIOS',
  },
  {
    id: 'ps2',
    name: 'PlayStation 2',
    emulator: 'PCSX2',
    path: 'library/system/bios/ps2/',
    files: [
      {
        name: 'SCPH-70012.BIN (or equivalent)',
        notes: 'NTSC-U PS2 BIOS. The exact filename depends on your console model.',
      },
    ],
    steps: [
      'Follow the official PCSX2 BIOS dumping guide — it covers extracting the BIOS from your own PS2 using a PS2 memory card exploit or a FreeMCBoot setup.',
      'The extracted BIOS folder will contain multiple .BIN and .NVM files — copy the entire set to library/system/bios/ps2/.',
      'PCSX2 will detect the BIOS automatically on the next launch.',
    ],
    official_url: 'https://pcsx2.net/guides/basic-setup/',
  },
  {
    id: 'xbox',
    name: 'Xbox (Original)',
    emulator: 'xemu',
    path: 'library/system/bios/xbox/',
    files: [
      {
        name: 'MCPX_1.0.bin',
        notes: 'MCPX boot ROM — required. Extracted from the MCPX chip on your Xbox motherboard.',
      },
      {
        name: 'Complex_4627v1.03.bin (or equivalent)',
        notes: 'Xbox BIOS ROM — required. Several versions exist; see xemu documentation.',
      },
    ],
    steps: [
      'Read the xemu documentation for the exact files required and their expected checksums.',
      'The MCPX ROM is extracted from the MCPX chip on your Xbox motherboard using specialist hardware (e.g. a TSOP flash programmer).',
      'The BIOS ROM can be extracted from an original Xbox with a modchip installed using xenium or a compatible tool.',
      'Place the extracted files in library/system/bios/xbox/.',
    ],
    official_url: 'https://xemu.app/docs/required-files/',
  },
]

function PlatformSection({ platform }: { platform: BiosPlatform }) {
  return (
    <section aria-labelledby={`heading-${platform.id}`} className="mb-12">
      <h2
        id={`heading-${platform.id}`}
        className="mb-1 text-xl font-semibold text-neutral-900 dark:text-neutral-100"
      >
        {platform.name}
      </h2>
      <p className="mb-4 text-sm text-neutral-500 dark:text-neutral-400">
        Emulator: {platform.emulator} · Place files in{' '}
        <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs dark:bg-surface-700">
          {platform.path}
        </code>
      </p>

      <h3 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
        Required files
      </h3>
      <ul className="mb-6 space-y-2">
        {platform.files.map((f) => (
          <li
            key={f.name}
            className="rounded-md p-3"
          style={{ border: '1px solid var(--border)' }}
          >
            <span className="font-mono text-xs font-medium text-neutral-900 dark:text-neutral-100">
              {f.name}
            </span>
            <span className="ml-2 text-sm text-neutral-500 dark:text-neutral-400">— {f.notes}</span>
          </li>
        ))}
      </ul>

      <h3 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
        How to dump from your own hardware
      </h3>
      <ol className="mb-4 list-decimal space-y-1.5 pl-5 text-sm text-neutral-600 dark:text-neutral-400">
        {platform.steps.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>

      <a
        href={platform.official_url}
        target="_blank"
        rel="noreferrer"
        className="text-sm text-[#ff8a5c] underline hover:opacity-80"
      >
        Official {platform.emulator} BIOS documentation →
      </a>
    </section>
  )
}

export default function BiosSourcing() {
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
          BIOS File Sourcing
        </h1>
        <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">
          Console emulators require BIOS files extracted from the original hardware. Peach 1UP does
          not supply BIOS files. You must dump them from hardware you own. Downloading BIOS files from
          the internet is a copyright violation regardless of whether you own the console.
        </p>

        {PLATFORMS.map((platform) => (
          <PlatformSection key={platform.id} platform={platform} />
        ))}
      </div>
    </div>
  )
}
