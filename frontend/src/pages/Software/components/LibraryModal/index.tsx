import { useState } from 'react';
import UploadBody from './UploadBody';
import ScanBody from './ScanBody';
import type { LibraryModalProps } from './types';

export type { LibraryModalConfig } from './types';

// Entry point. 'both' is a light tab switcher over the two bodies above, for
// any future domain that wants one button/one modal for both flows, no
// current domain uses it (Games keeps its existing two-button/two-modal
// layout via two separate 'upload'/'scan' instances, Media/App are
// 'upload'-only), but the config shape supports it so a domain can opt in
// without another extraction.
export function LibraryModal(props: LibraryModalProps) {
  const { config, open, onClose } = props;
  const [tab, setTab] = useState<'upload' | 'scan'>(config.mode === 'scan' ? 'scan' : 'upload');

  if (config.mode !== 'both') {
    return config.mode === 'scan' ? <ScanBody {...props} /> : <UploadBody {...props} />;
  }

  // 'both' renders a small segmented control above whichever body is active,
  // sharing one open/close lifecycle. Note: each body tracks its own `busy`
  // state locally and that state is not lifted up here, so switching tabs
  // mid-upload or mid-scan is not currently guarded against. A domain that
  // adopts 'both' should confirm this is acceptable, or lift `busy` up,
  // before relying on it.
  const tabButtonClass = (active: boolean) =>
    `rounded-md px-3 py-1 text-xs font-medium transition-colors ${
      active ? 'bg-accent text-neutral-950' : 'text-neutral-400 hover:text-neutral-200'
    }`;

  return (
    <>
      {open && (
        <div className="fixed inset-x-0 top-4 z-[60] mx-auto flex w-fit gap-1 rounded-lg border border-neutral-700 bg-neutral-900/95 p-1 shadow-lg">
          <button
            type="button"
            className={tabButtonClass(tab === 'upload')}
            onClick={() => setTab('upload')}
          >
            Upload
          </button>
          <button
            type="button"
            className={tabButtonClass(tab === 'scan')}
            onClick={() => setTab('scan')}
          >
            Scan
          </button>
        </div>
      )}
      {tab === 'upload' ? (
        <UploadBody
          {...props}
          onClose={onClose}
          config={{ ...config, modalTitle: `${config.modalTitle}, Upload` }}
        />
      ) : (
        <ScanBody
          {...props}
          onClose={onClose}
          config={{ ...config, modalTitle: `${config.modalTitle}, Scan` }}
        />
      )}
    </>
  );
}
