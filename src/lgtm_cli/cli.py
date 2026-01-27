import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from .config import load_config, DEFAULT_CONFIG_PATH
from .client import LokiClient, PrometheusClient, TempoClient


# Best practice defaults
DEFAULT_TIME_RANGE_MINUTES = 15  # Start with narrow time range
DEFAULT_LOKI_LIMIT = 50  # Reasonable limit for logs
DEFAULT_TEMPO_LIMIT = 20  # Reasonable limit for traces
DEFAULT_PROM_STEP = "60s"  # 1 minute resolution


def get_default_times(minutes: int = DEFAULT_TIME_RANGE_MINUTES) -> tuple[str, str]:
    """Get default start/end times (RFC3339) for the last N minutes."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=minutes)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_default_times_unix(minutes: int = DEFAULT_TIME_RANGE_MINUTES) -> tuple[str, str]:
    """Get default start/end times (Unix seconds) for the last N minutes."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=minutes)
    return str(int(start.timestamp())), str(int(now.timestamp()))


def output_json(data: dict):
    """Output JSON data, pretty-printed."""
    click.echo(json.dumps(data, indent=2))


def output_error(msg: str):
    """Output error message to stderr."""
    click.echo(f"Error: {msg}", err=True)


@click.group()
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), help="Config file path")
@click.option("--instance", "-i", help="Instance name from config")
@click.pass_context
def main(ctx, config: Path | None, instance: str | None):
    """LGTM CLI - Query Loki, Prometheus, and Tempo.

    Best practices are built-in:
    - Default time range: 15 minutes (use --start/--end to override)
    - Default limits: 50 for logs, 20 for traces
    - Always filter by labels when possible
    """
    ctx.ensure_object(dict)
    try:
        ctx.obj["config"] = load_config(config)
        ctx.obj["instance_name"] = instance
    except FileNotFoundError as e:
        output_error(str(e))
        output_error(f"Create a config file at {DEFAULT_CONFIG_PATH}")
        sys.exit(1)


# === LOKI COMMANDS ===

@main.group()
@click.pass_context
def loki(ctx):
    """Query Loki logs."""
    instance = ctx.obj["config"].get_instance(ctx.obj["instance_name"])
    if not instance.loki:
        output_error(f"Loki not configured for instance '{instance.name}'")
        sys.exit(1)
    ctx.obj["client"] = LokiClient(instance.loki)


@loki.command()
@click.argument("query")
@click.option("--start", "-s", help="Start time (RFC3339). Default: 15 minutes ago")
@click.option("--end", "-e", help="End time (RFC3339). Default: now")
@click.option("--limit", "-l", default=DEFAULT_LOKI_LIMIT, help=f"Max entries (default: {DEFAULT_LOKI_LIMIT})")
@click.option("--direction", "-d", type=click.Choice(["backward", "forward"]), default="backward")
@click.pass_context
def query(ctx, query: str, start: str | None, end: str | None, limit: int, direction: str):
    """Query logs with LogQL.

    Examples:

      lgtm loki query '{app="myapp"}'

      lgtm loki query '{app="myapp"} |= "error"' --limit 100

      lgtm loki query '{app="myapp"}' --start 2024-01-15T10:00:00Z --end 2024-01-15T11:00:00Z
    """
    default_start, default_end = get_default_times()
    try:
        result = ctx.obj["client"].query(
            query=query,
            start=start or default_start,
            end=end or default_end,
            limit=limit,
            direction=direction,
        )
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@loki.command()
@click.argument("query")
@click.option("--time", "-t", help="Evaluation time (RFC3339). Default: now")
@click.pass_context
def instant(ctx, query: str, time: str | None):
    """Run instant query (for metric queries like count_over_time).

    Examples:

      lgtm loki instant 'count_over_time({app="myapp"}[5m])'

      lgtm loki instant 'sum by (level) (count_over_time({app="myapp"} | json [5m]))'
    """
    try:
        result = ctx.obj["client"].query_instant(query, time)
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@loki.command()
@click.option("--start", "-s", help="Start time filter")
@click.option("--end", "-e", help="End time filter")
@click.pass_context
def labels(ctx, start: str | None, end: str | None):
    """List available labels.

    Use this first to discover what labels are available before querying.
    """
    try:
        result = ctx.obj["client"].labels(start, end)
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@loki.command("label-values")
@click.argument("label")
@click.option("--start", "-s", help="Start time filter")
@click.option("--end", "-e", help="End time filter")
@click.pass_context
def label_values(ctx, label: str, start: str | None, end: str | None):
    """List values for a label.

    Examples:

      lgtm loki label-values app

      lgtm loki label-values namespace
    """
    try:
        result = ctx.obj["client"].label_values(label, start, end)
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@loki.command()
@click.argument("match", nargs=-1, required=True)
@click.option("--start", "-s", help="Start time filter")
@click.option("--end", "-e", help="End time filter")
@click.pass_context
def series(ctx, match: tuple[str, ...], start: str | None, end: str | None):
    """List series matching selectors.

    Examples:

      lgtm loki series '{app="myapp"}'

      lgtm loki series '{namespace="prod"}' '{namespace="staging"}'
    """
    try:
        result = ctx.obj["client"].series(list(match), start, end)
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


