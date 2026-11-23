import { Checkbox, Radio, RadioGroup } from '@/ui';
import { ASSET_LIMIT, groupAssets, type MetadataAsset } from './metadataReview';

const NO_COVER = 'none';

interface FetchAssetPickerProps {
  assets: MetadataAsset[];
  selected: Set<string>;
  onToggle: (url: string, on: boolean) => void;
  /** Url of the image to become the game cover, null to leave the cover alone. */
  coverUrl: string | null;
  onCoverChange: (url: string | null) => void;
  disabled?: boolean;
}

export function FetchAssetPicker({
  assets,
  selected,
  onToggle,
  coverUrl,
  onCoverChange,
  disabled = false,
}: FetchAssetPickerProps) {
  const atLimit = selected.size >= ASSET_LIMIT;

  return (
    <section aria-label="Images" className="space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">Images</h3>
        <span className="text-xs text-neutral-400">
          {selected.size} of {ASSET_LIMIT} selected
        </span>
      </div>
      {atLimit && (
        <p className="text-xs text-amber-300">
          The limit is {ASSET_LIMIT} images per apply. Clear one to pick another.
        </p>
      )}
      <RadioGroup
        value={coverUrl ?? NO_COVER}
        onValueChange={(v) => onCoverChange(v === NO_COVER ? null : v)}
        disabled={disabled}
        className="gap-4"
      >
        <Radio value={NO_COVER} label="Leave the game cover as it is" />
        {groupAssets(assets).map((group) => (
          <div key={group.type} className="space-y-1.5">
            <h4 className="text-xs font-medium text-neutral-300">{group.label}</h4>
            <div className="grid grid-cols-3 gap-2">
              {group.assets.map((asset, i) => {
                const name = `${group.name} ${i + 1}`;
                const isSelected = selected.has(asset.url);
                return (
                  <div key={asset.url} className="space-y-1">
                    {asset.thumb_url ? (
                      <img
                        src={asset.thumb_url}
                        alt={name}
                        loading="lazy"
                        className="aspect-square w-full rounded-md border border-neutral-700 object-cover"
                      />
                    ) : (
                      <div className="flex aspect-square w-full items-center justify-center rounded-md border border-neutral-700 text-[0.625rem] text-neutral-500">
                        No preview
                      </div>
                    )}
                    <Checkbox
                      size="sm"
                      checked={isSelected}
                      onCheckedChange={(on) => onToggle(asset.url, on)}
                      disabled={disabled || (!isSelected && atLimit)}
                      label={
                        <>
                          Include <span className="sr-only">{name}</span>
                        </>
                      }
                    />
                    <Radio
                      value={asset.url}
                      disabled={disabled || !isSelected}
                      wrapperClassName="gap-2"
                      label={
                        <span className="text-xs">
                          Cover <span className="sr-only">{name}</span>
                        </span>
                      }
                    />
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </RadioGroup>
    </section>
  );
}
