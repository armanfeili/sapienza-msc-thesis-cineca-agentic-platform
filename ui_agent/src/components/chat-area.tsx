'use client'

import React, { useEffect, useRef, useMemo } from 'react'
import { useChat, ChatMessage, AgentRun, OrchestrationStep } from '@/stores/chat-store'
import { cn } from '@/lib/utils'
import { Loader2, CheckCircle2, XCircle, Clock, User, Bot, ChevronDown, ChevronRight, Code, FileText } from 'lucide-react'

interface ChatAreaProps {
  className?: string
}

// Loading dots animation component
function LoadingDots() {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="loading-dot w-1.5 h-1.5 bg-neutral-400 rounded-full" />
      <span className="loading-dot w-1.5 h-1.5 bg-neutral-400 rounded-full" />
      <span className="loading-dot w-1.5 h-1.5 bg-neutral-400 rounded-full" />
    </span>
  )
}

// Merged step with both action info and output
interface MergedStep {
  step_id: string
  action?: string
  input?: Record<string, unknown>
  output?: Record<string, unknown>
  error?: string | null
  latency_ms?: number
  started_at?: string
  finished_at?: string
}

// Merge steps and outputs by step_id
function mergeStepsAndOutputs(steps: OrchestrationStep[] | undefined): MergedStep[] {
  if (!steps || steps.length === 0) return []
  
  const merged = new Map<string, MergedStep>()
  
  for (const step of steps) {
    const stepId = step.step_id
    if (!stepId) continue
    
    const existing = merged.get(stepId) || { step_id: stepId }
    
    if (step.type === 'step' || (!step.type && step.action)) {
      // This is the action/input entry
      existing.action = step.action
      existing.input = step.input
      existing.started_at = step.started_at
      // Use latency from step if output doesn't have it
      if (step.latency_ms !== undefined && existing.latency_ms === undefined) {
        existing.latency_ms = step.latency_ms
      }
    } else if (step.type === 'output' || step.output !== undefined) {
      // This is the output entry
      existing.output = step.output
      existing.error = step.error
      existing.finished_at = step.finished_at
      // Prefer latency from output entry
      if (step.latency_ms !== undefined) {
        existing.latency_ms = step.latency_ms
      }
    }
    
    merged.set(stepId, existing)
  }
  
  // Convert to array and filter out final-output (handled separately)
  return Array.from(merged.values()).filter(s => s.step_id !== 'final-output')
}

// Get the final output from steps
function getFinalOutput(steps: OrchestrationStep[] | undefined): Record<string, unknown> | null {
  if (!steps) return null
  const finalStep = steps.find(s => s.step_id === 'final-output' && s.type === 'output')
  return finalStep?.output || null
}

// Format output value for display
function formatOutputValue(value: unknown, maxLength = 300): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'boolean' || typeof value === 'number') return String(value)
  
  try {
    const str = JSON.stringify(value, null, 2)
    if (str.length > maxLength) {
      return str.slice(0, maxLength) + '...'
    }
    return str
  } catch {
    return String(value)
  }
}

// Extract meaningful text from output object
function extractOutputText(output: Record<string, unknown> | undefined): string | null {
  if (!output) return null
  
  // Priority order for text fields
  const textFields = ['text', 'answer', 'result', 'explanation', 'message', 'response', 'content']
  
  for (const field of textFields) {
    if (output[field] && typeof output[field] === 'string') {
      return output[field] as string
    }
  }
  
  return null
}

// Step status indicator
function StepStatusIcon({ step }: { step: MergedStep }) {
  const hasOutput = step.output !== undefined
  const hasError = step.error !== undefined && step.error !== null
  
  if (hasError) {
    return <XCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
  }
  if (hasOutput) {
    return <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
  }
  return <Clock className="w-4 h-4 text-neutral-400 flex-shrink-0" />
}

