import { create } from 'zustand'
import type { JDownloaderStatus } from '../types'

interface UIState {
  isMobileMenuOpen: boolean
  jdConnected: boolean
  jdStatus: JDownloaderStatus | null
  toggleMobileMenu: () => void
  closeMobileMenu: () => void
  openMobileMenu: () => void
  setJdConnected: (connected: boolean) => void
  setJdStatus: (status: JDownloaderStatus | null) => void
}

export const useUIStore = create<UIState>((set) => ({
  isMobileMenuOpen: false,
  jdConnected: false,
  jdStatus: null,
  toggleMobileMenu: () => set((state) => ({ isMobileMenuOpen: !state.isMobileMenuOpen })),
  closeMobileMenu: () => set({ isMobileMenuOpen: false }),
  openMobileMenu: () => set({ isMobileMenuOpen: true }),
  setJdConnected: (connected) => set({ jdConnected: connected }),
  setJdStatus: (status) => set({ jdStatus: status }),
}))
