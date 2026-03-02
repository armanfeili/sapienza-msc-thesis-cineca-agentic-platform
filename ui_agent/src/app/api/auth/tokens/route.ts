/**
 * API route to dynamically generate Auth0 tokens.
 * 
 * This route generates fresh Auth0 tokens using the Password Realm Grant,
 * similar to how fetch_auth0_tokens.sh works. Each time Admin or User
 * role is selected, a fresh token is generated.
 * 
 * Environment variables required in .env.local:
 * - AUTH0_DOMAIN (e.g., cineca.eu.auth0.com)
 * - AUTH0_AUDIENCE (e.g., api://cineca-agentic-platform)
 * - AUTH0_USER_CLIENT_ID
 * - AUTH0_USER_CLIENT_SECRET
 * - AUTH0_ADMIN_USERNAME / AUTH0_ADMIN_PASSWORD
 * - AUTH0_USER_USERNAME / AUTH0_USER_PASSWORD
 */
import { NextRequest, NextResponse } from 'next/server'

interface Auth0TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  scope?: string
}

interface Auth0ErrorResponse {
  error: string
  error_description?: string
}

type TokenRole = 'admin' | 'user'

async function fetchAuth0Token(role: TokenRole): Promise<string> {
  const domain = process.env.AUTH0_DOMAIN
  const audience = process.env.AUTH0_AUDIENCE
  const clientId = process.env.AUTH0_USER_CLIENT_ID
  const clientSecret = process.env.AUTH0_USER_CLIENT_SECRET
  
  // Get credentials based on role
  const username = role === 'admin' 
    ? process.env.AUTH0_ADMIN_USERNAME 
    : process.env.AUTH0_USER_USERNAME
  const password = role === 'admin' 
    ? process.env.AUTH0_ADMIN_PASSWORD 
    : process.env.AUTH0_USER_PASSWORD
  
  // Scopes based on role
  const scopes = role === 'admin' 
    ? 'user:me tools:invoke:all admin:all'
    : 'user:me tools:invoke:basic'
  
  // Validate required config
  if (!domain || !audience || !clientId || !clientSecret || !username || !password) {
    const missing = []
    if (!domain) missing.push('AUTH0_DOMAIN')
    if (!audience) missing.push('AUTH0_AUDIENCE')
    if (!clientId) missing.push('AUTH0_USER_CLIENT_ID')
    if (!clientSecret) missing.push('AUTH0_USER_CLIENT_SECRET')
    if (!username) missing.push(role === 'admin' ? 'AUTH0_ADMIN_USERNAME' : 'AUTH0_USER_USERNAME')
    if (!password) missing.push(role === 'admin' ? 'AUTH0_ADMIN_PASSWORD' : 'AUTH0_USER_PASSWORD')
    throw new Error(`Missing Auth0 configuration: ${missing.join(', ')}`)
  }
  
  // Request token using Password Realm Grant
  const response = await fetch(`https://${domain}/oauth/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      grant_type: 'password',
      username,
      password,
      audience,
      scope: scopes,
      client_id: clientId,
      client_secret: clientSecret,
    }),
  })
  
  const data = await response.json() as Auth0TokenResponse | Auth0ErrorResponse
  
  if (!response.ok || 'error' in data) {
    const errorData = data as Auth0ErrorResponse
    throw new Error(errorData.error_description || errorData.error || 'Failed to fetch token')
  }
  
  const tokenData = data as Auth0TokenResponse
  return tokenData.access_token
}

// Cache tokens in memory with expiration
const tokenCache: Record<string, { token: string; expiresAt: number }> = {}
const TOKEN_CACHE_DURATION = 10 * 60 * 1000 // 10 minutes (tokens last 24h but we refresh more often)

async function getToken(role: TokenRole, forceRefresh = false): Promise<string> {
  const cacheKey = role
  const now = Date.now()
  
  // Return cached token if valid and not forcing refresh
  if (!forceRefresh && tokenCache[cacheKey] && tokenCache[cacheKey].expiresAt > now) {
    return tokenCache[cacheKey].token
  }
  
  // Fetch new token
  const token = await fetchAuth0Token(role)
  
  // Cache the token
  tokenCache[cacheKey] = {
    token,
    expiresAt: now + TOKEN_CACHE_DURATION,
  }
  
  return token
}

// GET: Fetch both admin and user tokens
export async function GET() {
  try {
    // Check if Auth0 is configured
    const domain = process.env.AUTH0_DOMAIN
    if (!domain) {
      return NextResponse.json(
        { 
          error: 'Auth0 is not configured. Please set AUTH0_* variables in .env.local',
          hasTokens: false 
        },
        { status: 503 }
      )
    }
    
    // Fetch both tokens
    const [adminToken, userToken] = await Promise.all([
      getToken('admin'),
      getToken('user'),
    ])
    
    return NextResponse.json({
      hasTokens: true,
      admin: adminToken,
      user: userToken,
    })
  } catch (error) {
    console.error('Error fetching tokens:', error)
    return NextResponse.json(
      { 
        error: error instanceof Error ? error.message : 'Failed to fetch tokens',
        hasTokens: false 
      },
      { status: 500 }
    )
  }
}

// POST: Generate a fresh token for a specific role
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const role = body.role as TokenRole
    const forceRefresh = body.forceRefresh ?? true // Default to fresh token
    
    if (!role || (role !== 'admin' && role !== 'user')) {
      return NextResponse.json(
        { error: 'Invalid role. Must be "admin" or "user"' },
        { status: 400 }
      )
    }
    
    const token = await getToken(role, forceRefresh)
    
    return NextResponse.json({
      success: true,
      role,
      token,
    })
  } catch (error) {
    console.error('Error generating token:', error)
    return NextResponse.json(
      { 
        error: error instanceof Error ? error.message : 'Failed to generate token',
        success: false 
      },
      { status: 500 }
    )
  }
}
