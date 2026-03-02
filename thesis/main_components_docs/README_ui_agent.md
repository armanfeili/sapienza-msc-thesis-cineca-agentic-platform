# README_Cineca-Agentic-Platform_ui_agent.md

## Overview

The `ui_agent` is a modern Next.js 14 web application that serves as the chat interface for the Cineca Agentic Platform. It provides a user-friendly frontend for interacting with AI agents, managing authentication roles, and visualizing agent execution results including orchestration steps, metrics, and outputs.

### Key Features

- **Role-based Authentication**: Support for Admin and User roles with dynamic Auth0 token generation
- **Real-time Chat Interface**: Interactive chat with AI agents featuring live status updates
- **Agent Run Visualization**: Detailed display of agent execution steps, metrics, and outputs
- **Model Selection**: Dynamic model selection from available backend models
- **Responsive Design**: Modern UI built with Tailwind CSS and Radix UI components
- **Type-Safe Development**: Full TypeScript implementation with strict configuration
- **State Management**: Zustand stores for authentication and chat state management
- **SSR-Safe**: Server-side rendering compatible with proper hydration handling

### Technology Stack

- **Framework**: Next.js 14.2.15 (React 18.3.1)
- **Language**: TypeScript 5.6.3
- **Styling**: Tailwind CSS 3.4.14 with custom design system
- **State Management**: Zustand 4.5.5
- **UI Components**: Radix UI primitives with shadcn/ui
- **Icons**: Lucide React 0.451.0
- **Development Tools**: ESLint, PostCSS, Next.js built-in tools

## Architecture

### Application Structure

The application follows Next.js 14 App Router architecture with a clean separation of concerns:

```
src/
├── app/                    # Next.js App Router pages
│   ├── layout.tsx         # Root layout with font and basic structure
│   ├── page.tsx           # Main chat interface page
│   └── globals.css        # Global Tailwind styles and custom CSS
├── components/            # React components
│   ├── chat-area.tsx      # Main chat display component
│   ├── chat-input.tsx     # Message input and model selection
│   ├── role-toggle.tsx    # Authentication role switcher
│   └── ui/               # Reusable UI components (shadcn/ui)
├── lib/                  # Utility libraries
│   ├── api.ts            # API client and TypeScript interfaces
│   └── utils.ts          # Utility functions (cn for class merging)
└── stores/               # Zustand state management
    ├── auth-store.ts     # Authentication state and token management
    └── chat-store.ts     # Chat messages and agent run state
```

### Component Architecture

The application uses a component-based architecture with clear separation of responsibilities:

1. **Page Components** (`src/app/`): Route-level components following Next.js App Router
2. **Feature Components** (`src/components/`): Business logic components (chat-area, chat-input, role-toggle)
3. **UI Components** (`src/components/ui/`): Reusable design system components
4. **State Management**: Centralized stores for auth and chat state
5. **API Layer**: Centralized API client with TypeScript interfaces

### State Management

The application uses Zustand for state management with two main stores:

#### Auth Store (`auth-store.ts`)
- **Purpose**: Manages user authentication state and token handling
- **Features**:
  - Role selection (admin/user)
  - Dynamic token generation from Auth0
  - SSR-safe hydration
  - Persistent storage with localStorage
  - Token refresh and error handling

#### Chat Store (`chat-store.ts`)
- **Purpose**: Manages chat messages and agent run state
- **Features**:
  - Message history management
  - Agent run tracking with real-time updates
  - Model selection and available models list
  - Loading states for submission and polling
  - Auto-scroll functionality

## Components

### Core Components

#### ChatArea (`chat-area.tsx`)
**Purpose**: Main chat display component handling message rendering and agent run visualization.

**Key Features**:
- Message display with user/agent differentiation
- Agent run status indicators (queued, running, succeeded, failed, cancelled)
- Collapsible orchestration steps with JSON output
- Execution metrics display (latency, token usage, tool calls)
- Todo items tracking with status indicators
- Auto-scroll to latest messages
- Error display and handling

