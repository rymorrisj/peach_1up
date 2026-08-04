import { useRef } from 'react';
import { Button, Input } from '@/ui';
import type { BackgroundJob } from '@/context/_AppContext';
import ProgressBar from './ProgressBar';

interface FolderUploadModeProps {
  busy: boolean;
  folderTitle: string;
  onFolderTitleChange: (value: string) => void;
  folderFiles: File[];
  onSelectFiles: (files: File[]) => void;
  folderStatus: 'idle' | 'uploading' | 'success' | 'error';
  folderError: string | null;
  folderProgress: number;
  folderBackground: boolean;
  folderJobId: string | null;
  folderResult: { type: 'item' | 'set'; title: string; discCount?: number } | null;
  backgroundJobs: BackgroundJob[];
}

export default function FolderUploadMode({
  busy,
  folderTitle,
  onFolderTitleChange,
  folderFiles,
  onSelectFiles,
  folderStatus,
  folderError,
  folderProgress,
  folderBackground,
  folderJobId,
  folderResult,
  backgroundJobs,
}: FolderUploadModeProps) {
  const folderInputRef = useRef<HTMLInputElement>(null);
  const folderJob = folderJobId ? backgroundJobs.find((j) => j.id === folderJobId) : undefined;

  return (
    <div className="space-y-3">
      <Input
        placeholder="Title (e.g. Sonic Adventure)"
        value={folderTitle}
        onChange={(e) => onFolderTitleChange(e.target.value)}
        disabled={busy}
      />
      <div className="flex items-center gap-3">
        <Button
          variant="secondary"
          size="sm"
          disabled={busy}
          onClick={() => folderInputRef.current?.click()}
        >
          Select Folder…
        </Button>
        {folderFiles.length > 0 && (
          <span className="text-sm text-neutral-400">
            {folderFiles.length} file{folderFiles.length !== 1 ? 's' : ''} selected
          </span>
        )}
        <input
          ref={folderInputRef}
          type="file"
          multiple
          // @ts-expect-error webkitdirectory is not in React's InputHTMLAttributes
          webkitdirectory=""
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => {
            if (e.target.files?.length) onSelectFiles(Array.from(e.target.files));
            e.target.value = '';
          }}
        />
      </div>
      {folderFiles.length > 0 && (
        <ul className="max-h-40 space-y-1 overflow-y-auto">
          {folderFiles.map((f, i) => (
            <li key={i} className="truncate rounded px-2 py-0.5 font-mono text-xs text-neutral-400">
              {f.name}
            </li>
          ))}
        </ul>
      )}
      {folderStatus === 'uploading' && (
        <div>
          <div className="mb-1 flex items-center justify-between text-xs text-neutral-400">
            <span>Uploading folder…</span>
            <span>{folderProgress}%</span>
          </div>
          <ProgressBar pct={folderProgress} />
        </div>
      )}
      {folderStatus === 'success' && folderResult && !folderBackground && (
        <p className="text-sm text-emerald-400">
          {folderResult.type === 'set'
            ? `Added "${folderResult.title}" as a ${folderResult.discCount}-disc set.`
            : `Added "${folderResult.title}" as a library item.`}
        </p>
      )}
      {folderStatus === 'success' &&
        folderResult &&
        folderBackground &&
        (() => {
          if (folderJob?.status === 'error') {
            return (
              <p className="text-sm text-red-400">
                Finalizing "{folderResult.title}" failed: {folderJob.error ?? 'Unknown error.'}
              </p>
            );
          }
          if (folderJob && folderJob.status !== 'done') {
            const pct = Math.round((folderJob.progress ?? 0) * 100);
            return (
              <div>
                <p className="text-sm text-neutral-400">{folderJob.message}</p>
                <div className="mt-1">
                  <ProgressBar pct={pct} slow />
                </div>
              </div>
            );
          }
          return (
            <p className="text-sm text-emerald-400">
              Added "{folderResult.title}" as a library item.
            </p>
          );
        })()}
      {folderStatus === 'error' && folderError && (
        <p role="alert" className="text-sm text-red-400">
          {folderError}
        </p>
      )}
    </div>
  );
}
