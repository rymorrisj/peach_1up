interface PreviousAssetsPanelProps {
  count: number;
  /** True when a cover image is picked, so both choices end by setting it. */
  coverChosen: boolean;
}

export function PreviousAssetsPanel({ count, coverChosen }: PreviousAssetsPanelProps) {
  const one = count === 1;
  return (
    <div
      role="alertdialog"
      aria-label="Previously fetched images"
      className="rounded-md border border-amber-600/50 bg-amber-950/30 p-3"
    >
      <p className="text-sm text-amber-300">
        This game's linked media already has {count} fetched image{one ? '' : 's'}. Choose what
        happens to {one ? 'it' : 'them'}.
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-200">
        <li>
          Replace removes {one ? 'it' : 'them'}, deletes {one ? 'its file' : 'their files'} when
          nothing else uses {one ? 'it' : 'them'}, clears covers that point at {one ? 'it' : 'them'}
          , then adds the selected images.
        </li>
        <li>Keep and add new leaves them and adds only selected images not already saved.</li>
        <li>
          {coverChosen
            ? 'Either way, the game cover is then set to the image you chose.'
            : 'Either way, no new game cover is set.'}
        </li>
        <li>Media you added yourself is never touched.</li>
      </ul>
    </div>
  );
}
