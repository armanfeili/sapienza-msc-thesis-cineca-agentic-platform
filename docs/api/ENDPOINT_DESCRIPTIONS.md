# Agent API Endpoint Descriptions# Agent API Endpoint Descriptions



## Sessions Management## Sessions Management



### Create Agent Session### Create Agent Session



**POST /v1/agents/sessions** – Start a new conversation or workflow with an agent**POST /v1/agents/sessions** – Start a new conversation or workflow with an agent



**Why we need this endpoint:****Why we need this endpoint:**



- Start long-running conversations where context and memory need to persist across multiple steps- Start long-running conversations where context and memory need to persist across multiple steps

- Set up configurations (like which LLM to use, tools available, temperature settings) before sending actual work- Set up configurations (like which LLM to use, tools available, temperature settings) before sending actual work

- Track related tasks together as a single workflow unit- Track related tasks together as a single workflow unit

- Enable users to pause, continue, or cancel work in progress- Enable users to pause, continue, or cancel work in progress



**What it does:****What it does:**



- Creates a new session with a unique ID that you can reference later- Creates a new session with a unique ID that you can reference later

- Stores your session preferences (temperature, max steps, tools allowed, etc.)- Stores your session preferences (temperature, max steps, tools allowed, etc.)

- Allows you to optionally provide your own session ID for idempotency- Allows you to optionally provide your own session ID for idempotency

- Returns full session details immediately so you can start adding steps to it- Returns full session details immediately so you can start adding steps to it

- If you send the same Idempotency-Key again, returns the same session without creating a duplicate- If you send the same Idempotency-Key again, returns the same session without creating a duplicate



**Access:****Access:**



- Regular users can create sessions and can only see/manage their own- Regular users can create sessions and can only see/manage their own

- Admins can create sessions on behalf of other users or see all sessions- Admins can create sessions on behalf of other users or see all sessions



**Behavior:****Behavior:**



- **Idempotency**: If you include an `Idempotency-Key` header, calling this endpoint twice with the same key returns the exact same result- **Idempotency**: If you include an `Idempotency-Key` header, calling this endpoint twice with the same key returns the exact same result

- **Caching**: Automatically optimized for high-traffic scenarios with efficient storage- **Caching**: Automatically optimized for high-traffic scenarios with efficient storage

- **Multi-tenant**: Each session is tied to a specific tenant for isolation- **Multi-tenant**: Each session is tied to a specific tenant for isolation



**Responses:****Responses:**



- **201 Created** – Session successfully created; includes the session details and a Location header pointing to the new session- **201 Created** – Session successfully created; includes the session details and a Location header pointing to the new session

- **400 Bad Request** – Invalid request body (e.g., temperature out of range, invalid tools list)- **400 Bad Request** – Invalid request body (e.g., temperature out of range, invalid tools list)

- **409 Conflict** – The session_id you provided already exists and is owned by another user- **409 Conflict** – The session_id you provided already exists and is owned by another user



**Examples:****Examples:**



```bash```bash

# Create a new session for a coding task# Create a new session for a coding task

curl -X POST http://localhost:8000/v1/agents/sessions \curl -X POST http://localhost:8000/v1/agents/sessions \

  -H "Authorization: Bearer $TOKEN" \  -H "Authorization: Bearer $TOKEN" \

  -H "Content-Type: application/json" \  -H "Content-Type: application/json" \

  -H "Idempotency-Key: session-coding-123" \  -H "Idempotency-Key: session-coding-123" \

  -d '{  -d '{

    "manager": "planner",    "manager": "planner",

    "tools": ["python_repl", "web_search"],    "tools": ["python_repl", "web_search"],

    "temperature": 0.1,    "temperature": 0.1,

    "max_steps": 10,    "max_steps": 10,

    "agent_role": "coder"    "agent_role": "coder"

  }'  }'

```

# Response includes session_id and other details

---```



### List Agent Sessions---



**GET /v1/agents/sessions** – See all your sessions and their current status### List Agent Sessions

**GET /v1/agents/sessions** – See all your sessions and their current status

