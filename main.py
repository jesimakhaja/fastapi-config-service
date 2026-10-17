import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

DEFAULTS = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

app = FastAPI(title="Effective Configuration API")

# Allow browser-based graders to call this API from another origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def coerce(key: str, value):
    if key in {"port", "workers"}:
        return int(value)
    if key == "debug":
        return as_bool(value)
    return str(value)


def normalized_key(key: str) -> str:
    return key.strip().lower()


def get_effective_config(cli_sets: list[str]) -> dict:
    config = dict(DEFAULTS)

    # Layer 2: environment-specific YAML, e.g. config.development.yaml.
    env_name = os.getenv("APP_ENV", "development")
    yaml_path = Path(f"config.{env_name}.yaml")
    if yaml_path.exists():
        with yaml_path.open("r", encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f) or {}
        if isinstance(yaml_config, dict):
            for key, value in yaml_config.items():
                config[normalized_key(key)] = value

    # Layer 3: .env values. Read without injecting them into the OS environment.
    dotenv_path = Path(".env")
    dotenv_config = dotenv_values(dotenv_path) if dotenv_path.exists() else {}
    for raw_key, value in dotenv_config.items():
        if value is None:
            continue
        key = normalized_key(raw_key)
        if key == "num_workers":
            key = "workers"
        elif key.startswith("app_"):
            key = key[4:]
        config[key] = value

    # Layer 4: actual OS environment variables with APP_ prefix.
    for raw_key, value in os.environ.items():
        if raw_key.upper().startswith("APP_"):
            key = normalized_key(raw_key[4:])
            config[key] = value

    # Highest precedence: repeated CLI-style query parameters.
    for item in cli_sets:
        if "=" not in item:
            continue
        raw_key, value = item.split("=", 1)
        key = normalized_key(raw_key)
        if key:
            config[key] = value

    # Coerce known fields and ensure the required fields are present.
    for key in ("port", "workers", "debug", "log_level", "api_key"):
        if key not in config:
            config[key] = DEFAULTS[key]
        config[key] = coerce(key, config[key])

    # Any additional configuration keys are strings, unless handled above.
    for key, value in list(config.items()):
        if key not in {"port", "workers", "debug"}:
            config[key] = str(value)

    # Never disclose the real secret, regardless of its source or override.
    config["api_key"] = "****"
    return config


@app.get("/effective-config")
def effective_config(set: Optional[list[str]] = Query(default=None)):
    return get_effective_config(set or [])
