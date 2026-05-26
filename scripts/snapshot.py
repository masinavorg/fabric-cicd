"""
snapshot.py – Pre-deployment workspace snapshot
================================================
Records the current state of the workspace before a deployment.
Useful as a rollback reference: if production deployment fails,
engineers can see exactly what was deployed before.

Usage:
  python scripts/snapshot.py --workspace prod --label pre-deploy-abc1234
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from azure.identity import DefaultAzureCredential

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
SNAPSHOTS_DIR = Path(__file__).parent.parent / ".snapshots"


def get_token() -> str:
    credential = DefaultAzureCredential()
    return credential.get_token("https://api.fabric.microsoft.com/.default").token


def list_workspace_items(workspace_id: str, token: str) -> list[dict]:
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("value", [])


def main():
    parser = argparse.ArgumentParser(description="Take a Fabric workspace snapshot.")
    parser.add_argument("--workspace", required=True, help="Environment name (dev/staging/prod)")
    parser.add_argument("--label", required=True, help="Label for this snapshot (e.g., pre-deploy-abc1234)")
    args = parser.parse_args()

    workspace_id = os.environ.get("FABRIC_WORKSPACE_ID")
    if not workspace_id:
        log.error("FABRIC_WORKSPACE_ID environment variable is required.")
        sys.exit(1)

    log.info(f"Taking snapshot of '{args.workspace}' workspace before deployment...")
    token = get_token()
    items = list_workspace_items(workspace_id, token)

    snapshot = {
        "workspace": args.workspace,
        "workspace_id": workspace_id,
        "label": args.label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "item_count": len(items),
        "items": [
            {
                "id": item.get("id"),
                "displayName": item.get("displayName"),
                "type": item.get("type"),
            }
            for item in items
        ],
    }

    SNAPSHOTS_DIR.mkdir(exist_ok=True)
    snapshot_file = SNAPSHOTS_DIR / f"{args.workspace}-{args.label}.json"
    snapshot_file.write_text(json.dumps(snapshot, indent=2))
    log.info(f"✅ Snapshot saved to: {snapshot_file.relative_to(Path.cwd())}")
    log.info(f"   Items captured: {len(items)}")


if __name__ == "__main__":
    main()