**Why we need this endpoint:**

**Why we need this endpoint:**

- Find sessions you've already started to continue or monitor them- Find sessions you've already started to continue or monitor them

- Track the status of ongoing work (active, completed, cancelled)- Track the status of ongoing work (active, completed, cancelled)

- Navigate through a history of your conversations and workflows- Navigate through a history of your conversations and workflows

- Support pagination so listing doesn't slow down with lots of sessions- Support pagination so listing doesn't slow down with lots of sessions



**What it does:****What it does:**

- Returns a paginated list of sessions you own (or all sessions if you're an admin)

- Returns a paginated list of sessions you own (or all sessions if you're an admin)- Includes minimal info per session (ID, status, creation date, last update)

- Includes minimal info per session (ID, status, creation date, last update)- Supports cursor-based pagination to efficiently page through results

- Supports cursor-based pagination to efficiently page through results- Caches the list result with ETag to avoid redundant responses

- Caches the list result with ETag to avoid redundant responses

**Access:**

**Access:**- Regular users see only their own sessions

- Admins see all sessions across all users

- Regular users see only their own sessions- Authenticated users only

- Admins see all sessions across all users

- Authenticated users only**Behavior:**

- **Pagination**: Use `limit` (default 20) and `cursor` parameters to fetch results page by page

**Behavior:**- **ETag Caching**: If you send an `If-None-Match` header with the previous response's ETag and nothing changed, you get a 304 Not Modified response

- **Rate Limiting**: Applies rate limits to prevent abuse of list operations

- **Pagination**: Use `limit` (default 20) and `cursor` parameters to fetch results page by page- **Ordering**: Results ordered by most recently updated first

- **ETag Caching**: If you send an `If-None-Match` header with the previous response's ETag and nothing changed, you get a 304 Not Modified response

- **Rate Limiting**: Applies rate limits to prevent abuse of list operations**Responses:**

- **Ordering**: Results ordered by most recently updated first- **200 OK** – List retrieved successfully; includes items array and optional next_cursor for pagination

- **304 Not Modified** – Nothing has changed since your last request (ETag matched)

**Responses:**

**Examples:**

- **200 OK** – List retrieved successfully; includes items array and optional next_cursor for pagination```bash

- **304 Not Modified** – Nothing has changed since your last request (ETag matched)# Get first page of sessions

curl -X GET "http://localhost:8000/v1/agents/sessions?limit=10" \

**Examples:**  -H "Authorization: Bearer $TOKEN"



```bash# Get next page using cursor from previous response

# Get first page of sessionscurl -X GET "http://localhost:8000/v1/agents/sessions?limit=10&cursor=eyJsYXN0X2lkIjogIm..." \

curl -X GET "http://localhost:8000/v1/agents/sessions?limit=10" \  -H "Authorization: Bearer $TOKEN"

  -H "Authorization: Bearer $TOKEN"

# Use ETag to avoid re-downloading unchanged list

# Get next page using cursor from previous responsecurl -X GET "http://localhost:8000/v1/agents/sessions" \

curl -X GET "http://localhost:8000/v1/agents/sessions?limit=10&cursor=eyJsYXN0X2lkIjogIm..." \  -H "Authorization: Bearer $TOKEN" \

  -H "Authorization: Bearer $TOKEN"  -H "If-None-Match: \"abc123def456\""

```

# Use ETag to avoid re-downloading unchanged list

curl -X GET "http://localhost:8000/v1/agents/sessions" \---

  -H "Authorization: Bearer $TOKEN" \

  -H "If-None-Match: \"abc123def456\""### Get Session Details

```**GET /v1/agents/sessions/{session_id}** – View current state and configuration of a specific session



---**Why we need this endpoint:**

- Check the current status of an ongoing session (is it still active, completed, failed?)

### Get Session Details- See session configuration and parameters (temperature, tools, max steps)

- Track metadata and timestamps of the session lifecycle

**GET /v1/agents/sessions/{session_id}** – View current state and configuration of a specific session- Retrieve the ID of the last step added to the session



**Why we need this endpoint:****What it does:**

- Retrieves all details about a session you own or that an admin has access to

- Check the current status of an ongoing session (is it still active, completed, failed?)- Includes session status, configuration, creation/update timestamps

- See session configuration and parameters (temperature, tools, max steps)- Provides the ID of the most recent step (useful for checking progress)

- Track metadata and timestamps of the session lifecycle- Supports ETag caching for efficient repeated checks

- Retrieve the ID of the last step added to the session- Validates that you have permission to view this specific session



**What it does:****Access:**

- Users can only view their own sessions

- Retrieves all details about a session you own or that an admin has access to- Admins can view any session

- Includes session status, configuration, creation/update timestamps- Requires authentication

- Provides the ID of the most recent step (useful for checking progress)

- Supports ETag caching for efficient repeated checks**Behavior:**

- Validates that you have permission to view this specific session- **Ownership Check**: Endpoint verifies you own this session (unless you're admin)

- **ETag Support**: Returns an ETag you can use to avoid re-downloading unchanged data

**Access:**- **404 Handling**: Returns clearly when session doesn't exist or isn't accessible



- Users can only view their own sessions**Responses:**

- Admins can view any session- **200 OK** – Session found and returned with full details

- Requires authentication- **304 Not Modified** – Session unchanged since your last check (ETag matched)

- **404 Not Found** – Session doesn't exist or you don't have permission to view it

**Behavior:**

**Examples:**

- **Ownership Check**: Endpoint verifies you own this session (unless you're admin)```bash

- **ETag Support**: Returns an ETag you can use to avoid re-downloading unchanged data# Get session details

- **404 Handling**: Returns clearly when session doesn't exist or isn't accessiblecurl -X GET http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000 \

  -H "Authorization: Bearer $TOKEN"

**Responses:**

# Check again with ETag to save bandwidth

- **200 OK** – Session found and returned with full detailscurl -X GET http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000 \

- **304 Not Modified** – Session unchanged since your last check (ETag matched)  -H "Authorization: Bearer $TOKEN" \

- **404 Not Found** – Session doesn't exist or you don't have permission to view it  -H "If-None-Match: \"session-v1-abc123\""

```

**Examples:**

---

```bash

# Get session details### Cancel Agent Session

curl -X GET http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000 \**DELETE /v1/agents/sessions/{session_id}** – Stop an active session and mark it as cancelled

  -H "Authorization: Bearer $TOKEN"

**Why we need this endpoint:**

# Check again with ETag to save bandwidth- Stop a session that's running longer than expected or is no longer needed

curl -X GET http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000 \- Signal the backend to clean up resources and stop any ongoing work

  -H "Authorization: Bearer $TOKEN" \- Enable users to gracefully exit from long-running conversations

  -H "If-None-Match: \"session-v1-abc123\""- Safe to call multiple times (idempotent) without side effects

```

**What it does:**

---- Marks the session as "cancelled" in the database

- Signals any running orchestrator/worker to stop processing this session

### Cancel Agent Session- Returns immediately (doesn't wait for cleanup to complete)

- Is idempotent: calling it multiple times is safe and produces the same result

**DELETE /v1/agents/sessions/{session_id}** – Stop an active session and mark it as cancelled

**Access:**

**Why we need this endpoint:**- Users can cancel their own sessions

- Admins can cancel any session

- Stop a session that's running longer than expected or is no longer needed- Requires authentication

- Signal the backend to clean up resources and stop any ongoing work

- Enable users to gracefully exit from long-running conversations**Behavior:**

- Safe to call multiple times (idempotent) without side effects- **Idempotent**: Calling DELETE twice returns success both times

- **Best-Effort**: The cancellation signal is sent but completion is not guaranteed

**What it does:**- **Status Update**: Subsequently calling GET on this session should show "cancelled" status

- **No Response Body**: Returns 204 with no content (just headers)

- Marks the session as "cancelled" in the database

- Signals any running orchestrator/worker to stop processing this session**Responses:**

- Returns immediately (doesn't wait for cleanup to complete)- **204 No Content** – Cancellation request accepted and processed

- Is idempotent: calling it multiple times is safe and produces the same result- **404 Not Found** – Session doesn't exist or you don't have permission to cancel it



**Access:****Examples:**

```bash

- Users can cancel their own sessions# Cancel a session

- Admins can cancel any sessioncurl -X DELETE http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000 \

- Requires authentication  -H "Authorization: Bearer $TOKEN"



**Behavior:**# Safe to call again (idempotent)

curl -X DELETE http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000 \

- **Idempotent**: Calling DELETE twice returns success both times  -H "Authorization: Bearer $TOKEN"

- **Best-Effort**: The cancellation signal is sent but completion is not guaranteed# Both return 204

- **Status Update**: Subsequently calling GET on this session should show "cancelled" status```

- **No Response Body**: Returns 204 with no content (just headers)

---

**Responses:**

## Session Steps

- **204 No Content** – Cancellation request accepted and processed

- **404 Not Found** – Session doesn't exist or you don't have permission to cancel it### List Session Steps

**GET /v1/agents/sessions/{session_id}/steps** – View all steps that have been added to a session

**Examples:**

**Why we need this endpoint:**

```bash- Track the history of what the agent has done (tools used, messages sent, errors)

# Cancel a session- Review step-by-step progression of the session workflow

curl -X DELETE http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000 \- Debug issues by examining individual step results and inputs

  -H "Authorization: Bearer $TOKEN"- Support pagination for sessions with many steps



# Safe to call again (idempotent)**What it does:**

curl -X DELETE http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000 \- Returns a paginated list of all steps in a session, ordered by sequence number

  -H "Authorization: Bearer $TOKEN"- Each step shows its type (message, tool call, error, etc.), content, and status

```- Includes timestamps for when each step was created and completed

- Supports cursor-based pagination for efficient loading

---- Caches results with ETag for bandwidth savings



## Session Steps**Access:**

- Users can view steps only for sessions they own

### List Session Steps- Admins can view steps for any session

- Requires authentication

**GET /v1/agents/sessions/{session_id}/steps** – View all steps that have been added to a session

**Behavior:**

**Why we need this endpoint:**- **Pagination**: Use `limit` (default 50) and `cursor` for paging through results

- **Ordering**: Steps appear in sequence number order (oldest to newest)

- Track the history of what the agent has done (tools used, messages sent, errors)- **ETag Caching**: Use `If-None-Match` header to get 304 if nothing changed

- Review step-by-step progression of the session workflow- **Rate Limiting**: Applies limits to prevent excessive list operations

- Debug issues by examining individual step results and inputs- **Ownership Validation**: Verifies session exists and you have access

- Support pagination for sessions with many steps

**Responses:**

**What it does:**- **200 OK** – Steps retrieved successfully; includes array of steps and optional next_cursor

- **304 Not Modified** – Step list unchanged since your last check (ETag matched)

- Returns a paginated list of all steps in a session, ordered by sequence number- **404 Not Found** – Session doesn't exist or you don't have permission to view it

- Each step shows its type (message, tool call, error, etc.), content, and status

- Includes timestamps for when each step was created and completed**Examples:**

- Supports cursor-based pagination for efficient loading```bash

- Caches results with ETag for bandwidth savings# Get first page of steps

curl -X GET "http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000/steps?limit=25" \

**Access:**  -H "Authorization: Bearer $TOKEN"



- Users can view steps only for sessions they own# Get next page

- Admins can view steps for any sessioncurl -X GET "http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000/steps?limit=25&cursor=..." \

- Requires authentication  -H "Authorization: Bearer $TOKEN"

```

**Behavior:**

---

- **Pagination**: Use `limit` (default 50) and `cursor` for paging through results

- **Ordering**: Steps appear in sequence number order (oldest to newest)### Add Step to Session

- **ETag Caching**: Use `If-None-Match` header to get 304 if nothing changed**POST /v1/agents/sessions/{session_id}/steps** – Submit a new step (message, tool input, etc.) to a session

- **Rate Limiting**: Applies limits to prevent excessive list operations

- **Ownership Validation**: Verifies session exists and you have access**Why we need this endpoint:**

- Add user messages to keep a conversation going

**Responses:**- Submit tool inputs and observe tool outputs

- Feed system messages or error information back to the agent

- **200 OK** – Steps retrieved successfully; includes array of steps and optional next_cursor- Build interactive multi-turn agent workflows step-by-step

- **304 Not Modified** – Step list unchanged since your last check (ETag matched)

- **404 Not Found** – Session doesn't exist or you don't have permission to view it**What it does:**

- Creates a new step within the specified session

**Examples:**- Automatically assigns the next sequence number

- Stores the step content (message, tool name, input/output data)

```bash- Marks the step status as queued/received

# Get first page of steps- Returns the created step with its assigned ID and sequence number

curl -X GET "http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000/steps?limit=25" \- Validates session is active before accepting the step

  -H "Authorization: Bearer $TOKEN"

**Access:**

# Get next page- Users can add steps only to sessions they own

curl -X GET "http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000/steps?limit=25&cursor=..." \- Admins can add steps to any session

  -H "Authorization: Bearer $TOKEN"- Requires authentication

```

**Behavior:**

---- **Sequencing**: Steps are automatically numbered in order within the session

- **Validation**: Session must exist and be in "active" status (not cancelled/completed)

### Add Step to Session- **Idempotency**: Include an `Idempotency-Key` header to safely retry

- **Type Validation**: Step type must be one of: message, user, assistant, tool, system, error

**POST /v1/agents/sessions/{session_id}/steps** – Submit a new step (message, tool input, etc.) to a session- **Async Processing**: Step is queued for processing; status updates as work progresses



**Why we need this endpoint:****Responses:**

- **201 Created** – Step created successfully; includes full step details with assigned ID and sequence

- Add user messages to keep a conversation going- **400 Bad Request** – Invalid request (invalid step type, session not active, etc.)

- Submit tool inputs and observe tool outputs- **404 Not Found** – Session doesn't exist or you don't have permission

- Feed system messages or error information back to the agent

- Build interactive multi-turn agent workflows step-by-step**Examples:**

```bash

**What it does:**# Add a user message to a session

curl -X POST http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000/steps \

- Creates a new step within the specified session  -H "Authorization: Bearer $TOKEN" \

- Automatically assigns the next sequence number  -H "Content-Type: application/json" \

- Stores the step content (message, tool name, input/output data)  -H "Idempotency-Key: step-msg-456" \

- Marks the step status as queued/received  -d '{

- Returns the created step with its assigned ID and sequence number    "type": "message",

- Validates session is active before accepting the step    "message": "Can you search for the latest AI news?"

  }'

**Access:**

# Add a tool call step

- Users can add steps only to sessions they owncurl -X POST http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000/steps \

- Admins can add steps to any session  -H "Authorization: Bearer $TOKEN" \

- Requires authentication  -H "Content-Type: application/json" \

  -d '{

**Behavior:**    "type": "tool",

    "tool": "web_search",

- **Sequencing**: Steps are automatically numbered in order within the session    "input": {"query": "latest AI news 2024"}

- **Validation**: Session must exist and be in "active" status (not cancelled/completed)  }'

- **Idempotency**: Include an `Idempotency-Key` header to safely retry

- **Type Validation**: Step type must be one of: message, user, assistant, tool, system, error# Add tool output/result step

- **Async Processing**: Step is queued for processing; status updates as work progressescurl -X POST http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000/steps \

  -H "Authorization: Bearer $TOKEN" \

**Responses:**  -H "Content-Type: application/json" \

  -d '{

- **201 Created** – Step created successfully; includes full step details with assigned ID and sequence    "type": "assistant",

- **400 Bad Request** – Invalid request (invalid step type, session not active, etc.)    "output": {"results": ["Article 1", "Article 2"]}

- **404 Not Found** – Session doesn't exist or you don't have permission  }'

```

**Examples:**

---

```bash

# Add a user message to a session## Agent Runs

curl -X POST http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000/steps \

  -H "Authorization: Bearer $TOKEN" \### Create Agent Run

  -H "Content-Type: application/json" \**POST /v1/agent-runs** – Execute a single agent task without needing a session

  -H "Idempotency-Key: step-msg-456" \

  -d '{**Why we need this endpoint:**

    "type": "message",- Solve a one-off task without setting up a full session

    "message": "Can you search for the latest AI news?"- Get a quick answer or processing result with a single request

  }'- Avoid session management overhead for simple scenarios

