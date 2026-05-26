"""
validate_config.py – Pre-deployment validation
===============================================
Validates all Fabric item .platform files and environment config files
before any deployment occurs. Runs in the CI (PR) workflow.

Checks performed:
  - Every item folder has a .platform file
  - .platform files are valid JSON with required fields
  - logicalId GUIDs are unique across items (no accidental duplicates)
  - Item type names match the supported Fabric item type list
  - Environment config files have all required keys
"""

import json
import sys
import uuid
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
FABRIC_ITEMS_DIR = REPO_ROOT / "fabric_items"
CONFIG_DIR = REPO_ROOT / "config"
ENVIRONMENTS = ["dev", "staging", "prod"]

# Supported Fabric item types (as of 2026)
# Ref: https://learn.microsoft.com/en-us/rest/api/fabric/core/items
SUPPORTED_ITEM_TYPES = {
    "Notebook",
    "DataPipeline",
    "SemanticModel",
    "Report",
    "Lakehouse",
    "Warehouse",
    "SparkJobDefinition",
    "MLModel",
    "MLExperiment",
    "Eventstream",
    "KQLDatabase",
    "KQLQueryset",
    "Dashboard",
    "Dataflow",
    "Environment",
    "Reflex",
}

REQUIRED_PLATFORM_FIELDS = ["$schema", "metadata", "config"]
REQUIRED_METADATA_FIELDS = ["type", "displayName"]
REQUIRED_CONFIG_FIELDS = ["version", "logicalId"]
REQUIRED_ENV_CONFIG_KEYS = ["workspace_name", "workspace_id", "description"]

errors = []
warnings = []


def fail(message: str):
    errors.append(message)
    print(f"  ❌  {message}")


def warn(message: str):
    warnings.append(message)
    print(f"  ⚠️  {message}")


def ok(message: str):
    print(f"  ✅  {message}")


# ── Validate environment configs ──────────────────────────────────────────────
print("\n── Validating environment config files ──────────────────────────────────")
for env in ENVIRONMENTS:
    config_file = CONFIG_DIR / f"{env}.json"
    if not config_file.exists():
        fail(f"Missing config file: config/{env}.json")
        continue
    try:
        cfg = json.loads(config_file.read_text())
    except json.JSONDecodeError as e:
        fail(f"Invalid JSON in config/{env}.json: {e}")
        continue
    missing_keys = [k for k in REQUIRED_ENV_CONFIG_KEYS if k not in cfg]
    if missing_keys:
        fail(f"config/{env}.json is missing keys: {missing_keys}")
    else:
        ok(f"config/{env}.json – valid")


# ── Validate Fabric item definitions ─────────────────────────────────────────
print("\n── Validating Fabric item .platform files ───────────────────────────────")

if not FABRIC_ITEMS_DIR.exists():
    fail(f"fabric_items/ directory not found at {FABRIC_ITEMS_DIR}")
else:
    logical_ids_seen: dict[str, str] = {}   # logicalId → item path (for duplicate check)

    for item_dir in sorted(FABRIC_ITEMS_DIR.iterdir()):
        if not item_dir.is_dir():
            continue

        platform_file = item_dir / ".platform"

        # Every item directory must have a .platform file
        if not platform_file.exists():
            fail(f"{item_dir.name}/ – missing .platform file")
            continue

        # .platform must be valid JSON
        try:
            platform = json.loads(platform_file.read_text())
        except json.JSONDecodeError as e:
            fail(f"{item_dir.name}/.platform – invalid JSON: {e}")
            continue

        # Check required top-level fields
        for field in REQUIRED_PLATFORM_FIELDS:
            if field not in platform:
                fail(f"{item_dir.name}/.platform – missing required field: '{field}'")

        # Validate metadata section
        metadata = platform.get("metadata", {})
        for field in REQUIRED_METADATA_FIELDS:
            if field not in metadata:
                fail(f"{item_dir.name}/.platform – metadata missing field: '{field}'")

        # Validate item type
        item_type = metadata.get("type", "")
        if item_type and item_type not in SUPPORTED_ITEM_TYPES:
            fail(
                f"{item_dir.name}/.platform – unknown item type '{item_type}'. "
                f"Supported: {sorted(SUPPORTED_ITEM_TYPES)}"
            )

        # Validate folder name convention: DisplayName.ItemType
        folder_name = item_dir.name
        if "." not in folder_name:
            warn(
                f"{folder_name}/ – folder name should follow the pattern "
                f"'DisplayName.ItemType' (e.g., SalesNotebook.Notebook)"
            )
        else:
            folder_type = folder_name.rsplit(".", 1)[-1]
            if item_type and folder_type != item_type:
                warn(
                    f"{folder_name}/ – folder suffix '{folder_type}' doesn't match "
                    f"metadata type '{item_type}'"
                )

        # Validate config section
        config_section = platform.get("config", {})
        for field in REQUIRED_CONFIG_FIELDS:
            if field not in config_section:
                fail(f"{item_dir.name}/.platform – config missing field: '{field}'")

        # Check logicalId is a valid GUID
        logical_id = config_section.get("logicalId", "")
        try:
            uuid.UUID(logical_id)
        except (ValueError, AttributeError):
            fail(f"{item_dir.name}/.platform – logicalId '{logical_id}' is not a valid GUID")
            logical_id = None

        # Check for duplicate logicalIds
        if logical_id:
            if logical_id in logical_ids_seen:
                fail(
                    f"{item_dir.name}/.platform – logicalId '{logical_id}' is already used by "
                    f"'{logical_ids_seen[logical_id]}'"
                )
            else:
                logical_ids_seen[logical_id] = item_dir.name
                ok(f"{item_dir.name}/.platform – valid")


# ── Summary ───────────────────────────────────────────────────────────────────
print("\n── Validation Summary ───────────────────────────────────────────────────")
print(f"  Errors   : {len(errors)}")
print(f"  Warnings : {len(warnings)}")

if errors:
    print("\nFailed validations:")
    for e in errors:
        print(f"  ❌ {e}")
    sys.exit(1)
elif warnings:
    print("\n⚠️  Validation passed with warnings. Review items above.")
else:
    print("\n✅  All validations passed.")
