import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { apiFetch } from '@/api/client';

// Server-side pagination envelope (backend/models/pagination.py: items/total/
// limit/offset). Typed locally, same as Software/index.tsx's own Page<T>, so
// this hook builds before @shared/types (which only has per-endpoint
// Page_XRead_ instantiations, not a reusable generic) is regenerated.
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface UsePaginatedListOptions {
  /** API path with no query string, e.g. "/api/v1/game-items". */
  path: string;
  /** Requested page size (sent as `limit`). Defaults to 50. */
  pageSize?: number;
  /**
   * Extra query params to forward alongside limit/offset, e.g. filters like
   * `{ era: 'dos' }`. The hook has no knowledge of what these mean; it only
   * merges them into the request and into the query key so a filter change
   * triggers a refetch (and resets back to the first page, see below).
   */
  params?: Record<string, string>;
  /** Query-param name used to track page position in the URL. Defaults to
   *  "offset"; override if a route ever needs two independent paginated
   *  lists side by side. */
  offsetParam?: string;
  /** Passed through to the underlying useQuery, set false to defer fetching. */
  enabled?: boolean;
}

export interface UsePaginatedListResult<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
  /** 1-indexed current page. */
  page: number;
  pageCount: number;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  hasPrevPage: boolean;
  hasNextPage: boolean;
  /** Jump to a 1-indexed page number. */
  goToPage: (page: number) => void;
  goToOffset: (offset: number) => void;
  nextPage: () => void;
  prevPage: () => void;
}

function serializeParams(params: Record<string, string> | undefined): string {
  if (!params) return '';
  return JSON.stringify(Object.entries(params).sort(([a], [b]) => a.localeCompare(b)));
}

/**
 * Generic fetch + navigation-controls hook for any paginated list view
 * consuming the backend's Page[T] envelope. Scoped intentionally to fetch +
 * next/prev/page-jump only, no caching strategy, hydration, or
 * stale-while-revalidate beyond whatever @tanstack/react-query does by
 * default; those are deferred to a later pass (dev_docs/v2/08_...md).
 *
 * Page position lives in the URL (`?offset=` by default) rather than in
 * component state, per the doc's "collection/pagination → query params" rule
 *, this makes a given page of a list bookmarkable/deep-linkable like any
 * other query-param-driven filter in the app.
 */
export function usePaginatedList<T>({
  path,
  pageSize = 50,
  params,
  offsetParam = 'offset',
  enabled = true,
}: UsePaginatedListOptions): UsePaginatedListResult<T> {
  const [searchParams, setSearchParams] = useSearchParams();

  const parsedOffset = Number(searchParams.get(offsetParam));
  const offset = Number.isFinite(parsedOffset) && parsedOffset > 0 ? Math.floor(parsedOffset) : 0;

  const setOffset = (next: number) => {
    const clamped = Math.max(0, Math.floor(next));
    setSearchParams((prev) => {
      const nextParams = new URLSearchParams(prev);
      if (clamped > 0) nextParams.set(offsetParam, String(clamped));
      else nextParams.delete(offsetParam);
      return nextParams;
    });
  };

  // A filter change (params changing identity/value) invalidates whatever
  // page the URL currently points at, e.g. going from "all games" to "DOS
  // only" while sitting on offset=200 could land on a page past the end of
  // the filtered result set. Reset to the first page whenever the caller's
  // params actually change value, mirroring what Software/index.tsx already
  // does by hand today for its own era filter.
  const paramsKey = serializeParams(params);
  const prevParamsKeyRef = useRef(paramsKey);
  useEffect(() => {
    if (prevParamsKeyRef.current !== paramsKey) {
      prevParamsKeyRef.current = paramsKey;
      setOffset(0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey]);

  const requestParams = new URLSearchParams(params);
  requestParams.set('limit', String(pageSize));
  requestParams.set('offset', String(offset));

  const { data, isLoading, isFetching, isError, error } = useQuery<Page<T>>({
    queryKey: ['paginated-list', path, paramsKey, offset, pageSize],
    queryFn: () => apiFetch<Page<T>>(`${path}?${requestParams.toString()}`),
    placeholderData: keepPreviousData,
    enabled,
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const limit = data?.limit ?? pageSize;
  const page = limit > 0 ? Math.floor(offset / limit) + 1 : 1;
  const pageCount = limit > 0 ? Math.max(1, Math.ceil(total / limit)) : 1;

  return {
    items,
    total,
    offset,
    limit,
    page,
    pageCount,
    isLoading,
    isFetching,
    isError,
    error,
    hasPrevPage: offset > 0,
    hasNextPage: offset + limit < total,
    goToOffset: setOffset,
    goToPage: (targetPage: number) => setOffset(Math.max(0, (targetPage - 1) * limit)),
    nextPage: () => setOffset(offset + limit),
    prevPage: () => setOffset(Math.max(0, offset - limit)),
  };
}