- Automatically create a session if you want results persisted

# Add a tool call step

curl -X POST http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000/steps \**What it does:**

  -H "Authorization: Bearer $TOKEN" \- Creates and executes an agent run with a single API call

  -H "Content-Type: application/json" \- Either uses an existing session (if you provide session_id) or auto-creates one

  -d '{- Orchestrates the agent to process your input and generate output

    "type": "tool",- Returns the final result along with metadata (execution time, model used, steps taken)

    "tool": "web_search",- Optionally returns individual steps showing the agent's reasoning and tool calls

    "input": {"query": "latest AI news 2024"}

  }'**Access:**

- Users can create runs (auto-created runs belong to that user)

# Add tool output/result step- Admins can create runs on behalf of other users

curl -X POST http://localhost:8000/v1/agents/sessions/550e8400-e29b-41d4-a716-446655440000/steps \- Requires authentication

  -H "Authorization: Bearer $TOKEN" \

  -H "Content-Type: application/json" \**Behavior:**

  -d '{- **Idempotency**: Include `Idempotency-Key` header to safely retry; same key returns same result

    "type": "assistant",- **Auto-Session Creation**: If no session_id provided, creates a session automatically for you

    "output": {"results": ["Article 1", "Article 2"]}- **Latency Tracking**: Measures and returns execution time in milliseconds

  }'- **Provenance**: Records the run in audit logs with trace ID for debugging

