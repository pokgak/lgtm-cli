# LGTM CLI

Lightweight CLI for querying Loki, Prometheus/Mimir, and Tempo.

## Installation

**Requires Python 3.12+**

```bash
# Install globally
uv tool install git+https://github.com/pokgak/lgtm-cli

# Or run directly without installing
uvx --from git+https://github.com/pokgak/lgtm-cli lgtm --help
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

## Configuration

Create config at `~/.config/lgtm/config.yaml`:

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
      token: "${LOKI_TOKEN}"  # Bearer auth
    prometheus:
      url: "https://mimir.example.com"
      username: "${MIMIR_USER}"  # Basic auth
      token: "${MIMIR_TOKEN}"
    tempo:
      url: "https://tempo.example.com"
      token: "${TEMPO_TOKEN}"
      headers:
        X-Scope-OrgID: "my-tenant"
```

Environment variables (`${VAR_NAME}`) are expanded at runtime.

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

## Compatibility

Config format is compatible with [lgtm-mcp](https://github.com/pokgak/lgtm-mcp) for easy migration.
