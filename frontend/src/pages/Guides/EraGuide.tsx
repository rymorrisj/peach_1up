import { Link } from 'react-router-dom'
import TopBar from '@/components/layout/TopBar'

interface EraSection {
  slug: string
  name: string
  what: string
  formats: string
  emulator: string
  emulatorUrl: string
  biosNote?: string
  biosUrl?: string
  biosInternal?: string
}

const ERAS: EraSection[] = [
  {
    slug: 'dos',
    name: 'DOS',
    what: 'MS-DOS and PC-DOS era games and software, typically targeting 8086–486 class PCs from the mid-1980s through the early 1990s.',
    formats: 'Supported file formats are .iso, .img (floppy or hard drive image), and .cue/.bin disc images.',
    emulator: 'DOSBox-X',
    emulatorUrl: 'https://dosbox-x.com',
  },
  {
    slug: 'win31',
    name: 'Windows 3.1',
    what: '16-bit Windows 3.x software running on top of DOS, including Windows 3.1 and Windows for Workgroups 3.11.',
    formats: 'Supported file formats are .iso, .img, and .cue/.bin disc images.',
    emulator: 'DOSBox-X',
    emulatorUrl: 'https://dosbox-x.com',
  },
  {
    slug: 'win95',
    name: 'Windows 95',
    what: '32-bit software from the Windows 95 era, including games and applications that require Win32 APIs introduced in Windows 95.',
    formats: 'Supported file formats are .iso, .img, and .cue/.bin disc images.',
    emulator: '86Box',
    emulatorUrl: 'https://86box.net',
    biosNote: '86Box requires a ROM pack to function. Download the official pack from',
    biosUrl: 'https://github.com/86Box/roms',
  },
  {
    slug: 'win98',
    name: 'Windows 98',
    what: '32-bit software targeting Windows 98 and Windows 98 SE, covering the peak era of CD-ROM PC gaming.',
    formats: 'Supported file formats are .iso, .img, and .cue/.bin disc images.',
    emulator: '86Box',
    emulatorUrl: 'https://86box.net',
    biosNote: '86Box requires a ROM pack to function. Download the official pack from',
    biosUrl: 'https://github.com/86Box/roms',
  },
  {
    slug: 'winxp',
    name: 'Windows XP',
    what: 'Software requiring Windows XP (NT 5.1), including DirectX 9 games and applications that depend on XP-era system libraries.',
    formats: 'Supported file formats are .iso, .img, and .cue/.bin disc images.',
    emulator: '86Box',
    emulatorUrl: 'https://86box.net',
    biosNote: '86Box requires a ROM pack to function. Download the official pack from',
    biosUrl: 'https://github.com/86Box/roms',
  },
  {
    slug: 'ps1',
    name: 'PlayStation 1',
    what: 'Sony PlayStation (PSX) games released between 1994 and 2006 on the original grey console.',
    formats: 'Supported file formats are .iso, .bin/.cue, and .chd compressed disc images.',
    emulator: 'DuckStation',
    emulatorUrl: 'https://www.duckstation.org',
    biosNote: 'DuckStation requires a PS1 BIOS dumped from your own console. See the',
    biosInternal: '/guides/bios-sourcing',
  },
  {
    slug: 'ps2',
    name: 'PlayStation 2',
    what: 'Sony PlayStation 2 games released between 2000 and 2013, spanning both CD-ROM and DVD formats.',
    formats: 'Supported file formats are .iso, .bin/.cue, and .chd compressed disc images.',
    emulator: 'PCSX2',
    emulatorUrl: 'https://pcsx2.net',
    biosNote: 'PCSX2 requires a PS2 BIOS extracted from your own console. See the',
    biosInternal: '/guides/bios-sourcing',
  },
  {
    slug: 'xbox',
    name: 'Xbox OG',
    what: 'Original Microsoft Xbox games released between 2001 and 2006 on the first-generation Xbox console.',
    formats: 'Supported file formats are .iso and .xiso (XDVDFS-formatted Xbox disc images).',
    emulator: 'xemu',
    emulatorUrl: 'https://xemu.app',
    biosNote: 'xemu requires an Xbox BIOS and MCPX bootrom from your own console. See the',
    biosInternal: '/guides/bios-sourcing',
  },
  {
    slug: 'dreamcast',
    name: 'Dreamcast',
    what: 'Sega Dreamcast games released between 1998 and 2001 on the GD-ROM format disc.',
    formats: 'Supported file formats are .gdi (GD-ROM rip), .cdi (DiscJuggler), .chd, and .cue/.bin.',
    emulator: 'Flycast',
    emulatorUrl: 'https://github.com/flyinghead/flycast',
    biosNote: 'Flycast requires Dreamcast Flash ROM files dumped from your own console. See the',
    biosInternal: '/guides/bios-sourcing',
  },
  {
    slug: 'nes',
    name: 'NES',
    what: 'Nintendo Entertainment System (Famicom) games released from 1983 onwards.',
    formats: 'Supported file formats are .nes (iNES) and .chd.',
    emulator: 'Mesen',
    emulatorUrl: 'https://www.mesen.ca',
  },
  {
    slug: 'n64',
    name: 'Nintendo 64',
    what: 'Nintendo 64 cartridge games released between 1996 and 2002.',
    formats: 'Supported file formats are .z64 (big-endian), .n64 (little-endian), and .v64 (byte-swapped).',
    emulator: 'Project64',
    emulatorUrl: 'https://www.pj64-emu.com',
  },
]

export default function EraGuide() {
  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Era Detection Guide" />
      <div className="p-6">
        <div className="max-w-2xl space-y-2">
          <p style={{ fontFamily: 'var(--font-display)', fontSize: 14, color: 'var(--fg-2)', lineHeight: 1.6, marginBottom: 24 }}>
            Peach 1UP detects the era of your media automatically using ISO volume labels, installer
            structure, PE header metadata, and file extensions. Here is what each era means and what
            kind of media belongs there.
          </p>

          <div className="space-y-6">
            {ERAS.map((era) => (
              <section
                key={era.slug}
                className="rounded-xl p-5 space-y-2"
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
                  {era.name}
                </h2>

                <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.55 }}>
                  {era.what}
                </p>

                <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.55 }}>
                  {era.formats}
                </p>

                <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.55 }}>
                  Handled by{' '}
                  <a
                    href={era.emulatorUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'var(--peach-500)' }}
                  >
                    {era.emulator}
                  </a>
                  .
                </p>

                {era.biosNote && (
                  <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)', lineHeight: 1.55 }}>
                    {era.biosNote}{' '}
                    {era.biosInternal ? (
                      <Link to={era.biosInternal} style={{ color: 'var(--peach-500)' }}>
                        BIOS Sourcing guide
                      </Link>
                    ) : (
                      <a
                        href={era.biosUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: 'var(--peach-500)' }}
                      >
                        {era.biosUrl}
                      </a>
                    )}
                    .
                  </p>
                )}
              </section>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