```- **Rate Limiting**: Enforces per-user rate limits on run creation

- **Demo Mode**: If orchestrator unavailable, returns a demo echo response

---

**Responses:**

## Agent Runs- **201 Created** – Run completed successfully; includes output and execution details with Location header

- **400 Bad Request** – Invalid request body or parameters (e.g., invalid session_id)

### Create Agent Run- **404 Not Found** – Session ID provided but session doesn't exist or not accessible



**POST /v1/agent-runs** – Execute a single agent task without needing a session**Examples:**

```bash

**Why we need this endpoint:**# One-off agent task without session

curl -X POST http://localhost:8000/v1/agent-runs \

- Solve a one-off task without setting up a full session  -H "Authorization: Bearer $TOKEN" \

- Get a quick answer or processing result with a single request  -H "Content-Type: application/json" \

- Avoid session management overhead for simple scenarios  -H "Idempotency-Key: run-search-789" \

- Automatically create a session if you want results persisted  -d '{

    "prompt": "Find and summarize the top 3 AI trends in 2024",

**What it does:**    "tools": ["web_search", "summarizer"],

    "temperature": 0.2,

- Creates and executes an agent run with a single API call    "max_steps": 5

- Either uses an existing session (if you provide session_id) or auto-creates one  }'

- Orchestrates the agent to process your input and generate output