# === PROMETHEUS COMMANDS ===

@main.group()
@click.pass_context
def prom(ctx):
    """Query Prometheus/Mimir metrics."""
    instance = ctx.obj["config"].get_instance(ctx.obj["instance_name"])
    if not instance.prometheus:
        output_error(f"Prometheus not configured for instance '{instance.name}'")
        sys.exit(1)
    ctx.obj["client"] = PrometheusClient(instance.prometheus)


@prom.command()
@click.argument("query")
@click.option("--time", "-t", help="Evaluation time (RFC3339). Default: now")
@click.pass_context
def query(ctx, query: str, time: str | None):
    """Run instant query.

    Examples:

      lgtm prom query 'up{job="prometheus"}'

      lgtm prom query 'rate(http_requests_total[5m])'
    """
    try:
        result = ctx.obj["client"].query(query, time)
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@prom.command()
@click.argument("query")
@click.option("--start", "-s", help="Start time (RFC3339). Default: 15 minutes ago")
@click.option("--end", "-e", help="End time (RFC3339). Default: now")
@click.option("--step", default=DEFAULT_PROM_STEP, help=f"Resolution step (default: {DEFAULT_PROM_STEP})")
@click.pass_context
def range(ctx, query: str, start: str | None, end: str | None, step: str):
    """Run range query.

    Examples:

      lgtm prom range 'rate(http_requests_total[5m])'

      lgtm prom range 'up' --step 5m --start 2024-01-15T10:00:00Z
    """
    default_start, default_end = get_default_times()
    try:
        result = ctx.obj["client"].query_range(
            query=query,
            start=start or default_start,
            end=end or default_end,
            step=step,
        )
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@prom.command()
@click.option("--start", "-s", help="Start time filter")
@click.option("--end", "-e", help="End time filter")
@click.pass_context
def labels(ctx, start: str | None, end: str | None):
    """List available labels.

    Use this first to discover what labels are available.
    """
    try:
        result = ctx.obj["client"].labels(start, end)
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@prom.command("label-values")
@click.argument("label")
@click.option("--start", "-s", help="Start time filter")
@click.option("--end", "-e", help="End time filter")
@click.pass_context
def prom_label_values(ctx, label: str, start: str | None, end: str | None):
    """List values for a label.

    Examples:

      lgtm prom label-values job

      lgtm prom label-values __name__  # List all metric names
    """
    try:
        result = ctx.obj["client"].label_values(label, start, end)
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@prom.command()
@click.argument("match", nargs=-1, required=True)
@click.option("--start", "-s", help="Start time filter")
@click.option("--end", "-e", help="End time filter")
@click.pass_context
def series(ctx, match: tuple[str, ...], start: str | None, end: str | None):
    """List series matching selectors.

    Examples:

      lgtm prom series 'up'

      lgtm prom series 'http_requests_total{job="api"}'
    """
    try:
        result = ctx.obj["client"].series(list(match), start, end)
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@prom.command()
@click.option("--metric", "-m", help="Filter by metric name")
@click.pass_context
def metadata(ctx, metric: str | None):
    """Get metric metadata.

    Examples:

      lgtm prom metadata

      lgtm prom metadata --metric http_requests_total
    """
    try:
        result = ctx.obj["client"].metadata(metric)
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


