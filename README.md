# Microsoft Fabric CI/CD with GitHub Actions

> A production-ready, customer-explainable reference project for automating
> Microsoft Fabric deployments using GitHub Actions and the official
> `fabric-cicd` library.

---

## Table of Contents

1. [What is Microsoft Fabric?](#1-what-is-microsoft-fabric)
2. [Why CI/CD for Fabric?](#2-why-cicd-for-fabric)
3. [How Fabric Git Integration Works](#3-how-fabric-git-integration-works)
4. [Project Architecture](#4-project-architecture)
5. [Branching Strategy](#5-branching-strategy)
6. [The Four GitHub Actions Workflows](#6-the-four-github-actions-workflows)
7. [Authentication – Service Principal vs OIDC](#7-authentication--service-principal-vs-oidc)
8. [The `fabric-cicd` Library Explained](#8-the-fabric-cicd-library-explained)
9. [Fabric Item Structure in Git](#9-fabric-item-structure-in-git)
10. [Parameter Substitution per Environment](#10-parameter-substitution-per-environment)
11. [Secrets Configuration Guide](#11-secrets-configuration-guide)
12. [Step-by-Step Setup](#12-step-by-step-setup)
13. [What Gets Deployed – Supported Item Types](#13-what-gets-deployed--supported-item-types)
14. [Security Best Practices](#14-security-best-practices)
15. [Rollback Strategy](#15-rollback-strategy)
16. [Frequently Asked Questions](#16-frequently-asked-questions)
17. [Troubleshooting](#17-troubleshooting)
18. [Glossary](#18-glossary)

---

## 1. What is Microsoft Fabric?

**Microsoft Fabric** is an all-in-one analytics platform (launched 2023) that
unifies every data and analytics workload under a single SaaS product:

| Workload | What it does |
|---|---|
| **Data Factory** | Low-code data pipelines and dataflows |
| **Synapse Data Engineering** | PySpark notebooks, Spark job definitions |
| **Synapse Data Science** | ML experiments, ML models |
| **Synapse Data Warehouse** | T-SQL warehouse on Delta Lake |
| **Real-Time Intelligence** | Event streams, KQL databases, Reflex alerts |
| **Power BI** | Semantic models (datasets), reports, dashboards |
| **OneLake** | Single unified data lake (all workloads share one lake) |

All of these run inside **Fabric Workspaces** — the organisational unit
(equivalent to a resource group in Azure).

---

## 2. Why CI/CD for Fabric?

Without CI/CD, Fabric development looks like this:

```
Developer opens Fabric portal → makes changes in Dev workspace
→ manually copies changes to Staging → manually copies to Production
→ no audit trail, no code review, easy to forget a step
```

**Problems this causes:**
- Changes deployed to production that were never reviewed
- "Works in Dev, broken in Prod" due to missed manual steps
- No rollback capability
- No audit history of what changed and who approved it
- Multiple developers overwriting each other's work

**With CI/CD and GitHub Actions:**

```
Developer pushes to 'dev' branch
→ GitHub Actions automatically deploys to Dev workspace
→ PR to 'staging' triggers automated UAT deployment
→ PR to 'main' requires 2 approvals → automatically deploys to Production
→ Full audit trail in GitHub
```

**Benefits:**
- **Repeatability** – the same process every time, no human mistakes
- **Traceability** – every deployment is linked to a git commit and PR
- **Governance** – required reviewers enforce a 4-eyes principle
- **Speed** – developers spend minutes not hours on deployments
- **Rollback** – revert a git commit to roll back a deployment

---

## 3. How Fabric Git Integration Works

Microsoft Fabric has built-in **Git Integration** that allows a workspace to be
connected to a GitHub (or Azure DevOps) repository branch.

```
GitHub Repo Branch  ←──sync──→  Fabric Workspace
```

When you commit a file to the branch, Fabric can detect the change and update
the workspace. However, **built-in Git sync is manual** — someone must click
"Update" in the Fabric portal, or it triggers on commit.

**This project goes further:** instead of relying on Fabric's built-in sync,
we use the **Fabric REST API** (via the `fabric-cicd` library) to push changes
programmatically from GitHub Actions. This gives us:

- Full control over *when* and *what* gets deployed
- Multi-environment promotion (Dev → Staging → Prod)
- Ability to inject per-environment parameter values
- Ability to remove items that were deleted from Git

### The Two Approaches Compared

| | Built-in Fabric Git Sync | This Project (API-based CI/CD) |
|---|---|---|
| Trigger | Manual or on-commit to connected branch | GitHub Actions pipeline |
| Multi-environment | ❌ One workspace per branch | ✅ Deploy same code to N workspaces |
| Parameter substitution | ❌ | ✅ Swap connection strings per env |
| Approval gates | ❌ | ✅ GitHub Environment protection rules |
| Audit trail | Git history only | Git history + GitHub Actions run log |
| Orphan cleanup | ❌ | ✅ Items deleted from Git are removed |
| Notifications | ❌ | ✅ Teams/Slack webhooks |

---

## 4. Project Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         GitHub Repository                               │
│                                                                         │
│  fabric_items/          ← Fabric item definitions (checked into Git)   │
│  ├── SalesNotebook.Notebook/                                            │
│  ├── SalesPipeline.DataPipeline/                                        │
│  ├── SalesModel.SemanticModel/                                          │
│  └── SalesLakehouse.Lakehouse/                                          │
│                                                                         │
│  .github/workflows/     ← GitHub Actions pipeline definitions          │
│  ├── 1-ci-validate.yml  ← Runs on every PR (lint + validate)           │
│  ├── 2-deploy-dev.yml   ← Pushes to Dev workspace on merge to 'dev'    │
│  ├── 3-deploy-staging.yml ← Pushes to Staging on merge to 'staging'   │
│  └── 4-deploy-prod.yml  ← Pushes to Prod on merge to 'main' (gated)   │
│                                                                         │
│  scripts/deploy.py      ← Wraps fabric-cicd library                    │
│  config/{env}.json      ← Per-environment metadata (non-sensitive)     │
└────────────────────────────────────────┬────────────────────────────────┘
                                         │ Fabric REST API
                          ┌──────────────▼──────────────────────────┐
                          │         Microsoft Fabric                 │
                          │                                          │
                          │  ┌─────────┐  ┌──────────┐  ┌──────┐  │
                          │  │   Dev   │  │ Staging  │  │ Prod │  │
                          │  │Workspace│  │Workspace │  │  WS  │  │
                          │  └─────────┘  └──────────┘  └──────┘  │
                          └──────────────────────────────────────────┘
```

### Data Flow Inside a Workspace

```
OneLake (SalesLakehouse)
  ├── Tables/
  │   ├── bronze_sales     ← Raw data ingested by SalesPipeline
  │   ├── silver_sales     ← Cleaned by SalesNotebook
  │   └── gold_daily_revenue ← Aggregated, read by SalesModel
  └── Files/
      └── raw/             ← Source files (CSV, Parquet, etc.)

SalesPipeline (Data Factory)
  1. Copy activity → bronze_sales
  2. Notebook activity → runs SalesNotebook
  3. Refresh activity → refreshes SalesModel

SalesModel (Power BI Semantic Model)
  └── Reads gold_daily_revenue
      └── Powers dashboards and reports
```

---

## 5. Branching Strategy

This project uses **GitFlow-style** branching with three permanent branches
mapped directly to three Fabric workspaces:

```
feature/my-change ──►  dev  ──►  staging  ──►  main
                        │            │             │
                   Dev Workspace  Staging WS   Prod WS
                   (auto-deploy)  (auto-deploy) (gated)
```

| Branch | Purpose | Fabric Workspace | Deploy Trigger |
|---|---|---|---|
| `feature/*` | Developer work | — | None (PR only) |
| `dev` | Integration branch | Dev | Auto on push |
| `staging` | UAT branch | Staging | Auto on push |
| `main` | Production branch | Production | Manual approval required |

### Developer Workflow

```
1. git checkout -b feature/add-new-kpi-report
2. Make changes to fabric_items/
3. git push → open PR to 'dev'
4. CI workflow validates .platform files and JSON
5. PR approved → merged to 'dev'
6. GitHub Actions auto-deploys to Dev workspace (2-deploy-dev.yml)
7. Test in Dev
8. Open PR: dev → staging
9. Merged → GitHub Actions deploys to Staging (3-deploy-staging.yml)
10. UAT sign-off
11. Open PR: staging → main
12. Requires 2 reviewer approvals (GitHub Environment rule)
13. GitHub Actions requests approval from designated reviewers
14. Approved → GitHub Actions deploys to Production (4-deploy-prod.yml)
```

---

## 6. The Four GitHub Actions Workflows

### Workflow 1: `1-ci-validate.yml` — Pull Request Validation

**When it runs:** Every PR targeting `dev`, `staging`, or `main`

**What it does:**
1. Installs Python dependencies
2. Validates all `config/*.json` files are valid JSON
3. Validates all `.platform` files have required fields and valid GUIDs
4. Checks that item type names are recognised Fabric types
5. Checks for duplicate `logicalId` values (would cause deployment failures)
6. Lints Python scripts with `flake8`

**Why it matters:** Catches errors *before* merging, not after a failed deployment.

---

### Workflow 2: `2-deploy-dev.yml` — Deploy to Development

**When it runs:** Every push to the `dev` branch (i.e., after PR merge)

**What it does:**
1. Authenticates to Azure using OIDC (no secrets stored!)
2. Runs `scripts/deploy.py` which calls `fabric-cicd`
3. Publishes all item folders from `fabric_items/` to the Dev workspace
4. Removes items from the workspace that were deleted from Git
5. Sends a Teams notification with pass/fail status

**Key property:** Fully automatic. Zero human interaction after PR merge.

---

### Workflow 3: `3-deploy-staging.yml` — Deploy to Staging

**When it runs:** Every push to the `staging` branch

**Additional step beyond Dev:** Runs `scripts/smoke_tests.py` after deployment
to verify that key items are present and accessible in the workspace via the
Fabric REST API.

**GitHub Environment:** The `staging` GitHub Environment can be configured to
require **1 reviewer approval** before the deployment job runs — this is set
in `GitHub → Settings → Environments → staging`.

---

### Workflow 4: `4-deploy-prod.yml` — Deploy to Production

**When it runs:** Push to `main` OR manual `workflow_dispatch` trigger

**Critical safety features:**
1. **Manual confirmation:** If triggered manually, the user must type `DEPLOY`
2. **GitHub Environment protection:** The `production` environment requires
   **2 reviewer approvals** and has a **10-minute wait timer** before the
   deployment job can start (giving time to cancel)
3. **Pre-deploy snapshot:** Captures the current state of the production
   workspace before any changes (rollback reference)
4. **Post-deploy smoke tests:** Verifies all expected items are present
5. **Failure notification:** Immediate Teams alert if production deploy fails

---

## 7. Authentication – Service Principal vs OIDC

### Option A: OIDC / Workload Identity Federation (Recommended)

This is the **preferred** approach. No long-lived secrets are stored anywhere.

```
GitHub Actions runner                Azure AD
       │                                │
       │  presents short-lived          │
       │  JWT token (OIDC)    ─────────►│  validates token
       │                                │  issues short-lived
       │◄───────── Azure access token ──│  access token
       │
       │ uses access token
       ▼
  Fabric REST API
```

**Setup steps:**
1. Create an App Registration in Azure AD (Entra ID)
2. Under **Certificates & secrets → Federated credentials**, add a credential:
   - Type: **GitHub Actions**
   - Organisation: your GitHub org
   - Repository: your repo name
   - Entity: `Branch` → `main` (repeat for `dev`, `staging`)
3. Grant the App Registration the **Fabric Administrator** or
   **Workspace Contributor** role on each Fabric workspace
4. Store only three non-secret values as GitHub secrets:
   - `AZURE_CLIENT_ID`
   - `AZURE_TENANT_ID`
   - `AZURE_SUBSCRIPTION_ID`

No `AZURE_CLIENT_SECRET` needed at all.

---

### Option B: Service Principal with Client Secret

Use this if OIDC is not feasible in your environment.

```
GitHub Actions runner
       │
       │  client_id + client_secret ──► Azure AD ──► access token
       │
       ▼
  Fabric REST API
```

**Setup steps:**
1. Create an App Registration in Azure AD
2. Create a **client secret** (set an expiry, e.g., 1 year)
3. Store as GitHub secrets:
   - `AZURE_CLIENT_ID`
   - `AZURE_CLIENT_SECRET`
   - `AZURE_TENANT_ID`
4. Grant the SP **Workspace Contributor** or **Admin** role on Fabric workspaces

**Important:** Rotate the client secret before it expires and update the GitHub secret.

---

### Azure AD Permissions Required

The Service Principal / App Registration needs:

| Permission | Where to set | Purpose |
|---|---|---|
| Fabric workspace role: **Admin** or **Contributor** | Fabric workspace settings | Create/update/delete items |
| `Fabric.Admin.ReadWrite.All` (API permission) | Azure AD app registration | If using admin-level operations |

> **Tip:** Use **Workspace Contributor** (not Admin) to follow the principle of
> least privilege. It can create and update items but cannot manage workspace
> membership.

---

## 8. The `fabric-cicd` Library Explained

`fabric-cicd` is an **official open-source Microsoft library** that provides a
high-level Python API for deploying Fabric items.

- **GitHub:** https://github.com/microsoft/fabric-cicd
- **Docs:** https://microsoft.github.io/fabric-cicd/
- **Install:** `pip install fabric-cicd`

### Core API

```python
from fabric_cicd import FabricWorkspace, publish_all_items, unpublish_all_orphan_items

# 1. Describe the workspace and where items live in the repo
workspace = FabricWorkspace(
    workspace_id="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    repository_directory="/path/to/fabric_items",
    item_type_in_scope=["Notebook", "DataPipeline", "SemanticModel"],
    environment="prod",   # used for parameter substitution
)

# 2. Publish: creates new items and updates existing ones
publish_all_items(workspace)

# 3. Cleanup: removes items from workspace that were deleted from Git
unpublish_all_orphan_items(workspace)
```

### What `publish_all_items` does internally

For each folder in `repository_directory`:
1. Reads `.platform` to determine item type and display name
2. Calls `GET /workspaces/{id}/items` to check if the item already exists
3. If **new**: calls `POST /workspaces/{id}/items` (create)
4. If **existing**: calls `PATCH /workspaces/{id}/items/{itemId}/definition` (update)
5. Applies **parameter substitutions** (e.g., replaces `{{workspace_id}}` with
   the actual workspace GUID for this environment)

### What `unpublish_all_orphan_items` does

1. Gets the full list of items in the workspace
2. Compares against item folders in the repository
3. Deletes any workspace items that no longer have a matching folder in Git
4. This keeps the workspace perfectly in sync with the repository

---

## 9. Fabric Item Structure in Git

Fabric stores each item as a **folder** containing:
- A `.platform` file (metadata: type, display name, logical ID)
- One or more content files (the actual item definition)

### Folder Naming Convention

```
DisplayName.ItemType/
```

Examples:
```
fabric_items/
├── SalesNotebook.Notebook/
│   ├── .platform
│   └── notebook-content.ipynb
├── SalesPipeline.DataPipeline/
│   ├── .platform
│   └── pipeline-content.json
├── SalesModel.SemanticModel/
│   ├── .platform
│   └── definition.pbism
└── SalesLakehouse.Lakehouse/
    └── .platform
```

### The `.platform` File

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
  "metadata": {
    "type": "Notebook",
    "displayName": "SalesNotebook",
    "description": "Optional description"
  },
  "config": {
    "version": "2.0",
    "logicalId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
  }
}
```

**Key field: `logicalId`**
The `logicalId` is a stable GUID that uniquely identifies the item *across
environments*. When the same item is deployed to Dev, Staging, and Prod, it
gets a different `itemId` in each workspace, but the `logicalId` stays the same.
This is how `fabric-cicd` knows it's the same logical item in all workspaces.

> **Generate a unique GUID for each item:** Use `python -c "import uuid; print(uuid.uuid4())"`

---

## 10. Parameter Substitution per Environment

Different environments need different values — for example:
- The Dev lakehouse has a different ID than the Prod lakehouse
- SQL connection strings differ per environment

`fabric-cicd` supports parameter files that define these substitutions.
Create `fabric_items/parameter.yml`:

```yaml
# fabric_items/parameter.yml
find_replace:
  - find: "{{lakehouse_id}}"
    replace:
      dev:     "aaaa-dev-lakehouse-guid"
      staging: "bbbb-stg-lakehouse-guid"
      prod:    "cccc-prd-lakehouse-guid"

  - find: "{{workspace_id}}"
    replace:
      dev:     "1111-dev-workspace-guid"
      staging: "2222-stg-workspace-guid"
      prod:    "3333-prd-workspace-guid"
```

When `deploy.py` calls `publish_all_items(workspace)` with `environment="prod"`,
`fabric-cicd` automatically substitutes `{{lakehouse_id}}` with the prod value
before uploading the item definition to the workspace.

---

## 11. Secrets Configuration Guide

Configure these in **GitHub → Settings → Secrets and variables → Actions**.

### Repository-level secrets (shared across environments)

| Secret Name | Description |
|---|---|
| `AZURE_CLIENT_ID` | App Registration client ID |
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `TEAMS_WEBHOOK_URL` | Incoming webhook URL for Teams notifications |

### Environment-level secrets (per GitHub Environment)

Set these under **GitHub → Settings → Environments → [environment name] → Secrets**:

| Secret Name | Environment | Description |
|---|---|---|
| `DEV_FABRIC_WORKSPACE_ID` | `development` | GUID of the Dev Fabric workspace |
| `STAGING_FABRIC_WORKSPACE_ID` | `staging` | GUID of the Staging Fabric workspace |
| `PROD_FABRIC_WORKSPACE_ID` | `production` | GUID of the Production Fabric workspace |

> **Where to find the Workspace ID:** Open the Fabric workspace in the browser.
> The GUID is in the URL: `https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/...`

### GitHub Environment Protection Rules

Configure in **GitHub → Settings → Environments**:

| Environment | Required reviewers | Wait timer | Allowed branches |
|---|---|---|---|
| `development` | 0 | 0 min | `dev` |
| `staging` | 1 | 0 min | `staging` |
| `production` | 2 | 10 min | `main` |

---

## 12. Step-by-Step Setup

### Prerequisites

- [ ] Microsoft Fabric tenant with at least 3 workspaces (Dev, Staging, Prod)
- [ ] Azure subscription with ability to create App Registrations
- [ ] GitHub repository (can be private)
- [ ] Python 3.11+ (for local development)

### Step 1 – Fork or clone this repository

```bash
git clone https://github.com/your-org/fabric-cicd-demo.git
cd fabric-cicd-demo
```

### Step 2 – Create Azure App Registration

```bash
# Using Azure CLI
az ad app create --display-name "FabricCICD-ServicePrincipal"

# Note the appId (client ID) from the output
az ad sp create --id <appId>
```

### Step 3 – Configure Federated Credential (OIDC) for each branch

In Azure Portal:
1. Go to **Azure Active Directory → App registrations → FabricCICD-ServicePrincipal**
2. **Certificates & secrets → Federated credentials → Add credential**
3. Scenario: **GitHub Actions deploying Azure resources**
4. Fill in Organisation, Repository, Entity type: Branch, Branch: `dev`
5. Repeat for `staging` and `main`

### Step 4 – Grant workspace access in Fabric

1. Open each Fabric workspace in the browser
2. **Workspace settings → Permissions → Add member**
3. Search for `FabricCICD-ServicePrincipal`
4. Role: **Contributor** (or Admin if creating Lakehouses)
5. Save

### Step 5 – Set GitHub Secrets

In your GitHub repository:
```
Settings → Secrets and variables → Actions → New repository secret
```
Add: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`

Then under **Settings → Environments**, create `development`, `staging`,
`production` and add the workspace ID secrets to each.

### Step 6 – Install local dev dependencies

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

### Step 7 – Add your Fabric items

Put your item folders inside `fabric_items/`.
Naming: `DisplayName.ItemType/` with a `.platform` file inside.

### Step 8 – Test locally

```bash
# Authenticate with your personal account (local dev only)
az login

# Dry run against Dev workspace (no actual changes)
export FABRIC_WORKSPACE_ID=<your-dev-workspace-id>
export ENVIRONMENT=dev
export DRY_RUN=true
python scripts/deploy.py
```

### Step 9 – Push and watch the pipeline

```bash
git checkout -b feature/my-first-deployment
git add fabric_items/
git commit -m "feat: add SalesNotebook and SalesPipeline"
git push origin feature/my-first-deployment
# Open PR to 'dev' → CI workflow validates
# Merge → Dev deployment runs automatically
```

---

## 13. What Gets Deployed – Supported Item Types

| Item Type | Description | File format |
|---|---|---|
| `Notebook` | PySpark / SQL / Scala notebooks | `.ipynb` |
| `DataPipeline` | Data Factory pipelines | `.json` |
| `SemanticModel` | Power BI datasets | `.pbism`, `.tmdl` |
| `Report` | Power BI reports | `.pbir` |
| `Lakehouse` | Delta Lake + SQL analytics endpoint | metadata only |
| `Warehouse` | Fabric SQL warehouse | metadata only |
| `SparkJobDefinition` | Batch Spark jobs | `.json` |
| `MLModel` | Registered ML models | metadata |
| `MLExperiment` | MLflow experiments | metadata |
| `Eventstream` | Real-time event streams | `.json` |
| `KQLDatabase` | Kusto database | `.json` |
| `KQLQueryset` | KQL query collections | `.json` |

> **Note:** Lakehouses and Warehouses deploy the *item definition* (so it
> appears in the workspace), but Delta table schemas and data are NOT deployed
> via CI/CD — data lives in OneLake and is managed separately.

---

## 14. Security Best Practices

### Implemented in this project

| Practice | Implementation |
|---|---|
| Principle of least privilege | SP uses Workspace Contributor, not Fabric Admin |
| No long-lived secrets | OIDC Workload Identity Federation (no client secret) |
| Secrets in GitHub Secrets | Workspace IDs are environment secrets, not in code |
| Branch protection rules | `main` requires 2 PR approvals + passing CI |
| Deployment gates | Production requires 2 manual approvals before deploy |
| Audit trail | Every deployment linked to a commit, PR, and approver |
| Pre-deploy snapshot | State captured before production changes |
| Smoke tests | Automated post-deploy verification |

### Additional recommendations for production

- Enable **Fabric workspace audit logs** in Microsoft Purview
- Use **Microsoft Entra Privileged Identity Management (PIM)** for workspace Admin roles
- Restrict the `production` GitHub Environment to run only on the `main` branch
- Rotate Service Principal credentials annually (or use OIDC to avoid this entirely)
- Enable **GitHub branch protection** on `dev`, `staging`, and `main`:
  - Require PR before merging
  - Require CI status checks to pass
  - Require linear history

---

## 15. Rollback Strategy

### Option 1: Git revert (recommended)

```bash
# Find the last good commit
git log --oneline

# Revert the bad commit (creates a new commit undoing the change)
git revert <commit-hash>
git push origin main
# This triggers the production deployment workflow with the reverted code
```

**Why `git revert` over `git reset`:** `git revert` preserves history.
`git reset --hard` rewrites history, which is dangerous on shared branches.

### Option 2: Re-run a previous deployment

In GitHub Actions:
1. Go to **Actions → CD – Deploy to Production**
2. Find the last successful run
3. Click **Re-run jobs** → this re-deploys the code from that commit

### Option 3: Pre-deploy snapshot reference

The `snapshot.py` script (run automatically before every prod deployment)
saves a JSON file listing all items that were in the workspace before the
deployment. Engineers can use this to manually identify and restore any
items that were incorrectly removed.

---

## 16. Frequently Asked Questions

**Q: Do we need Fabric's built-in Git integration enabled?**
A: No. This project uses the Fabric REST API directly. Built-in Git
integration and this CI/CD pipeline can coexist but are independent.

**Q: Can we deploy to multiple workspaces in one pipeline run?**
A: Yes. Add more deployment steps to a workflow or create a matrix strategy.
Each step gets its own `FABRIC_WORKSPACE_ID`.

**Q: What happens if a deployment fails halfway?**
A: `fabric-cicd` deploys items sequentially. Items deployed before the failure
remain deployed. Re-running the pipeline will re-attempt all items (it's
idempotent – already-correct items are updated, not duplicated).

**Q: Can I use this with Azure DevOps instead of GitHub Actions?**
A: Yes. The `fabric-cicd` library works the same way. The workflow YAML
syntax differs (Azure Pipelines vs GitHub Actions), but `scripts/deploy.py`
is identical.

**Q: Does this handle Power BI reports and semantic models?**
A: Yes. `Report` and `SemanticModel` are in `ITEM_TYPES_IN_SCOPE`. Reports
reference semantic models via the `logicalId`, so cross-item references
resolve correctly across environments.

**Q: How do we handle sensitive data in notebooks (e.g., SQL passwords)?**
A: Never put passwords in notebooks. Use:
- Fabric **Managed Private Endpoints** for SQL connections
- Azure Key Vault linked via Fabric's **Key Vault secret provider**
- Parameter substitution in `parameter.yml` (values come from secrets, not code)

**Q: What if a developer directly edits a workspace in the Fabric portal?**
A: The next pipeline run will overwrite their changes with the Git version.
Enforce a "no manual edits" policy on Staging and Production workspaces.
Dev workspace can allow direct edits — just remember to commit the changes to Git.

**Q: How do we add a new Fabric item to the pipeline?**
A: 
1. Create the item in the Dev workspace
2. Download the item definition (Fabric portal → item → ... → Export)
3. Place the exported folder in `fabric_items/`
4. Add a unique `logicalId` GUID to its `.platform` file
5. Commit and push

---

## 17. Troubleshooting

### `403 Forbidden` from Fabric API
- The Service Principal is not a member of the workspace
- Go to Fabric workspace → Settings → Permissions → Add the SP as Contributor

### `Token acquisition failed`
- In GitHub Actions: ensure `id-token: write` permission is set in the workflow
- Locally: run `az login` first; `DefaultAzureCredential` will use CLI token

### Item type not recognised during validation
- Update `SUPPORTED_ITEM_TYPES` in `scripts/validate_config.py`
- Fabric releases new item types regularly — check the [Fabric REST API docs](https://learn.microsoft.com/en-us/rest/api/fabric/core/items)

### Duplicate `logicalId` error
- Each item needs a unique GUID. Generate one: `python -c "import uuid; print(uuid.uuid4())"`

### `publish_all_items` takes a long time
- Normal for first-time deployments creating many items
- Subsequent runs are faster (only changed items are updated)

### Smoke tests fail after deployment
- The item may exist but be in an error state (e.g., invalid connection)
- Check the Fabric portal for item-level errors
- Look at the item's last refresh/run status

---

## 18. Glossary

| Term | Definition |
|---|---|
| **Fabric workspace** | A container in Microsoft Fabric that holds items (notebooks, pipelines, etc.) |
| **Item** | Any Fabric asset: notebook, pipeline, semantic model, lakehouse, etc. |
| **logicalId** | A stable GUID that represents the same logical item across multiple workspaces |
| **itemId** | The workspace-specific ID of a deployed item; differs across workspaces |
| **fabric-cicd** | Microsoft's open-source Python library for deploying Fabric items via REST API |
| **OIDC** | OpenID Connect – allows GitHub Actions to authenticate to Azure without storing a client secret |
| **Workload Identity Federation** | Azure AD feature enabling OIDC-based trust between GitHub Actions and Azure |
| **GitHub Environment** | A GitHub feature that groups secrets and protection rules for a deployment target |
| **Parameter substitution** | Replacing placeholder tokens (e.g., `{{workspace_id}}`) with environment-specific values at deploy time |
| **Orphan item** | An item in a Fabric workspace that no longer has a corresponding folder in Git |
| **OneLake** | Microsoft Fabric's unified data lake — all workloads in a tenant share one lake |
| **Delta Lake** | Open-source ACID-compliant table storage format used by Fabric lakehouses |
| **CI** | Continuous Integration – automated testing and validation on every code change |
| **CD** | Continuous Delivery/Deployment – automated deployment of validated code to environments |
| **GitFlow** | A branching strategy with dedicated branches for features, dev, staging, and production |

---

## Project File Structure

```
fabric-test/
├── .github/
│   └── workflows/
│       ├── 1-ci-validate.yml       ← PR validation (lint, schema check)
│       ├── 2-deploy-dev.yml        ← Auto-deploy to Dev on push to 'dev'
│       ├── 3-deploy-staging.yml    ← Auto-deploy to Staging on push to 'staging'
│       └── 4-deploy-prod.yml       ← Gated deploy to Production on push to 'main'
│
├── fabric_items/                   ← All Fabric items stored as code
│   ├── SalesNotebook.Notebook/
│   │   ├── .platform               ← Item metadata (type, displayName, logicalId)
│   │   └── notebook-content.ipynb  ← Notebook code (PySpark)
│   ├── SalesPipeline.DataPipeline/
│   │   ├── .platform
│   │   └── pipeline-content.json   ← Pipeline activities definition
│   ├── SalesModel.SemanticModel/
│   │   └── .platform
│   └── SalesLakehouse.Lakehouse/
│       └── .platform
│
├── scripts/
│   ├── deploy.py                   ← Main deployment script (wraps fabric-cicd)
│   ├── validate_config.py          ← Pre-deploy validation (runs in CI)
│   ├── smoke_tests.py              ← Post-deploy verification via Fabric REST API
│   └── snapshot.py                 ← Pre-deploy workspace snapshot (rollback ref)
│
├── config/
│   ├── dev.json                    ← Dev environment metadata
│   ├── staging.json                ← Staging environment metadata
│   └── prod.json                   ← Production environment metadata
│
├── requirements.txt                ← Python dependencies
├── .gitignore
└── README.md                       ← This file
```

---

*Built with the [microsoft/fabric-cicd](https://github.com/microsoft/fabric-cicd) library.*
*Microsoft Fabric documentation: https://learn.microsoft.com/en-us/fabric/*
