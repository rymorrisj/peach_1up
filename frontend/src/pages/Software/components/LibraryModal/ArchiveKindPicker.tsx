import { useState } from 'react';
import type { MediaKind } from '@/generated/constants';
import { Button, Select } from '@/ui';

const KIND_OPTIONS: { value: MediaKind; label: string }[] = [
  { value: 'image', label: 'Images' },
  { value: 'audio', label: 'Audio' },
  { value: 'video', label: 'Video' },
  { value: 'text', label: 'Documents' },
];

interface ArchiveKindPickerProps {
  onConfirm: (kind: MediaKind) => void;
  onCancel: () => void;
}

// An archive's media kind cannot be read from its extension, so the user
// chooses it before the upload starts.
export default function ArchiveKindPicker({ onConfirm, onCancel }: ArchiveKindPickerProps) {
  const [kind, setKind] = useState<MediaKind | ''>('');
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-2">
      <span className="text-xs text-neutral-500 dark:text-neutral-400">
        What does this archive contain?
      </span>
      <Select
        value={kind}
        onValueChange={(v) => setKind(v as MediaKind)}
        options={KIND_OPTIONS}
        placeholder="Choose a kind"
      />
      <Button size="sm" disabled={kind === ''} onClick={() => kind && onConfirm(kind)}>
        Upload
      </Button>
      <Button size="sm" variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
    </div>
  );
}
