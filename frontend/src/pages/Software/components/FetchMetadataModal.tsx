import { useEffect, useState, type ReactNode } from 'react';
import { Button, Modal } from '@/ui';
import { useToast } from '@/ui/ToastProvider';
import { apiFetch } from '@/api/client';
import { parseNaiveUtc } from '@/lib/date';
import { METADATA_LOOKUP_TIMEOUT_MS, lookupErrorMessage } from '@/lib/metadataFetch';
import { RATING_CHANGE_ERROR_TYPE, ratingChangeDetail } from '@/hooks/useRatingChangeConfirm';
import { useMetadataApplyJob, isMetadataJobActive } from '@/hooks/useMetadataApplyJob';
import type { RatingChangeDetail } from '@/hooks/useRatingChangeConfirm';
import { FetchApplyStep } from './FetchApplyStep';
import { FetchReviewStep } from './FetchReviewStep';
import { FetchSearchStep } from './FetchSearchStep';
import { PreviousAssetsPanel } from './PreviousAssetsPanel';
import {
  PREVIOUS_ASSETS_ERROR_TYPE,
  previousAssetsCount,
  type PreviousAssetsChoice,
} from './previousAssets';
import { webLinks } from './externalLinks';
import {
  buildEnrichPayload,
  buildReviewFields,
  countCheckedItems,
  defaultAssetSelection,
  defaultCoverUrl,
  defaultFieldSelection,
  defaultRatingSelected,
  uniqueAssets,
  type CurrentMetadata,
  type EnrichSelection,
  type GameDetails,
  type SearchResult,
} from './metadataReview';
import type { GameItemBundleData } from './CollectionCard';

type Phase = 'search' | 'review' | 'apply';

const STEP_LABELS: Record<Phase, string> = {
  search: 'Step 1 of 3: Search',
  review: 'Step 2 of 3: Review',
  apply: 'Step 3 of 3: Apply',
};

const NO_SELECTION: EnrichSelection = {
  fields: {
    title: false,
    year: false,
    description: false,
    genre: false,
    developer: false,
    publisher: false,
  },
  rating: false,
  links: true,
};

function readCachedResults(storageKey: string): SearchResult[] | null {
  try {
    const cached = sessionStorage.getItem(storageKey);
    return cached ? (JSON.parse(cached) as SearchResult[]) : null;
  } catch {
    return null;
  }
}

async function requestDetails(gameId: number): Promise<GameDetails> {
  const data = await apiFetch<GameDetails>(
    `/api/v1/game-items/metadata-details?game_id=${gameId}`,
    {
      timeoutMs: METADATA_LOOKUP_TIMEOUT_MS,
    },
  );
  return {
    ...data,
    assets: uniqueAssets(data.assets ?? []),
    external_links: webLinks(data.external_links),
  };
}

interface FetchMetadataModalProps {
  open: boolean;
  onClose: () => void;
  bundle: GameItemBundleData;
  /** Key the search results are cached under in sessionStorage. */
  storageKey: string;
  /** The provider game id already matched to this game by the active provider,
   *  or null. When set the modal opens on Review instead of Search. */
  knownMatchId: number | null;
  /** Called after metadata or images were applied, to refresh the game. */
  onSuccess: () => void;
  /** Notified while a request or the apply job is in flight, so the trigger
   *  button can show its own loading state even with the modal closed. */
  onBusyChange?: (busy: boolean) => void;
  /** Display label of the active provider ('TheGamesDB' or 'IGDB'), recorded
   *  as metadata_source when metadata is applied. */
  activeProviderLabel: string;
}

/**
 * Hosts the apply job so it outlives the dialog: closing the modal while the
 * job runs leaves it running, and the flow underneath is rebuilt (reset)
 * whenever the modal opens or closes with no job in flight.
 */
export function FetchMetadataModal(props: FetchMetadataModalProps) {
  const { open, bundle, onSuccess, onBusyChange } = props;
  const job = useMetadataApplyJob({ gameTitle: bundle.title, onApplied: onSuccess });
  const [flowBusy, setFlowBusy] = useState(false);
  const [episode, setEpisode] = useState(0);
  const [prevOpen, setPrevOpen] = useState(open);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (!job.active) {
      job.reset();
      setEpisode((e) => e + 1);
    }
  }

  const busy = flowBusy || job.active;
  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);

  return <FetchMetadataFlow key={episode} {...props} job={job} onFlowBusy={setFlowBusy} />;
}