**Props**: None (uses Zustand stores)

**State Dependencies**:
- `useChatStore`: messages, currentRunId, isPolling, shouldAutoScroll
- `useAuthStore`: getActiveToken()

**Rendering Logic**:
- Maps through messages array
- For agent messages, displays run status and collapsible details
- Shows orchestration steps as expandable sections
- Displays metrics in formatted tables
- Handles different output types (JSON, string, objects)

#### ChatInput (`chat-input.tsx`)
**Purpose**: Message input component with model selection and submission handling.

**Key Features**:
- Model selection dropdown with available models
- Auto-resizing textarea for message input
- Submit button with loading states
- Real-time polling for agent run completion
- Error handling and display

**Props**: None (uses Zustand stores)

**State Dependencies**:
- `useChatStore`: selectedModel, availableModels, isSubmitting, addUserMessage, addAgentResponse, updateAgentRun, setCurrentRunId, setIsSubmitting, setIsPolling
- `useAuthStore`: getActiveToken()

**Functionality**:
- Fetches available models on mount
- Handles form submission with API calls
- Implements polling mechanism for run status updates
- Updates chat store with new messages and run data

#### RoleToggle (`role-toggle.tsx`)
**Purpose**: Authentication role selection component.

**Key Features**:
- Toggle between Admin and User roles
- Dynamic token generation
- Loading states during authentication
- Error display for authentication failures
- Visual feedback for current role

**Props**: None (uses Zustand stores)

**State Dependencies**:
- `useAuthStore`: role, isLoading, tokenError, signIn, signOut

**Functionality**:
- Displays current authentication status
- Handles role switching with token generation
- Shows loading spinners during auth operations
- Displays error messages for failed authentications

### UI Components (`src/components/ui/`)

The application uses shadcn/ui components built on Radix UI primitives:

#### Button (`button.tsx`)
- Variants: default, destructive, outline, secondary, ghost, link
- Sizes: default, sm, lg, icon
- Built on Radix UI Button primitive

#### Select (`select.tsx`)
- Single selection dropdown
- Built on Radix UI Select primitive
- Supports custom trigger and content

#### Textarea (`textarea.tsx`)
- Auto-resizing textarea component
- Built on native textarea with custom styling

#### Toggle (`toggle.tsx`)
- Toggle button component
- Built on Radix UI Toggle primitive

#### ToggleGroup (`toggle-group.tsx`)
- Group of toggle buttons
- Single and multiple selection modes
- Built on Radix UI ToggleGroup primitive

## State Management

### Auth Store Details

**Interface**:
```typescript
interface AuthState {
  role: Role
  adminToken: string | null
  userToken: string | null
  isLoading: boolean
  hasHydrated: boolean
  tokensFetched: boolean
  tokenError: string | null
  // Actions...
}
```

**Key Methods**:
- `setRole(role: Role)`: Update current role
- `signIn(role: 'admin' | 'user')`: Authenticate with role and generate token
- `signOut()`: Clear authentication
- `getActiveToken()`: Get current role's token
- `fetchTokens()`: Load tokens from server
- `generateToken(role)`: Generate fresh token for role

**Persistence**:
- Uses Zustand persist middleware
- Stores role in localStorage
- Tokens not persisted for security (fetched fresh)
- SSR-safe with custom storage implementation

### Chat Store Details

**Interface**:
```typescript
interface ChatState {
  messages: ChatMessage[]
  selectedModel: string
  availableModels: Array<{ id: string; name: string }>
  currentRunId: string | null
  isSubmitting: boolean
  isPolling: boolean
  shouldAutoScroll: boolean
  // Actions...
}
```

**Key Methods**:
- `addUserMessage(content: string)`: Add user message to chat
- `addAgentResponse(messageId, run)`: Add agent response with run data
- `updateAgentRun(messageId, run)`: Update existing run data
- `setSelectedModel(model)`: Update selected model
- `setAvailableModels(models)`: Update available models list
- `clearMessages()`: Clear chat history