- Returns the final result along with metadata (execution time, model used, steps taken)# Reuse existing session for follow-up

- Optionally returns individual steps showing the agent's reasoning and tool callscurl -X POST http://localhost:8000/v1/agent-runs \

  -H "Authorization: Bearer $TOKEN" \

**Access:**  -H "Content-Type: application/json" \

  -d '{

- Users can create runs (auto-created runs belong to that user)    "session_id": "550e8400-e29b-41d4-a716-446655440000",

- Admins can create runs on behalf of other users    "prompt": "Based on the previous search, which trend is most important?",

- Requires authentication    "tools": ["web_search", "summarizer"]

  }'

**Behavior:**

# Retry safely with idempotency

- **Idempotency**: Include `Idempotency-Key` header to safely retry; same key returns same resultcurl -X POST http://localhost:8000/v1/agent-runs \

- **Auto-Session Creation**: If no session_id provided, creates a session automatically for you  -H "Authorization: Bearer $TOKEN" \

- **Latency Tracking**: Measures and returns execution time in milliseconds  -H "Content-Type: application/json" \

- **Provenance**: Records the run in audit logs with trace ID for debugging  -H "Idempotency-Key: run-search-789" \

- **Rate Limiting**: Enforces per-user rate limits on run creation  -d '{

- **Demo Mode**: If orchestrator unavailable, returns a demo echo response    "prompt": "Find and summarize the top 3 AI trends in 2024",

    "tools": ["web_search", "summarizer"]

