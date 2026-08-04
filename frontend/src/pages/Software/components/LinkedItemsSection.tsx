import { Link } from 'react-router-dom';
import { GAME_ROUTE_BASE, MEDIA_ROUTE_BASE, APP_ROUTE_BASE } from '../types';
import type { LinkedEntityRef } from '../types';

// Resolves a LinkedEntityRef's counterpart into a route path, or null when the
// counterpart has no deep-linkable detail page. Game is slug-routed
// (gameConfig's identifierParam), Media/App are id-routed. A media_item leaf
// counterpart has no detail route of its own, only media_item_bundle does,
// /software/media/:id resolves bundle ids only (backend/api/routes/media.py
// exposes a leaf item only via the separate GET /media-item/{id} route, with
// no frontend page for it), so it renders as plain text, not a link.
export function linkedEntityRoute(ref: LinkedEntityRef): string | null {
  switch (ref.entity_type) {
    case 'game_item_bundle':
      return ref.slug ? `${GAME_ROUTE_BASE}/${ref.slug}` : null;
    case 'app_item_bundle':
      return `${APP_ROUTE_BASE}/${ref.entity_id}`;
    case 'media_item_bundle':
      return `${MEDIA_ROUTE_BASE}/${ref.entity_id}`;
    default:
      return null;
  }
}

interface LinkedItemsSectionProps {
  items: LinkedEntityRef[];
}

export function LinkedItemsSection({ items }: LinkedItemsSectionProps) {
  if (items.length === 0) return null;

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        Linked Items
      </h2>
      <ul className="space-y-1">
        {items.map((item) => {
          const to = linkedEntityRoute(item);
          return (
            <li key={item.link_id}>
              {to ? (
                <Link to={to} className="text-sm text-blue-600 hover:underline dark:text-blue-400">
                  {item.title}
                </Link>
              ) : (
                <span className="text-sm text-neutral-500 dark:text-neutral-400">{item.title}</span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
