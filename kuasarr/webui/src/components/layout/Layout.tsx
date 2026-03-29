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
    <div className="min-h-screen bg-bg-primary">
      {/* Top Navigation */}
      <Navbar jdConnected={jdConnected} />

      {/* Left Sidebar (Desktop) */}
      <Sidebar />

      {/* Main Content Area */}
      <main className="pt-16 lg:pl-64 pb-16 lg:pb-0 min-h-screen">
        <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
          {children}
        </div>
      </main>

      {/* Bottom Navigation (Mobile) */}
      <MobileNav />
    </div>
  )
}