**Responses:**  }'

# Returns same result as first request

- **201 Created** – Run completed successfully; includes output and execution details with Location header```

- **400 Bad Request** – Invalid request body or parameters (e.g., invalid session_id)

- **404 Not Found** – Session ID provided but session doesn't exist or not accessible---



**Examples:**### Get Agent Run by ID

**GET /v1/agent-runs/{run_id}** – Retrieve details and results of a specific agent run

```bash

# One-off agent task without session**Why we need this endpoint:**

curl -X POST http://localhost:8000/v1/agent-runs \- Check on results of a run that was submitted earlier

  -H "Authorization: Bearer $TOKEN" \- Access the generated output and step-by-step execution details

  -H "Content-Type: application/json" \- Track execution metrics (how long it took, which model was used)

  -H "Idempotency-Key: run-search-789" \- Verify that a run succeeded or debug why it failed

  -d '{

    "prompt": "Find and summarize the top 3 AI trends in 2024",**What it does:**

    "tools": ["web_search", "summarizer"],- Returns complete details of a previously-created agent run

    "temperature": 0.2,- Includes the final output, execution metrics, and all steps taken

    "max_steps": 5- Shows which session the run was linked to (if any)

  }'- Provides tracing information (trace_id, event_id) for debugging

- Validates that you have permission to view this specific run

