import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";

// Distinct from the Emulators page's CatalogEntryResponse — this list merges
// emulator catalog entries with non-emulator third-party tools (extract-xiso)
// via a dedicated backend endpoint, so it must never drive the Emulators page.
interface AttributionEntry {
  name: string;
  license: string;
  copyright: string;
  source_url: string;
}

export default function AttributionTab() {
  const { data: attribution } = useQuery<AttributionEntry[]>({
    queryKey: ["attribution"],
    queryFn: () => apiFetch<AttributionEntry[]>("/api/v1/emulator-items/attribution"),
    staleTime: 60_000,
  });

  return (
    <div className="max-w-xl">
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
          Attribution
        </h2>
        <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
          Open-source software used by Peach 1UP, bundled with the app or downloaded
          on first use. Source code is available via the links below.
        </p>
        <ul className="mt-4 divide-y divide-neutral-100 dark:divide-neutral-800">
          {(attribution ?? []).map((entry) => (
            <li key={entry.name} className="py-3">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
                    {entry.name}
                  </span>
                  {entry.copyright && (
                    <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
                      {entry.copyright}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-xs text-neutral-500 dark:text-neutral-400">
                    {entry.license}
                  </span>
                  {entry.source_url && (
                    <a
                      href={entry.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-accent underline hover:opacity-80"
                    >
                      Source →
                    </a>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>

        <div className="mt-6">
          <h3 className="text-xs font-semibold text-neutral-700 dark:text-neutral-300">
            Contributors
          </h3>
          <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
            Contributors will be listed here in a future update.
          </p>
        </div>
      </section>
    </div>
  );
}
