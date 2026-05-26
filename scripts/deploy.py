"""
deploy.py – Core Fabric CI/CD deployment script
================================================
Uses the `fabric-cicd` Python library (microsoft/fabric-cicd) to publish
Fabric items from this repository to a target Microsoft Fabric workspace.

Authentication Priority (tried in order):
  1. Azure OIDC (Workload Identity Federation) – recommended for GitHub Actions
  2. Service Principal with client secret – fallback
  3. Azure CLI / interactive – for local development

Environment Variables Required:
  - FABRIC_WORKSPACE_ID  : GUID of the target Fabric workspace
  - ENVIRONMENT          : "dev" | "staging" | "prod"
  - AZURE_CLIENT_ID      : Service principal / managed identity client ID
  - AZURE_TENANT_ID      : Azure AD tenant ID
  - AZURE_CLIENT_SECRET  : (only needed for SP with secret, not OIDC)
  - DRY_RUN              : "true" to skip actual API calls (default: "false")
"""

import os
import sys
import json
import logging
from pathlib import Path

# fabric-cicd is the official Microsoft library for Fabric CI/CD deployments
# GitHub: https://github.com/microsoft/fabric-cicd
# Docs:   https://microsoft.github.io/fabric-cicd/
from fabric_cicd import FabricWorkspace, publish_all_items, unpublish_all_orphan_items
from azure.identity import DefaultAzureCredential

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent

# Which Fabric item types this pipeline manages.
# Only items of these types will be published/unpublished.
# Full list: https://learn.microsoft.com/en-us/rest/api/fabric/core/items
ITEM_TYPES_IN_SCOPE = [
    "Notebook",           # PySpark / SQL notebooks
    "DataPipeline",       # Data Factory pipelines
    "SemanticModel",      # Power BI semantic models (datasets)
    "Report",             # Power BI reports
    "Lakehouse",          # Delta Lake + SQL analytics endpoint
    "Warehouse",          # Fabric SQL warehouse
    "SparkJobDefinition", # Batch Spark jobs
    "MLModel",            # Machine learning models
    "MLExperiment",       # ML experiments (MLflow)
    "Eventstream",        # Real-time event streams
    "KQLDatabase",        # Kusto Query Language database
    "KQLQueryset",        # KQL query sets
]


def load_environment_config(environment: str) -> dict:
    """Load the environment-specific configuration file."""
    config_path = REPO_ROOT / "config" / f"{environment}.json"
    if not config_path.exists():
        log.error(f"Config file not found: {config_path}")
        sys.exit(1)
    with open(config_path) as f:
        config = json.load(f)
    log.info(f"Loaded config for environment: {environment}")
    return config


def get_required_env(name: str) -> str:
    """Get a required environment variable or exit with a clear error."""
    value = os.environ.get(name)
    if not value:
        log.error(
            f"Required environment variable '{name}' is not set.\n"
            f"Set it as a GitHub Actions secret and pass it via the 'env:' block."
        )
        sys.exit(1)
    return value


def main():
    # ── Read required inputs ─────────────────────────────────────────────────
    workspace_id = get_required_env("FABRIC_WORKSPACE_ID")
    environment  = os.environ.get("ENVIRONMENT", "dev")
    dry_run      = os.environ.get("DRY_RUN", "false").lower() == "true"

    log.info("=" * 60)
    log.info(f"  Fabric CI/CD Deployment")
    log.info(f"  Environment  : {environment.upper()}")
    log.info(f"  Workspace ID : {workspace_id}")
    log.info(f"  Dry Run      : {dry_run}")
    log.info("=" * 60)

    if dry_run:
        log.info("DRY RUN MODE – No changes will be made to the Fabric workspace.")

    # ── Load environment config ───────────────────────────────────────────────
    config = load_environment_config(environment)

    # Items are stored in fabric_items/<environment>/
    # Each item is a folder named:  DisplayName.ItemType
    #   e.g.  SalesNotebook.Notebook
    #         SalesPipeline.DataPipeline
    repository_directory = str(REPO_ROOT / "fabric_items")

    log.info(f"Repository directory : {repository_directory}")
    log.info(f"Item types in scope  : {', '.join(ITEM_TYPES_IN_SCOPE)}")

    if not Path(repository_directory).exists():
        log.error(f"fabric_items/ directory not found at: {repository_directory}")
        sys.exit(1)

    # ── Build the FabricWorkspace object ─────────────────────────────────────
    #
    # Authentication happens automatically via the azure-identity library
    # using the DefaultAzureCredential chain:
    #   1. Environment variables (AZURE_CLIENT_ID + AZURE_CLIENT_SECRET)
    #   2. Workload Identity (GitHub OIDC token → Azure federated credential)
    #   3. Managed Identity
    #   4. Azure CLI (great for local development: `az login`)
    #
    credential = DefaultAzureCredential()

    workspace = FabricWorkspace(
        workspace_id=workspace_id,
        repository_directory=repository_directory,
        item_type_in_scope=ITEM_TYPES_IN_SCOPE,
        # environment is used to resolve parameter replacements in item definitions
        # (e.g. swap connection strings / SQL endpoints per environment)
        environment=environment,
        token_credential=credential,
    )

    if dry_run:
        log.info("Dry run complete. Exiting without making changes.")
        return

    # ── Publish items from repo → workspace ──────────────────────────────────
    #
    # publish_all_items() does the following for every item folder:
    #   1. Reads the .platform file to get the item type and display name
    #   2. Creates the item if it doesn't exist in the workspace
    #   3. Updates the item definition if it already exists
    #   4. Applies parameter substitutions (e.g. lakehouse IDs per environment)
    #
    log.info("Publishing all items from repository to workspace...")
    publish_all_items(workspace)
    log.info("✅ publish_all_items complete.")

    # ── Unpublish items removed from the repo ────────────────────────────────
    #
    # unpublish_all_orphan_items() removes items from the workspace that
    # no longer exist in the repository (keeps workspace in sync with git).
    #
    log.info("Removing orphan items (items deleted from repo)...")
    unpublish_all_orphan_items(workspace)
    log.info("✅ unpublish_all_orphan_items complete.")

    log.info("=" * 60)
    log.info(f"  Deployment to {environment.upper()} completed successfully.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