# Reuse existing session for follow-up

curl -X POST http://localhost:8000/v1/agent-runs \**Access:**

  -H "Authorization: Bearer $TOKEN" \- Users can view runs they created

  -H "Content-Type: application/json" \- Admins can view any run

  -d '{- Requires authentication

    "session_id": "550e8400-e29b-41d4-a716-446655440000",

    "prompt": "Based on the previous search, which trend is most important?",**Behavior:**

    "tools": ["web_search", "summarizer"]- **Ownership Check**: Endpoint verifies you own this run or you're an admin

  }'- **ETag Support**: Returns ETag for caching unchanged results

- **Tracing**: Includes trace_id and event_id for correlating logs

# Retry safely with idempotency- **Timestamps**: Shows when run started and finished

curl -X POST http://localhost:8000/v1/agent-runs \- **Full Context**: Includes associated session_id if run was linked to one

  -H "Authorization: Bearer $TOKEN" \

  -H "Content-Type: application/json" \**Responses:**

  -H "Idempotency-Key: run-search-789" \- **200 OK** – Run found and returned with complete details including output

  -d '{- **304 Not Modified** – Run details unchanged since your last check (ETag matched)

    "prompt": "Find and summarize the top 3 AI trends in 2024",- **404 Not Found** – Run doesn't exist or you don't have permission to view it

    "tools": ["web_search", "summarizer"]

  }'**Examples:**

``````bash

# Get run details

---curl -X GET http://localhost:8000/v1/agent-runs/660e8400-e29b-41d4-a716-446655440001 \

  -H "Authorization: Bearer $TOKEN"

### Get Agent Run by ID

# Response includes output, steps, execution time, trace info, etc.

**GET /v1/agent-runs/{run_id}** – Retrieve details and results of a specific agent run

# Efficient retry with ETag

**Why we need this endpoint:**curl -X GET http://localhost:8000/v1/agent-runs/660e8400-e29b-41d4-a716-446655440001 \

  -H "Authorization: Bearer $TOKEN" \

- Check on results of a run that was submitted earlier  -H "If-None-Match: \"run-v1-def456\""

