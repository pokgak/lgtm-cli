import os
import re
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


def expand_env_vars(value: str) -> str:
    pattern = r'\$\{([^}]+)\}'
    def replace(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")
    return re.sub(pattern, replace, value)


def parse_service_config(data: dict | None) -> ServiceConfig | None:
    if not data:
        return None
    return ServiceConfig(
        url=expand_env_vars(data.get("url", "")),
        token=expand_env_vars(data["token"]) if data.get("token") else None,
        username=expand_env_vars(data["username"]) if data.get("username") else None,
        headers={k: expand_env_vars(v) for k, v in data.get("headers", {}).items()} or None,
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
        )

    return Config(
        version=data.get("version", "1"),
        default_instance=data.get("default_instance"),
        instances=instances,
    )
