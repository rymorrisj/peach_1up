import { Link } from 'react-router-dom'

interface Platform {
  id: string
  name: string
  outputFormats: string[]
  hardware: { name: string; notes: string }[]
  steps: string[]
  notes: string[]
}

const PLATFORMS: Platform[] = [
  {
    id: 'nes',
    name: 'NES',
    outputFormats: ['.nes', '.chd'],
    hardware: [
      {
        name: 'RetroBlaster',
        notes: 'Windows software. Reads NES and Famicom cartridges directly via USB.',
      },
      {
        name: 'INLretro System',
        notes:
          'Open-source dumper. Cross-platform software. Supports NES, Famicom, and a wide range of other cartridge types.',
      },
      {
        name: 'Retrode 2 with NES adapter',
        notes:
          'Appears as a USB mass storage device — no drivers required. Requires the optional NES/Famicom adapter.',
      },
    ],
    steps: [
      'Connect the dumping hardware to your computer via USB.',
      'Insert the cartridge into the dumper or adapter.',
      'Use the dumper software to read the cartridge.',
      'Save the output as a .nes file. The file will include the iNES header (16 bytes) followed by PRG ROM data and CHR ROM data.',
      'Verify the dump by comparing the file size and checksum against a known-good reference if available.',
    ],
    notes: [
      'The .nes format includes a 16-byte iNES header that identifies the mapper, PRG ROM size, CHR ROM size, and mirroring type. Most dumping software writes this automatically.',
      'Some cartridges use proprietary mappers or battery-backed SRAM. The dumper must support the specific mapper for the ROM to be valid.',
      'CHD format (.chd) is an alternative compressed format. Mesen accepts both .nes and .chd files.',
      'Dump only cartridges you own. Making or distributing copies of software you do not own is a copyright violation.',
    ],
  },
  {
    id: 'n64',
    name: 'Nintendo 64',
    outputFormats: ['.z64', '.n64', '.v64'],
    hardware: [
      {
        name: 'Retrode 2 with N64 adapter',
        notes:
          'Appears as a USB mass storage device — no drivers required. Requires the official N64 adapter. Reads ROM directly to a .z64 file.',
      },
      {
        name: 'INLretro System with N64 adapter',
        notes: 'Open-source. Cross-platform software. Produces .z64 output.',
      },
      {
        name: '64drive',
        notes:
          'An N64 flash cartridge that can also dump ROMs from original cartridges when used with the PC USB interface.',
      },
      {
        name: 'EverDrive-64 X7',
        notes:
          'Primarily a flash cartridge, but supports ROM dumping via the USB port with compatible software.',
      },
    ],
    steps: [
      'Connect the dumping hardware to your computer via USB.',
      'Insert the N64 cartridge into the dumper or adapter.',
      'Use the dumper software to read the cartridge ROM.',
      'Save the output. Most dumpers write .z64 (big-endian) by default.',
      'Verify the dump against a known checksum if available.',
    ],
    notes: [
      'N64 ROMs exist in three byte-order formats: .z64 (big-endian, native N64 order), .n64 (little-endian), and .v64 (byteswapped). Project64 handles all three — you do not need to convert between them.',
      '.z64 is the standard format and the most widely supported. Prefer it when your dumper gives you a choice.',
      'N64 cartridges do not use CHD format. Only .z64, .n64, and .v64 are accepted by Project64.',
      'Some cartridges include expansion pak requirements or region locks. These are encoded in the ROM header and handled by the emulator.',
      'Dump only cartridges you own. Making or distributing copies of software you do not own is a copyright violation.',
    ],
  },
]

function FormatBadge({ fmt }: { fmt: string }) {
  return (
    <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-xs text-neutral-600 dark:bg-surface-700 dark:text-neutral-400">
      {fmt}
    </span>
  )
}

