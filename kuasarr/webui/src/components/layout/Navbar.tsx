import { Link, useLocation } from 'react-router-dom'
import { Menu, X, Activity } from 'lucide-react'
import { useUIStore } from '../../stores/uiStore'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

interface NavLink {
  label: string
  href: string
}

const navLinks: NavLink[] = [
  { label: 'Dashboard', href: '/' },
  { label: 'Packages', href: '/packages' },
  { label: 'Search', href: '/search' },
  { label: 'Categories', href: '/categories' },
  { label: 'Hosters', href: '/hosters' },
  { label: 'Settings', href: '/settings' },
]

interface NavbarProps {
  jdConnected?: boolean
}

export function Navbar({ jdConnected = false }: NavbarProps) {
  const location = useLocation()
  const { isMobileMenuOpen, toggleMobileMenu, closeMobileMenu } = useUIStore()

  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-16">
      <nav className="h-full glass border-b border-bg-tertiary/50">
        <div className="h-full px-4 sm:px-6 lg:px-8 flex items-center justify-between">
          {/* Logo */}
          <Link
            to="/"
            className="flex items-center gap-3 hover:opacity-90 transition-opacity"
            onClick={closeMobileMenu}
          >
            <img
              src="/static/logo.png"
              alt="Kuasarr"
              className="h-8 w-auto"
              width={32}
              height={32}
            />
            <span className="font-heading font-bold text-xl text-gradient hidden sm:block">
              Kuasarr
            </span>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden lg:flex items-center gap-1">
            {navLinks.map((link) => {
              const isActive = location.pathname === link.href
              return (
                <Link
                  key={link.href}
                  to={link.href}
                  className={cn(
                    'px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                    isActive
                      ? 'bg-kuasarr-primary/20 text-kuasarr-primary-light'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
                  )}
                >
                  {link.label}
                </Link>
              )
            })}
          </div>

          {/* Right Section: JD Status + Mobile Menu */}
          <div className="flex items-center gap-4">
            {/* JDownloader Connection Status */}
            <div
              className={cn(
                'hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border',
                jdConnected
                  ? 'bg-kuasarr-success/10 text-kuasarr-success border-kuasarr-success/30'
                  : 'bg-kuasarr-error/10 text-kuasarr-error border-kuasarr-error/30'
              )}
              title={jdConnected ? 'JDownloader Connected' : 'JDownloader Disconnected'}
            >
              <Activity className="w-3.5 h-3.5" />
              <span className="hidden md:inline">
                {jdConnected ? 'JD Connected' : 'JD Disconnected'}
              </span>
            </div>

            {/* Mobile Menu Button */}
            <button
              type="button"
              onClick={toggleMobileMenu}
              className="lg:hidden p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
              aria-label={isMobileMenuOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={isMobileMenuOpen}
            >
              {isMobileMenuOpen ? (
                <X className="w-6 h-6" />
              ) : (
                <Menu className="w-6 h-6" />
              )}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Dropdown */}
        {isMobileMenuOpen && (
          <div className="lg:hidden glass border-t border-bg-tertiary/50 animate-fade-in">
            <div className="px-4 py-3 space-y-1">
              {navLinks.map((link) => {
                const isActive = location.pathname === link.href
                return (
                  <Link
                    key={link.href}
                    to={link.href}
                    onClick={closeMobileMenu}
                    className={cn(
                      'block px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200',
                      isActive
                        ? 'bg-kuasarr-primary/20 text-kuasarr-primary-light'
                        : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
                    )}
                  >
                    {link.label}
                  </Link>
                )
              })}

              {/* Mobile JD Status */}
              <div
                className={cn(
                  'sm:hidden flex items-center gap-2 px-4 py-3 rounded-lg text-sm font-medium mt-2',
                  jdConnected
                    ? 'bg-kuasarr-success/10 text-kuasarr-success'
                    : 'bg-kuasarr-error/10 text-kuasarr-error'
                )}
              >
                <Activity className="w-4 h-4" />
                <span>{jdConnected ? 'JDownloader Connected' : 'JDownloader Disconnected'}</span>
              </div>
            </div>
          </div>
        )}
      </nav>
    </header>
  )
}
