'use client'

import { RoleToggle } from '@/components/role-toggle'
import { ChatArea } from '@/components/chat-area'
import { ChatInput } from '@/components/chat-input'

export default function Home() {
  return (
    <div className="flex flex-col h-screen h-[100dvh] bg-white">
      {/* Top bar with role toggles */}
      <header className="flex-shrink-0 border-b border-neutral-200 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-3 flex flex-col sm:flex-row items-center justify-between gap-2">
          <h1 className="text-lg font-semibold text-neutral-900">
            Cineca Agent
          </h1>
          <RoleToggle />
        </div>
      </header>
      
      {/* Main content area */}
      <main className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {/* Scrollable chat area */}
        <ChatArea className="flex-1 min-h-0" />
        
        {/* Sticky chat input bar */}
        <ChatInput className="flex-shrink-0" />
      </main>
    </div>
  )
}
