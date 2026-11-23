import { groupLinks, webLinks } from './externalLinks';

interface ExternalLinksSectionProps {
  links: readonly unknown[] | null | undefined;
}

export function ExternalLinksSection({ links }: ExternalLinksSectionProps) {
  const groups = groupLinks(webLinks(links));
  if (groups.length === 0) return null;

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
        Links
      </h2>
      {groups.map((group) => (
        <div key={group.label} className="space-y-1">
          <h3 className="text-xs font-medium text-neutral-500 dark:text-neutral-400">
            {group.label}
          </h3>
          <ul className="space-y-1">
            {group.links.map((link) => (
              <li key={link.url}>
                <a
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="break-all text-sm text-blue-600 hover:underline dark:text-blue-400"
                >
                  {link.url}
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
