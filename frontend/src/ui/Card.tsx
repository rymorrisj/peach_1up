// Bordered container primitive. Other components compose inside of it, it
// is not an image-forward card pattern and has no shadow by default.
//
// Usage:
//   <Card>
//     <Card.Header>Metadata Provider</Card.Header>
//     <p className="text-sm text-fg-2">content...</p>
//   </Card>
//
//   <Card size="lg" className="mt-4">...</Card>
//
// Props:
//   size?: 'sm' | 'md' | 'lg'   maps to p-4 / p-5 / p-6, default 'sm' (p-4)
//   className?: string          merged onto the root, standard div props also pass through
//   children: ReactNode

import { CardRoot } from './CardRoot';
import { CardHeader } from './CardHeader';

export const Card = Object.assign(CardRoot, { Header: CardHeader });
