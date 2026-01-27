import os
import re
import subprocess
from pathlib import Path
from dataclasses import dataclass

import yaml


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "lgtm" / "config.yaml"


@dataclass
class ServiceConfig:
    url: str
    token: str | None = None
    username: str | None = None
    headers: dict[str, str] | None = None


@dataclass
class InstanceConfig:
    name: str
    loki: ServiceConfig | None = None
    prometheus: ServiceConfig | None = None
    tempo: ServiceConfig | None = None
    alerting: ServiceConfig | None = None


@dataclass
class Config:
    version: str
    default_instance: str | None
    instances: dict[str, InstanceConfig]

    def get_instance(self, name: str | None = None) -> InstanceConfig:
        if name:
            if name not in self.instances:
                raise ValueError(f"Instance '{name}' not found in config")
            return self.instances[name]
        if self.default_instance:
            return self.instances[self.default_instance]
        return next(iter(self.instances.values()))


def resolve_1password_ref(ref: str) -> str:
    """Resolve a 1Password reference using the op CLI.

    Args:
        ref: 1Password reference in format 'op://vault/item/field'

    Returns:
        The secret value from 1Password

    Raises:
        RuntimeError: If op CLI fails or is not available
    """
    try:
        result = subprocess.run(
            ["op", "read", ref],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except FileNotFoundError:
        raise RuntimeError("1Password CLI (op) not found. Install it from https://1password.com/downloads/command-line/")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to read from 1Password: {e.stderr.strip()}")


def resolve_secret(value: str) -> str:
    """Resolve secrets from environment variables or 1Password.

    Supports:
    - Environment variables: ${VAR_NAME}
    - 1Password references: op://vault/item/field

    Args:
        value: The value to resolve

    Returns:
        The resolved value with secrets substituted
    """
    # Check if entire value is a 1Password reference
    if value.startswith("op://"):
        return resolve_1password_ref(value)

    # Handle ${op://...} pattern for 1Password within strings
    op_pattern = r'\$\{(op://[^}]+)\}'
    def replace_op(match):
        return resolve_1password_ref(match.group(1))
    value = re.sub(op_pattern, replace_op, value)

    # Handle ${VAR_NAME} pattern for environment variables
    env_pattern = r'\$\{([^}]+)\}'
    def replace_env(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")
    return re.sub(env_pattern, replace_env, value)


def parse_service_config(data: dict | None) -> ServiceConfig | None:
    if not data:
        return None
    return ServiceConfig(
        url=resolve_secret(data.get("url", "")),
        token=resolve_secret(data["token"]) if data.get("token") else None,
        username=resolve_secret(data["username"]) if data.get("username") else None,
        headers={k: resolve_secret(v) for k, v in data.get("headers", {}).items()} or None,
    )


def load_config(path: Path | None = None) -> Config:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    instances = {}
    for name, instance_data in data.get("instances", {}).items():
        instances[name] = InstanceConfig(
            name=name,
            loki=parse_service_config(instance_data.get("loki")),
            prometheus=parse_service_config(instance_data.get("prometheus")),
            tempo=parse_service_config(instance_data.get("tempo")),
            alerting=parse_service_config(instance_data.get("alerting")),
        )

    return Config(
        version=data.get("version", "1"),
        default_instance=data.get("default_instance"),
        instances=instances,
    )
