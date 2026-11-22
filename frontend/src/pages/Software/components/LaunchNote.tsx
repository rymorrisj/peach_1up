import { Link } from 'react-router-dom';
import type { LaunchGate } from '../types';

export function LaunchNote({ gate }: { gate: LaunchGate }) {
  if (!gate.launchNote) return null;
  return (
    <p className="text-center text-xs text-neutral-400 dark:text-neutral-500">
      {gate.launchNote}
      {gate.launchNoteLink && (
        <>
          {' '}
          <Link
            to={gate.launchNoteLink.to}
            className="text-blue-600 hover:underline dark:text-blue-400"
          >
            {gate.launchNoteLink.label}
          </Link>
        </>
      )}
    </p>
  );
}
