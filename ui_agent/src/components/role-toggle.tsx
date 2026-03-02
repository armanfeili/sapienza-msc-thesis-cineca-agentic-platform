'use client'

import { useAuth, Role } from '@/stores/auth-store'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Loader2, AlertCircle } from 'lucide-react'

interface RoleToggleProps {
  className?: string
}

export function RoleToggle({ className }: RoleToggleProps) {
  const { role, signIn, signOut, hasHydrated, isLoading, tokenError, tokensFetched } = useAuth()

  // Don't render until hydrated to avoid hydration mismatch
  if (!hasHydrated) {
    return (
      <div className={cn('flex items-center gap-2', className)}>
        <div className="h-9 w-20 bg-muted animate-pulse rounded-md" />
        <div className="h-9 w-16 bg-muted animate-pulse rounded-md" />
      </div>
    )
  }

  const handleRoleClick = async (clickedRole: 'admin' | 'user') => {
    if (isLoading) return
    
    if (role === clickedRole) {
      // Same role clicked - sign out
      signOut()
    } else {
      // Different role clicked - sign in as that role
      await signIn(clickedRole)
    }
  }

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Button
        variant={role === 'admin' ? 'default' : 'outline'}
        size="sm"
        onClick={() => handleRoleClick('admin')}
        disabled={isLoading}
        className={cn(
          'min-w-[80px] transition-all',
          role === 'admin' && 'bg-neutral-900 text-white hover:bg-neutral-800'
        )}
      >
        {isLoading && role === null ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          'Admin'
        )}
      </Button>
      <Button
        variant={role === 'user' ? 'default' : 'outline'}
        size="sm"
        onClick={() => handleRoleClick('user')}
        disabled={isLoading}
        className={cn(
          'min-w-[80px] transition-all',
          role === 'user' && 'bg-neutral-900 text-white hover:bg-neutral-800'
        )}
      >
        {isLoading && role === null ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          'User'
        )}
      </Button>
      
      {role && (
        <span className="text-xs text-neutral-500 ml-2">
          Signed in as {role}
        </span>
      )}
      
      {tokenError && (
        <div className="flex items-center gap-1 text-xs text-red-500 ml-2">
          <AlertCircle className="w-3 h-3" />
          <span>{tokenError}</span>
        </div>
      )}
    </div>
  )
}