function PlatformSection({ platform }: { platform: Platform }) {
  return (
    <section aria-labelledby={`heading-${platform.id}`} className="mb-12">
      <h2
        id={`heading-${platform.id}`}
        className="mb-4 text-xl font-semibold text-neutral-900 dark:text-neutral-100"
      >
        {platform.name}
      </h2>

      <div className="mb-4 flex items-center gap-2">
        <span className="text-sm text-neutral-500 dark:text-neutral-400">Output formats:</span>
        {platform.outputFormats.map((fmt) => (
          <FormatBadge key={fmt} fmt={fmt} />
        ))}
      </div>

      <h3 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
        Compatible hardware
      </h3>
      <ul className="mb-6 space-y-2">
        {platform.hardware.map((hw) => (
          <li
            key={hw.name}
            className="rounded-md border border-neutral-200 p-3 dark:border-neutral-800"
          >
            <span className="font-medium text-neutral-900 dark:text-neutral-100">{hw.name}</span>
            <span className="ml-2 text-sm text-neutral-500 dark:text-neutral-400">—</span>
            <span className="ml-2 text-sm text-neutral-600 dark:text-neutral-400">{hw.notes}</span>
          </li>
        ))}
      </ul>

      <h3 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
        How to dump
      </h3>
      <ol className="mb-6 list-decimal space-y-1.5 pl-5 text-sm text-neutral-600 dark:text-neutral-400">
        {platform.steps.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>

      <h3 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-300">Notes</h3>
      <ul className="list-disc space-y-1.5 pl-5 text-sm text-neutral-600 dark:text-neutral-400">
        {platform.notes.map((note, i) => (
          <li key={i}>{note}</li>
        ))}
      </ul>
    </section>
  )
}

function RomPackFallback() {
  return (
    <section aria-labelledby="rompack-fallback" className="mb-12">
      <h2
        id="rompack-fallback"
        className="mb-3 text-xl font-semibold text-neutral-900 dark:text-neutral-100"
      >
        86Box ROM Pack — Manual Install Fallback
      </h2>
      <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-400">
        86Box requires a ROM pack (firmware images for emulated hardware) to start. Peach 1UP can
        clone it automatically via git from the Emulators page. If git is not available or the clone
        fails, follow these steps to install manually.
      </p>

      <h3 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-300">
        Manual install steps
      </h3>
      <ol className="mb-6 list-decimal space-y-2 pl-5 text-sm text-neutral-600 dark:text-neutral-400">
        <li>
          Download the ROM pack as a ZIP archive from the{' '}
          <a
            href="https://github.com/86Box/roms/releases"
            target="_blank"
            rel="noreferrer"
            className="text-[#ff8a5c] underline hover:opacity-80"
          >
            86Box/roms GitHub Releases page
          </a>
          . Download the latest release ZIP.
        </li>
        <li>
          Extract the contents of the ZIP. The archive contains a top-level folder called{' '}
          <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs dark:bg-surface-700">
            roms
          </code>{' '}
          or similar — you want the <em>contents</em> of that folder, not the folder itself.
        </li>
        <li>
          Copy all extracted files and subfolders into{' '}
          <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs dark:bg-surface-700">
            library/roms/86box/
          </code>{' '}
          inside your Peach 1UP folder. After copying, the path{' '}
          <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs dark:bg-surface-700">
            library/roms/86box/
          </code>{' '}
          should contain directories such as{' '}
          <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs dark:bg-surface-700">
            machines
          </code>
          ,{' '}
          <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-xs dark:bg-surface-700">
            sound
          </code>
          , and others.
        </li>
        <li>
          Return to the Emulators page. The 86Box ROM Pack status will update from Missing to Present
          automatically.
        </li>
      </ol>

      <div className="rounded-md border border-neutral-200 p-3 dark:border-neutral-800">
        <p className="text-xs text-neutral-500 dark:text-neutral-400">
          The ROM pack is maintained by the 86Box project and is redistributed under the terms of the
          individual firmware copyright holders. See the{' '}
          <a
            href="https://github.com/86Box/roms"
            target="_blank"
            rel="noreferrer"
            className="text-[#ff8a5c] underline hover:opacity-80"
          >
            86Box/roms repository
          </a>{' '}
          for licensing information.
        </p>
      </div>
    </section>
  )
}

export default function CartridgeImaging() {
  return (
    <>
      <div className="mb-6">
        <Link
          to="/guides"
          className="text-xs text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
        >
          ← Guides
        </Link>
      </div>

      <h1 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Cartridge Imaging Guide
      </h1>
      <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">
        How to dump cartridge media from physical hardware for use with Peach 1UP. You are
        responsible for sourcing the hardware and for ensuring you own any software you dump.
      </p>

      {PLATFORMS.map((platform) => (
        <PlatformSection key={platform.id} platform={platform} />
      ))}

      <RomPackFallback />
    </>
  )
}
