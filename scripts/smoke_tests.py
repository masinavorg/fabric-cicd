"""
smoke_tests.py – Post-deployment smoke tests
============================================
Verifies that key Fabric items exist and are accessible in the
target workspace immediately after deployment.

These are lightweight "is it there?" checks, NOT functional tests.
Functional/integration tests should be run separately.

Environment Variables Required:
  - FABRIC_WORKSPACE_ID : GUID of the workspace to validate
  - AZURE_CLIENT_ID     : For authentication
  - AZURE_TENANT_ID     : For authentication
"""

import os
import sys
import logging
import requests
from azure.identity import DefaultAzureCredential

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"


def get_token() -> str:
    """Acquire a Bearer token using DefaultAzureCredential."""
    credential = DefaultAzureCredential()
    token = credential.get_token("https://api.fabric.microsoft.com/.default")
    return token.token


def list_workspace_items(workspace_id: str, token: str) -> list[dict]:
    """Call the Fabric REST API to list all items in a workspace."""
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json().get("value", [])


def main():
    workspace_id = os.environ.get("FABRIC_WORKSPACE_ID")
    if not workspace_id:
        log.error("FABRIC_WORKSPACE_ID environment variable is required.")
        sys.exit(1)

    log.info("=" * 55)
    log.info("  Post-Deploy Smoke Tests")
    log.info(f"  Workspace: {workspace_id}")
    log.info("=" * 55)

    # Get an access token
    log.info("Acquiring access token...")
    try:
        token = get_token()
        log.info("✅ Token acquired.")
    except Exception as e:
        log.error(f"Failed to acquire token: {e}")
        sys.exit(1)

    # List items in the workspace
    log.info("Fetching workspace items from Fabric API...")
    try:
        items = list_workspace_items(workspace_id, token)
        log.info(f"✅ Found {len(items)} items in workspace.")
    except Exception as e:
        log.error(f"Failed to list workspace items: {e}")
        sys.exit(1)

    # Build a lookup: displayName → item
    item_map = {item["displayName"]: item for item in items}

    # ── Define expected items per environment ─────────────────────────────────
    # In a real project, load this from config/<environment>.json instead
    # of hardcoding it here.
    EXPECTED_ITEMS = [
        {"displayName": "SalesNotebook",    "type": "Notebook"},
        {"displayName": "SalesPipeline",    "type": "DataPipeline"},
        {"displayName": "SalesModel",       "type": "SemanticModel"},
        {"displayName": "SalesLakehouse",   "type": "Lakehouse"},
    ]

    failures = []
    for expected in EXPECTED_ITEMS:
        name = expected["displayName"]
        expected_type = expected["type"]
        if name not in item_map:
            msg = f"MISSING: '{name}' ({expected_type}) not found in workspace"
            log.error(f"  ❌ {msg}")
            failures.append(msg)
        else:
            actual_type = item_map[name].get("type", "?")
            if actual_type != expected_type:
                msg = (
                    f"TYPE MISMATCH: '{name}' found but type is "
                    f"'{actual_type}' (expected '{expected_type}')"
                )
                log.error(f"  ❌ {msg}")
                failures.append(msg)
            else:
                log.info(f"  ✅ '{name}' ({expected_type}) — present")

    # ── Summary ───────────────────────────────────────────────────────────────
    log.info("=" * 55)
    if failures:
        log.error(f"  SMOKE TESTS FAILED: {len(failures)} issue(s)")
        for f in failures:
            log.error(f"    - {f}")
        sys.exit(1)
    else:
        log.info(f"  ✅ All {len(EXPECTED_ITEMS)} smoke tests passed.")
    log.info("=" * 55)


if __name__ == "__main__":
    main()
