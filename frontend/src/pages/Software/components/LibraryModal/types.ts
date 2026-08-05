import type { UploadDomain } from '@/lib/chunkedUpload';

// Domain-agnostic upload/scan modal, extracted from the former (games-only)
// AddMediaModal.tsx and ScanModal.tsx. A domain wires this in by supplying a
// LibraryModalConfig, the same way gameConfig/mediaConfig/appConfig already
// drive the list/detail pages, no domain-specific JSX or copy lives in this
// file, it all comes from config.
export interface LibraryModalConfig {
  // Which UI this modal instance renders. 'both' shows a tab switcher between
  // the upload and scan bodies in one modal; 'upload' or 'scan' render just
  // that body (this is how Games keeps its existing two-button/two-modal
  // layout, two LibraryModal instances, one of each mode, unchanged from
  // before this extraction).
  mode: 'upload' | 'scan' | 'both';
  // Which route-per-domain endpoint this modal instance uploads to
  // (/api/v1/uploads/software-games|software-media|software-apps, see
  // chunkedUpload.ts). All three now have a live backend endpoint; this
  // value only picks the URL, it is never sent in a request body.
  uploadDomain: UploadDomain;
  modalTitle: string;
  entityLabel: string;
  entityLabelPlural: string;
  // Optional `accept` attribute hint for the file inputs (e.g. ".iso,.img").
  // Undefined means "accept anything", matching the pre-extraction behavior.
  acceptFileTypes?: string;
  // Sub-features of the upload body. All default to false except where noted.
  // Game enables every one of these (unchanged behavior); Media/App only
  // get the plain single/multi-file drop zone unless explicitly turned on.
  supportsMultiDisc?: boolean;
  supportsFolderMode?: boolean;
  // Browse-server-path import has no backend route outside game-items today
  // (see AddMediaModal's former import-from-path flow), only supply
  // importFromPathApiPath when a domain actually has one.
  importFromPathApiPath?: string;
}

export interface UploadEntry {
  id: string;
  file: File;
  progress: number;
  status: 'uploading' | 'success' | 'reused' | 'error';
  error?: string;
  // Set only when the finalize step went to a background job (202 response).
  // While set, the entry's live progress/message are read from
  // state.backgroundJobs instead of the static "success" label below.
  jobId?: string;
}

export interface StagedDisc {
  id: string;
  file: File;
}

// A file or folder picked via the server-side file browser (real, absolute,
// server-resolved path, never a browser File object), staged for import via
// config.importFromPathApiPath. Unlike the drag-and-drop/file-input entries
// above, these can offer "delete original after import" because the backend
// already knows the source's real path.
export interface BrowseImportEntry {
  id: string;
  path: string;
  name: string;
  isDir: boolean;
  deleteOriginal: boolean;
  status: 'staged' | 'importing' | 'processing' | 'success' | 'partial' | 'error';
  error?: string;
  note?: string;
  // Set only when the import went to a background job (job_id in the inline
  // response). While set and the job isn't done yet, status stays 'processing'
  // and live progress/message are read from state.backgroundJobs.
  jobId?: string;
}

// Shape of the inline (non-background) response body from the
// import-from-path endpoint. delete_original_error is only ever present when
// delete_original was true and the post-import cleanup failed; its presence
// never means the import itself failed (the collection/item was already
// committed by that point). No result_type/target_type field here, this
// response never carried one, and nothing read it, so it is not carried
// forward into this generalized component.
export interface ImportFromPathResult {
  job_id?: string;
  delete_original_note?: string;
  delete_original_error?: string;
}

export interface LibraryModalProps {
  open: boolean;
  onClose: () => void;
  // Fired after a successful upload, import, or scan-import, callers pass
  // the same cache-invalidation callback for every mode, exactly as Games.tsx
  // already did for AddMediaModal's onAdded and ScanModal's onImported.
  onComplete: () => void;
  mediaPath?: string | null;
  config: LibraryModalConfig;
}
