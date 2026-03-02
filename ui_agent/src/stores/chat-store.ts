/**
 * Chat store for managing chat sessions and messages.
 * 
 * Handles:
 * - Chat messages (user prompts and agent responses)
 * - Agent runs with steps and status
 * - Loading states
 * - Model selection
 */
import { create } from 'zustand'

// Types matching backend schemas
export interface OrchestrationStep {
  step_id: string
  action?: string
  input?: Record<string, unknown>
  output?: Record<string, unknown>
  error?: string
  started_at?: string
  finished_at?: string
  latency_ms?: number
  type?: 'step' | 'output'
}

export interface TodoItem {
  task: string
  status?: 'pending' | 'in_progress' | 'completed' | 'failed'
  evidence?: string[]
}

export interface ExecutionMetrics {
  overall_ms?: number
  llm?: Array<{
    model: string
    latency_ms: number
    success: boolean
    input_tokens?: number
    output_tokens?: number
    total_tokens?: number
    purpose?: string
    error?: string
  }>
  tools?: Array<{
    name: string
    latency_ms: number
    success: boolean
  }>
  total_llm_calls?: number
  tool_calls?: number
  tool_errors?: number
}

export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface AgentRun {
  run_id: string
  session_id?: string
  user_id: string
  tenant_id: string
  model?: string
  manager?: string
  latency_ms?: number
  trace_id?: string
  request_id?: string
  event_id?: string
  status: RunStatus
  started_at: string
  finished_at?: string
  output?: Record<string, unknown> | string | null
  steps?: OrchestrationStep[]
  todos?: TodoItem[]
  metrics?: ExecutionMetrics
  errors?: string[]
}

export interface ChatMessage {
  id: string
  type: 'user' | 'agent'
  content: string
  timestamp: Date
  run?: AgentRun
}

interface ChatState {
  // Messages in the current session
  messages: ChatMessage[]
  
  // Current model selection
  selectedModel: string
  
  // Available models (fetched from backend)
  availableModels: Array<{ id: string; name: string }>
  
  // Current run being executed
  currentRunId: string | null
  
  // Loading states
  isSubmitting: boolean
  isPolling: boolean
  
  // Auto-scroll state
  shouldAutoScroll: boolean
  
  // Actions
  addUserMessage: (content: string) => string
  addAgentResponse: (messageId: string, run: AgentRun) => void
  updateAgentRun: (messageId: string, run: AgentRun) => void
  setSelectedModel: (model: string) => void
  setAvailableModels: (models: Array<{ id: string; name: string }>) => void
  setCurrentRunId: (runId: string | null) => void
  setIsSubmitting: (isSubmitting: boolean) => void
  setIsPolling: (isPolling: boolean) => void
  setShouldAutoScroll: (shouldAutoScroll: boolean) => void
  clearMessages: () => void
  getMessageByRunId: (runId: string) => ChatMessage | undefined
}

// Generate unique ID
const generateId = () => `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

export const useChatStore = create<ChatState>()((set, get) => ({
  messages: [],
  selectedModel: 'default',
  availableModels: [{ id: 'default', name: 'Default Model' }],
  currentRunId: null,
  isSubmitting: false,
  isPolling: false,
  shouldAutoScroll: true,

  addUserMessage: (content: string) => {
    const id = generateId()
    const message: ChatMessage = {
      id,
      type: 'user',
      content,
      timestamp: new Date(),
    }
    set((state) => ({
      messages: [...state.messages, message],
      shouldAutoScroll: true,
    }))
    return id
  },

  addAgentResponse: (messageId: string, run: AgentRun) => {
    const agentMessage: ChatMessage = {
      id: `agent-${messageId}`,
      type: 'agent',
      content: '',
      timestamp: new Date(),
      run,
    }
    set((state) => ({
      messages: [...state.messages, agentMessage],
      shouldAutoScroll: true,
    }))
  },

  updateAgentRun: (messageId: string, run: AgentRun) => {
    set((state) => ({
      messages: state.messages.map((msg) => {
        if (msg.id === `agent-${messageId}` || msg.run?.run_id === run.run_id) {
          return { ...msg, run }
        }
        return msg
      }),
    }))
  },

  setSelectedModel: (model: string) => {
    set({ selectedModel: model })
  },

  setAvailableModels: (models: Array<{ id: string; name: string }>) => {
    set({ availableModels: models })
  },

  setCurrentRunId: (runId: string | null) => {
    set({ currentRunId: runId })
  },

  setIsSubmitting: (isSubmitting: boolean) => {
    set({ isSubmitting })
  },

  setIsPolling: (isPolling: boolean) => {
    set({ isPolling })
  },

  setShouldAutoScroll: (shouldAutoScroll: boolean) => {
    set({ shouldAutoScroll })
  },

  clearMessages: () => {
    set({ messages: [], currentRunId: null })
  },

  getMessageByRunId: (runId: string) => {
    return get().messages.find((msg) => msg.run?.run_id === runId)
  },
}))

// Hook for easy access
export function useChat() {
  return useChatStore()
}