// Collapsible output display
function StepOutput({ output, error }: { output?: Record<string, unknown>; error?: string | null }) {
  const [isExpanded, setIsExpanded] = React.useState(false)
  
  if (error) {
    return (
      <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-sm text-red-600">
        {error}
      </div>
    )
  }
  
  if (!output) return null
  
  // Extract text content if available
  const textContent = extractOutputText(output)
  const hasOtherFields = Object.keys(output).filter(k => !['text', 'answer', 'result', 'explanation'].includes(k)).length > 0
  
  // Check for specific output types
  const isOk = output.ok !== undefined
  const hasCypher = output.cypher !== undefined
  const rowCount: number | null = typeof output.rowcount === 'number' 
    ? output.rowcount 
    : Array.isArray(output.rows) 
      ? output.rows.length 
      : null
  
  return (
    <div className="mt-2 space-y-2">
      {/* Quick status indicator for tool outputs */}
      {isOk && (
        <div className={cn(
          "inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium",
          output.ok ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
        )}>
          {output.ok ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
          {output.ok ? 'Success' : 'Failed'}
          {rowCount !== null && <span className="ml-1">• {String(rowCount)} rows</span>}
        </div>
      )}
      
      {/* Cypher query display */}
      {hasCypher && (
        <div className="p-2 bg-neutral-800 text-neutral-100 rounded text-xs font-mono overflow-x-auto">
          <div className="flex items-center gap-1 text-neutral-400 mb-1">
            <Code className="w-3 h-3" />
            <span>Cypher Query</span>
          </div>
          {String(output.cypher)}
        </div>
      )}
      
      {/* Text content */}
      {textContent && (
        <div className="text-sm text-neutral-700 whitespace-pre-wrap">
          {textContent}
        </div>
      )}
      
      {/* Expandable JSON for complex outputs */}
      {hasOtherFields && !textContent && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-700"
        >
          {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          {isExpanded ? 'Hide details' : 'Show details'}
        </button>
      )}
      
      {isExpanded && hasOtherFields && (
        <pre className="p-2 bg-neutral-50 border border-neutral-200 rounded text-xs overflow-x-auto max-h-64 overflow-y-auto">
          {formatOutputValue(output, 2000)}
        </pre>
      )}
    </div>
  )
}

// Single orchestration step component
function StepItem({ step, index, isLast, isRunning }: { step: MergedStep; index: number; isLast: boolean; isRunning: boolean }) {
  const stepTitle = step.action || step.step_id || 'Step'
  const isInProgress = isLast && isRunning && !step.output && !step.error
  
  // Format latency nicely
  const latencyDisplay = step.latency_ms !== undefined 
    ? step.latency_ms >= 1000 
      ? `${(step.latency_ms / 1000).toFixed(1)}s`
      : `${step.latency_ms}ms`
    : null
  
  return (
    <div className="py-2">
      <div className="flex items-start gap-2">
        <div className="mt-0.5">
          {isInProgress ? (
            <Loader2 className="w-4 h-4 text-blue-500 animate-spin flex-shrink-0" />
          ) : (
            <StepStatusIcon step={step} />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-neutral-700">
              {stepTitle}
            </span>
            {isInProgress && <LoadingDots />}
            {latencyDisplay && (
              <span className="text-xs text-neutral-400 bg-neutral-100 px-1.5 py-0.5 rounded">
                {latencyDisplay}
              </span>
            )}
          </div>
          
          {/* Step output */}
          <StepOutput output={step.output} error={step.error} />
        </div>
      </div>
    </div>
  )
}

// Agent run response component
function AgentResponse({ run }: { run: AgentRun }) {
  const isRunning = run.status === 'queued' || run.status === 'running'
  const isSucceeded = run.status === 'succeeded'
  const isFailed = run.status === 'failed'
  
  // Merge steps and outputs
  const mergedSteps = useMemo(() => mergeStepsAndOutputs(run.steps), [run.steps])
  const finalOutput = useMemo(() => getFinalOutput(run.steps), [run.steps])
  
  // Extract final answer - check multiple sources
  let finalAnswer: string | null = null
  
  // 1. First try the final-output from steps
  if (finalOutput) {
    finalAnswer = extractOutputText(finalOutput)
  }
  
  // 2. Then try run.output
  if (!finalAnswer && run.output) {
    if (typeof run.output === 'string') {
      finalAnswer = run.output
    } else if (typeof run.output === 'object') {
      finalAnswer = extractOutputText(run.output as Record<string, unknown>)
      if (!finalAnswer) {
        // Last resort: JSON stringify if no text field found
        const out = run.output as Record<string, unknown>
        if (Object.keys(out).length > 0) {
          finalAnswer = formatOutputValue(out, 1000)
        }
      }
    }
  }
  
  // Calculate total time
  const totalTime = run.latency_ms 
    ? `${(run.latency_ms / 1000).toFixed(1)}s`
    : run.metrics?.overall_ms 
      ? `${(run.metrics.overall_ms / 1000).toFixed(1)}s`
      : null
  
  return (
    <div className="space-y-3">
      {/* Status indicator */}
      <div className="flex items-center gap-2 flex-wrap">
        {isRunning && (
          <>
            <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
            <span className="text-sm text-blue-600 font-medium">
              {run.status === 'queued' ? 'Queued' : 'Processing'}...
            </span>
          </>
        )}
        {isSucceeded && (
          <>
            <CheckCircle2 className="w-4 h-4 text-green-500" />
            <span className="text-sm text-green-600 font-medium">Completed</span>
            {totalTime && (
              <span className="text-xs text-neutral-400 bg-neutral-100 px-2 py-0.5 rounded">
                {totalTime}
              </span>
            )}
          </>
        )}
        {isFailed && (
          <>
            <XCircle className="w-4 h-4 text-red-500" />
            <span className="text-sm text-red-600 font-medium">Failed</span>
          </>
        )}
      </div>
      
      {/* Steps list - collapsible */}
      {mergedSteps.length > 0 && (
        <StepsSection steps={mergedSteps} isRunning={isRunning} />
      )}
      
      {/* TODOs progress */}
      {run.todos && run.todos.length > 0 && (
        <div className="text-sm text-neutral-500 flex items-center gap-2">
          <FileText className="w-4 h-4" />
          {run.todos.filter(t => t.status === 'completed').length}/{run.todos.length} tasks completed
        </div>
      )}
      
      {/* Errors */}
      {run.errors && run.errors.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-md p-3">
          {run.errors.map((error, i) => (
            <p key={`error-${i}`} className="text-sm text-red-600">{error}</p>
          ))}
        </div>
      )}
      
      {/* Final answer */}
      {finalAnswer && (
        <div className="mt-4 pt-4 border-t border-neutral-200">
          <div className="prose prose-neutral prose-sm max-w-none">
            <p className="text-neutral-800 whitespace-pre-wrap leading-relaxed">{finalAnswer}</p>
          </div>
        </div>
      )}
    </div>
  )
}

// Collapsible steps section
function StepsSection({ steps, isRunning }: { steps: MergedStep[]; isRunning: boolean }) {
  const [isExpanded, setIsExpanded] = React.useState(true)
  
  return (
    <div className="border border-neutral-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3 bg-neutral-50 hover:bg-neutral-100 transition-colors"
      >
        <span className="text-sm font-medium text-neutral-600">
          Execution Steps ({steps.length})
        </span>
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-neutral-400" />
        ) : (
          <ChevronRight className="w-4 h-4 text-neutral-400" />
        )}
      </button>
      
      {isExpanded && (
        <div className="border-t border-neutral-200 divide-y divide-neutral-100">
          {steps.map((step, index) => (
            <div key={`step-${index}-${step.step_id}`} className="px-3">
              <StepItem 
                step={step}
                index={index}
                isLast={index === steps.length - 1}
                isRunning={isRunning}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Single chat message component
function ChatMessageItem({ message }: { message: ChatMessage }) {
  const isUser = message.type === 'user'
  
  return (
    <div className={cn(
      'flex gap-3 py-4',
      isUser ? 'flex-row' : 'flex-row'
    )}>
      {/* Avatar */}
      <div className={cn(
        'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
        isUser ? 'bg-neutral-900 text-white' : 'bg-neutral-100 text-neutral-600'
      )}>
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>
      
      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-sm text-neutral-700">
            {isUser ? 'You' : 'Agent'}
          </span>
          <span className="text-xs text-neutral-400">
            {message.timestamp.toLocaleTimeString()}
          </span>
        </div>
        
        {isUser ? (
          <p className="text-neutral-800 whitespace-pre-wrap">{message.content}</p>
        ) : message.run ? (
          <AgentResponse run={message.run} />
        ) : (
          <p className="text-neutral-500">Processing...</p>
        )}
      </div>
    </div>
  )
}

// Empty state component
function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      <div className="w-16 h-16 bg-neutral-100 rounded-full flex items-center justify-center mb-4">
        <Bot className="w-8 h-8 text-neutral-400" />
      </div>
      <h3 className="text-lg font-medium text-neutral-700 mb-2">
        Cineca Agent
      </h3>
      <p className="text-neutral-500 max-w-md">
        Select a role above and send a message to start a conversation with the AI agent.
      </p>
    </div>
  )
}

export function ChatArea({ className }: ChatAreaProps) {
  const { messages, shouldAutoScroll, setShouldAutoScroll } = useChat()
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const isUserScrollingRef = useRef(false)
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  
  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (shouldAutoScroll && messagesEndRef.current && scrollContainerRef.current) {
      // Use scrollTop instead of scrollIntoView to prevent page jump
      const container = scrollContainerRef.current
      container.scrollTop = container.scrollHeight
    }
  }, [messages, shouldAutoScroll])
  
  // Detect manual scroll to disable auto-scroll
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const container = e.currentTarget
    const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100
    
    // Clear any existing timeout
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current)
    }
    
    // Use a small delay to debounce scroll events
    scrollTimeoutRef.current = setTimeout(() => {
      if (isAtBottom && !shouldAutoScroll) {
        setShouldAutoScroll(true)
      } else if (!isAtBottom && shouldAutoScroll) {
        setShouldAutoScroll(false)
      }
    }, 50)
  }
  
  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current)
      }
    }
  }, [])
  
  if (messages.length === 0) {
    return (
      <div className={cn('flex-1 overflow-hidden', className)}>
        <EmptyState />
      </div>
    )
  }
  
  return (
    <div 
      ref={scrollContainerRef}
      onScroll={handleScroll}
      className={cn(
        'flex-1 overflow-y-auto scrollbar-thin px-4 sm:px-6',
        className
      )}
    >
      <div className="max-w-3xl mx-auto divide-y divide-neutral-100">
        {messages.map((message) => (
          <div key={message.id}>
            <ChatMessageItem message={message} />
          </div>
        ))}
        {/* Invisible element at the end to scroll to */}
        <div ref={messagesEndRef} className="h-px" />
      </div>
    </div>
  )
}
