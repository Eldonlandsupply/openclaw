#!/usr/bin/env python3
"""
Validate all projects/<slug>/project.yaml files against the project binding schema.
Runs in CI and locally: python3 .github/scripts/validate_projects.py
"""
import sys
import os
import yaml
import jsonschema
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent  # repo root

PROJECT_SCHEMA = {
    "type": "object",
    "required": ["slug", "name", "description", "status", "priority", "owner", "created", "updated"],
    "properties": {
        "slug": {
            "type": "string",
            "pattern": "^[a-z0-9-]+$",
            "description": "Lowercase, hyphens only"
        },
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string", "minLength": 10},
        "status": {"type": "string", "enum": ["active", "paused", "archived", "planning"]},
        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
        "owner": {"type": "string", "minLength": 1},
        "created": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "updated": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "operating_mode": {
            "type": "string",
            "enum": ["always-on", "scheduled", "on-demand", "manual"]
        },
        "related_source": {"type": "string"},
        "related_agents": {"type": "array", "items": {"type": "string"}},
        "related_workflows": {"type": "array", "items": {"type": "string"}},
        "external_systems": {"type": "array", "items": {"type": "string"}},
        "status_note": {"type": "string"},
    },
    "additionalProperties": False
}

INDEX_SCHEMA = {
    "type": "object",
    "required": ["projects"],
    "properties": {
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["slug", "name", "path", "status", "priority", "description", "owner"],
                "properties": {
                    "slug": {"type": "string", "pattern": "^[a-z0-9-]+$"},
                    "name": {"type": "string"},
                    "path": {"type": "string"},
                    "status": {"type": "string"},
                    "priority": {"type": "string"},
                    "description": {"type": "string"},
                    "owner": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "operating_mode": {"type": "string"},
                    "related_source": {"type": "string"},
                    "created": {"type": "string"},
                    "updated": {"type": "string"},
                },
                "additionalProperties": False
            }
        }
    }
}

errors = []
validated = []

# 1. Validate projects/index.yaml
index_path = ROOT / "projects" / "index.yaml"
if not index_path.exists():
    errors.append("MISSING: projects/index.yaml")
else:
    try:
        with open(index_path) as f:
            index_data = yaml.safe_load(f)
        jsonschema.validate(index_data, INDEX_SCHEMA)
        validated.append(str(index_path.relative_to(ROOT)))
        print(f"✓ projects/index.yaml  ({len(index_data.get('projects', []))} projects)")
    except Exception as e:
        errors.append(f"projects/index.yaml: {e}")

# 2. Validate each projects/<slug>/project.yaml
projects_dir = ROOT / "projects"
slugs_in_index = set()
if index_path.exists():
    try:
        idx = yaml.safe_load(open(index_path))
        slugs_in_index = {p["slug"] for p in idx.get("projects", [])}
    except Exception:
        pass

for project_dir in sorted(projects_dir.iterdir()):
    if not project_dir.is_dir() or project_dir.name.startswith("_"):
        continue
    manifest = project_dir / "project.yaml"
    if not manifest.exists():
        errors.append(f"MISSING: {project_dir.name}/project.yaml")
        continue
    try:
        with open(manifest) as f:
            data = yaml.safe_load(f)
        jsonschema.validate(data, PROJECT_SCHEMA)

        # slug must match directory name
        if data.get("slug") != project_dir.name:
            errors.append(
                f"{manifest.relative_to(ROOT)}: slug '{data.get('slug')}' must match directory name '{project_dir.name}'"
            )
            continue

        # slug must be in index
        if data["slug"] not in slugs_in_index:
            errors.append(
                f"{manifest.relative_to(ROOT)}: slug '{data['slug']}' not found in projects/index.yaml"
            )
            continue

        # README.md must exist
        readme = project_dir / "README.md"
        if not readme.exists():
            errors.append(f"MISSING: {project_dir.name}/README.md")
            continue

        validated.append(str(manifest.relative_to(ROOT)))
        print(f"✓ {manifest.relative_to(ROOT)}  (slug={data['slug']}, status={data['status']})")
    except jsonschema.ValidationError as e:
        errors.append(f"{manifest.relative_to(ROOT)}: schema error — {e.message} (path: {list(e.absolute_path)})")
    except Exception as e:
        errors.append(f"{manifest.relative_to(ROOT)}: {e}")

# 3. Check for orphaned project dirs (in projects/ but not in index)
if index_path.exists():
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir() and not project_dir.name.startswith("_"):
            if project_dir.name not in slugs_in_index:
                errors.append(
                    f"projects/{project_dir.name}/ exists but has no entry in projects/index.yaml"
                )

print()
print(f"Validated {len(validated)} file(s).")

if errors:
    print(f"\n{len(errors)} error(s) found:\n")
    for e in errors:
        print(f"  ✗ {e}")
    sys.exit(1)
else:
    print("All project bindings are valid.")
