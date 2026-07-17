import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-surface-0">
      <div className="text-center">
        <h1 className="mb-2 text-6xl font-bold text-fg-3">404</h1>
        <h2 className="mb-4 text-xl font-semibold text-neutral-700 dark:text-neutral-300">
          Page not found
        </h2>
        <Link
          to="/software"
          className="text-sm font-medium text-peach underline-offset-4 hover:underline"
        >
          Go to Software
        </Link>
      </div>
    </main>
  )
}
