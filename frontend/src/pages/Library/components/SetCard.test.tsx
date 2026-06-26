import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { SetCard } from './SetCard'
import type { LibrarySetData } from './SetCard'

function makeSet(overrides?: Partial<LibrarySetData>): LibrarySetData {
  return {
    id: 1,
    title: 'Test Collection',
    sort_title: null,
    era: 'dos',
    category: null,
    description: null,
    publisher: null,
    year: null,
    content_rating: null,
    requires_install: false,
    launch_review_flagged: false,
    platform_id: null,
    profile_id: null,
    drive_id: null,
    launch_disk_id: 10,
    display_disk_id: null,
    last_launched_at: null,
    launch_count: 0,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    items: [
      { id: 10, set_id: 1, disc_number: 1, media_path: '/a.iso', cover_art_path: null, cover_art_url: 'http://x/disc1.jpg', executable_path: null, file_size_bytes: null },
      { id: 20, set_id: 1, disc_number: 2, media_path: '/b.iso', cover_art_path: null, cover_art_url: 'http://x/disc2.jpg', executable_path: null, file_size_bytes: null },
      { id: 30, set_id: 1, disc_number: 3, media_path: '/c.iso', cover_art_path: null, cover_art_url: 'http://x/disc3.jpg', executable_path: null, file_size_bytes: null },
    ],
    ...overrides,
  }
}

describe('SetCard', () => {
  it('renders the launch disc as front face when display_disk_id is null', () => {
    const set = makeSet({ launch_disk_id: 10, display_disk_id: null })
    render(<MemoryRouter><SetCard set={set} /></MemoryRouter>)
    // Front face image (layer A, z=3) — alt text is the set title
    const frontImg = screen.getByAltText('Test Collection')
    expect(frontImg).toHaveAttribute('src', 'http://x/disc1.jpg')
  })

  it('renders display_disk_id disc as front face without changing launch_disk_id', () => {
    const set = makeSet({ launch_disk_id: 10, display_disk_id: 20 })
    render(<MemoryRouter><SetCard set={set} /></MemoryRouter>)
    // Front face shows disc 2 (display)
    const frontImg = screen.getByAltText('Test Collection')
    expect(frontImg).toHaveAttribute('src', 'http://x/disc2.jpg')
    // Divergence badge must appear indicating disc 1 (launch_disk_id) will launch
    expect(screen.getByTitle('Disc 1 will launch')).toBeInTheDocument()
    // Background layer for disc 1 — alt "Disc 1"
    expect(screen.getByAltText('Disc 1')).toHaveAttribute('src', 'http://x/disc1.jpg')
  })

  it('shows divergence badge when display_disk_id differs from launch_disk_id and hides it when they match', () => {
    const { rerender } = render(<MemoryRouter><SetCard set={makeSet({ launch_disk_id: 10, display_disk_id: 20 })} /></MemoryRouter>)
    expect(screen.getByTitle('Disc 1 will launch')).toBeInTheDocument()

    // When display == launch, no divergence badge
    rerender(<MemoryRouter><SetCard set={makeSet({ launch_disk_id: 10, display_disk_id: null })} /></MemoryRouter>)
    expect(screen.queryByTitle(/will launch/)).not.toBeInTheDocument()
  })

  it('calls onSetDisplayDisk with the correct set and disc ids when a non-displayed disc strip button is clicked', async () => {
    const user = userEvent.setup()
    const onSetDisplayDisk = vi.fn()
    const set = makeSet({ launch_disk_id: 10, display_disk_id: null })
    render(<MemoryRouter><SetCard set={set} onSetDisplayDisk={onSetDisplayDisk} /></MemoryRouter>)

    // Disc 2 is the first non-display disc button with this title
    const [disc2btn] = screen.getAllByTitle('Set as display cover')
    await user.click(disc2btn)
    expect(onSetDisplayDisk).toHaveBeenCalledWith(1, 20)
  })
})
