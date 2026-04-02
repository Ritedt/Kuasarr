import type { ReactNode } from 'react'
import { Navbar } from './Navbar'
import { Sidebar } from './Sidebar'
import { MobileNav } from './MobileNav'

interface LayoutProps {
  children: ReactNode
  jdConnected?: boolean
}

export function Layout({ children, jdConnected = false }: LayoutProps) {
  return (
    <div className="h-[100dvh] flex flex-col bg-bg-primary overflow-hidden">
      {/* Top Navigation */}
      <Navbar jdConnected={jdConnected} />

      {/* Middle: Sidebar + Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Sidebar (Desktop) */}
        <Sidebar />

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto">
          <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
            {children}
          </div>
        </main>
      </div>

      {/* Bottom Navigation (Mobile) */}
      <MobileNav />
    </div>
  )
}
