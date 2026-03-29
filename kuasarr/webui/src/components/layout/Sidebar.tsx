import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Package,
  Search,
  FolderOpen,
  Globe,
  BarChart3,
  Bell,
  Settings,
  X,
} from 'lucide-react'
import { useUIStore } from '../../stores/uiStore'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

interface SidebarItem {
  label: string
  href: string
  icon: React.ElementType
}

const sidebarItems: SidebarItem[] = [
  { label: 'Dashboard', href: '/', icon: LayoutDashboard },
  { label: 'Packages', href: '/packages', icon: Package },
  { label: 'Search', href: '/search', icon: Search },
  { label: 'Categories', href: '/categories', icon: FolderOpen },
  { label: 'Hosters', href: '/hosters', icon: Globe },
  { label: 'Statistics', href: '/statistics', icon: BarChart3 },
  { label: 'Notifications', href: '/notifications', icon: Bell },
  { label: 'Settings', href: '/settings', icon: Settings },
]

export function Sidebar() {
  const location = useLocation()
  const { isMobileMenuOpen, closeMobileMenu } = useUIStore()

  const sidebarContent = (
    <>
      {/* Header with close button on mobile */}
      <div className="flex items-center justify-between p-4 lg:hidden">
        <span className="font-heading font-bold text-lg text-gradient">Menu</span>
        <button
          type="button"
          onClick={closeMobileMenu}
          className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
          aria-label="Close menu"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Navigation Items */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {sidebarItems.map((item) => {
          const Icon = item.icon
          const isActive = location.pathname === item.href

          return (
            <Link
              key={item.href}
              to={item.href}
              onClick={closeMobileMenu}
              className={cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 group',
                isActive
                  ? 'bg-kuasarr-primary/20 text-kuasarr-primary-light'
                  : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
              )}
            >
              <Icon
                className={cn(
                  'w-5 h-5 transition-colors',
                  isActive
                    ? 'text-kuasarr-primary-light'
                    : 'text-text-secondary group-hover:text-text-primary'
                )}
              />
              <span>{item.label}</span>
              {isActive && (
                <span className="ml-auto w-1.5 h-1.5 rounded-full bg-kuasarr-primary-light" />
              )}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-bg-tertiary">
        <div className="text-xs text-text-secondary text-center">
          <span className="font-heading font-medium text-text-primary">Kuasarr</span>
          <span className="mx-1">·</span>
          <span>v1.0.0</span>
        </div>
      </div>
    </>
  )

  return (
    <>
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex flex-col w-64 h-screen fixed left-0 top-16 bg-bg-secondary border-r border-bg-tertiary">
        {sidebarContent}
      </aside>

      {/* Mobile Sidebar Overlay */}
      {isMobileMenuOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/50 z-40 lg:hidden"
            onClick={closeMobileMenu}
            aria-hidden="true"
          />
          {/* Mobile Sidebar */}
          <aside className="fixed left-0 top-0 bottom-0 w-64 bg-bg-secondary border-r border-bg-tertiary z-50 flex flex-col lg:hidden animate-slide-up">
            {sidebarContent}
          </aside>
        </>
      )}
    </>
  )
}
