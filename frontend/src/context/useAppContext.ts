import { useContext } from 'react';
import type { AppContextValue } from './_AppContext';
import { AppContext } from './_AppContext';

export function useAppContext(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used within AppProvider');
  return ctx;
}
