import { createContext, useContext } from 'react'
import { buildAuthSnapshot } from '@/context/buildAuthSnapshot'

export const AuthContext = createContext({
    token: null,
    isAdmin: false,
    isJournalist: false,
    isCurator: false,
    hasApiKey: false,
    hasCuratorKey: false,
    displayName: null,
    displayNameConfirmed: false,
    role: 'user',
    expiresIn: null,
})

export const AuthUIContext = createContext({
    openLoginModal: () => { },
    closeLoginModal: () => { },
    logout: () => { },
    isLoginModalOpen: false,
})

export function useAuth() {
    return useContext(AuthContext)
}

export function useAuthUI() {
    return useContext(AuthUIContext)
}

export { buildAuthSnapshot }
