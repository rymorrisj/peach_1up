import { Info } from 'lucide-react';
import { Tooltip } from '@/ui';

interface EraReviewHintProps {
  // Plain text, rendered as a text node. It can include disc-supplied strings.
  text: string;
}

// Info icon beside the era field. The trigger is a real button so the tooltip
// opens on keyboard focus as well as hover, the width is capped and the text
// wraps so a long volume label cannot stretch the tooltip.
export function EraReviewHint({ text }: EraReviewHintProps) {
  return (
    <Tooltip
      content={<span className="block max-w-xs whitespace-normal break-words">{text}</span>}
      side="top"
    >
      <button
        type="button"
        aria-label="About this platform"
        className="inline-flex shrink-0 items-center rounded-full text-fg-3 hover:text-fg-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      >
        <Info size={16} aria-hidden="true" />
      </button>
    </Tooltip>
  );
}
