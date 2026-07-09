import { useState, useEffect } from 'react'
import { Button, Modal } from '@/ui'
import { apiFetch } from '@/api/client'
import { useAppContext } from '@/context/useAppContext'

interface SearchResult {
  game_id: number
  title: string
  release_date: string | null
}

interface GameDetails {
  game_id: number
  title: string | null
  release_date: string | null
  overview: string | null
  rating: string | null
  platform_id: number | null
  cover_art_url: string | null
  cover_art_thumb_url: string | null
  genres: string[] | null
  developer: string | null
  publisher: string | null
}

interface FetchMetadataModalProps {
  open: boolean
  onClose: () => void
  entityType: 'library_collection' | 'library_item'
  entityId: number
  entityTitle: string
  storageKey: string
  onSuccess: () => void
  /** Current content_rating on the collection, if any — used to warn when the
   *  fetched rating would lower or clear it. Only meaningful for entityType
   *  'library_collection'; library_item has no content_rating field. */
  currentContentRating?: string | null
  /** Notified whenever a search/fetch/apply request is in flight, so the
   *  trigger button that opens this modal can show its own loading state. */
  onBusyChange?: (busy: boolean) => void
}

export function FetchMetadataModal({
  open,
  onClose,
  entityType,
  entityId,
  entityTitle,
  storageKey,
  onSuccess,
  currentContentRating = null,
  onBusyChange,
}: FetchMetadataModalProps) {
  const { dispatch } = useAppContext()

  const [query, setQuery] = useState(entityTitle)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [results, setResults] = useState<SearchResult[] | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const [phase, setPhase] = useState<'search' | 'preview'>('search')
  const [fetching, setFetching] = useState(false)
  const [details, setDetails] = useState<GameDetails | null>(null)

  const [applying, setApplying] = useState(false)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [confirmRatingChange, setConfirmRatingChange] = useState(false)

  // Pre-fill the search field with the item's title on open — editable, not
  // re-applied on every render (only when the modal transitions to open).
  useEffect(() => {
    if (open) setQuery(entityTitle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Restore cached results from sessionStorage on modal open
  useEffect(() => {
    if (!open) return
    const cached = sessionStorage.getItem(storageKey)
    if (cached) {
      try {
        const parsed = JSON.parse(cached) as SearchResult[]
        setResults(parsed)
      } catch {
        // ignore malformed cache
      }
    }
  }, [open, storageKey])

  // Reset transient state when modal closes
  useEffect(() => {
    if (!open) {
      setQuery('')
      setSearching(false)
      setSearchError(null)
      setResults(null)
      setSelectedId(null)
      setPhase('search')
      setFetching(false)
      setDetails(null)
      setApplying(false)
      setApplyError(null)
      setConfirmRatingChange(false)
    }
  }, [open])

  async function handleSearch() {
    const q = query.trim()
    if (!q) return
    setSearching(true)
    setSearchError(null)
    try {
      const data = await apiFetch<{ results: SearchResult[] }>(
        `/api/v1/library/metadata-search?name=${encodeURIComponent(q)}`,
      )
      setResults(data.results)
      setSelectedId(null)
      sessionStorage.setItem(storageKey, JSON.stringify(data.results))
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Search failed.')
    } finally {
      setSearching(false)
    }
  }

  async function handleFetchNow() {
    if (selectedId == null) return
    setFetching(true)
    setSearchError(null)
    try {
      const data = await apiFetch<GameDetails>(
        `/api/v1/library/metadata-details?game_id=${selectedId}`,
      )
      setDetails(data)
      setPhase('preview')
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Failed to fetch details.')
    } finally {
      setFetching(false)
    }
  }

  async function handleKeep() {
    if (!details) return
    if (ratingChanged && !confirmRatingChange) return
    setApplying(true)
    setApplyError(null)

    const payload: Record<string, unknown> = {
      entity_type: entityType,
      entity_id: entityId,
      metadata_source: 'TheGamesDB',
    }

    if (entityType === 'library_collection') {
      // Metadata lives on the collection — cover_art_url is not supported here.
      if (details.title) payload.title = details.title
      if (details.overview) payload.description = details.overview
      if (details.rating) payload.content_rating = details.rating
      if (ratingChanged) payload.confirm_rating_change = confirmRatingChange
      if (details.release_date) {
        const year = parseInt(details.release_date.split('-')[0], 10)
        if (!isNaN(year)) payload.year = year
      }
      if (details.developer) payload.developer = details.developer
      if (details.publisher) payload.publisher = details.publisher
      if (details.genres && details.genres.length > 0) payload.genre = details.genres
    } else if (entityType === 'library_item') {
      // Leaf: only per-disc cover_art_url is supported.
      if (details.cover_art_url) payload.cover_art_url = details.cover_art_url
    }

    try {
      await apiFetch('/api/v1/library/enrich', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      sessionStorage.removeItem(storageKey)
      dispatch({
        type: 'ADD_TOAST',
        payload: {
          id: crypto.randomUUID(),
          message: `Metadata applied: ${details.title ?? entityTitle}`,
        },
      })
      onSuccess()
      onClose()
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : 'Failed to apply metadata.')
    } finally {
      setApplying(false)
    }
  }

  function handleRedo() {
    setPhase('search')
    setDetails(null)
    setApplyError(null)
    // results stay in state (and sessionStorage) — no re-search needed
  }

  const showCoverArt = entityType === 'library_item'
  const showMetadata = entityType === 'library_collection'
  const busy = phase === 'search' ? searching || fetching : applying

  useEffect(() => {
    onBusyChange?.(busy)
  }, [busy, onBusyChange])

  useEffect(() => {
    if (!open) onBusyChange?.(false)
  }, [open, onBusyChange])
  // Coarse string comparison against the raw provider rating (not the normalized
  // form the backend will store) — this can flag changes the backend later decides
  // don't need confirmation (e.g. a same-rating restated differently, or a raise),
  // but it can never miss a real lower/clear. The backend's normalized comparison
  // in enrich.py is the actual safety gate; this is just visibility for the user.
  const ratingChanged = Boolean(
    showMetadata && details?.rating && currentContentRating && details.rating !== currentContentRating,
  )

  return (
    <Modal
      open={open}
      title="Fetch Metadata"
      onClose={onClose}
      busy={busy}
      footer={
        phase === 'search' ? (
          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={onClose} disabled={searching || fetching}>
              Cancel
            </Button>
            <Button
              onClick={handleFetchNow}
              disabled={selectedId == null || searching || fetching}
              loading={fetching}
            >
              Fetch Now
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={handleRedo} disabled={applying}>
              Redo
            </Button>
            <Button
              onClick={handleKeep}
              disabled={applying || (ratingChanged && !confirmRatingChange)}
              loading={applying}
            >
              Keep
            </Button>
          </div>
        )
      }
    >
      {phase === 'search' ? (
        <div className="space-y-4">
          <div className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void handleSearch() }}
              placeholder="Search game title…"
              disabled={searching}
              className="min-w-0 flex-1 rounded-lg border border-neutral-600 bg-neutral-800 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 outline-none focus:border-[#ff8a5c]"
            />
            <Button
              onClick={() => void handleSearch()}
              disabled={!query.trim() || searching}
              loading={searching}
              size="sm"
            >
              Search
            </Button>
          </div>

          {searchError && (
            <p role="alert" className="text-sm text-red-400">{searchError}</p>
          )}

          {results !== null && results.length === 0 && (
            <p className="text-sm text-neutral-400">No results found.</p>
          )}

          {results !== null && results.length > 0 && (
            <fieldset>
              <legend className="mb-2 text-xs font-semibold uppercase tracking-wider text-neutral-400">
                Select a match
              </legend>
              <ul className="max-h-64 space-y-1 overflow-y-auto">
                {results.map((r) => (
                  <li key={r.game_id}>
                    <label className="flex cursor-pointer items-center gap-3 rounded-md border border-neutral-700 bg-neutral-800/50 px-3 py-2 text-sm hover:border-[#ff8a5c]/60 has-[:checked]:border-[#ff8a5c] has-[:checked]:bg-[#ff8a5c]/10">
                      <input
                        type="radio"
                        name="game-select"
                        value={r.game_id}
                        checked={selectedId === r.game_id}
                        onChange={() => setSelectedId(r.game_id)}
                        className="accent-[#ff8a5c]"
                      />
                      <span className="flex-1 font-medium text-neutral-100">{r.title}</span>
                      {r.release_date && (
                        <span className="shrink-0 text-xs text-neutral-400">
                          {r.release_date.split('-')[0]}
                        </span>
                      )}
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {details && (
            <>
              {showCoverArt && details.cover_art_thumb_url && (
                <div className="flex justify-center">
                  <img
                    src={details.cover_art_thumb_url}
                    alt={details.title ?? 'Cover art'}
                    className="max-h-48 rounded-md border border-neutral-700 object-contain"
                  />
                </div>
              )}

              {showCoverArt && !details.cover_art_thumb_url && (
                <p className="text-sm text-neutral-400 italic">No cover art found.</p>
              )}

              <dl className="space-y-1.5 text-sm">
                {showMetadata && details.title && (
                  <div className="flex gap-2">
                    <dt className="w-28 shrink-0 font-medium text-neutral-400">Title</dt>
                    <dd className="text-neutral-100">{details.title}</dd>
                  </div>
                )}
                {details.release_date && (
                  <div className="flex gap-2">
                    <dt className="w-28 shrink-0 font-medium text-neutral-400">Release</dt>
                    <dd className="text-neutral-100">{details.release_date}</dd>
                  </div>
                )}
                {showMetadata && details.overview && (
                  <div className="flex gap-2">
                    <dt className="w-28 shrink-0 font-medium text-neutral-400">Overview</dt>
                    <dd className="line-clamp-4 text-neutral-100">{details.overview}</dd>
                  </div>
                )}
                {showMetadata && details.rating && (
                  <div className="flex gap-2">
                    <dt className="w-28 shrink-0 font-medium text-neutral-400">Rating</dt>
                    <dd className="text-neutral-100">
                      {ratingChanged ? (
                        <span>
                          <span className="text-neutral-400 line-through">{currentContentRating}</span>
                          {' → '}
                          <span className="font-medium text-amber-400">{details.rating}</span>
                        </span>
                      ) : (
                        details.rating
                      )}
                    </dd>
                  </div>
                )}
                {showMetadata && details.genres && details.genres.length > 0 && (
                  <div className="flex gap-2">
                    <dt className="w-28 shrink-0 font-medium text-neutral-400">Genre</dt>
                    <dd className="text-neutral-100">{details.genres.join(', ')}</dd>
                  </div>
                )}
                {showMetadata && details.developer && (
                  <div className="flex gap-2">
                    <dt className="w-28 shrink-0 font-medium text-neutral-400">Developer</dt>
                    <dd className="text-neutral-100">{details.developer}</dd>
                  </div>
                )}
                {showMetadata && details.publisher && (
                  <div className="flex gap-2">
                    <dt className="w-28 shrink-0 font-medium text-neutral-400">Publisher</dt>
                    <dd className="text-neutral-100">{details.publisher}</dd>
                  </div>
                )}
              </dl>

              {ratingChanged && (
                <div className="rounded-md border border-amber-600/50 bg-amber-950/30 p-3">
                  <p className="text-sm text-amber-300">
                    The content rating is changing from <strong>{currentContentRating}</strong> to{' '}
                    <strong>{details.rating}</strong>. If this lowers or clears an existing rating,
                    it can affect what sub-accounts are allowed to see.
                  </p>
                  <label className="mt-2 flex cursor-pointer items-center gap-2 text-sm text-amber-200">
                    <input
                      type="checkbox"
                      checked={confirmRatingChange}
                      onChange={(e) => setConfirmRatingChange(e.target.checked)}
                      className="accent-[#ff8a5c]"
                    />
                    I understand and want to apply this rating change
                  </label>
                </div>
              )}
            </>
          )}

          {applyError && (
            <p role="alert" className="text-sm text-red-400">{applyError}</p>
          )}
        </div>
      )}
    </Modal>
  )
}
