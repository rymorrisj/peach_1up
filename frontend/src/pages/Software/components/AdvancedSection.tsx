import * as Collapsible from '@radix-ui/react-collapsible'
import { Button } from '@/ui'
import LaunchCommandList from '@/components/LaunchCommandList'
interface AdvancedSectionProps {
  item: { launch_review_flagged: boolean }
  flagging: boolean
  flagError: string | null
  onFlagLaunch: () => void
  launchCommands: string[] | null
  setLaunchCommands: (cmds: string[]) => void
}

export function AdvancedSection({
  item,
  flagging,
  flagError,
  onFlagLaunch,
  launchCommands,
  setLaunchCommands,
}: AdvancedSectionProps) {
  return (
    <Collapsible.Root className="space-y-4">
      <Collapsible.Trigger className="group flex w-full items-center justify-between text-xs font-semibold uppercase tracking-wider text-neutral-400 hover:text-neutral-600 dark:text-neutral-500 dark:hover:text-neutral-300">
        <span>Advanced</span>
        <span aria-hidden="true" className="hidden group-data-[state=open]:inline">▲</span>
        <span aria-hidden="true" className="group-data-[state=open]:hidden">▼</span>
      </Collapsible.Trigger>

      <Collapsible.Content>
        <div className="space-y-5">
          {item.launch_review_flagged && (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-700 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-400">
              ⚠ Launch commands may be incorrect — please review.
            </div>
          )}

          <div>
            <div className="mb-1 flex items-center gap-1.5">
              <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                Autoexec commands
              </span>
              <span className="group relative inline-flex cursor-help">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="h-4 w-4 text-neutral-400 dark:text-neutral-500"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
                    clipRule="evenodd"
                  />
                </svg>
                <span className="pointer-events-none absolute bottom-full left-1/2 mb-1.5 w-64 -translate-x-1/2 rounded bg-neutral-800 px-2 py-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100 dark:bg-neutral-700">
                  Commands run in sequence when the game launches, like a DOS autoexec.bat. Use CD to navigate directories, then run your executable. Example: CD DOOMCD then DOOM.EXE
                </span>
              </span>
            </div>
            <LaunchCommandList
              value={launchCommands ?? []}
              onChange={setLaunchCommands}
            />
          </div>

          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              size="sm"
              loading={flagging}
              onClick={onFlagLaunch}
            >
              Flag broken launch
            </Button>
          </div>
          {flagError && (
            <p role="alert" className="text-xs text-red-600 dark:text-red-400">
              ❌ {flagError}
            </p>
          )}
        </div>
      </Collapsible.Content>
    </Collapsible.Root>
  )
}
