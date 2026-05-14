import { Link } from 'react-router-dom'
import { BookOpen } from 'lucide-react'

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
    <>
      <h1 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">Guides</h1>
      <p className="mb-8 text-sm text-neutral-500 dark:text-neutral-400">
        Step-by-step instructions for setting up emulators, sourcing assets, and preparing media.
      </p>

      <ul className="space-y-3">
        {GUIDES.map((g) => (
          <li key={g.to}>
            <Link
              to={g.to}
              className="flex items-start gap-3 rounded-lg border border-neutral-200 p-4 transition-colors hover:border-[#ff8a5c]/50 hover:bg-neutral-50 dark:border-neutral-800 dark:hover:bg-surface-800"
            >
              <BookOpen size={18} className="mt-0.5 shrink-0 text-[#ff8a5c]" aria-hidden="true" />
              <div>
                <span className="font-medium text-neutral-900 dark:text-neutral-100">{g.title}</span>
                <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">{g.description}</p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </>
  )
}
