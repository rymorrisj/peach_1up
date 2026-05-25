import { Link } from 'react-router-dom'
import { BookOpen } from 'lucide-react'
import TopBar from '@/components/layout/TopBar'

interface GuideEntry {
  to: string
  title: string
  description: string
}

const GUIDES: GuideEntry[] = [
  {
    to: '/guides/virtualbox-setup',
    title: 'VirtualBox Environment Setup',
    description: 'How to source a pre-installed HDD image, register it as an Environment, and launch software from it.',
  },
  {
    to: '/guides/86box-hardware',
    title: '86Box Hardware Profiles',
    description: 'Which hardware profile to choose for Win95/98 games — 3dfx, OPL music, MIDI, or the standard setup.',
  },
  {
    to: '/guides/bios-sourcing',
    title: 'BIOS File Sourcing',
    description: 'Where to obtain PS1, PS2, and Xbox OG BIOS files from your own hardware.',
  },
  {
    to: '/guides/cartridge-imaging',
    title: 'Cartridge Imaging',
    description: 'How to dump NES and N64 cartridges from physical hardware using recommended USB dumpers.',
  },
]

export default function GuidesIndex() {
  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Guides" />
      <div className="p-6">
        <ul className="space-y-3">
          {GUIDES.map((g) => (
            <li key={g.to}>
              <Link
                to={g.to}
                className="flex items-start gap-3 rounded-xl p-4 transition-colors duration-[120ms]"
                style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.background = 'var(--surface-2)' }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.background = 'var(--surface-1)' }}
              >
                <BookOpen size={18} className="mt-0.5 shrink-0" style={{ color: 'var(--peach-500)' }} aria-hidden="true" />
                <div>
                  <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--fg-1)' }}>{g.title}</span>
                  <p style={{ fontFamily: 'var(--font-display)', fontSize: 13, color: 'var(--fg-3)', marginTop: 4 }}>{g.description}</p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