# === TEMPO COMMANDS ===

@main.group()
@click.pass_context
def tempo(ctx):
    """Query Tempo traces."""
    instance = ctx.obj["config"].get_instance(ctx.obj["instance_name"])
    if not instance.tempo:
        output_error(f"Tempo not configured for instance '{instance.name}'")
        sys.exit(1)
    ctx.obj["client"] = TempoClient(instance.tempo)


@tempo.command()
@click.argument("trace_id")
@click.pass_context
def trace(ctx, trace_id: str):
    """Get trace by ID.

    Use this when you have a specific trace ID to investigate.

    Examples:

      lgtm tempo trace abc123def456
    """
    try:
        result = ctx.obj["client"].trace(trace_id)
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@tempo.command()
@click.option("--query", "-q", help="TraceQL query")
@click.option("--start", "-s", help="Start time (Unix seconds). Default: 15 minutes ago")
@click.option("--end", "-e", help="End time (Unix seconds). Default: now")
@click.option("--min-duration", help="Minimum duration (e.g., 100ms, 1s)")
@click.option("--max-duration", help="Maximum duration")
@click.option("--limit", "-l", default=DEFAULT_TEMPO_LIMIT, help=f"Max traces (default: {DEFAULT_TEMPO_LIMIT})")
@click.pass_context
def search(ctx, query: str | None, start: str | None, end: str | None,
           min_duration: str | None, max_duration: str | None, limit: int):
    """Search traces with TraceQL.

    Examples:

      lgtm tempo search -q '{resource.service.name="api"}'

      lgtm tempo search -q '{status=error}' --min-duration 1s

      lgtm tempo search --min-duration 500ms --limit 50
    """
    default_start, default_end = get_default_times_unix()
    try:
        result = ctx.obj["client"].search(
            query=query,
            start=start or default_start,
            end=end or default_end,
            min_duration=min_duration,
            max_duration=max_duration,
            limit=limit,
        )
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@tempo.command()
@click.pass_context
def tags(ctx):
    """List available tags.

    Use this first to discover what tags/attributes are available.
    """
    try:
        result = ctx.obj["client"].tags()
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


@tempo.command("tag-values")
@click.argument("tag")
@click.pass_context
def tag_values(ctx, tag: str):
    """List values for a tag.

    Examples:

      lgtm tempo tag-values service.name

      lgtm tempo tag-values http.status_code
    """
    try:
        result = ctx.obj["client"].tag_values(tag)
        output_json(result)
    except Exception as e:
        output_error(str(e))
        sys.exit(1)


# === CONFIG COMMANDS ===

@main.command()
@click.pass_context
def instances(ctx):
    """List configured instances."""
    config = ctx.obj["config"]
    result = {
        "default": config.default_instance,
        "instances": {}
    }
    for name, instance in config.instances.items():
        result["instances"][name] = {
            "loki": instance.loki.url if instance.loki else None,
            "prometheus": instance.prometheus.url if instance.prometheus else None,
            "tempo": instance.tempo.url if instance.tempo else None,
        }
    output_json(result)


if __name__ == "__main__":
    main()
