/**
 * Auth store for managing user authentication state.
 * 
 * Handles:
 * - Role selection (Admin / User)
 * - Dynamic token generation from Auth0 (via /api/auth/tokens)
 * - SSR-safe initialization
 */
import { create, StateCreator } from 'zustand'
import { persist, createJSONStorage, PersistOptions } from 'zustand/middleware'

export type Role = 'admin' | 'user' | null

interface TokensResponse {
  hasTokens: boolean
  admin: string | null
  user: string | null
  error?: string
}

interface GenerateTokenResponse {
  success: boolean
  role: string
  token: string
  error?: string
}

interface AuthState {
  // Current active role
  role: Role
  
  // Tokens for each role (fetched from server)
  adminToken: string | null
  userToken: string | null
  
  // Loading state
  isLoading: boolean
  
  // Hydration flag for SSR safety
  hasHydrated: boolean
  
  // Token fetch state
  tokensFetched: boolean
  tokenError: string | null
  
  // Actions
  setRole: (role: Role) => void
  signIn: (role: 'admin' | 'user') => Promise<void>
  signOut: () => void
  getActiveToken: () => string | null
  setHasHydrated: (state: boolean) => void
  fetchTokens: () => Promise<void>
  generateToken: (role: 'admin' | 'user') => Promise<string | null>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      role: null,
      adminToken: null,
      userToken: null,
      isLoading: false,
      hasHydrated: false,
      tokensFetched: false,
      tokenError: null,

      setRole: (role: Role) => {
        set({ role })
      },

      signIn: async (role: 'admin' | 'user') => {
        set({ isLoading: true, tokenError: null })
        
        try {
          // Generate a fresh token for this role
          const token = await get().generateToken(role)
          
          if (!token) {
            const errorMsg = `Failed to generate ${role} token`
            console.error(errorMsg)
            set({ 
              isLoading: false, 
              tokenError: errorMsg 
            })
            return
          }
          
          // Update state with new token and role
          if (role === 'admin') {
            set({ 
              role: 'admin', 
              adminToken: token,
              isLoading: false,
              tokenError: null,
            })
          } else {
            set({ 
              role: 'user', 
              userToken: token,
              isLoading: false,
              tokenError: null,
            })
          }
          
          console.log(`Signed in as ${role} with fresh token`)
        } catch (error) {
          const errorMsg = error instanceof Error ? error.message : `Failed to sign in as ${role}`
          console.error('Sign in error:', errorMsg)
          set({ 
            isLoading: false, 
            tokenError: errorMsg 
          })
        }
      },

      signOut: () => {
        set({ role: null, tokenError: null })
      },

      getActiveToken: () => {
        const state = get()
        if (state.role === 'admin') return state.adminToken
        if (state.role === 'user') return state.userToken
        return null
      },

      setHasHydrated: (hasHydrated: boolean) => {
        set({ hasHydrated })
      },
      
      // Generate a fresh token for a specific role (POST to /api/auth/tokens)
      generateToken: async (role: 'admin' | 'user'): Promise<string | null> => {
        try {
          const response = await fetch('/api/auth/tokens', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
              role, 
              forceRefresh: true  // Always get a fresh token
            }),
          })
          
          const data: GenerateTokenResponse = await response.json()
          
          if (!response.ok || !data.success) {
            const errorMsg = data.error || `Failed to generate ${role} token`
            console.error('Token generation failed:', errorMsg)
            set({ tokenError: errorMsg })
            return null
          }
          
          return data.token
        } catch (error) {
          const errorMsg = error instanceof Error ? error.message : 'Unknown error generating token'
          console.error('Token generation error:', errorMsg)
          set({ tokenError: errorMsg })
          return null
        }
      },
      
      // Fetch both tokens (GET /api/auth/tokens) - used for initial load
      fetchTokens: async () => {
        set({ isLoading: true, tokenError: null })
        
        try {
          const response = await fetch('/api/auth/tokens')
          const data: TokensResponse = await response.json()
          
          if (!response.ok || !data.hasTokens) {
            const errorMsg = data.error || 'Failed to fetch authentication tokens'
            console.error('Token fetch failed:', errorMsg)
            set({ 
              isLoading: false, 
              tokensFetched: true, 
              tokenError: errorMsg 
            })
            return
          }
          
          set({
            adminToken: data.admin,
            userToken: data.user,
            isLoading: false,
            tokensFetched: true,
            tokenError: null,
          })
          
          console.log('Auth tokens loaded successfully')
        } catch (error) {
          const errorMsg = error instanceof Error ? error.message : 'Unknown error fetching tokens'
          console.error('Failed to fetch tokens:', errorMsg)
          set({ 
            isLoading: false, 
            tokensFetched: true, 
            tokenError: errorMsg 
          })
        }
      },
    }),
    {
      name: 'cineca-agent-auth',
      storage: createJSONStorage(() => {
        // SSR-safe: only access localStorage on client
        if (typeof window === 'undefined') {
          return {
            getItem: () => null,
            setItem: () => {},
            removeItem: () => {},
          }
        }
        return localStorage
      }),
      onRehydrateStorage: () => (state) => {
        // Mark as hydrated after rehydration completes
        state?.setHasHydrated(true)
        // Fetch tokens after hydration (for initial page load)
        if (typeof window !== 'undefined') {
          state?.fetchTokens()
        }
      },
      partialize: (state) => ({
        role: state.role,
        // Don't persist tokens in localStorage for security
        // They will be fetched fresh from the server
      }),
    }
  )
)

// Hook to safely access auth state (waits for hydration)
export function useAuth() {
  const store = useAuthStore()
  
  return {
    ...store,
    isReady: store.hasHydrated && store.tokensFetched,
    isAuthenticated: store.hasHydrated && store.role !== null,
  }
}
