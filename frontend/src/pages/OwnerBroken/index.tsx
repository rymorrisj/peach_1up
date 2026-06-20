export default function OwnerBroken() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-white px-4 dark:bg-surface-950">
      <div className="max-w-md text-center">
        <h1 className="mb-2 text-xl font-semibold text-neutral-700 dark:text-neutral-300">
          Owner account unavailable
        </h1>
        <p className="mb-4 text-sm text-neutral-600 dark:text-neutral-400">
          The owner account is missing or locked. Recovery requires running the
          setup script from the host machine, in the project directory:
        </p>
        <pre className="rounded bg-neutral-100 px-3 py-2 text-left text-sm font-mono text-neutral-800 dark:bg-surface-800 dark:text-neutral-200">
          python scripts/setup_admin_user.py
        </pre>
        <p className="mt-4 text-xs text-neutral-500 dark:text-neutral-500">
          This prompts for a new owner name and PIN, then the app can be used again.
        </p>
      </div>
    </main>
  )
}
