# Cineca CLI

A lightweight command-line interface for the Cineca Agentic Platform. Perfect for scripting, automation, and developers who prefer the terminal.

## Quick Start

### 1. Make Executable

```bash
chmod +x examples/cli/cineca-cli
```

### 2. (Optional) Add to PATH

```bash
# Add to your shell profile (~/.zshrc or ~/.bashrc)
export PATH="$PATH:/path/to/Cineca-Agentic-Platform/examples/cli"

# Or create a symlink
sudo ln -s /path/to/Cineca-Agentic-Platform/examples/cli/cineca-cli /usr/local/bin/cineca-cli
```

### 3. Set Environment Variables

```bash
# API endpoint (defaults to http://localhost:8080)
export CINECA_API_BASE="http://localhost:8080"

# Authentication token (get from quickstart guide)
export CINECA_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### 4. Try It Out

```bash
# Check API health
cineca-cli health

# List all agents
cineca-cli list

# Create a new agent
cineca-cli create --name "MyCLIAgent" --model "gpt-4" --description "Agent created from CLI"

# Ask a question (replace agent_abc123 with actual agent ID)
cineca-cli ask agent_abc123 "What is 15 * 23?"

# View agent run history
cineca-cli runs agent_abc123
```

## Commands

### `health` - Check API Health

Check if the API is reachable and healthy.

```bash
cineca-cli health
```

**Output:**
```
✅ API is healthy!
   Status: healthy
   Version: 1.0.0
```

### `list` - List All Agents

List all available agents.

```bash
cineca-cli list
```

**Output:**
```
🤖 Found 2 agent(s):

  📋 QuickstartAgent (agent_abc123)
     Model: gpt-4, Temp: 0.7
     My first AI agent!

  📋 MathBot (agent_def456)
     Model: gpt-3.5-turbo, Temp: 0.3
     Specialized in mathematical calculations
```

### `create` - Create a New Agent

Create a new agent with custom configuration.

```bash
cineca-cli create \
  --name "MathBot" \
  --model "gpt-3.5-turbo" \
  --description "Specialized in math"
```

**Options:**
- `--name` (required): Agent name
- `--model` (required): LLM model (e.g., `gpt-4`, `gpt-3.5-turbo`)
- `--description` (optional): Agent description

**Output:**
```
✅ Successfully created agent!
   Name: MathBot
   ID: agent_xyz789
   Model: gpt-3.5-turbo
```

### `ask` - Ask a Question

Ask an agent a question and get a response.

```bash
cineca-cli ask agent_abc123 "What is the capital of France?"
```

**Output:**
```
🤔 Asking agent...

🤖 Agent Response:

   The capital of France is Paris.

📊 Metadata:
   Run ID: run_123456
   Status: completed
   Tokens: 15 total
   Duration: 1234ms
```

### `runs` - View Run History

View recent runs for an agent.

```bash
cineca-cli runs agent_abc123 --limit 5
```

**Options:**
- `--limit` (optional): Number of runs to show (default: 5)

**Output:**
```
📊 Recent runs for agent agent_abc123:

  1. Run ID: run_123456
     Input: What is the capital of France?...
     Output: The capital of France is Paris....
     Status: completed, Created: 2025-01-20T10:30:00Z

  2. Run ID: run_123455
     Input: Calculate 15 * 23...
     Output: 15 * 23 = 345...
     Status: completed, Created: 2025-01-20T10:25:00Z
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CINECA_API_BASE` | API endpoint | `http://localhost:8080` |
| `CINECA_TOKEN` | JWT authentication token | None (warning shown) |

### Setting Up Authentication

1. **Get a demo token** from the quickstart guide (`docs/QUICKSTART.md`)
2. **Or get a real token** from your OIDC provider (see `docs/AUTH_GUIDE.md`)
3. **Set the token:**

```bash
export CINECA_TOKEN="your-jwt-token-here"
```

**Tip:** Add this to your `~/.zshrc` or `~/.bashrc` to persist across sessions.

## Examples

### Example 1: Create and Use an Agent

