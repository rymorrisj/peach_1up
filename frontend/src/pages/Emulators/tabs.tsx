import type { TabConfig } from '@/components/layout/TabbedLayout';
import { buildTabRoutes } from '@/components/layout/buildTabRoutes';
import EmulatorList from './Emulators';
import Bios from './Bios';
import RomPacks from './RomPacks';
import Profiles from './Profiles';

export const emulatorsTabs: TabConfig[] = [
  { label: 'Emulators', segment: 'emulators', element: <EmulatorList /> },
  { label: 'BIOS', segment: 'bios', element: <Bios /> },
  { label: 'ROM Packs', segment: 'rom-packs', element: <RomPacks /> },
  { label: 'Profiles', segment: 'profiles', element: <Profiles /> },
];

// Consumed by main.tsx alongside <Emulators/> to declare the
// /emulators/{emulators,bios,rom-packs,profiles} child routes (+ index/
// catchall redirects to emulators) in the same place the app's other routes
// live. /emulators/:slug (EmulatorDetail) is a deliberate sibling exception —
// see dev_docs/v2/08_emulator_profiles_navigation.md, Locked decision 13.
export const emulatorsTabRoutes = buildTabRoutes(emulatorsTabs);
