import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Package, Search, FolderOpen, MoreHorizontal } from 'lucide-react'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

interface MobileNavItem {
  label: string
  href: string
  icon: React.ElementType
}

const mobileNavItems: MobileNavItem[] = [
  { label: 'Home', href: '/', icon: LayoutDashboard },
  { label: 'Packages', href: '/packages', icon: Package },
  { label: 'Search', href: '/search', icon: Search },
  { label: 'Categories', href: '/categories', icon: FolderOpen },
  { label: 'More', href: '/settings', icon: MoreHorizontal },
]

export function MobileNav() {
  const location = useLocation()

  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 bg-bg-secondary/95 backdrop-blur-lg border-t border-bg-tertiary safe-area-pb">
      <div className="flex items-center justify-around h-16">
        {mobileNavItems.map((item) => {
          const Icon = item.icon
          const isActive = location.pathname === item.href

          return (
            <Link
              key={item.label}
              to={item.href}
              className={cn(
                'flex flex-col items-center justify-center gap-1 flex-1 h-full transition-all duration-200',
                isActive
                  ? 'text-kuasarr-primary-light'
                  : 'text-text-secondary hover:text-text-primary'
              )}
            >
              <div
                className={cn(
                  'relative p-1.5 rounded-xl transition-all duration-200',
                  isActive && 'bg-kuasarr-primary/20'
                )}
              >
                <Icon className="w-5 h-5" />
                {isActive && (
                  <span className="absolute -top-0.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-kuasarr-primary-light" />
                )}
              </div>
              <span className="text-[10px] font-medium">{item.label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
