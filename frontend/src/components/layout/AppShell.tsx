import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'

export default function AppShell() {
  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-surface-950">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-auto p-[1.5em]">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