- Access the generated output and step-by-step execution details```

- Track execution metrics (how long it took, which model was used)

- Verify that a run succeeded or debug why it failed---



**What it does:**## Common Patterns



- Returns complete details of a previously-created agent run### Idempotency

- Includes the final output, execution metrics, and all steps takenMany POST endpoints support an `Idempotency-Key` header for safe retries:

- Shows which session the run was linked to (if any)```bash

- Provides tracing information (trace_id, event_id) for debuggingcurl -X POST http://localhost:8000/v1/agents/sessions \

- Validates that you have permission to view this specific run  -H "Authorization: Bearer $TOKEN" \

  -H "Idempotency-Key: session-unique-123" \

**Access:**  -d '{...}'

```

- Users can view runs they createdIf the network fails and you resend with the same key, you get the exact same response without creating duplicates.

- Admins can view any run

- Requires authentication### ETag Caching (HTTP 304)

GET endpoints return an `ETag` header. On subsequent requests, include the ETag:

**Behavior:**```bash

curl -X GET http://localhost:8000/v1/agents/sessions \

- **Ownership Check**: Endpoint verifies you own this run or you're an admin  -H "Authorization: Bearer $TOKEN" \

- **ETag Support**: Returns ETag for caching unchanged results  -H "If-None-Match: \"abc123def456\""

- **Tracing**: Includes trace_id and event_id for correlating logs# Returns 304 Not Modified if unchanged (saves bandwidth)

- **Timestamps**: Shows when run started and finished```

- **Full Context**: Includes associated session_id if run was linked to one

### Pagination

**Responses:**List endpoints support cursor-based pagination:

```bash

- **200 OK** – Run found and returned with complete details including output# First request

- **304 Not Modified** – Run details unchanged since your last check (ETag matched)curl -X GET "http://localhost:8000/v1/agents/sessions?limit=10"

- **404 Not Found** – Run doesn't exist or you don't have permission to view it

# Response includes: items, next_cursor

**Examples:**

# Subsequent request

```bashcurl -X GET "http://localhost:8000/v1/agents/sessions?limit=10&cursor=$NEXT_CURSOR"

# Get run details```

curl -X GET http://localhost:8000/v1/agent-runs/660e8400-e29b-41d4-a716-446655440001 \

  -H "Authorization: Bearer $TOKEN"### Error Handling

All errors return RFC 7807 Problem Detail format:

# Response includes output, steps, execution time, trace info, etc.```json

{

# Efficient retry with ETag  "type": "https://example.com/problems/session-not-found",

curl -X GET http://localhost:8000/v1/agent-runs/660e8400-e29b-41d4-a716-446655440001 \  "title": "Session Not Found",

  -H "Authorization: Bearer $TOKEN" \  "detail": "Session 550e8400... does not exist",

  -H "If-None-Match: \"run-v1-def456\""  "status": 404,

```  "instance": "/v1/agents/sessions/550e8400..."

}

---```


## Common Patterns

### Idempotency

Many POST endpoints support an `Idempotency-Key` header for safe retries:

```bash
curl -X POST http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: session-unique-123" \
  -d '{...}'
```

If the network fails and you resend with the same key, you get the exact same response without creating duplicates.

### ETag Caching (HTTP 304)

GET endpoints return an `ETag` header. On subsequent requests, include the ETag:

```bash
curl -X GET http://localhost:8000/v1/agents/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "If-None-Match: \"abc123def456\""
```

Returns 304 Not Modified if unchanged (saves bandwidth)

### Pagination

List endpoints support cursor-based pagination:

```bash
# First request
curl -X GET "http://localhost:8000/v1/agents/sessions?limit=10"

# Response includes: items, next_cursor

# Subsequent request
curl -X GET "http://localhost:8000/v1/agents/sessions?limit=10&cursor=$NEXT_CURSOR"
```

### Error Handling

All errors return RFC 7807 Problem Detail format:

```json
{
  "type": "https://example.com/problems/session-not-found",
  "title": "Session Not Found",
  "detail": "Session 550e8400... does not exist",
  "status": 404,
  "instance": "/v1/agents/sessions/550e8400..."
}
```
