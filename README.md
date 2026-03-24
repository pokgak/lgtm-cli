# LGTM CLI

Lightweight CLI for querying Loki, Prometheus/Mimir, and Tempo.

## Installation

**Requires Python 3.12+**

```bash
# Run directly without installing
uvx lgtm-cli --help

# Or install globally
uv tool install lgtm-cli
```

## Usage

```bash
# List configured instances
lgtm instances

# Query Loki logs (defaults: last 15 min, limit 50)
lgtm loki query '{app="myapp"} |= "error"'

# Query Prometheus metrics
lgtm prom query 'rate(http_requests_total[5m])'

# Search Tempo traces (defaults: last 15 min, limit 20)
lgtm tempo search -q '{resource.service.name="api"}'

# Use specific instance
lgtm -i production loki labels
```

## Grafana Cloud Auto-Discovery

Automatically discover all stacks in your Grafana Cloud org and generate config entries.

**Requirements:** A Grafana Cloud Access Policy token with the `stacks:read` scope.
Create one at: **Grafana Cloud → Administration → Cloud Access Policies**.

```bash
# Discover all accessible stacks
GRAFANA_CLOUD_API_TOKEN=glc_xxx lgtm discover

# Discover stacks for a specific org
lgtm discover --org myorg --token glc_xxx

# Preview without writing
lgtm discover --dry-run

# Overwrite existing entries
lgtm discover --overwrite
```

This generates config entries for each active stack with Loki, Prometheus, and Tempo endpoints.
Alerting is not included as it requires per-stack service account tokens.

## Configuration

Create config at `~/.config/lgtm/config.yaml` (or use `lgtm discover` to generate it):

```yaml
version: "1"
default_instance: "local"

instances:
  local:
    loki:
      url: "http://localhost:3100"
    prometheus:
      url: "http://localhost:9090"
    tempo:
      url: "http://localhost:3200"
```

### Authentication

| Config Fields | Auth Type | Description |
|---------------|-----------|-------------|
| `token` only | Bearer | `Authorization: Bearer <token>` header |
| `username` + `token` | Basic | HTTP Basic auth |
| `headers` | Custom | Custom headers (e.g., `X-Scope-OrgID` for multi-tenant) |

Example with authentication:

```yaml
version: "1"
default_instance: "production"

instances:
  production:
    loki:
      url: "https://loki.example.com"
      token: "${LOKI_TOKEN}"  # Bearer auth (env var)
    prometheus:
      url: "https://mimir.example.com"
      username: "${MIMIR_USER}"  # Basic auth
      token: "op://vault/mimir/token"  # 1Password reference
    tempo:
      url: "https://tempo.example.com"
      token: "${TEMPO_TOKEN}"
      headers:
        X-Scope-OrgID: "my-tenant"
```

Secrets are resolved at runtime:
- Environment variables: `${VAR_NAME}`
- 1Password references: `op://vault/item/field` (requires [1Password CLI](https://1password.com/downloads/command-line/))

## Built-in Best Practices

- **Default time range:** 15 minutes (not hours/days)
- **Default limits:** 50 for logs, 20 for traces
- **Discovery commands:** Explore labels/metrics/tags first

### Recommended Workflow

1. **Discover** what's available:
   ```bash
   lgtm loki labels
   lgtm loki label-values app
   ```

2. **Aggregate** to get overview:
   ```bash
   lgtm loki instant 'sum by (app) (count_over_time({namespace="prod"} |= "error" [15m]))'
   ```

3. **Drill down** to specifics:
   ```bash
   lgtm loki query '{namespace="prod", app="checkout"} |= "error"' --limit 20
   ```

## Commands

### Loki

```bash
lgtm loki labels                  # List available labels
lgtm loki label-values <label>    # List values for a label
lgtm loki query <logql>           # Query logs
lgtm loki instant <logql>         # Instant query (for aggregations)
lgtm loki series <selector>...    # List series
```

### Prometheus

```bash
lgtm prom labels                  # List available labels
lgtm prom label-values <label>    # List values for a label
lgtm prom query <promql>          # Instant query
lgtm prom range <promql>          # Range query
lgtm prom series <selector>...    # List series
lgtm prom metadata                # Get metric metadata
```

### Tempo

```bash
lgtm tempo tags                   # List available tags
lgtm tempo tag-values <tag>       # List values for a tag
lgtm tempo search                 # Search traces
lgtm tempo trace <trace_id>       # Get trace by ID
```

### Alerts

```bash
lgtm alerts list                  # List firing alerts
lgtm alerts groups                # List alerts grouped by receiver/labels
lgtm alerts silences              # List all silences
lgtm alerts silence-get <id>      # Get a specific silence
lgtm alerts silence-create        # Create a new silence
lgtm alerts silence-delete <id>   # Delete/expire a silence
```

### Discovery

```bash
lgtm discover                     # Discover Grafana Cloud stacks
lgtm discover --org <slug>        # Discover stacks for a specific org
lgtm discover --dry-run           # Preview without writing config
lgtm instances                    # List configured instances
```

## Agent Integration

lgtm-cli is designed to be agent-friendly. All commands output JSON by default, and additional features help AI agents use the CLI programmatically.

### Command Schema Discovery

Agents can introspect the full command tree as JSON without parsing `--help` text:

```bash
lgtm schema              # Full schema with query syntax and defaults
lgtm schema --compact    # Minimal schema (names and flags only, fewer tokens)
```

### Response Envelope

Use the `--envelope` flag (or set `LGTM_ENVELOPE=1`) to wrap all responses in a consistent envelope:

```bash
lgtm --envelope loki query '{app="myapp"}'
```

```json
{
  "status": "success",
  "data": { "..." },
  "metadata": {
    "command": "lgtm loki query",
    "count": 42
  }
}
```

Errors in envelope mode include actionable suggestions:

```json
{
  "status": "error",
  "error_message": "Loki not configured for instance 'production'",
  "metadata": { "command": "lgtm loki" },
  "suggestions": [
    "Add a 'loki' section to this instance in config",
    "Or run 'lgtm discover' to auto-configure"
  ]
}
```

## Compatibility

Config format is compatible with [lgtm-mcp](https://github.com/pokgak/lgtm-mcp) for easy migration.