```bash
# Create a new agent
cineca-cli create --name "WriteBot" --model "gpt-4" --description "Creative writing assistant"

# Ask it a question (use the ID from create output)
cineca-cli ask agent_abc123 "Write a haiku about programming"

# View its run history
cineca-cli runs agent_abc123
```

### Example 2: Scripting with the CLI

```bash
#!/bin/bash
# automation.sh - Automated agent testing

AGENT_ID="agent_abc123"
QUESTIONS=(
  "What is 2+2?"
  "Explain quantum computing in one sentence"
  "What is the meaning of life?"
)

for question in "${QUESTIONS[@]}"; do
  echo "Asking: $question"
  cineca-cli ask "$AGENT_ID" "$question"
  echo "---"
done
```

### Example 3: CI/CD Integration

```yaml
# .github/workflows/test-agent.yml
name: Test Agent
on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Test Agent API
        env:
          CINECA_API_BASE: ${{ secrets.API_BASE }}
          CINECA_TOKEN: ${{ secrets.API_TOKEN }}
        run: |
          chmod +x examples/cli/cineca-cli
          examples/cli/cineca-cli health
          examples/cli/cineca-cli list
```

## Troubleshooting

### "Cannot reach API"

**Problem:** CLI can't connect to the API.

**Solution:**
1. Check if the API is running: `docker-compose ps`
2. Verify API_BASE: `echo $CINECA_API_BASE`
3. Test with curl: `curl http://localhost:8080/health`

### "No token set" Warning

**Problem:** No authentication token configured.

**Solution:**
```bash
export CINECA_TOKEN="your-jwt-token"
```

Get a token from:
- Demo token in `docs/QUICKSTART.md`
- Your OIDC provider (see `docs/AUTH_GUIDE.md`)

### "403 Forbidden"

**Problem:** Token doesn't have required permissions.

**Solution:**
- Check token permissions with `jwt.io`
- Ensure token has required scopes (e.g., `read:agents`, `write:agents`, `run:agents`)
- See `docs/AUTH_GUIDE.md` for role configuration

### "Agent not found"

**Problem:** Invalid agent ID.

**Solution:**
1. List all agents: `cineca-cli list`
2. Use the correct agent ID from the list
3. Or create a new agent: `cineca-cli create --name "MyAgent" --model "gpt-4"`

## Advanced Usage

### Custom API Endpoint

```bash
# Connect to a remote API
export CINECA_API_BASE="https://api.example.com"
cineca-cli health
```

### JSON Output (Future Enhancement)

The CLI currently outputs human-readable text. For JSON output (useful for scripting), you can modify the script or use the API directly with `curl`:

```bash
# Direct API call with JSON output
curl -H "Authorization: Bearer $CINECA_TOKEN" \
     http://localhost:8080/api/v1/agents | jq .
```

## Development

### Project Structure

```
examples/cli/
├── cineca-cli      # Main CLI script (Python)
└── README.md       # This file
```

### Dependencies

The CLI only requires Python 3.7+ and the `requests` library:

```bash
pip install requests
```

### Adding New Commands

1. Add a new subparser in `main()`:
   ```python
   new_parser = subparsers.add_parser("newcmd", help="New command")
   new_parser.add_argument("--option", help="An option")
   ```

2. Add a handler function:
   ```python
   def handle_newcmd(option: str):
       print(f"Handling newcmd with option: {option}")
   ```

3. Add to the command dispatcher:
   ```python
   elif args.command == "newcmd":
       handle_newcmd(args.option)
   ```

## Resources

- **Quickstart Guide**: `docs/QUICKSTART.md`
- **Authentication Guide**: `docs/AUTH_GUIDE.md`
- **API Documentation**: `api/openapi.json`
- **Streamlit UI**: `ops/ui_streamlit/` (alternative to CLI)

## License

Same as the Cineca Agentic Platform. See `LICENSE` file.

## Support

For issues or questions:
1. Check the troubleshooting section above
2. See the full platform documentation in `docs/`
3. Run `cineca-cli --help` for command reference
