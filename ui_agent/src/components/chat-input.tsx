'use client'

import React, { useState, useRef, useEffect, useCallback } from 'react'
import { useAuth } from '@/stores/auth-store'
import { useChat } from '@/stores/chat-store'
import { createAgentRun, pollRunUntilComplete, listModels, getDefaultModel, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { Send, Loader2 } from 'lucide-react'

interface ChatInputProps {
  className?: string
}

export function ChatInput({ className }: ChatInputProps) {
  const { role, getActiveToken, hasHydrated, isReady, tokenError } = useAuth()
  const {
    selectedModel,
    setSelectedModel,
    availableModels,
    setAvailableModels,
    addUserMessage,
    addAgentResponse,
    updateAgentRun,
    isSubmitting,
    setIsSubmitting,
    setIsPolling,
    setCurrentRunId,
  } = useChat()
  
  const [prompt, setPrompt] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [modelsLoaded, setModelsLoaded] = useState(false)
  
  // Load available models when role changes
  useEffect(() => {
    const loadModels = async () => {
      if (!role || !isReady) return
      
      const token = getActiveToken()
      if (!token) {
        console.warn('No auth token available')
        return
      }
      
      try {
        // First, try to get the default model from the backend
        let defaultModelId: string | null = null
        try {
          const defaultModel = await getDefaultModel(token)
          if (defaultModel?.chat?.instance_id) {
            defaultModelId = defaultModel.chat.instance_id
            console.log('Default model from backend:', defaultModel.chat.name)
          }
        } catch (defaultError) {
          console.warn('Failed to load default model:', defaultError)
        }
        
        // Then load the list of available models
        const response = await listModels(token)
        const models = response.items
          .filter((m) => m.enabled && m.loaded)
          .map((m) => ({
            id: m.id,
            name: m.instance_name || m.model_id,
          }))
        
        if (models.length > 0) {
          setAvailableModels(models)
          // Use the default model from backend if available, otherwise use first model
          if (defaultModelId && models.some(m => m.id === defaultModelId)) {
            setSelectedModel(defaultModelId)
          } else if (models.length > 0) {
            setSelectedModel(models[0].id)
          }
        } else {
          setAvailableModels([{ id: 'default', name: 'Default Model' }])
          setSelectedModel('default')
        }
        setModelsLoaded(true)
      } catch (error) {
        console.warn('Failed to load models:', error)
        setAvailableModels([{ id: 'default', name: 'Default Model' }])
        setModelsLoaded(true)
      }
    }
    
    loadModels()
  }, [role, isReady, getActiveToken, setAvailableModels, setSelectedModel])
  
  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [prompt])
  
  // Check if can submit
  const canSubmit = isReady && role !== null && prompt.trim().length > 0 && !isSubmitting && !tokenError
  
  // Handle submit
  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return
    
    const token = getActiveToken()
    if (!token) {
      console.error('No auth token available for submission')
      return
    }
    
    const messageContent = prompt.trim()
    
    setPrompt('')
    setIsSubmitting(true)
    
    // Add user message to chat
    const userMessageId = addUserMessage(messageContent)
    
    try {
      // Create agent run
      const createResponse = await createAgentRun(
        { 
          prompt: messageContent,
          metadata: {
            agent_role: role,
          },
        },
        token
      )
      
      // Add initial agent response
      addAgentResponse(userMessageId, createResponse)
      setCurrentRunId(createResponse.run_id)
      setIsPolling(true)
      
      // Poll for completion
      await pollRunUntilComplete(
        createResponse.run_id,
        token,
        (updatedRun) => {
          updateAgentRun(userMessageId, updatedRun)
        },
        2000, // Poll every 2 seconds
        300   // Max 10 minutes
      )
      
    } catch (error) {
      console.error('Failed to submit prompt:', error)
      
      // Add error response
      const errorMessage = error instanceof ApiError 
        ? error.detail || error.message
        : 'An error occurred while processing your request.'
      
      addAgentResponse(userMessageId, {
        run_id: `error-${Date.now()}`,
        user_id: 'system',
        tenant_id: 'global',
        status: 'failed',
        started_at: new Date().toISOString(),
        finished_at: new Date().toISOString(),
        errors: [errorMessage],
      })
    } finally {
      setIsSubmitting(false)
      setIsPolling(false)
      setCurrentRunId(null)
    }
  }, [
    canSubmit,
    prompt,
    role,
    getActiveToken,
    addUserMessage,
    addAgentResponse,
    updateAgentRun,
    setIsSubmitting,
    setIsPolling,
    setCurrentRunId,
  ])
  
  // Handle keyboard shortcuts
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }
  
  // Render placeholder when not ready
  if (!isReady) {
    return (
      <div className={cn('border-t border-neutral-200 bg-white', className)}>
        <div className="max-w-3xl mx-auto p-4">
          <div className="h-[52px] bg-muted animate-pulse rounded-md" />
        </div>
      </div>
    )
  }
  
  return (
    <div className={cn('border-t border-neutral-200 bg-white', className)}>
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-3 sm:py-4">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-end gap-2 sm:gap-3">
          {/* Model selector - full width on mobile */}
          <Select
            value={selectedModel}
            onValueChange={setSelectedModel}
            disabled={!role || isSubmitting}
          >
            <SelectTrigger className="w-full sm:w-[180px] h-10">
              <SelectValue placeholder="Select model" />
            </SelectTrigger>
            <SelectContent>
              {availableModels.map((model) => (
                <SelectItem key={model.id} value={model.id}>
                  {model.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          
          {/* Prompt input + send button row */}
          <div className="flex-1 flex items-end gap-2">
            <div className="flex-1 relative">
              <Textarea
                ref={textareaRef}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  !role 
                    ? 'Select a role above to start chatting...'
                    : tokenError
                    ? 'Authentication error - check configuration'
                    : 'Type your message... (Enter to send)'
                }
                disabled={!role || isSubmitting || !!tokenError}
                className={cn(
                  'min-h-[44px] max-h-[200px] resize-none',
                  'text-neutral-900 placeholder:text-neutral-400'
                )}
                rows={1}
              />
            </div>
            
            {/* Send button */}
            <Button
              onClick={handleSubmit}
              disabled={!canSubmit}
              size="icon"
              className={cn(
                'h-10 w-10 shrink-0',
                'bg-neutral-900 hover:bg-neutral-800 text-white',
                'disabled:bg-neutral-300 disabled:cursor-not-allowed'
              )}
            >
              {isSubmitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          </div>
        </div>
        
        {/* Status message */}
        {!role && isReady && (
          <p className="text-xs text-neutral-500 mt-2 text-center">
            Select Admin or User above to start sending messages
          </p>
        )}
        
        {isSubmitting && (
          <p className="text-xs text-neutral-500 mt-2 text-center">
            Processing your request...
          </p>
        )}
      </div>
    </div>
  )
}