## API Integration

### API Client (`api.ts`)

The application communicates with the Cineca Agentic Platform backend through a comprehensive API client.

**Base Configuration**:
```typescript
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
```

**Core Interfaces**:

#### Agent Run Types
```typescript
interface CreateRunRequest {
  prompt: string
  model?: string
  session_id?: string
}

interface CreateRunResponse {
  run_id: string
  status: string
}

interface AgentRun {
  run_id: string
  session_id?: string
  user_id: string
  tenant_id: string
  model?: string
  manager?: string
  status: RunStatus
  started_at: string
  finished_at?: string
  output?: Record<string, unknown> | string | null
  steps?: OrchestrationStep[]
  todos?: TodoItem[]
  metrics?: ExecutionMetrics
  errors?: string[]
}
```

#### Model Types
```typescript
interface ListModelsResponse {
  models: Array<{ id: string; name: string }>
}

interface GetDefaultModelResponse {
  model: string
}
```

#### Orchestration Types
```typescript
interface OrchestrationStep {
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

interface TodoItem {
  task: string
  status?: 'pending' | 'in_progress' | 'completed' | 'failed'
  evidence?: string[]
}

interface ExecutionMetrics {
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
```

**API Methods**:

#### Agent Run Operations
- `createAgentRun(request, token)`: Create new agent run
- `getAgentRun(runId, token)`: Get run details
- `getAgentRunSteps(runId, token)`: Get run orchestration steps

#### Model Operations
- `listModels(token)`: Get available models
- `getDefaultModel(token)`: Get default model

#### Authentication
- `getAuthMe(token)`: Get current user info

#### Polling Utility
- `pollRunUntilComplete(runId, token, onUpdate, intervalMs, maxAttempts)`: Poll run status until completion

**Error Handling**:
```typescript
class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}
```

All API calls include proper error handling, token authentication, and TypeScript typing.

## Configuration

### Next.js Configuration (`next.config.js`)

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
}

