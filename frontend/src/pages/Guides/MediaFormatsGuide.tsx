import { Link } from 'react-router-dom'
import TopBar from '@/components/layout/TopBar'

const CONCEPTS = [
  {
    id: 'magic-bytes',
    heading: 'Magic bytes / file signature',
    body: 'The first few bytes of a file that identify its format. Software reads these to confirm what a file actually is, regardless of extension. A .bin file might be a PS1 track dump, a Dreamcast sector image, or a raw floppy — magic bytes tell the truth.',
    link: { label: 'List of file signatures', href: 'https://en.wikipedia.org/wiki/List_of_file_signatures' },
  },
  {
    id: 'file-header',
    heading: 'File header',
    body: 'Structured metadata at the start of a file describing its contents, version, and layout. Emulators read headers to configure themselves before loading any game data — the iNES header in a .nes file tells Mesen the mapper number and mirroring mode before a single byte of game code runs.',
    link: { label: 'FAT filesystem header reference', href: 'https://wiki.osdev.org/FAT' },
  },
  {
    id: 'sector-size',
    heading: 'Sector size',
    body: 'Disc media is divided into fixed-size sectors. CDs use 2048-byte sectors (data only) or 2352-byte sectors when raw error-correction data is included. GD-ROM (Dreamcast) always uses raw 2352-byte sectors; standard DVDs use 2048. The sector size determines how a disc image must be read and whether formats are interchangeable.',
    link: { label: 'CD-ROM sector structure', href: 'https://en.wikipedia.org/wiki/CD-ROM#Sector_structure' },
  },
  {
    id: 'offsets',
    heading: 'Memory addresses (offsets)',
    body: 'A byte offset is the distance from the start of a file to a specific piece of data, measured in bytes. Detection logic reads specific offsets to find magic bytes or headers without loading the whole file. This is how Peach 1UP identifies disc images: it checks known offsets for platform-specific signatures rather than trusting the file extension.',
    link: null,
  },
]

const EMULATORS = [
  {
    emulator: 'DOSBox-X',
    platform: 'DOS / Win 3.1',
    formats: '.iso, .img, .zip, .exe, .com, folder',
    recommended: '.iso or folder',
    notes: 'No disc magic required. Loose executables, folders, and ZIP archives are all mountable.',
  },
  {
    emulator: '86Box',
    platform: 'Win 95/98/XP',
    formats: '.iso, .img, .vhd',
    recommended: 'Pre-installed .img or .vhd',
    notes: 'OS must be pre-installed in the image. Installer ISOs work but require manual setup.',
  },
  {
    emulator: 'DuckStation',
    platform: 'PS1',
    formats: '.iso, .bin/.cue, .chd, .zip',
    recommended: '.chd',
    notes: 'CHD reduces file size significantly with no quality loss. ZIP of a bin/cue or iso loads directly.',
  },
  {
    emulator: 'PCSX2',
    platform: 'PS2',
    formats: '.iso, .bin/.cue, .chd, .zip',
    recommended: '.chd',
    notes: 'Full PS2 BIOS set required. ZIP-wrapped ISOs are supported.',
  },
  {
    emulator: 'Flycast',
    platform: 'Dreamcast',
    formats: '.gdi, .cdi, .chd, .zip',
    recommended: '.chd',
    notes: 'GDI is the most accurate raw format. CHD compresses GDI cleanly. ZIP supported for CDI and single-track images.',
  },
  {
    emulator: 'Mesen',
    platform: 'NES / SNES',
    formats: '.nes, .sfc, .smc, .zip',
    recommended: '.nes / .sfc',
    notes: 'No BIOS required for standard titles. ZIP archives load directly and are faster to scan in large collections.',
  },
  {
    emulator: 'Project64',
    platform: 'N64',
    formats: '.z64, .n64, .v64, .zip',
    recommended: '.z64',
    notes: '.z64 is big-endian native; .v64 is byteswapped — both work. ZIP archives are supported.',
  },
  {
    emulator: 'xemu',
    platform: 'Xbox OG',
    formats: '.iso (xiso format only)',
    recommended: 'xiso-format .iso',
    notes: 'Raw DVD rips (7–8 GB) are rejected. Must be converted with extract-xiso before use.',
  },
]

const TABLE_COLS = ['Emulator', 'Platform', 'Supported formats', 'Recommended', 'Notes']

const CODE: React.CSSProperties = {
  fontFamily: 'monospace',
  fontSize: 12,
  color: 'var(--fg-1)',
  background: 'var(--surface-2)',
  borderRadius: 4,
  padding: '1px 5px',
}

