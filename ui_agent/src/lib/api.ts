/**
 * API client for interacting with the Cineca Agentic Platform backend.
 * 
 * Provides:
 * - Agent run creation (POST /v1/agent-runs)
 * - Run status polling (GET /v1/agent-runs/{id})
 * - Model listing (GET /v1/models/instances)
 */

import { AgentRun } from '@/stores/chat-store'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

interface CreateRunRequest {
  prompt: string
  temperature?: number
  max_steps?: number
  metadata?: Record<string, unknown>
}

interface CreateRunResponse extends AgentRun {}

interface ListModelsResponse {
  items: Array<{
    id: string
    instance_name: string
    model_id: string
    provider_id: string
    enabled: boolean
    loaded: boolean
  }>
  total: number
  etag?: string
  next_page_token?: string
}

interface GetDefaultModelResponse {
  chat: {
    instance_id: string
    name: string
    provider_id: string
    model_id: string
  }
  etag?: string
}

class ApiError extends Error {
  status: number
  detail?: string
  
  constructor(message: string, status: number, detail?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function fetchWithAuth(
  url: string,
  options: RequestInit,
  token: string | null
): Promise<Response> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  
  const response = await fetch(url, {
    ...options,
    headers,
  })
  
  if (!response.ok) {
    let detail: string | undefined
    try {
      const body = await response.json()
      detail = body.detail || body.message || JSON.stringify(body)
    } catch {
      detail = response.statusText
    }
    throw new ApiError(
      `API request failed: ${response.status}`,
      response.status,
      detail
    )
  }
  
  return response
}

/**
 * Create a new agent run.
 * Returns immediately with status='queued', then poll for completion.
 */
export async function createAgentRun(
  request: CreateRunRequest,
  token: string | null
): Promise<CreateRunResponse> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/v1/agent-runs`,
    {
      method: 'POST',
      body: JSON.stringify({
        prompt: request.prompt,
        temperature: request.temperature ?? 0.2,
        max_steps: request.max_steps ?? 8,
        metadata: request.metadata ?? {},
      }),
    },
    token
  )
  
  return response.json()
}

/**
 * Get agent run details by ID.
 * Use for polling until status is 'succeeded' | 'failed' | 'cancelled'.
 */
export async function getAgentRun(
  runId: string,
  token: string | null
): Promise<AgentRun> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/v1/agent-runs/${runId}`,
    { method: 'GET' },
    token
  )
  
  return response.json()
}

/**
 * Get execution steps for an agent run.
 */
export async function getAgentRunSteps(
  runId: string,
  token: string | null
): Promise<Array<Record<string, unknown>>> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/v1/agent-runs/${runId}/steps`,
    { method: 'GET' },
    token
  )
  
  return response.json()
}

/**
 * List available model instances.
 */
export async function listModels(
  token: string | null
): Promise<ListModelsResponse> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/v1/models/instances`,
    { method: 'GET' },
    token
  )
  
  return response.json()
}

/**
 * Get the default model with precedence resolution (user → tenant → global).
 * Returns the configured default model from the PostgreSQL database.
 */
export async function getDefaultModel(
  token: string | null
): Promise<GetDefaultModelResponse | null> {
  try {
    const response = await fetchWithAuth(
      `${API_BASE_URL}/v1/models/defaults`,
      { method: 'GET' },
      token
    )
    
    return response.json()
  } catch (error) {
    // 404 means no default configured - return null instead of throwing
    if (error instanceof ApiError && error.status === 404) {
      return null
    }
    throw error
  }
}

/**
 * Get auth info for current token (for debugging).
 */
export async function getAuthMe(
  token: string | null
): Promise<Record<string, unknown>> {
  const response = await fetchWithAuth(
    `${API_BASE_URL}/v1/auth/me`,
    { method: 'GET' },
    token
  )
  
  return response.json()
}

/**
 * Poll run status until completion.
 * 
 * @param runId - Run ID to poll
 * @param token - Auth token
 * @param onUpdate - Callback for each poll update
 * @param intervalMs - Polling interval (default 2000ms)
 * @param maxAttempts - Max polling attempts (default 300 = 10 minutes)
 */
export async function pollRunUntilComplete(
  runId: string,
  token: string | null,
  onUpdate: (run: AgentRun) => void,
  intervalMs: number = 2000,
  maxAttempts: number = 300
): Promise<AgentRun> {
  let attempts = 0
  
  while (attempts < maxAttempts) {
    const run = await getAgentRun(runId, token)
    onUpdate(run)
    
    // Check if run is complete
    if (['succeeded', 'failed', 'cancelled'].includes(run.status)) {
      return run
    }
    
    // Wait before next poll
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
    attempts++
  }
  
  throw new Error(`Polling timed out after ${maxAttempts} attempts`)
}

export { ApiError }