module.exports = nextConfig
```

### TypeScript Configuration (`tsconfig.json`)

```json
{
  "compilerOptions": {
    "lib": ["dom", "dom.iterable", "es6"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

### Tailwind Configuration (`tailwind.config.ts`)

```typescript
import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: ['class'],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  prefix: '',
  theme: {
    container: {
      center: true,
      padding: '2rem',
      screens: {
        '2xl': '1400px',
      },
    },
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}

export default config
```

### ESLint Configuration (`.eslintrc.json`)

```json
{
  "extends": ["next/core-web-vitals"]
}
```

### PostCSS Configuration (`postcss.config.js`)

```javascript
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

## Development Setup

### Prerequisites

- Node.js 18+
- npm or yarn
- Backend API running on `http://localhost:8000`

### Installation

1. **Clone and navigate to ui_agent directory**:
   ```bash
   cd ui_agent
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Configure environment variables**:
   ```bash
   cp .env.example .env.local
   ```

   Edit `.env.local` with appropriate values.

4. **Start development server**:
   ```bash
   npm run dev
   ```

   The application will be available at `http://localhost:3001`.

### Environment Variables

Create a `.env.local` file with the following variables:

```env
# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:8000

# Auth0 Configuration (for token generation)
AUTH0_DOMAIN=your-auth0-domain.auth0.com
AUTH0_CLIENT_ID=your-client-id
AUTH0_CLIENT_SECRET=your-client-secret
AUTH0_AUDIENCE=your-api-audience

# Admin User Credentials
AUTH0_ADMIN_USERNAME=admin@example.com
AUTH0_ADMIN_PASSWORD=admin-password

# Regular User Credentials
AUTH0_USER_USERNAME=user@example.com
AUTH0_USER_PASSWORD=user-password
```

### Available Scripts

```json
{
  "scripts": {
    "dev": "next dev -p 3001",
    "build": "next build",
    "start": "next start -p 3001",
    "lint": "next lint"
  }
}
```

## Usage

### Authentication

1. **Select Role**: Use the role toggle in the header to switch between Admin and User roles.
2. **Automatic Token Generation**: Tokens are generated dynamically when switching roles.
3. **Token Management**: Tokens are managed server-side and refreshed as needed.

### Chat Interface

1. **Select Model**: Choose from available models in the dropdown.
2. **Enter Prompt**: Type your message in the textarea.
3. **Submit**: Click the send button or press Enter.
4. **Monitor Progress**: Watch real-time status updates and orchestration steps.
5. **View Results**: Expand sections to see detailed outputs, metrics, and todos.

### Features

- **Real-time Updates**: Agent runs update in real-time with polling.
- **Collapsible Details**: Click to expand/collapse orchestration steps and outputs.
- **Auto-scroll**: Chat automatically scrolls to show latest messages.
- **Error Handling**: Clear error messages for failed operations.
- **Responsive Design**: Works on desktop and mobile devices.

## File Structure

```
ui_agent/
├── .env.example              # Environment variables template
├── .env.local               # Local environment variables (gitignored)
├── .eslintrc.json           # ESLint configuration
├── next.config.js           # Next.js configuration
├── package.json             # Dependencies and scripts
├── postcss.config.js        # PostCSS configuration
├── tailwind.config.ts       # Tailwind CSS configuration
├── tsconfig.json            # TypeScript configuration
└── src/
    ├── app/
    │   ├── globals.css      # Global styles and CSS variables
    │   ├── layout.tsx       # Root layout component
    │   └── page.tsx         # Main chat page
    ├── components/
    │   ├── chat-area.tsx    # Chat display component
    │   ├── chat-input.tsx   # Message input component
    │   ├── role-toggle.tsx  # Role selection component
    │   └── ui/              # Reusable UI components
    │       ├── button.tsx
    │       ├── select.tsx
    │       ├── textarea.tsx
    │       ├── toggle.tsx
    │       └── toggle-group.tsx
    ├── lib/
    │   ├── api.ts           # API client and interfaces
    │   └── utils.ts         # Utility functions
    └── stores/
        ├── auth-store.ts     # Authentication state management
        └── chat-store.ts     # Chat state management
```

## Dependencies

### Core Dependencies

```json
{
  "next": "14.2.15",
  "react": "^18.3.1",
  "react-dom": "^18.3.1",
  "typescript": "^5.6.3",
  "tailwindcss": "^3.4.14",
  "zustand": "^4.5.5"
}
```

### UI Libraries

```json
{
  "@radix-ui/react-select": "^2.1.2",
  "@radix-ui/react-toggle": "^1.1.0",
  "@radix-ui/react-toggle-group": "^1.1.0",
  "lucide-react": "^0.451.0",
  "tailwindcss-animate": "^1.0.7"
}
```

### Development Dependencies

```json
{
  "@types/node": "^20",
  "@types/react": "^18",
  "@types/react-dom": "^18",
  "autoprefixer": "^10.0.1",
  "eslint": "^8",
  "eslint-config-next": "14.2.15",
  "postcss": "^8",
  "tailwind-merge": "^2.5.4"
}
```

## Environment Variables

### Required Variables

- `NEXT_PUBLIC_API_URL`: Backend API base URL (default: `http://localhost:8000`)

### Auth0 Configuration (for token generation)

- `AUTH0_DOMAIN`: Auth0 domain
- `AUTH0_CLIENT_ID`: Auth0 client ID
- `AUTH0_CLIENT_SECRET`: Auth0 client secret
- `AUTH0_AUDIENCE`: Auth0 API audience
- `AUTH0_ADMIN_USERNAME`: Admin user email
- `AUTH0_ADMIN_PASSWORD`: Admin user password
- `AUTH0_USER_USERNAME`: Regular user email
- `AUTH0_USER_PASSWORD`: Regular user password

## Build and Deployment

### Build Process

1. **Install dependencies**:
   ```bash
   npm ci
   ```

2. **Build application**:
   ```bash
   npm run build
   ```

3. **Start production server**:
   ```bash
   npm start
   ```

### Docker Deployment

The application can be containerized using the provided Dockerfile in the root directory.

### Environment Setup

Ensure the backend API is running and accessible at the configured `NEXT_PUBLIC_API_URL`.

## Testing

### Current Testing Status

The ui_agent currently does not have a comprehensive test suite. Future development should include:

- **Unit Tests**: Component testing with React Testing Library
- **Integration Tests**: API integration and state management testing
- **E2E Tests**: Playwright tests for critical user flows

### Recommended Testing Strategy

1. **Component Testing**: Test individual components with mocked stores
2. **Store Testing**: Test Zustand stores and state transitions
3. **API Testing**: Mock API calls and test error handling
4. **E2E Testing**: Test complete user flows from authentication to chat completion

## Troubleshooting

### Common Issues

#### Authentication Problems

**Issue**: "Failed to generate token"
- **Cause**: Auth0 configuration incorrect or backend not running
- **Solution**: Check Auth0 credentials and ensure backend `/api/auth/tokens` endpoint is accessible

**Issue**: Role toggle not working
- **Cause**: Hydration mismatch or store not initialized
- **Solution**: Check browser console for hydration errors, ensure SSR-safe code

#### Chat Issues

**Issue**: Messages not sending
- **Cause**: API URL incorrect or backend not responding
- **Solution**: Verify `NEXT_PUBLIC_API_URL` and check backend logs

**Issue**: Polling not updating
- **Cause**: Network issues or run status not changing
- **Solution**: Check network tab, verify run ID is correct

#### UI Issues

**Issue**: Components not rendering
- **Cause**: Missing CSS variables or Tailwind not loading
- **Solution**: Check `globals.css` and ensure Tailwind is properly configured

**Issue**: Auto-scroll not working
- **Cause**: Component ref issues or state not updating
- **Solution**: Check chat store state and component refs

### Development Tips

1. **Use React DevTools** to inspect component state and props
2. **Check browser Network tab** for API call failures
3. **Use Zustand devtools** for state debugging
4. **Enable React strict mode** for development warnings
5. **Test with different screen sizes** for responsive design

### Performance Considerations

- **Polling Optimization**: Consider WebSocket connection for real-time updates instead of polling
- **Bundle Size**: Monitor bundle size with `npm run build --analyze`
- **Image Optimization**: Use Next.js Image component for any future images
- **Code Splitting**: Implement route-based code splitting for better performance

## Security Considerations

### Token Management

- Tokens are not stored in localStorage for security
- Fresh tokens generated on each role switch
- Server-side token generation prevents client-side exposure

### API Security

- All API calls include authentication headers
- Error responses don't expose sensitive information
- CORS configuration handled by backend

### Environment Variables

- Sensitive Auth0 credentials stored securely
- Public API URL exposed to client safely
- No secrets committed to version control

## Future Enhancements

### Planned Features

1. **WebSocket Integration**: Replace polling with real-time WebSocket updates
2. **Chat History Persistence**: Save chat sessions to backend
3. **File Upload Support**: Allow file attachments in chat
4. **Voice Input**: Speech-to-text functionality
5. **Multi-language Support**: Internationalization (i18n)
6. **Dark/Light Theme Toggle**: Complete theme system
7. **Offline Support**: Service worker for offline functionality
8. **Push Notifications**: Browser notifications for completed runs

### Technical Improvements

1. **Testing Suite**: Comprehensive unit and integration tests
2. **Error Boundaries**: React error boundaries for better error handling
3. **Performance Monitoring**: Real user monitoring and analytics
4. **Accessibility**: WCAG compliance and screen reader support
5. **Progressive Web App**: PWA features for mobile experience
6. **Component Library**: Expand shadcn/ui component usage
7. **State Management**: Consider Redux Toolkit for complex state needs

This comprehensive README provides detailed documentation for the ui_agent component of the Cineca Agentic Platform, covering all aspects from architecture and implementation to deployment and troubleshooting.