export default function MediaFormatsGuide() {
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
        <div style={{ maxWidth: 820 }} className="space-y-8">
          <p style={{ fontFamily: 'var(--font-display)', fontSize: 14, color: 'var(--fg-2)', lineHeight: 1.6 }}>
            A disc image is a byte-for-byte copy of physical media. The file extension tells you the
            container format, not necessarily the platform — a <code style={CODE}>.bin</code> file
            might be a PS1 track, a Dreamcast sector dump, or a raw floppy image.
          </p>

          {/* Section 1 */}
          <section>
            <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15, color: 'var(--fg-1)', marginBottom: 12 }}>
              How disc images work
            </h2>
            <div className="space-y-3">
              {CONCEPTS.map((c) => (
                <div
                  key={c.id}
                  className="rounded-xl p-5 space-y-2"
                  style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
                >
                  <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14, color: 'var(--fg-1)' }}>
                    {c.heading}
                  </h3>
                  <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.55 }}>
                    {c.body}
                  </p>
                  {c.link && (
                    <a
                      href={c.link.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ fontFamily: 'var(--font-display)', fontSize: 12, color: 'var(--peach-500)' }}
                    >
                      {c.link.label} →
                    </a>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* Section 2 */}
          <section>
            <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15, color: 'var(--fg-1)', marginBottom: 12 }}>
              Format compatibility by emulator
            </h2>
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--border)' }}>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-display)' }}>
                  <thead>
                    <tr style={{ background: 'var(--surface-2)' }}>
                      {TABLE_COLS.map((col) => (
                        <th
                          key={col}
                          style={{
                            padding: '10px 14px',
                            textAlign: 'left',
                            fontSize: 12,
                            fontWeight: 600,
                            color: 'var(--fg-3)',
                            borderBottom: '1px solid var(--border)',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {EMULATORS.map((row, i) => (
                      <tr
                        key={row.emulator}
                        style={{ background: i % 2 === 0 ? 'var(--surface-1)' : 'var(--surface-2)' }}
                      >
                        <td style={{ padding: '10px 14px', fontSize: 13, fontWeight: 600, color: 'var(--fg-1)', whiteSpace: 'nowrap', borderBottom: '1px solid var(--border)' }}>
                          {row.emulator}
                        </td>
                        <td style={{ padding: '10px 14px', fontSize: 13, color: 'var(--fg-2)', whiteSpace: 'nowrap', borderBottom: '1px solid var(--border)' }}>
                          {row.platform}
                        </td>
                        <td style={{ padding: '10px 14px', fontSize: 12, color: 'var(--fg-3)', borderBottom: '1px solid var(--border)', fontFamily: 'monospace' }}>
                          {row.formats}
                        </td>
                        <td style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600, color: 'var(--peach-500)', whiteSpace: 'nowrap', borderBottom: '1px solid var(--border)', fontFamily: 'monospace' }}>
                          {row.recommended}
                        </td>
                        <td style={{ padding: '10px 14px', fontSize: 12, color: 'var(--fg-3)', borderBottom: '1px solid var(--border)', lineHeight: 1.5, minWidth: 200 }}>
                          {row.notes}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {/* Section 3 */}
          <section>
            <h2 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15, color: 'var(--fg-1)', marginBottom: 12 }}>
              Converting and preparing disc images
            </h2>
            <div className="space-y-3">
              <div
                className="rounded-xl p-5 space-y-2"
                style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
              >
                <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14, color: 'var(--fg-1)' }}>
                  Xbox: converting a raw DVD rip to xiso
                </h3>
                <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.55 }}>
                  Raw DVD rips of Xbox games contain a video partition — a stub of video content that shipped on every
                  Xbox disc to prevent the drive from booting on a standard DVD player. xemu expects a clean XDVDFS
                  image with this partition stripped. Raw rips are typically 7–8 GB; after stripping they shrink to
                  2–4 GB. Use{' '}
                  <a
                    href="https://github.com/xboxdev/extract-xiso"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'var(--peach-500)' }}
                  >
                    extract-xiso
                  </a>{' '}
                  to perform the conversion:{' '}
                  <code style={CODE}>extract-xiso -r game.iso</code> rewrites the image in place, stripping the video
                  partition and rebuilding the XDVDFS layout.
                </p>
              </div>

              <div
                className="rounded-xl p-5 space-y-2"
                style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
              >
                <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14, color: 'var(--fg-1)' }}>
                  Compressing to CHD
                </h3>
                <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.55 }}>
                  CHD (Compressed Hunks of Data) is a lossless archive format developed by MAME for disc images. It
                  works for PS1, PS2, and Dreamcast GDI, and compresses 30–50% smaller than a raw image. The process
                  is fully reversible. Use{' '}
                  <a
                    href="https://docs.libretro.com/guides/chd-guide/"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'var(--peach-500)' }}
                  >
                    chdman
                  </a>{' '}
                  to convert: <code style={CODE}>chdman createcd -i input.cue -o output.chd</code>. For GDI images use{' '}
                  <code style={CODE}>-i input.gdi</code> instead. DuckStation, PCSX2, and Flycast all read CHD natively.
                </p>
              </div>

              <div
                className="rounded-xl p-5 space-y-2"
                style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
              >
                <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14, color: 'var(--fg-1)' }}>
                  PS1: .bin/.cue vs .iso
                </h3>
                <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.55 }}>
                  A .bin/.cue pair and a .iso are functionally equivalent for most PS1 games. The .cue sheet is a
                  plain-text track index pointing to one or more .bin files that contain raw sector data. A .iso
                  contains only the 2048-byte data sectors without error-correction bytes. Games that use CD audio
                  tracks require .bin/.cue because .iso cannot store audio tracks. CHD supersedes both — it compresses
                  the full sector data including audio and is the preferred format for long-term storage.
                </p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
