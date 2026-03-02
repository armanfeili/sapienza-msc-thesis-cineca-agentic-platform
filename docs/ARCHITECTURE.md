# CINECA AGENTIC PLATFORM — FULL ARCHITECTURE

> **Enterprise-Grade AI Agent Orchestration Platform**  
> Connecting Multi-Tenant Architecture, MCP Tools, and Secure Graph Querying

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [High-Level Architecture Overview](#2-high-level-architecture-overview)
3. [Layer 1: Identity & Authentication](#3-layer-1-identity--authentication)
4. [Layer 2: Security Middleware Stack](#4-layer-2-security-middleware-stack)
5. [Layer 3: API Layer (Routers)](#5-layer-3-api-layer-routers)
6. [Layer 4: Execution Workflows](#6-layer-4-execution-workflows)
7. [Layer 5: Service Layer (Orchestrator)](#7-layer-5-service-layer-orchestrator)
8. [Layer 6: LLM Providers](#8-layer-6-llm-providers)
9. [Layer 7: MCP Runtime & Tools](#9-layer-7-mcp-runtime--tools)
10. [Layer 8: NL-to-Cypher Pipeline](#10-layer-8-nl-to-cypher-pipeline)
11. [Layer 9: Data Layer](#11-layer-9-data-layer)
12. [Layer 10: Adapters](#12-layer-10-adapters)
13. [Layer 11: Resilience Framework](#13-layer-11-resilience-framework)
14. [Layer 12: Background Framework](#14-layer-12-background-framework)
15. [Layer 13: Observability & Monitoring](#15-layer-13-observability--monitoring)
16. [Appendix: Architecture Diagrams](#16-appendix-architecture-diagrams)

---

## 1. Executive Summary

### 1.1 Platform Overview

The **CINECA Agentic Platform** is a production-grade AI agent orchestration system designed to bridge the gap between natural language queries and secure, auditable database operations. It enables researchers and operators to interact with complex graph databases using conversational language while maintaining enterprise-grade security, multi-tenancy, and full compliance auditability.

### 1.2 Key Capabilities

| Capability | Description |
|------------|-------------|
| **NL-to-Cypher** | Translate natural language to validated Cypher queries |
| **Multi-Tenant** | Complete data isolation between organizations |
| **Model-Agnostic** | Switch between OpenAI, Azure, Ollama without code changes |
| **34 MCP Tools** | Extensible tool ecosystem with RBAC enforcement |
| **Full Observability** | OpenTelemetry tracing, Prometheus metrics, Grafana dashboards |
| **Resilience** | Circuit breakers, retries, provider fallback chains |

### 1.3 Platform Statistics

```
┌─────────────────────────────────────────────────────────────┐
│                    PLATFORM SCALE                           │
├─────────────────────────────────────────────────────────────┤
│  76 API Endpoints        │  34 MCP Tools                    │
│  16 FastAPI Routers      │  17 Tool Categories              │
│  3,000+ Automated Tests  │  16+ Infrastructure Components   │
│  ~411,700 Lines of Code  │  3-Database Architecture         │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. High-Level Architecture Overview

### 2.1 Architectural Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL CLIENTS                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │  Agent Chat UI  │  │ Control Panel   │  │   External      │              │
│  │  (Next.js)      │  │ (Streamlit)     │  │   API Clients   │              │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘              │
└───────────┼─────────────────────┼─────────────────────┼─────────────────────┘
            │                     │                     │
            ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LAYER 1: GATEWAY & AUTH                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    NGINX (Reverse Proxy)                              │   │
│  │         TLS Termination │ CORS │ Load Balancing │ Routing            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │              Identity Provider (OIDC / Auth0)                         │   │
│  │       OAuth 2.0 │ JWT Tokens │ JWKS │ Refresh/Revoke                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   LAYER 2: SECURITY MIDDLEWARE                               │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐         │
│  │ CORS   │→│ Trace  │→│ Auth   │→│ Rate   │→│ Tenant │→│ Input  │→        │
│  │Handler │ │Context │ │  JWT   │ │Limiter │ │Resolver│ │ Guard  │         │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘         │
│                                                          ┌────────┐ ┌──────┐│
│                                                          │ Output │→│Error ││
│                                                          │ Guard  │ │Hdlr  ││
│                                                          └────────┘ └──────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LAYER 3: API LAYER                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    FastAPI Routers (76 endpoints)                    │    │
│  │  /v1/health │ /v1/auth │ /v1/agents │ /v1/agent-runs │ /v1/jobs    │    │
│  │  /v1/tools │ /v1/models │ /v1/graph │ /v1/tenants │ /v1/sessions   │    │
│  │  /v1/batch │ /v1/export │ /v1/admin │ /v1/internal                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌───────────────────────────────┐   ┌───────────────────────────────┐
│    WORKFLOW A: Agent Runs     │   │   WORKFLOW B: Long Jobs       │
│  ┌─────────────────────────┐  │   │  ┌─────────────────────────┐  │
│  │   BackgroundTasks       │  │   │  │   Redis Queue           │  │
│  │   (In-Process)          │  │   │  │   + Workers             │  │
│  └─────────────────────────┘  │   │  └─────────────────────────┘  │
└───────────────────────────────┘   └───────────────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     LAYER 5: SERVICE LAYER                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    ORCHESTRATOR SERVICE                              │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │    │
│  │  │ Phase 1  │→ │ Phase 2  │→ │ Phase 3  │→ │ Phase 4  │            │    │
│  │  │ Intent   │  │  TODO    │  │  Step    │  │ Final    │            │    │
│  │  │ Classify │  │ Planning │  │ Execute  │  │ Response │            │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ Session Svc  │ │ Job Service  │ │ Health Svc   │ │ ETL Service  │       │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
┌───────────────────────┐ ┌───────────────────┐ ┌───────────────────────┐
│    LLM PROVIDERS      │ │   MCP TOOLS       │ │   NL→CYPHER           │
│  ┌─────────────────┐  │ │  ┌─────────────┐  │ │  ┌─────────────────┐  │
│  │ Ollama (Local)  │  │ │  │ 34 Tools    │  │ │  │ 6-Stage         │  │
│  │ OpenAI (Cloud)  │  │ │  │ 17 Categs   │  │ │  │ Pipeline        │  │
│  │ Azure OpenAI    │  │ │  │ RBAC Check  │  │ │  │ Validation      │  │
│  └─────────────────┘  │ │  └─────────────┘  │ │  └─────────────────┘  │
└───────────────────────┘ └───────────────────┘ └───────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LAYER 9: DATA LAYER                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │     REDIS       │  │   POSTGRESQL    │  │    MEMGRAPH     │              │
│  │  ═══════════    │  │  ═══════════    │  │  ═══════════    │              │
│  │  Cache          │  │  Durable State  │  │  Graph DB       │              │
│  │  Queues         │  │  Audit Logs     │  │  Bioinformatics │              │
│  │  Rate Limits    │  │  Transactions   │  │  Cypher Queries │              │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     OBSERVABILITY & MONITORING                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │  OpenTelemetry  │  │   Prometheus    │  │    Grafana      │              │
│  │  (Tracing)      │  │   (Metrics)     │  │  (Dashboards)   │              │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Request Flow Summary

```
Client Request
      │
      ▼
┌─────────────────┐
│ NGINX Gateway   │ ──► TLS, Routing, CORS
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Security Stack  │ ──► JWT Auth, RBAC, Rate Limit, Tenant, Guards
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ API Router      │ ──► Endpoint Matching, Request Parsing
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────┐
│Wkflow │ │Wkflow │
│   A   │ │   B   │
│(sync) │ │(async)│
└───┬───┘ └───┬───┘
    │         │
    └────┬────┘
         ▼
┌─────────────────┐
│ Orchestrator    │ ──► Intent → Plan → Execute → Finalize
└────────┬────────┘
         │
    ┌────┼────┬────┐
    ▼    ▼    ▼    ▼
  ┌───┐┌───┐┌───┐┌───┐
  │LLM││MCP││N2C││DBs│
  └───┘└───┘└───┘└───┘
         │
         ▼
┌─────────────────┐
│ Response        │ ──► PII Scrub, Output Guard, Audit Log
└─────────────────┘
```

---

## 3. Layer 1: Identity & Authentication

### 3.1 Identity Provider (OIDC / Auth0)

The platform uses industry-standard OAuth 2.0 / OpenID Connect for authentication.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         IDENTITY PROVIDER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐        ┌──────────────┐        ┌──────────────┐          │
│   │   OAuth 2.0  │        │     JWT      │        │    JWKS      │          │
│   │   Login Flow │───────►│    Tokens    │◄───────│   Endpoint   │          │
│   └──────────────┘        └──────────────┘        └──────────────┘          │
│                                  │                                           │
│                                  ▼                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         JWT Token Claims                             │   │
│   ├─────────────────────────────────────────────────────────────────────┤   │
│   │  sub        │ Unique user identifier                                 │   │
│   │  tenant_id  │ Organization the user belongs to                       │   │
│   │  roles[]    │ admin, operator, user, viewer                          │   │
│   │  scopes[]   │ read, write, graph:read, graph:write, tools:invoke     │   │
│   │  exp        │ Token expiration timestamp                             │   │
│   │  iat        │ Token issued at timestamp                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                      Principal Object                                 │  │
│   │  { sub, tenant_id, roles: [admin|operator|user|viewer],              │  │
│   │    scopes: [user:me, admin:all, tools:invoke:*, graph:*] }           │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 User Interfaces

#### Agent Chat UI (Next.js/React) — Workflow A

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AGENT CHAT UI                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  Technology: Next.js / React                                                 │
│  Purpose: End-user chat interface for AI agent interactions                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Features:                                                                  │
│   ├── JWT-based authentication                                               │
│   ├── SSE streaming support for real-time updates                           │
│   ├── Agent runs & steps visualization                                       │
│   └── Real-time polling for status updates                                   │
│                                                                              │
│   API Call:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  POST /v1/agent-runs                                                 │   │
│   │  Headers: Authorization: Bearer <JWT>                                │   │
│   │  Body: { prompt, model, temperature }                                │   │
│   │  Response: { run_id, status: "queued" }                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Control Panel UI (Streamlit) — Workflow B

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CONTROL PANEL UI                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  Technology: Streamlit                                                       │
│  Purpose: Admin/Operator dashboard for platform management                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Features:                                                                  │
│   ├── Jobs / models / tools management                                       │
│   ├── Graph + NL→Cypher experiments                                         │
│   ├── SSE streaming for job events                                           │
│   └── ETL / backup / maintenance triggers                                    │
│                                                                              │
│   API Call:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  POST /v1/jobs                                                       │   │
│   │  Headers: Authorization: Bearer <JWT>                                │   │
│   │  Body: { type, payload }                                             │   │
│   │  Job Types: demo, test, long-running, agent.run                      │   │
│   │  Response: { id, status, created_at }                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Reverse Proxy / API Gateway (NGINX)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NGINX                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│   │    TLS      │  │   Routing   │  │    CORS     │  │    Load     │        │
│   │ Termination │  │  to Backend │  │  Handling   │  │  Balancing  │        │
│   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                              │
│   Request Flow:                                                              │
│   HTTPS Request → TLS Decrypt → Route Match → Backend Forward               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Layer 2: Security Middleware Stack

Every request passes through **8 security middleware layers** before reaching business logic.

### 4.1 Middleware Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SECURITY MIDDLEWARE PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Request ─┬─► [1] CORS Handler                                              │
│            │        │                                                        │
│            │        ▼                                                        │
│            ├─► [2] Trace Context (OpenTelemetry)                             │
│            │        │                                                        │
│            │        ▼                                                        │
│            ├─► [3] Auth JWT (OIDC + RBAC)                                    │
│            │        │                                                        │
│            │        ▼                                                        │
│            ├─► [4] Rate Limiter (Redis-backed)                               │
│            │        │                                                        │
│            │        ▼                                                        │
│            ├─► [5] Tenant Resolver                                           │
│            │        │                                                        │
│            │        ▼                                                        │
│            ├─► [6] Input Guard (Validation + Sanitization)                   │
│            │        │                                                        │
│            │        ▼                                                        │
│            │   ┌─────────────────┐                                           │
│            │   │ Business Logic  │                                           │
│            │   └─────────────────┘                                           │
│            │        │                                                        │
│            │        ▼                                                        │
│            ├─► [7] Output Guard (PII + Compliance)                           │
│            │        │                                                        │
│            │        ▼                                                        │
│            └─► [8] Error Handler                                             │
│                     │                                                        │
│                     ▼                                                        │
│                Response                                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Middleware Details

#### [1] CORS Handler
```
┌─────────────────────────────────────────────────────────┐
│  CORS Handler                                           │
├─────────────────────────────────────────────────────────┤
│  • Allowed origins configuration                        │
│  • Preflight OPTIONS request handling                   │
│  • Credentials and expose headers support               │
│                                                         │
│  Example:                                               │
│  ✓ https://chat.cineca.it → Allowed                    │
│  ✗ https://malicious-site.com → Blocked                │
└─────────────────────────────────────────────────────────┘
```

#### [2] Trace Context (OpenTelemetry)
```
┌─────────────────────────────────────────────────────────┐
│  Trace Context                                          │
├─────────────────────────────────────────────────────────┤
│  • Injects/extracts W3C trace-context headers           │
│    (traceparent, tracestate)                            │
│  • Creates root span if missing                         │
│  • Propagates existing trace                            │
│  • Adds trace_id, span_id, parent_id to context         │
│                                                         │
│  Example:                                               │
│  trace_id: abc123 follows through API → Orchestrator    │
│  → Memgraph → Response (visible in Grafana)             │
└─────────────────────────────────────────────────────────┘
```

#### [3] Auth JWT with RBAC
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Auth JWT + RBAC                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Validates Bearer token via JWKS endpoint (RS256/RS384/RS512)              │
│  • Extracts claims: sub, tenant_id, roles[], scopes[], exp, iat              │
│  • Builds Principal object for downstream authorization                      │
│  • Rejects expired/invalid/malformed tokens → 401 Unauthorized               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                         RBAC PERMISSION MATRIX                               │
│  ┌──────────┬────────────┬──────┬───────┬─────────┬──────────────┐          │
│  │   Role   │ agent-runs │ jobs │ tools │ tenants │ graph:write  │          │
│  ├──────────┼────────────┼──────┼───────┼─────────┼──────────────┤          │
│  │  admin   │    CRUD    │ CRUD │ CRUD  │  CRUD   │      ✓       │          │
│  │ operator │    CRU     │ CRUD │   R   │    R    │      ✗       │          │
│  │   user   │    CR      │ CRD  │   R   │    ✗    │      ✗       │          │
│  │  viewer  │     R      │  R   │   R   │    ✗    │      ✗       │          │
│  └──────────┴────────────┴──────┴───────┴─────────┴──────────────┘          │
│                                                                              │
│  Example: Viewer tries to delete agent run → 403 Forbidden                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### [4] Rate Limiter
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Rate Limiter (Redis-backed, Multi-dimension)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Rate Limit Keys:                                                           │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  ratelimit:user:{sub}           │ Per-user limits                    │  │
│   │  ratelimit:tenant:{tenant_id}   │ Per-tenant limits                  │  │
│   │  ratelimit:endpoint:{method}:{path} │ Per-endpoint limits            │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│   Response Headers:                                                          │
│   • X-RateLimit-Limit: 100                                                   │
│   • X-RateLimit-Remaining: 45                                                │
│   • X-RateLimit-Reset: 1643723400                                            │
│                                                                              │
│   Exceeded → 429 Too Many Requests                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### [5] Tenant Resolver
```
┌─────────────────────────────────────────────────────────┐
│  Tenant Resolver                                        │
├─────────────────────────────────────────────────────────┤
│  • Resolves tenant config from Redis or PostgreSQL      │
│  • Injects tenant_id filter into all DB queries         │
│  • Enforces complete data isolation                     │
│  • Loads tenant-specific settings                       │
│                                                         │
│  Example:                                               │
│  User from tenant_id: cineca_bioinformatics only       │
│  sees bioinformatics data, never other orgs' data      │
└─────────────────────────────────────────────────────────┘
```

#### [6] Input Guard
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Input Guard (Validation + Sanitization)                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Protections:                                                               │
│   ├── Pydantic schema validation for all request bodies                      │
│   ├── SQL injection detection (DROP TABLE, UNION SELECT)                     │
│   ├── Cypher injection detection (graph DB attacks)                          │
│   ├── Command injection detection (; rm -rf /)                               │
│   ├── Content-type validation                                                │
│   └── Request size limits                                                    │
│                                                                              │
│   Example:                                                                   │
│   Prompt: "; DROP TABLE users;--"                                           │
│   Result: 400 Bad Request (SQL injection detected)                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### [7] Output Guard
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Output Guard (PII + Compliance)                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Protections:                                                               │
│   ├── PII scrubbing (email → [EMAIL REDACTED])                               │
│   ├── Phone masking, SSN removal                                             │
│   ├── Content filtering for sensitive patterns                               │
│   ├── Response size validation and truncation                                │
│   └── Audit logging with correlation IDs                                     │
│                                                                              │
│   Example:                                                                   │
│   LLM Output: "Contact user@email.com for details"                          │
│   Filtered:   "Contact [EMAIL REDACTED] for details"                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### [8] Error Handler
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Error Handler (Centralized Exception Handling)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Responsibilities:                                                          │
│   ├── Normalize exceptions → consistent error format                         │
│   ├── Attach correlation/trace IDs                                           │
│   ├── Map domain errors to HTTP status codes                                 │
│   ├── Hide internal details                                                  │
│   └── Structured logging for debugging                                       │
│                                                                              │
│   Example:                                                                   │
│   Internal: psycopg2.OperationalError: connection refused at 10.0.1.5       │
│   Response: {"error": "Service temporarily unavailable",                     │
│              "correlation_id": "req-xyz789"}                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Layer 3: API Layer (Routers)

### 5.1 Endpoint Overview

The platform exposes **76 endpoints** organized into **16 versioned API groups**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           API ENDPOINTS                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────┬──────────────────────────────────────────────────────┐  │
│  │   Endpoint     │   Description                                         │  │
│  ├────────────────┼──────────────────────────────────────────────────────┤  │
│  │ /v1/health     │ Health probes (live, ready, startup, components)     │  │
│  │ /v1/auth       │ Token introspection, identity verification           │  │
│  │ /v1/agents     │ Agent definitions and configurations                 │  │
│  │ /v1/agent-runs │ Agent run lifecycle (create, poll, cancel)           │  │
│  │ /v1/tools      │ MCP tool registry and invocation                     │  │
│  │ /v1/jobs       │ Async job lifecycle (create, stream, cancel)         │  │
│  │ /v1/models     │ Model and provider management                        │  │
│  │ /v1/admin      │ Administrative operations                            │  │
│  │ /v1/tenants    │ Multi-tenant configuration                           │  │
│  │ /v1/sessions   │ Session management                                   │  │
│  │ /v1/graph      │ Graph query endpoints                                │  │
│  │ /v1/batch      │ Batch operations                                     │  │
│  │ /v1/export     │ Data export utilities                                │  │
│  │ /v1/internal   │ Internal diagnostics                                 │  │
│  └────────────────┴──────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Layer 4: Execution Workflows

The platform supports two distinct execution paths for different use cases.

### 6.1 Workflow Comparison

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       WORKFLOW COMPARISON                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────┐         ┌─────────────────────────┐            │
│  │    WORKFLOW A           │         │    WORKFLOW B           │            │
│  │    Agent Runs           │         │    Long-Running Jobs    │            │
│  ├─────────────────────────┤         ├─────────────────────────┤            │
│  │ Execution: In-process   │         │ Execution: Worker pool  │            │
│  │ Via: BackgroundTasks    │         │ Via: Redis queue        │            │
│  │ Duration: Short/Medium  │         │ Duration: Long          │            │
│  │ Fault-tolerance: Basic  │         │ Fault-tolerance: High   │            │
│  │ Scaling: Vertical       │         │ Scaling: Horizontal     │            │
│  │ Use: Chat, quick Q&A    │         │ Use: ETL, batch, heavy  │            │
│  └─────────────────────────┘         └─────────────────────────┘            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Workflow A: Agent Runs

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW A: AGENT RUNS                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Endpoints:                                                                 │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ POST /v1/agent-runs             │ Start sync execution               │  │
│   │ POST /v1/agent-runs?use_jobs=true │ Route to async worker           │  │
│   │ GET  /v1/agent-runs/{id}        │ Retrieve run (ETag caching)        │  │
│   │ GET  /v1/agent-runs/{id}/steps  │ Get execution trace                │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│   State Machine:                                                             │
│   ┌──────────┐    ┌──────────┐    ┌───────────┐                             │
│   │  queued  │───►│ running  │───►│ succeeded │                             │
│   └──────────┘    └──────────┘    └───────────┘                             │
│                         │                                                    │
│                         └────────►┌──────────┐                              │
│                                   │  failed  │                              │
│                                   └──────────┘                              │
│                                                                              │
│   Response Format:                                                           │
│   {                                                                          │
│     "id": "run-abc123",                                                      │
│     "status": "succeeded",                                                   │
│     "outputs": ["Found 5 institutions..."],                                  │
│     "steps": [{ type, action, latency_ms }],                                │
│     "todos": [{ action, status: "completed" }],                             │
│     "metrics": { duration_ms, tokens_input, tokens_output }                 │
│   }                                                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.3 Workflow B: Long-Running Jobs

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   WORKFLOW B: LONG-RUNNING JOBS                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Endpoints:                                                                 │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ POST   /v1/jobs           │ Create job → 202 + Location header      │  │
│   │ GET    /v1/jobs/{id}      │ Get status + results                     │  │
│   │ GET    /v1/jobs/{id}/events │ SSE streaming                          │  │
│   │ DELETE /v1/jobs/{id}      │ Cancel via Redis Lua script              │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│   State Machine:                                                             │
│   ┌──────────┐    ┌──────────┐    ┌───────────┐                             │
│   │  queued  │───►│ running  │───►│ finished  │                             │
│   └──────────┘    └──────────┘    └───────────┘                             │
│                         │              │                                     │
│                         ├──────────────┼──────►┌───────────┐                │
│                         │              │       │ cancelled │                │
│                         │              │       └───────────┘                │
│                         └──────────────┴──────►┌──────────┐                 │
│                                                │  failed  │                 │
│                                                └──────────┘                 │
│                                                                              │
│   Job Types: demo, test, long-running, agent.run                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.4 Job Creation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        JOB CREATION FLOW                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────┐                                                        │
│   │ 1. VALIDATE     │  Pydantic schema + Job-type JSON Schema               │
│   └────────┬────────┘                                                        │
│            ▼                                                                 │
│   ┌─────────────────┐                                                        │
│   │ 2. IDEMPOTENCY  │  Check Redis + PostgreSQL for existing job            │
│   │    CHECK        │  If found → return existing job (no duplicate)         │
│   └────────┬────────┘                                                        │
│            ▼                                                                 │
│   ┌─────────────────┐                                                        │
│   │ 3. CREATE       │  INSERT INTO jobs (status='queued') → PostgreSQL      │
│   │    RECORD       │                                                        │
│   └────────┬────────┘                                                        │
│            ▼                                                                 │
│   ┌─────────────────┐                                                        │
│   │ 4. ENQUEUE      │  LPUSH job_id → Redis jobs:queue:{type}               │
│   │                 │  HSET job state → Redis jobs:state:{id}                │
│   └────────┬────────┘                                                        │
│            ▼                                                                 │
│   ┌─────────────────┐                                                        │
│   │ 5. CACHE KEY    │  Store idempotency:{key} → job_id in Redis            │
│   └────────┬────────┘                                                        │
│            ▼                                                                 │
│   ┌─────────────────┐                                                        │
│   │ 6. RESPOND      │  HTTP 202 Accepted                                     │
│   │                 │  { id, status: "queued", created_at }                  │
│   │                 │  + Location: /v1/jobs/{id}                             │
│   └─────────────────┘                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.5 Worker Processing Loop

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      WORKER PROCESSING LOOP                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                      │   │
│   │  ┌────────────────┐                                                  │   │
│   │  │ 1. POP JOB     │  BRPOP jobs:queue:{type} (blocking wait)        │   │
│   │  └───────┬────────┘                                                  │   │
│   │          ▼                                                           │   │
│   │  ┌────────────────┐                                                  │   │
│   │  │ 2. LOAD META   │  SELECT * FROM jobs WHERE id = ?                 │   │
│   │  └───────┬────────┘                                                  │   │
│   │          ▼                                                           │   │
│   │  ┌────────────────┐                                                  │   │
│   │  │ 3. CHECK CANCEL│  EXISTS jobs:cancel:{id} → skip if set          │   │
│   │  └───────┬────────┘                                                  │   │
│   │          ▼                                                           │   │
│   │  ┌────────────────┐                                                  │   │
│   │  │ 4. TRANSITION  │  status: queued → running                        │   │
│   │  │    STATUS      │  + emit SSE event                                │   │
│   │  └───────┬────────┘                                                  │   │
│   │          ▼                                                           │   │
│   │  ┌────────────────┐                                                  │   │
│   │  │ 5. HEARTBEAT   │  SETEX jobs:heartbeat:{id} every 30s            │   │
│   │  └───────┬────────┘                                                  │   │
│   │          ▼                                                           │   │
│   │  ┌────────────────┐                                                  │   │
│   │  │ 6. EXECUTE     │  Route to handler by job type                    │   │
│   │  │    HANDLER     │  Uses same adapters as main app                  │   │
│   │  └───────┬────────┘                                                  │   │
│   │          ▼                                                           │   │
│   │  ┌────────────────┐                                                  │   │
│   │  │ 7. EMIT EVENTS │  RPUSH jobs:events:{id} → SSE stream            │   │
│   │  └───────┬────────┘                                                  │   │
│   │          ▼                                                           │   │
│   │  ┌────────────────┐                                                  │   │
│   │  │ 8. FINALIZE    │  status → finished | failed | cancelled         │   │
│   │  │                │  Persist result → PostgreSQL                     │   │
│   │  └────────────────┘                                                  │   │
│   │                                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   Resources: 2 CPU, 4GB RAM per worker                                       │
│   Shared codebase with main app (same adapters/services)                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Layer 5: Service Layer (Orchestrator)

The Orchestrator Service is the core execution engine, processing prompts through **4 phases**.

### 7.1 Orchestrator Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR SERVICE                                     │
│                      (1 run per prompt)                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐ │
│   │   PHASE 1    │   │   PHASE 2    │   │   PHASE 3    │   │   PHASE 4    │ │
│   │   Intent     │──►│    TODO      │──►│    Step      │──►│   Final      │ │
│   │  Classify    │   │   Planning   │   │  Execution   │   │  Response    │ │
│   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Phase 1: Intent Classification

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 1: INTENT CLASSIFICATION                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Process:                                                                   │
│   1. Check params.category → match prompt catalog                            │
│   2. If no match → call classify_intent() via LLM                            │
│                                                                              │
│   ┌─────────────┬────────────────────────────────────────────────────────┐  │
│   │   Intent    │   Description                                          │  │
│   ├─────────────┼────────────────────────────────────────────────────────┤  │
│   │   CHAT      │   Conversational responses ("What is ML?")             │  │
│   │   GRAPH     │   NL→Cypher queries ("Which institutions?")            │  │
│   │   SECURITY  │   Permission/access questions                          │  │
│   │   ADMIN     │   Administrative write operations                      │  │
│   │   DANGEROUS │   Destructive ops → refuse + offer EXPLAIN             │  │
│   │   EXPLAIN   │   Query analysis without execution                     │  │
│   └─────────────┴────────────────────────────────────────────────────────┘  │
│                                                                              │
│   Example:                                                                   │
│   "How many Blast nodes?" → GRAPH                                           │
│   "Delete all data" → DANGEROUS (refused)                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.3 Phase 2: TODO Planning

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PHASE 2: TODO PLANNING                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Inputs:                                                                    │
│   • User's goal (original prompt)                                            │
│   • Conversation context (prior messages, session state)                     │
│   • Schema information (available tools, graph schema, permissions)          │
│                                                                              │
│   Output:                                                                    │
│   TODO Array: [{ "action": "query_graph", "params": {...} },                │
│                { "action": "summarize", "params": {...} }]                  │
│                                                                              │
│   ┌─────────────┬────────────────────────────────────────────────────────┐  │
│   │    Mode     │   Description                                          │  │
│   ├─────────────┼────────────────────────────────────────────────────────┤  │
│   │    full     │   LLM generates detailed plan for each TODO            │  │
│   │             │   Best for complex, multi-step tasks                   │  │
│   ├─────────────┼────────────────────────────────────────────────────────┤  │
│   │  optional   │   Try direct execution; fall back to planning          │  │
│   │             │   Good for simple-to-medium complexity                 │  │
│   ├─────────────┼────────────────────────────────────────────────────────┤  │
│   │    none     │   Deterministic execution without LLM planning         │  │
│   │             │   Used for predefined workflows or catalog matches     │  │
│   └─────────────┴────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.4 Phase 3: Step Execution

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PHASE 3: STEP EXECUTION                                  │
│                    (FOR EACH TODO ITEM)                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                                                                     │    │
│   │  ┌──────────────────┐                                               │    │
│   │  │ 1. CALL LLM      │  Planner / Reflector / Responder roles       │    │
│   │  │    PROVIDER      │  Via resilient adapter layer                  │    │
│   │  └────────┬─────────┘                                               │    │
│   │           ▼                                                         │    │
│   │  ┌──────────────────┐                                               │    │
│   │  │ 2. INVOKE MCP    │  34 tools, RBAC check before invocation      │    │
│   │  │    TOOLS         │  graph.query, cache.get, security.validate   │    │
│   │  └────────┬─────────┘                                               │    │
│   │           ▼                                                         │    │
│   │  ┌──────────────────┐                                               │    │
│   │  │ 3. GRAPH MODE    │  If GRAPH intent → NL→Cypher pipeline        │    │
│   │  │    PIPELINE      │  6-stage validation + execution               │    │
│   │  └────────┬─────────┘                                               │    │
│   │           ▼                                                         │    │
│   │  ┌──────────────────┐                                               │    │
│   │  │ 4. PERSIST STEP  │  Save to PostgreSQL immediately               │    │
│   │  │                  │  {id, action, input, output, latency_ms}      │    │
│   │  └────────┬─────────┘                                               │    │
│   │           ▼                                                         │    │
│   │  ┌──────────────────┐                                               │    │
│   │  │ 5. USE REDIS     │  Session state, cache, cancellation check    │    │
│   │  └──────────────────┘                                               │    │
│   │                                                                     │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│   Step Record Format:                                                        │
│   { id, action, input, output, latency_ms, started_at, finished_at }        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.5 Phase 4: Finalization & Response Generation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  PHASE 4: FINALIZATION & RESPONSE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                                                                       │  │
│   │  ┌─────────────────┐                                                  │  │
│   │  │ 1. BUILD        │  Aggregate results from all steps               │  │
│   │  │    RESPONSE     │  Mode: fallback-only | llm-best-effort          │  │
│   │  └────────┬────────┘                                                  │  │
│   │           ▼                                                           │  │
│   │  ┌─────────────────┐                                                  │  │
│   │  │ 2. CANONICAL    │  { goal, steps[], outputs[], todos[], metrics } │  │
│   │  │    OUTPUT       │                                                  │  │
│   │  └────────┬────────┘                                                  │  │
│   │           ▼                                                           │  │
│   │  ┌─────────────────┐                                                  │  │
│   │  │ 3. NORMALIZE    │  text + optional JSON payload                   │  │
│   │  └────────┬────────┘                                                  │  │
│   │           ▼                                                           │  │
│   │  ┌─────────────────┐                                                  │  │
│   │  │ 4. SAFETY       │  PII scrubbing + output guard                   │  │
│   │  │    COMPLIANCE   │                                                  │  │
│   │  └────────┬────────┘                                                  │  │
│   │           ▼                                                           │  │
│   │  ┌─────────────────┐                                                  │  │
│   │  │ 5. PERSIST      │  Save to PostgreSQL (result_json)               │  │
│   │  │    FINAL STATE  │  Update status → succeeded | failed              │  │
│   │  └────────┬────────┘                                                  │  │
│   │           ▼                                                           │  │
│   │  ┌─────────────────┐                                                  │  │
│   │  │ 6. OBSERVABILITY│  Emit Prometheus metrics + OTel traces          │  │
│   │  └─────────────────┘                                                  │  │
│   │                                                                       │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Layer 6: LLM Providers

### 8.1 Model-Agnostic Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      LLM PROVIDERS                                           │
│               (Model-Agnostic Architecture)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         OLLAMA (Local)                               │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │  Benefits:                                                           │    │
│  │  • Data sovereignty (prompts never leave your infra)                 │    │
│  │  • No API costs (only pay for compute)                               │    │
│  │  • Offline capable                                                   │    │
│  │  • Customization (fine-tune for domain-specific tasks)               │    │
│  │                                                                      │    │
│  │  Supported Models:                                                   │    │
│  │  • Phi-3 Mini (Microsoft, 3.8B params)                               │    │
│  │  • Mistral / Mixtral (Mistral AI)                                    │    │
│  │  • LLaMA 2/3 (Meta, 7B–70B)                                          │    │
│  │  • Qwen (Alibaba, multilingual)                                      │    │
│  │  • Gemma (Google, lightweight)                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         OPENAI (Cloud)                               │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │  Benefits: Zero infrastructure, automatic updates                    │    │
│  │  Models: GPT-4/4o/4 Turbo, GPT-3.5 Turbo                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      AZURE OPENAI / Others                           │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │  Benefits: Compliance certs, regional data residency, SLA            │    │
│  │  Compatible: Azure OpenAI, Anthropic Claude, vLLM                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Provider Selection Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   PROVIDER SELECTION HIERARCHY                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│         ┌─────────────────────────────┐                                      │
│         │   Request-level override    │  ◄── User specifies in API call     │
│         └────────────┬────────────────┘                                      │
│                      │ (if not set)                                          │
│                      ▼                                                       │
│         ┌─────────────────────────────┐                                      │
│         │   Session-level default     │  ◄── Team/user preference            │
│         └────────────┬────────────────┘                                      │
│                      │ (if not set)                                          │
│                      ▼                                                       │
│         ┌─────────────────────────────┐                                      │
│         │   Tenant-level default      │  ◄── Organization policy             │
│         └────────────┬────────────────┘                                      │
│                      │ (if not set)                                          │
│                      ▼                                                       │
│         ┌─────────────────────────────┐                                      │
│         │   Global platform default   │  ◄── System-wide fallback            │
│         └─────────────────────────────┘                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Layer 7: MCP Runtime & Tools

### 9.1 Tool Ecosystem Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     MCP RUNTIME & TOOLS                                      │
│                  34 Tools across 17 Categories                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Architecture:                                                              │
│   • Tool Registry → PostgreSQL-backed manifests                              │
│   • Tool Policies → RBAC per tool (required_scopes)                          │
│   • MCP Runtime → ToolContext, audit logging                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Tool Invocation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TOOL INVOCATION FLOW                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User Request                                                               │
│        │                                                                     │
│        ▼                                                                     │
│   ┌────────────────────────┐                                                 │
│   │ Input Validation       │  JSON Schema validation                         │
│   │ (if invalid → 400)     │                                                 │
│   └───────────┬────────────┘                                                 │
│               ▼                                                              │
│   ┌────────────────────────┐                                                 │
│   │ RBAC Check             │  Verify caller has required scopes              │
│   │ (if missing → 403)     │                                                 │
│   └───────────┬────────────┘                                                 │
│               ▼                                                              │
│   ┌────────────────────────┐                                                 │
│   │ Execute Tool           │  Actual operation                               │
│   │ (if error → 500)       │                                                 │
│   └───────────┬────────────┘                                                 │
│               ▼                                                              │
│   ┌────────────────────────┐                                                 │
│   │ Audit Log              │  Log all attempts (even failures)               │
│   └───────────┬────────────┘                                                 │
│               ▼                                                              │
│        Return Result                                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.3 Tool Categories

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TOOL CATEGORIES                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┬─────────────────────────────────────────────────────────┐  │
│  │  Category   │  Tools                                                   │  │
│  ├─────────────┼─────────────────────────────────────────────────────────┤  │
│  │  GRAPH      │  query, secure_query, generate_cypher, schema, explain  │  │
│  │  SECURITY   │  describe_principal, allowed_operations, validate       │  │
│  │  SYSTEM     │  health, metrics, config, status                        │  │
│  │  CACHE      │  get, set, delete, invalidate                           │  │
│  │  CATALOG    │  discover, describe, search                             │  │
│  │  MODEL      │  list, info, warmup, switch                             │  │
│  │  AGENT      │  context, history, state                                │  │
│  │  ANALYTICS  │  query, aggregate, visualize                            │  │
│  │  ADMIN      │  create_index, drop_index, constraint                   │  │
│  │  ETL        │  import, export, transform                              │  │
│  │  CRUD       │  create_node, update_node, delete_node                  │  │
│  │  EXPORT     │  csv, json, cypher                                      │  │
│  └─────────────┴─────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.4 Tool Manifest Schema

```json
{
  "name": "graph.secure_query",
  "description": "Execute tenant-isolated Cypher query",
  "input_schema": {
    "type": "object",
    "properties": {
      "cypher": { "type": "string" },
      "params": { "type": "object" }
    },
    "required": ["cypher"]
  },
  "required_scopes": ["graph:read"],
  "rate_limit": {
    "requests": 100,
    "window": 60
  }
}
```

---

## 10. Layer 8: NL-to-Cypher Pipeline

### 10.1 Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     NL-TO-CYPHER PIPELINE                                    │
│                        (6 Stages)                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐  ┌─────┐ │
│   │    1     │  │    2     │  │    3     │  │    4     │  │  5   │  │  6  │ │
│   │Normalize │─►│ Catalog  │─►│ Generate │─►│ Validate │─►│ Exec │─►│ Sum │ │
│   │          │  │  Lookup  │  │  Cypher  │  │ (6-layer)│  │      │  │     │ │
│   └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────┘  └─────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 Stage Details

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PIPELINE STAGE DETAILS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   STAGE 1: NORMALIZE                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Lowercase, remove fillers                                         │   │
│   │  • Input sanitization, entity extraction                             │   │
│   │  Example: "Hey, how many Blast nodes??" → "count blast nodes"       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   STAGE 2: CATALOG LOOKUP                                                    │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Check if query matches known patterns                             │   │
│   │  • If matched → use cached Cypher (fast, deterministic)              │   │
│   │  • If not → proceed to LLM generation                                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   STAGE 3: GENERATE CYPHER                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • LLM generates Cypher with schema context                          │   │
│   │  Example: "Which BlastedSeq has most inbound?" →                    │   │
│   │  MATCH (b:Blast)-[:OUTPUT]->(s:BlastedSeq)                          │   │
│   │  RETURN s, count(b) ORDER BY count DESC LIMIT 10                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   STAGE 4: VALIDATE (6-Layer)                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  ✓ Syntax check         ✓ Tenant boundary                           │   │
│   │  ✓ Query depth limits   ✓ Timeout guards                            │   │
│   │  ✓ Result size caps     ✓ Read-only enforcement                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   STAGE 5: EXECUTE                                                           │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • Run validated Cypher on Memgraph via graph.secure_query           │   │
│   │  • Tenant isolation enforced, timing metrics captured                │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   STAGE 6: SUMMARIZE                                                         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  • LLM converts results to natural language                          │   │
│   │  • Returns: text response + structured data                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.3 End-to-End Example

```
Input:  "Show 5 Blast pairs outputting to same BlastedSeq"

1. NORMALIZE  → "blast pairs same blastedseq limit 5"
2. CATALOG    → No match → LLM
3. GENERATE   → MATCH (b1:Blast)-[:OUTPUT]->(s)<-[:OUTPUT]-(b2:Blast) 
                WHERE b1<>b2 LIMIT 5
4. VALIDATE   → ✓ Read-only ✓ Tenant ✓ Depth ✓ Timeout
5. EXECUTE    → Returns 5 pairs
6. SUMMARIZE  → "Found 5 Blast pairs sharing BlastedSeq targets..."
```

---

## 11. Layer 9: Data Layer

### 11.1 Three-Database Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       DATA LAYER                                             │
│            3-Database Architecture for Different Needs                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐        │
│  │      REDIS        │  │   POSTGRESQL      │  │    MEMGRAPH       │        │
│  │   Speed Layer     │  │  Durability Layer │  │ Relationship Layer│        │
│  └───────────────────┘  └───────────────────┘  └───────────────────┘        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 11.2 Database Comparison

| Aspect | Redis | PostgreSQL | Memgraph |
|--------|-------|------------|----------|
| **Role** | Speed layer | Durability layer | Relationship layer |
| **Use Case** | Cache, queues, rate limits | State, audit, config | Graph queries, lineage |
| **Data Model** | Key-value + structures | Relational tables | Property graph |
| **Query** | Commands (GET, SET, LPUSH) | SQL | Cypher |
| **Persistence** | Optional (RDB/AOF) | Always (WAL, ACID) | Always (WAL) |
| **Consistency** | Eventual | Strong (ACID) | Strong (ACID) |
| **Latency** | Sub-ms | Low ms | Low ms (in-memory) |

### 11.3 Redis (Speed Layer)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           REDIS                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   CACHE                                                                      │
│   ┌──────────────────────────┬────────────────────────────────────────────┐ │
│   │ Key Pattern              │ Purpose                                    │ │
│   ├──────────────────────────┼────────────────────────────────────────────┤ │
│   │ session:{id}             │ Session data                               │ │
│   │ tenant:config:{id}       │ Tenant configurations                      │ │
│   │ model:defaults:{id}      │ Model defaults                             │ │
│   └──────────────────────────┴────────────────────────────────────────────┘ │
│                                                                              │
│   QUEUES                                                                     │
│   ┌──────────────────────────┬────────────────────────────────────────────┐ │
│   │ Key Pattern              │ Purpose                                    │ │
│   ├──────────────────────────┼────────────────────────────────────────────┤ │
│   │ jobs:queue:{type}        │ Job queue (LPUSH/BRPOP)                    │ │
│   │ jobs:events:{id}         │ SSE event buffer (ring)                    │ │
│   │ jobs:state:{id}          │ Job state (HASH)                           │ │
│   └──────────────────────────┴────────────────────────────────────────────┘ │
│                                                                              │
│   RATE LIMITING                                                              │
│   ┌──────────────────────────┬────────────────────────────────────────────┐ │
│   │ Key Pattern              │ Purpose                                    │ │
│   ├──────────────────────────┼────────────────────────────────────────────┤ │
│   │ ratelimit:user:{id}      │ Per-user limits                            │ │
│   │ ratelimit:tenant:{id}    │ Per-tenant limits                          │ │
│   │ ratelimit:endpoint:{...} │ Per-endpoint limits                        │ │
│   └──────────────────────────┴────────────────────────────────────────────┘ │
│                                                                              │
│   CONTROL                                                                    │
│   ┌──────────────────────────┬────────────────────────────────────────────┐ │
│   │ Key Pattern              │ Purpose                                    │ │
│   ├──────────────────────────┼────────────────────────────────────────────┤ │
│   │ idempotency:{key}        │ Idempotency mapping                        │ │
│   │ circuit:{provider}       │ Circuit breaker state                      │ │
│   │ jobs:cancel:{id}         │ Cancellation flag                          │ │
│   └──────────────────────────┴────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 11.4 PostgreSQL (Durability Layer)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         POSTGRESQL                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   CORE TABLES                                                                │
│   ┌─────────────────┬────────────────────────────────────────────────────┐  │
│   │ Table           │ Purpose                                            │  │
│   ├─────────────────┼────────────────────────────────────────────────────┤  │
│   │ tenants         │ Multi-tenant configurations                        │  │
│   │ agent_runs      │ Agent run records with status                      │  │
│   │ agent_sessions  │ Conversation state                                 │  │
│   │ agent_steps     │ Per-step execution records                         │  │
│   │ jobs            │ Async job records                                  │  │
│   │ job_events      │ Job progress events (append-only)                  │  │
│   │ tools           │ MCP tool definitions                               │  │
│   │ tool_invocations│ Tool execution audit trail                         │  │
│   │ model_defaults  │ Default model configurations                       │  │
│   │ providers       │ LLM provider registry                              │  │
│   │ provider_secrets│ Encrypted API keys                                 │  │
│   │ audit_logs      │ Compliance trail (all actions)                     │  │
│   │ idempotency_keys│ Request deduplication                              │  │
│   └─────────────────┴────────────────────────────────────────────────────┘  │
│                                                                              │
│   Migrations: SQLAlchemy + Alembic                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 11.5 Memgraph (Graph Layer)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          MEMGRAPH                                            │
│                  (Bioinformatics Domain)                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   NODE TYPES (14 types)                                                      │
│   ┌────────────────┬──────────────────────────────────────────────────────┐ │
│   │ Label          │ Key Properties                                       │ │
│   ├────────────────┼──────────────────────────────────────────────────────┤ │
│   │ :User          │ user_id, firstName, lastName, email                  │ │
│   │ :Institution   │ id, name, country, type                              │ │
│   │ :Task          │ task_id, status, start, tags (Blast, CreateDb, etc.) │ │
│   │ :File          │ file_id, user_filename, size, extension              │ │
│   │ :Dataset       │ id, name, description, version                       │ │
│   │ :Sample        │ id, name, organism, tissue                           │ │
│   │ :Experiment    │ id, name, protocol, date                             │ │
│   │ :Publication   │ id, doi, title, journal, year                        │ │
│   │ :Gene          │ id, symbol, name, chromosome                         │ │
│   │ :Protein       │ id, name, sequence, function                         │ │
│   │ :Pathway       │ id, name, description                                │ │
│   │ :Tool          │ id, name, version, type                              │ │
│   │ :Workflow      │ id, name, steps, inputs                              │ │
│   │ :Result        │ id, type, metrics, timestamp                         │ │
│   └────────────────┴──────────────────────────────────────────────────────┘ │
│                                                                              │
│   RELATIONSHIP TYPES (4 types)                                               │
│   ┌────────────────┬──────────────────────────────────────────────────────┐ │
│   │ Relationship   │ Pattern                                              │ │
│   ├────────────────┼──────────────────────────────────────────────────────┤ │
│   │ WORKS_AT       │ (User)-[:WORKS_AT {since, role}]->(Institution)      │ │
│   │ RUNS           │ (User)-[:RUNS]->(Task)                               │ │
│   │ INPUT          │ (File)-[:INPUT]->(Task)                              │ │
│   │ OUTPUT         │ (Task)-[:OUTPUT]->(File)                             │ │
│   └────────────────┴──────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Layer 10: Adapters

### 12.1 Adapter Pattern

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ADAPTERS                                            │
│          Swappable interfaces for external services                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         LLM ADAPTERS                                 │   │
│   ├─────────────────────────────────────────────────────────────────────┤   │
│   │                                                                      │   │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│   │  │   Ollama    │  │   OpenAI    │  │   Azure     │  │ Stub/Demo   │ │   │
│   │  │   Adapter   │  │   Adapter   │  │   Adapter   │  │  Adapter    │ │   │
│   │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │   │
│   │         │                │                │                │        │   │
│   │         └────────────────┼────────────────┼────────────────┘        │   │
│   │                          ▼                                          │   │
│   │                ┌─────────────────────┐                              │   │
│   │                │  Unified LLM API    │                              │   │
│   │                │  (same interface)   │                              │   │
│   │                └─────────────────────┘                              │   │
│   │                                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                       DATABASE ADAPTERS                              │   │
│   ├─────────────────────────────────────────────────────────────────────┤   │
│   │                                                                      │   │
│   │  ┌─────────────────────────────────────────────────────────────┐    │   │
│   │  │ Redis Adapter                                                │    │   │
│   │  │ cache.get/set, queue.push/pop, ratelimit.check, lock.acquire│    │   │
│   │  └─────────────────────────────────────────────────────────────┘    │   │
│   │                                                                      │   │
│   │  ┌─────────────────────────────────────────────────────────────┐    │   │
│   │  │ PostgreSQL Adapter                                           │    │   │
│   │  │ repository.CRUD, transaction.begin/commit, query.execute    │    │   │
│   │  └─────────────────────────────────────────────────────────────┘    │   │
│   │                                                                      │   │
│   │  ┌─────────────────────────────────────────────────────────────┐    │   │
│   │  │ Memgraph Adapter                                             │    │   │
│   │  │ graph.query, graph.secure_query, graph.nl_to_cypher         │    │   │
│   │  └─────────────────────────────────────────────────────────────┘    │   │
│   │                                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 13. Layer 11: Resilience Framework

### 13.1 Circuit Breaker Pattern

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CIRCUIT BREAKER                                        │
│            (Per provider, stored in Redis circuit:{provider})                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                      ┌─────────────────┐                                     │
│          Normal      │     CLOSED      │     All requests go through        │
│          Operation   │                 │                                     │
│                      └────────┬────────┘                                     │
│                               │                                              │
│                               │ N consecutive failures                       │
│                               ▼                                              │
│                      ┌─────────────────┐                                     │
│          Fail-Fast   │      OPEN       │     Reject immediately              │
│                      │                 │     Return fallback                 │
│                      └────────┬────────┘                                     │
│                               │                                              │
│                               │ After timeout (e.g., 60s)                    │
│                               ▼                                              │
│                      ┌─────────────────┐                                     │
│          Test        │   HALF-OPEN     │     Allow 1 probe request           │
│          Recovery    │                 │                                     │
│                      └────────┬────────┘                                     │
│                               │                                              │
│                    Success    │    Failure                                   │
│                  ┌────────────┴────────────┐                                 │
│                  ▼                         ▼                                 │
│           Back to CLOSED            Back to OPEN                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 13.2 Retry Strategy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EXPONENTIAL BACKOFF RETRIES                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────┬─────────┐                                                     │
│   │ Attempt  │  Delay  │                                                     │
│   ├──────────┼─────────┤                                                     │
│   │   1st    │   0s    │                                                     │
│   │   2nd    │   1s    │                                                     │
│   │   3rd    │   2s    │                                                     │
│   │   4th    │   4s    │                                                     │
│   │   5th    │   8s    │                                                     │
│   └──────────┴─────────┘                                                     │
│                                                                              │
│   Prevents hammering a recovering service                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 13.3 Provider Fallback Chain

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PROVIDER FALLBACK CHAIN                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Request                                                                    │
│      │                                                                       │
│      ▼                                                                       │
│   ┌─────────────────────────┐                                                │
│   │ Primary: OpenAI GPT-4   │ ──► Success → Return                          │
│   └───────────┬─────────────┘                                                │
│               │ Failure                                                      │
│               ▼                                                              │
│   ┌─────────────────────────┐                                                │
│   │ Fallback 1: Azure GPT-4 │ ──► Success → Return                          │
│   └───────────┬─────────────┘                                                │
│               │ Failure                                                      │
│               ▼                                                              │
│   ┌─────────────────────────┐                                                │
│   │ Fallback 2: Ollama      │ ──► Success → Return                          │
│   └───────────┬─────────────┘                                                │
│               │ Failure                                                      │
│               ▼                                                              │
│         Return Error                                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 13.4 Cost Tracking

| Metric | What It Tracks | Purpose |
|--------|----------------|---------|
| `tokens_input` | Tokens in prompt | Billing |
| `tokens_output` | Tokens in response | Billing |
| `cost_usd` | Estimated cost | Budgets |
| `latency_ms` | Response time | Performance |

---

## 14. Layer 12: Background Framework

### 14.1 APScheduler Tasks

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      APSCHEDULER (Background Tasks)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────┬────────────┬────────────────────────────────────┐ │
│   │ Task                │ Frequency  │ Description                        │ │
│   ├─────────────────────┼────────────┼────────────────────────────────────┤ │
│   │ Health Check        │ 30 seconds │ Ping Postgres, Redis, Memgraph     │ │
│   │                     │            │ Check LLM provider availability    │ │
│   ├─────────────────────┼────────────┼────────────────────────────────────┤ │
│   │ Cleanup             │ Hourly     │ Remove stale sessions              │ │
│   │                     │            │ Clear expired cache                │ │
│   │                     │            │ Archive old jobs                   │ │
│   │                     │            │ Clean orphan runs                  │ │
│   ├─────────────────────┼────────────┼────────────────────────────────────┤ │
│   │ Backup              │ Daily      │ PostgreSQL pg_dump                 │ │
│   │                     │            │ Redis RDB snapshot                 │ │
│   │                     │            │ Memgraph archives                  │ │
│   │                     │            │ Export audit logs                  │ │
│   ├─────────────────────┼────────────┼────────────────────────────────────┤ │
│   │ Provider Monitoring │ 60 seconds │ Check LLM provider health          │ │
│   │                     │            │ Update circuit breaker states      │ │
│   │                     │            │ Emit metrics                       │ │
│   └─────────────────────┴────────────┴────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 15. Layer 13: Observability & Monitoring

### 15.1 Tracing (OpenTelemetry)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      OPENTELEMETRY TRACING                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Request → App creates trace span → Child spans → OTLP export → APM        │
│                                                                              │
│   Trace Spans:                                                               │
│   ┌─────────────────────┬────────────────────────────────────────────────┐  │
│   │ Span                │ What It Captures                               │  │
│   ├─────────────────────┼────────────────────────────────────────────────┤  │
│   │ agent_run           │ Full execution from prompt to response         │  │
│   │ step_execution      │ Each TODO step within a run                    │  │
│   │ tool_invocation     │ Every MCP tool call with inputs/outputs        │  │
│   │ db_query            │ PostgreSQL, Redis, Memgraph with timing        │  │
│   │ llm_call            │ LLM requests with model, tokens, latency       │  │
│   │ job_lifecycle       │ enqueue → execute → complete/fail/cancel       │  │
│   └─────────────────────┴────────────────────────────────────────────────┘  │
│                                                                              │
│   Export to: Jaeger / Tempo / Datadog                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 15.2 Prometheus Metrics

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PROMETHEUS METRICS                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────┬────────────────────────────────────────────────┐  │
│   │ Category            │ Example Metrics                                │  │
│   ├─────────────────────┼────────────────────────────────────────────────┤  │
│   │ HTTP                │ http_request_duration_seconds                  │  │
│   │                     │ http_requests_total (by endpoint, status)      │  │
│   ├─────────────────────┼────────────────────────────────────────────────┤  │
│   │ Agent Runs          │ agent_run_duration_seconds                     │  │
│   │                     │ agent_run_total (by status)                    │  │
│   ├─────────────────────┼────────────────────────────────────────────────┤  │
│   │ Steps               │ agent_step_duration_seconds                    │  │
│   │                     │ agent_step_total (by type)                     │  │
│   ├─────────────────────┼────────────────────────────────────────────────┤  │
│   │ Tools               │ tool_invocation_duration_seconds               │  │
│   │                     │ tool_invocation_total (by tool name)           │  │
│   ├─────────────────────┼────────────────────────────────────────────────┤  │
│   │ LLM                 │ llm_tokens_total, llm_cost_usd_total           │  │
│   │                     │ llm_latency_seconds (by provider/model)        │  │
│   ├─────────────────────┼────────────────────────────────────────────────┤  │
│   │ Circuit Breaker     │ circuit_breaker_state (0/0.5/1)                │  │
│   ├─────────────────────┼────────────────────────────────────────────────┤  │
│   │ Jobs                │ job_queue_depth, job_processing_duration       │  │
│   ├─────────────────────┼────────────────────────────────────────────────┤  │
│   │ System              │ component_health (1=healthy, 0=unhealthy)      │  │
│   └─────────────────────┴────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 15.3 Grafana Dashboards

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       GRAFANA DASHBOARDS                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────┬────────────────────────────────────────────────┐  │
│   │ Dashboard           │ Shows                                          │  │
│   ├─────────────────────┼────────────────────────────────────────────────┤  │
│   │ HTTP Overview       │ Request rate, latency p50/p95/p99, error rate  │  │
│   │ Agent Runs          │ Runs/min, success rate, duration, step count   │  │
│   │ Job Processing      │ Queue depth, processing time, completion rate  │  │
│   │ Tool Invocations    │ Most-used tools, latency by tool, error rates  │  │
│   │ LLM Providers       │ Health, circuit breakers, token usage, costs   │  │
│   │ System Health       │ Component status, DB pools, memory usage       │  │
│   └─────────────────────┴────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 15.4 Health Endpoints

```
/v1/health/live      - Is the process running?
/v1/health/ready     - Can it serve requests?
/v1/health/startup   - Has initialization completed?
/v1/health/components - Per-component status (PostgreSQL, Redis, Memgraph)
```

---

## 16. Appendix: Architecture Diagrams

### 16.1 Complete System Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    CINECA AGENTIC PLATFORM                                           │
│                                   Complete Architecture Flow                                         │
├─────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                                    CLIENT LAYER                                              │    │
│  │   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                                │    │
│  │   │ Agent Chat   │     │Control Panel │     │  External    │                                │    │
│  │   │ (Next.js)    │     │ (Streamlit)  │     │   Clients    │                                │    │
│  │   └──────┬───────┘     └──────┬───────┘     └──────┬───────┘                                │    │
│  └──────────┼────────────────────┼────────────────────┼────────────────────────────────────────┘    │
│             │                    │                    │                                              │
│             └────────────────────┼────────────────────┘                                              │
│                                  ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                              GATEWAY LAYER                                                   │    │
│  │   ┌────────────────────────────────────────────────────────────────────────────────────┐   │    │
│  │   │                     NGINX + Identity Provider (Auth0)                               │   │    │
│  │   │              TLS │ CORS │ Load Balance │ JWT Auth │ JWKS                           │   │    │
│  │   └────────────────────────────────────────────────────────────────────────────────────┘   │    │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘    │
│                                  │                                                                   │
│                                  ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                          SECURITY MIDDLEWARE (8 Layers)                                      │    │
│  │   CORS → Trace → Auth JWT → Rate Limit → Tenant → Input Guard → Output Guard → Error       │    │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘    │
│                                  │                                                                   │
│                                  ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                            API LAYER (76 Endpoints)                                          │    │
│  │   /health │ /auth │ /agents │ /agent-runs │ /jobs │ /tools │ /models │ /graph │ ...       │    │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘    │
│                                  │                                                                   │
│                    ┌─────────────┴─────────────┐                                                     │
│                    ▼                           ▼                                                     │
│  ┌─────────────────────────┐     ┌─────────────────────────┐                                        │
│  │  WORKFLOW A             │     │  WORKFLOW B             │                                        │
│  │  Agent Runs             │     │  Long-Running Jobs      │                                        │
│  │  (BackgroundTasks)      │     │  (Redis Queue+Workers)  │                                        │
│  └───────────┬─────────────┘     └───────────┬─────────────┘                                        │
│              │                               │                                                       │
│              └───────────────┬───────────────┘                                                       │
│                              ▼                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                           ORCHESTRATOR SERVICE                                               │    │
│  │   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                    │    │
│  │   │ Phase 1     │ → │ Phase 2     │ → │ Phase 3     │ → │ Phase 4     │                    │    │
│  │   │ Intent      │   │ TODO Plan   │   │ Step Exec   │   │ Finalize    │                    │    │
│  │   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘                    │    │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘    │
│                              │                                                                       │
│              ┌───────────────┼───────────────┐                                                       │
│              ▼               ▼               ▼                                                       │
│  ┌───────────────────┐ ┌───────────────┐ ┌───────────────────────────┐                              │
│  │  LLM PROVIDERS    │ │  MCP TOOLS    │ │  NL→CYPHER PIPELINE       │                              │
│  │  ─────────────    │ │  ─────────    │ │  ─────────────────        │                              │
│  │  • Ollama         │ │  34 tools     │ │  Normalize → Lookup →     │                              │
│  │  • OpenAI         │ │  17 categories│ │  Generate → Validate →    │                              │
│  │  • Azure          │ │  RBAC check   │ │  Execute → Summarize      │                              │
│  └───────────────────┘ └───────────────┘ └───────────────────────────┘                              │
│                              │                                                                       │
│                              ▼                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                              DATA LAYER                                                      │    │
│  │   ┌───────────────┐     ┌───────────────┐     ┌───────────────┐                             │    │
│  │   │    REDIS      │     │  POSTGRESQL   │     │   MEMGRAPH    │                             │    │
│  │   │  ───────────  │     │  ───────────  │     │  ───────────  │                             │    │
│  │   │  • Cache      │     │  • Jobs       │     │  • Graph DB   │                             │    │
│  │   │  • Queues     │     │  • Audit Logs │     │  • Cypher     │                             │    │
│  │   │  • Rate Limit │     │  • Sessions   │     │  • Lineage    │                             │    │
│  │   └───────────────┘     └───────────────┘     └───────────────┘                             │    │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘    │
│                              │                                                                       │
│                              ▼                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐    │
│  │                           OBSERVABILITY                                                      │    │
│  │   ┌───────────────┐     ┌───────────────┐     ┌───────────────┐                             │    │
│  │   │ OpenTelemetry │     │  Prometheus   │     │   Grafana     │                             │    │
│  │   │   (Tracing)   │     │   (Metrics)   │     │ (Dashboards)  │                             │    │
│  │   └───────────────┘     └───────────────┘     └───────────────┘                             │    │
│  └──────────────────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 16.2 Data Flow for Agent Run

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              AGENT RUN DATA FLOW                                         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   User: "How many Blast nodes are in the database?"                                     │
│                                                                                          │
│   1. POST /v1/agent-runs                                                                 │
│      { "prompt": "How many Blast nodes?", "model": "gpt-4o" }                           │
│                                                                                          │
│   2. Security Middleware                                                                 │
│      ├── JWT validated ✓                                                                │
│      ├── RBAC check: user has graph:read ✓                                              │
│      ├── Rate limit: 45/100 remaining ✓                                                 │
│      ├── Tenant: cineca_bioinformatics                                                  │
│      └── Input sanitized ✓                                                              │
│                                                                                          │
│   3. Orchestrator Phase 1: Intent Classification                                         │
│      └── Intent: GRAPH                                                                  │
│                                                                                          │
│   4. Orchestrator Phase 2: TODO Planning                                                 │
│      └── [{ action: "query_graph" }, { action: "summarize" }]                           │
│                                                                                          │
│   5. Orchestrator Phase 3: Step Execution                                                │
│      ├── Step 1: NL→Cypher Pipeline                                                     │
│      │   ├── Normalize: "count blast nodes"                                             │
│      │   ├── Generate: MATCH (b:Blast) RETURN count(b)                                  │
│      │   ├── Validate: ✓ read-only ✓ tenant ✓ depth ✓ timeout                          │
│      │   └── Execute: { count: 186 }                                                    │
│      │                                                                                   │
│      └── Step 2: Summarize (LLM)                                                        │
│          └── "There are 186 Blast nodes in the database."                               │
│                                                                                          │
│   6. Orchestrator Phase 4: Finalization                                                  │
│      ├── PII scrubbed ✓                                                                 │
│      ├── Output guard ✓                                                                 │
│      └── Metrics emitted                                                                │
│                                                                                          │
│   7. Response                                                                            │
│      {                                                                                   │
│        "id": "run-abc123",                                                              │
│        "status": "succeeded",                                                           │
│        "outputs": ["There are 186 Blast nodes in the database."],                       │
│        "metrics": { "duration_ms": 1240, "tokens": 850 }                                │
│      }                                                                                   │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Document Information

| Attribute | Value |
|-----------|-------|
| **Version** | 1.0 |
| **Based On** | DIAGRAM.md, Presentation Slides |
| **Author** | Arman Feili |
| **Institution** | Sapienza University of Rome / CINECA |
| **Generated** | February 2026 |

---

*End of Architecture Document*