interface FlowProps extends FetchMetadataModalProps {
  job: ReturnType<typeof useMetadataApplyJob>;
  onFlowBusy: (busy: boolean) => void;
}

function FetchMetadataFlow({
  open,
  onClose,
  bundle,
  storageKey,
  knownMatchId,
  onSuccess,
  activeProviderLabel,
  job,
  onFlowBusy,
}: FlowProps) {
  const { showToast } = useToast();

  const [phase, setPhase] = useState<Phase>(
    job.status ? 'apply' : knownMatchId != null ? 'review' : 'search',
  );
  const [query, setQuery] = useState(bundle.title);
  const [results, setResults] = useState<SearchResult[] | null>(() =>
    readCachedResults(storageKey),
  );
  const [selectedId, setSelectedId] = useState<number | null>(null);
  // The flow is rebuilt on every open, so a stored match on a fresh open
  // loads its details once, from the effect below.
  const [autoLoadId] = useState(() =>
    open && !job.status && knownMatchId != null ? knownMatchId : null,
  );
  const [searching, setSearching] = useState(false);
  const [fetching, setFetching] = useState(autoLoadId != null);
  const [lookupError, setLookupError] = useState<string | null>(null);

  const [details, setDetails] = useState<GameDetails | null>(null);
  const [selection, setSelection] = useState<EnrichSelection>(NO_SELECTION);
  const [assetSelected, setAssetSelected] = useState<Set<string>>(new Set());
  const [coverUrl, setCoverUrl] = useState<string | null>(null);

  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [ratingConflict, setRatingConflict] = useState<RatingChangeDetail | null>(null);
  const [confirmRating, setConfirmRating] = useState(false);
  // Set from a previous-assets 409: how many fetched images the linked media
  // already holds, while the Replace / Keep choice is shown.
  const [existingCount, setExistingCount] = useState<number | null>(null);
  const [previousChoice, setPreviousChoice] = useState<PreviousAssetsChoice | undefined>();

  const current: CurrentMetadata = {
    title: bundle.title,
    year: bundle.year,
    description: bundle.description,
    genres: bundle.genres,
    developer: bundle.developer,
    publisher: bundle.publisher,
    content_rating: bundle.content_rating,
  };
  const fields = details ? buildReviewFields(current, details) : [];
  const status = job.status;

  function showDetails(loaded: GameDetails) {
    const picked = defaultAssetSelection(loaded.assets);
    setDetails(loaded);
    setSelection({
      fields: defaultFieldSelection(buildReviewFields(current, loaded)),
      rating: defaultRatingSelected(bundle.content_rating, loaded),
      links: true,
    });
    setAssetSelected(picked);
    setCoverUrl(defaultCoverUrl(loaded.assets, picked));
    setRatingConflict(null);
    setConfirmRating(false);
    setApplyError(null);
    setExistingCount(null);
    setPhase('review');
  }

  async function loadDetails(gameId: number) {
    setFetching(true);
    setLookupError(null);
    try {
      showDetails(await requestDetails(gameId));
    } catch (err) {
      setLookupError(lookupErrorMessage(err, 'Failed to fetch details.'));
    } finally {
      setFetching(false);
    }
  }

  useEffect(() => {
    if (autoLoadId == null) return;
    let stale = false;
    requestDetails(autoLoadId)
      .then((loaded) => !stale && showDetails(loaded))
      .catch((err) => !stale && setLookupError(lookupErrorMessage(err, 'Failed to fetch details.')))
      .finally(() => !stale && setFetching(false));
    return () => {
      stale = true;
    };
    // One request per fresh open, so the deps stay at the stored id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoadId]);

  async function handleSearch() {
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setLookupError(null);
    try {
      const data = await apiFetch<{ results: SearchResult[] }>(
        `/api/v1/game-items/metadata-search?name=${encodeURIComponent(q)}`,
        { timeoutMs: METADATA_LOOKUP_TIMEOUT_MS },
      );
      setResults(data.results);
      setSelectedId(null);
      sessionStorage.setItem(storageKey, JSON.stringify(data.results));
    } catch (err) {
      setLookupError(lookupErrorMessage(err, 'Search failed.'));
    } finally {
      setSearching(false);
    }
  }

  function handleSearchAgain() {
    setPhase('search');
    setDetails(null);
    setLookupError(null);
    setApplyError(null);
    setExistingCount(null);
  }

  function toggleAsset(url: string, on: boolean) {
    if (!details) return;
    const next = new Set(assetSelected);
    if (on) next.add(url);
    else next.delete(url);
    setAssetSelected(next);
    if (coverUrl === url && !on) setCoverUrl(defaultCoverUrl(details.assets, next));
  }

  function changeSelection(next: EnrichSelection) {
    setSelection(next);
    if (!next.rating) {
      setRatingConflict(null);
      setConfirmRating(false);
    }
  }

  async function startJob(previous?: PreviousAssetsChoice) {
    if (!details) return;
    const chosen = details.assets.filter((a) => assetSelected.has(a.url));
    try {
      const started = await apiFetch<{ job_id: string }>(
        `/api/v1/game-items/${bundle.id}/accept-metadata-assets`,
        {
          method: 'POST',
          body: JSON.stringify({
            assets: chosen,
            ...(previous ? { previous_assets: previous } : {}),
            ...(coverUrl ? { cover_asset_url: coverUrl } : {}),
          }),
          quietErrorTypes: [PREVIOUS_ASSETS_ERROR_TYPE],
        },
      );
      setPreviousChoice(previous);
      setExistingCount(null);
      job.track(started.job_id, chosen.length);
      setPhase('apply');
    } catch (err) {
      const existing = previousAssetsCount(err);
      if (existing === null || previous !== undefined) throw err;
      setExistingCount(existing);
    }
  }

  async function handleChoose(previous?: PreviousAssetsChoice) {
    setApplying(true);
    setApplyError(null);
    try {
      await startJob(previous);
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : 'Failed to start applying images.');
    } finally {
      setApplying(false);
    }
  }

  async function handleApply() {
    if (!details) return;
    setApplying(true);
    setApplyError(null);
    try {
      const payload = buildEnrichPayload({
        bundleId: bundle.id,
        providerLabel: activeProviderLabel,
        details,
        fields,
        selection,
        confirmRatingChange: confirmRating,
      });
      if (payload) {
        try {
          await apiFetch('/api/v1/game-items/enrich', {
            method: 'POST',
            body: JSON.stringify(payload),
            quietErrorTypes: [RATING_CHANGE_ERROR_TYPE],
          });
        } catch (err) {
          const conflict = ratingChangeDetail(err);
          if (!conflict) throw err;
          setRatingConflict(conflict);
          setConfirmRating(false);
          return;
        }
        sessionStorage.removeItem(storageKey);
        setRatingConflict(null);
        onSuccess();
      }
      if (assetSelected.size === 0) {
        showToast(`Metadata applied: ${details.title ?? bundle.title}`, 'success');
        onClose();
        return;
      }
      await startJob(previousChoice);
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : 'Failed to apply metadata.');
    } finally {
      setApplying(false);
    }
  }

  function handleRetry() {
    job.reset();
    setPhase('review');
    void handleChoose(previousChoice);
  }

  const lookingUp = searching || fetching;
  const blocking = lookingUp || applying;
  useEffect(() => {
    onFlowBusy(blocking);
  }, [blocking, onFlowBusy]);
  useEffect(() => () => onFlowBusy(false), [onFlowBusy]);

  const checkedCount = details ? countCheckedItems(fields, details, selection) : 0;
  const imageCount = assetSelected.size;
  const needsRatingConfirm = ratingConflict != null && selection.rating && !confirmRating;
  const nothingToApply = checkedCount === 0 && imageCount === 0;

  function summary(): string {
    if (nothingToApply) return 'Nothing is selected to apply.';
    const parts: string[] = [];
    if (checkedCount > 0)
      parts.push(`update ${checkedCount} field${checkedCount === 1 ? '' : 's'}`);
    if (imageCount > 0) {
      parts.push(`save ${imageCount} image${imageCount === 1 ? '' : 's'} to this game's media`);
      if (coverUrl) parts.push('set the game cover to the chosen image');
    }
    const last = parts.pop();
    return `Apply will ${parts.length > 0 ? `${parts.join(', ')} and ` : ''}${last}.`;
  }

  let footer: ReactNode;
  if (phase === 'search') {
    footer = (
      <>
        <Button variant="secondary" onClick={onClose} disabled={lookingUp}>
          Cancel
        </Button>
        <Button
          onClick={() => selectedId != null && void loadDetails(selectedId)}
          disabled={selectedId == null || lookingUp}
          loading={fetching}
        >
          Fetch Now
        </Button>
      </>
    );
  } else if (phase === 'review' && !details) {
    footer = (
      <>
        <Button variant="secondary" onClick={onClose} disabled={fetching}>
          Cancel
        </Button>
        {lookupError && (
          <>
            <Button variant="secondary" onClick={handleSearchAgain}>
              Search instead
            </Button>
            <Button
              onClick={() => knownMatchId != null && void loadDetails(knownMatchId)}
              loading={fetching}
            >
              Retry
            </Button>
          </>
        )}
      </>
    );
  } else if (phase === 'review' && existingCount !== null) {
    footer = (
      <>
        <Button variant="secondary" onClick={() => setExistingCount(null)} disabled={applying}>
          Back
        </Button>
        <Button
          variant="secondary"
          onClick={() => void handleChoose('keep')}
          disabled={applying}
          loading={applying}
        >
          Keep and add new
        </Button>
        <Button
          variant="destructive"
          onClick={() => void handleChoose('replace')}
          disabled={applying}
          loading={applying}
        >
          Replace
        </Button>
      </>
    );
  } else if (phase === 'review') {
    footer = (
      <>
        <Button variant="secondary" onClick={onClose} disabled={applying}>
          Cancel
        </Button>
        <Button
          onClick={() => void handleApply()}
          disabled={applying || nothingToApply || needsRatingConfirm}
          loading={applying}
        >
          Apply
        </Button>
      </>
    );
  } else {
    footer = (
      <>
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
        {isMetadataJobActive(status) && (
          <Button
            variant="destructive"
            onClick={() => void job.cancel()}
            disabled={status?.cancel_requested}
          >
            {status?.cancel_requested ? 'Cancelling' : 'Cancel apply'}
          </Button>
        )}
        {status && (status.state === 'failed' || status.state === 'cancelled') && (
          <Button onClick={handleRetry}>Retry</Button>
        )}
      </>
    );
  }

  return (
    <Modal
      open={open}
      title="Fetch Metadata"
      onClose={onClose}
      busy={blocking}
      footer={<div className="flex items-center gap-3">{footer}</div>}
    >
      <p className="text-xs text-neutral-400">{STEP_LABELS[phase]}</p>

      {phase !== 'apply' && bundle.metadata_fetched_at && (
        <p
          role="note"
          className="rounded-md border border-neutral-700 bg-neutral-800/50 p-3 text-xs text-neutral-300"
        >
          Metadata was last fetched on {parseNaiveUtc(bundle.metadata_fetched_at).toLocaleString()}.
          Fetching again uses additional provider API credits.
        </p>
      )}

      {phase === 'search' && (
        <FetchSearchStep
          query={query}
          onQueryChange={setQuery}
          onSearch={() => void handleSearch()}
          searching={searching}
          results={results}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      )}

      {phase === 'review' && !details && fetching && (
        <p className="text-sm text-neutral-400">Loading details…</p>
      )}

      {phase === 'review' && details && (
        <>
          <p className="text-sm text-neutral-300">
            Matched <strong className="text-neutral-100">{details.title ?? bundle.title}</strong>.{' '}
            <button
              type="button"
              onClick={handleSearchAgain}
              disabled={applying}
              className="text-accent hover:underline disabled:opacity-50"
            >
              Wrong match? Search again
            </button>
          </p>
          <FetchReviewStep
            details={details}
            fields={fields}
            currentRating={bundle.content_rating}
            currentLinks={bundle.external_links}
            selection={selection}
            onSelectionChange={changeSelection}
            ratingConflict={ratingConflict}
            confirmRating={confirmRating}
            onConfirmRating={setConfirmRating}
            assetSelected={assetSelected}
            onToggleAsset={toggleAsset}
            coverUrl={coverUrl}
            onCoverChange={setCoverUrl}
            disabled={applying || existingCount !== null}
          />
          {existingCount !== null && (
            <PreviousAssetsPanel count={existingCount} coverChosen={coverUrl != null} />
          )}
          <p className="text-xs text-neutral-400">{summary()}</p>
        </>
      )}

      {phase === 'apply' && status && (
        <FetchApplyStep status={status} cancelError={job.cancelError} />
      )}

      {lookupError && phase !== 'apply' && (
        <p role="alert" className="text-sm text-red-400">
          {lookupError}
        </p>
      )}
      {applyError && (
        <p role="alert" className="text-sm text-red-400">
          {applyError}
        </p>
      )}
    </Modal>
  );
}
