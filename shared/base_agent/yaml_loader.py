"""YAML skill loader - loads skill metadata and prompts from YAML files."""
import importlib.resources
from pathlib import Path
from typing import Any

import yaml


def load_skill_yaml(skill_dir: Path, skill_name: str) -> dict[str, Any]:
    """Load skill definition from YAML file."""
    yaml_path = skill_dir / f"{skill_name}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"Skill YAML not found: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_skill_metadata(yaml_data: dict) -> dict[str, Any]:
    """Extract metadata from YAML data."""
    return {
        "id": yaml_data.get("id", ""),
        "name": yaml_data.get("name", ""),
        "description": yaml_data.get("description", ""),
        "tags": yaml_data.get("tags", []),
        "examples": yaml_data.get("examples", []),
    }


def get_skill_tools(yaml_data: dict) -> list[dict]:
    """Extract tool definitions from YAML data."""
    return yaml_data.get("tools", [])


def get_skill_prompt(yaml_data: dict) -> str:
    """Extract prompt instructions from YAML data."""
    return yaml_data.get("prompt", "")
