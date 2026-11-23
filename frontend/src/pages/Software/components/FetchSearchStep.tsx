import { Button, Input, Radio, RadioGroup } from '@/ui';
import type { SearchResult } from './metadataReview';

interface FetchSearchStepProps {
  query: string;
  onQueryChange: (query: string) => void;
  onSearch: () => void;
  searching: boolean;
  results: SearchResult[] | null;
  selectedId: number | null;
  onSelect: (gameId: number) => void;
}

export function FetchSearchStep({
  query,
  onQueryChange,
  onSearch,
  searching,
  results,
  selectedId,
  onSelect,
}: FetchSearchStepProps) {
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onSearch();
          }}
          placeholder="Search game title…"
          disabled={searching}
          className="min-w-0 flex-1"
        />
        <Button
          onClick={onSearch}
          disabled={!query.trim() || searching}
          loading={searching}
          size="sm"
        >
          Search
        </Button>
      </div>

      {results !== null && results.length === 0 && (
        <p className="text-sm text-neutral-400">No results found.</p>
      )}

      {results !== null && results.length > 0 && (
        <fieldset>
          <legend className="mb-2 text-xs font-semibold uppercase tracking-wider text-neutral-400">
            Select a match
          </legend>
          <RadioGroup
            value={selectedId != null ? String(selectedId) : ''}
            onValueChange={(v) => onSelect(parseInt(v, 10))}
            className="max-h-64 space-y-1 overflow-y-auto"
          >
            {results.map((r) => (
              <Radio
                key={r.game_id}
                value={String(r.game_id)}
                wrapperClassName="cursor-pointer rounded-md border border-neutral-700 bg-neutral-800/50 px-3 py-2 text-sm hover:border-accent/60 has-[[data-state=checked]]:border-accent has-[[data-state=checked]]:bg-accent/10"
                label={
                  <span className="flex flex-1 items-center gap-3">
                    <span className="flex-1 font-medium text-neutral-100">{r.title}</span>
                    {r.platform && (
                      <span
                        className="max-w-[40%] shrink truncate text-xs text-neutral-400"
                        title={r.platform}
                      >
                        {r.platform}
                      </span>
                    )}
                    {r.release_date && (
                      <span className="shrink-0 text-xs text-neutral-400">
                        {r.release_date.split('-')[0]}
                      </span>
                    )}
                  </span>
                }
              />
            ))}
          </RadioGroup>
        </fieldset>
      )}
    </div>
  );
}
