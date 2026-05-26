# Microsoft Fabric CI/CD — Zero to Hero Setup Guide

> A complete guide to understanding, configuring, and explaining this project.

---

## Table of Contents

1. [What This Project Is](#1-what-this-project-is)
2. [The Big Picture — 3 Concepts You Need to Understand](#2-the-big-picture--3-concepts-you-need-to-understand)
3. [Project Structure Explained](#3-project-structure-explained)
4. [How a Deployment Works](#4-how-a-deployment-works)
5. [The 4 Automated Workflows](#5-the-4-automated-workflows)
6. [Step-by-Step Setup Guide](#6-step-by-step-setup-guide)
7. [Normal Day-to-Day Developer Flow](#7-normal-day-to-day-developer-flow)
8. [How to Explain This to a Customer](#8-how-to-explain-this-to-a-customer)
9. [What Each Environment Config Does](#9-what-each-environment-config-does)
10. [Quick Reference](#10-quick-reference)

---

## 1. What This Project Is

This is a **CI/CD automation system for Microsoft Fabric** — it automates how
Fabric analytics items (notebooks, pipelines, semantic models, lakehouses) move
from a developer's hands all the way to production, with no manual steps, full
audit trails, and required approvals.

---

## 2. The Big Picture — 3 Concepts You Need to Understand

### Concept 1 — Microsoft Fabric

Think of Fabric as a single cloud platform that replaces what used to be
separate tools:

| Old tool | Fabric equivalent |
|---|---|
| Azure Data Factory | **Data Pipelines** |
| Azure Databricks notebooks | **Notebooks** |
| Power BI datasets | **Semantic Models** |
| Azure Data Lake | **OneLake / Lakehouse** |

Everything lives inside **Workspaces** — like folders that group related items
together. This project manages 3 workspaces: **Dev**, **Staging**, and
**Production**.

---

### Concept 2 — The Problem Without CI/CD

Without this project, a Fabric developer does this manually:

1. Build a notebook in Dev
2. Open Staging → manually recreate it
3. Open Prod → manually recreate it again
4. No one knows what changed, who approved it, or how to roll back

---

### Concept 3 — What This Project Solves

```
Developer pushes code to Git
         ↓
GitHub Actions automatically deploys to Dev
         ↓  (PR + approval)
Automatically deploys to Staging + runs smoke tests
         ↓  (2 approvers required + 10-minute wait)
Automatically deploys to Production
```

---

## 3. Project Structure Explained

```
fabric-test/
│
├── fabric_items/                     ← Your Fabric "items" stored as code
│   ├── SalesNotebook.Notebook/       (naming convention: DisplayName.ItemType)
│   ├── SalesPipeline.DataPipeline/
│   ├── SalesModel.SemanticModel/
│   └── SalesLakehouse.Lakehouse/
│       └── .platform                 ← Metadata: item type, name, unique GUID
│
├── config/
│   ├── dev.json                      ← Dev-specific settings (lakehouse name, SQL server, etc.)
│   ├── staging.json
│   └── prod.json
│
├── scripts/
│   ├── deploy.py          ← Core script: pushes items to Fabric via REST API
│   ├── validate_config.py ← Pre-deploy: validates .platform files and configs
│   ├── smoke_tests.py     ← Post-deploy: confirms items landed in Fabric
│   └── snapshot.py        ← Captures workspace state before prod deploy (rollback ref)
│
└── requirements.txt       ← Python packages: fabric-cicd, azure-identity, requests
```

**Key insight:** Every Fabric item is just a **folder with files**. A Notebook
is a `.ipynb` file + a `.platform` metadata file. A Pipeline is a
`pipeline-content.json` + `.platform`. Git stores them like any other code.

---

## 4. How a Deployment Works

```
fabric_items/ folder
        ↓  read by
scripts/deploy.py
        ↓  calls
fabric-cicd library  (pip install fabric-cicd)
        ↓  calls
Fabric REST API  (api.fabric.microsoft.com)
        ↓  creates / updates / deletes items in
Fabric Workspace  (Dev / Staging / Prod)
```

`deploy.py` does exactly two things:

1. **`publish_all_items`** — for every folder in `fabric_items/`, create or
   update the item in the target Fabric workspace.
2. **`unpublish_all_orphan_items`** — if a folder was deleted from Git, delete
   the matching item from the workspace too (keeps workspace in sync with Git).

---

## 5. The 4 Automated Workflows

| File | When it runs | What it does |
|---|---|---|
| `1-ci-validate.yml` | Every PR | Validates JSON, checks for duplicate logicalIds, lints Python |
| `2-deploy-dev.yml` | Push to `dev` branch | Auto-deploys to Dev workspace |
| `3-deploy-staging.yml` | Push to `staging` branch | Deploys to Staging + runs smoke tests |
| `4-deploy-prod.yml` | Push to `main` (gated) | Snapshots prod → deploys → smoke tests |

---

## 6. Step-by-Step Setup Guide

### Prerequisites

- [ ] Microsoft Fabric tenant — ability to create workspaces (Fabric Admin or
      capacity admin role)
- [ ] Azure subscription — ability to create App Registrations (Entra ID)
- [ ] GitHub repository (can be private)
- [ ] Python 3.11+ installed locally

---

### Step 1 — Create 3 Fabric Workspaces

In [app.fabric.microsoft.com](https://app.fabric.microsoft.com):

1. Click **Workspaces → New workspace**
2. Create: `Sales-Analytics-Dev`
3. Create: `Sales-Analytics-Staging`
4. Create: `Sales-Analytics-Prod`

> **Copy the Workspace ID from each URL:**
> `https://app.fabric.microsoft.com/groups/`**`{THIS-IS-THE-GUID}`**`/...`
> You will need these GUIDs in Step 6.

---

### Step 2 — Create an Azure App Registration

This is the identity that GitHub Actions will use to authenticate to Azure and
call the Fabric API.

**Option A — Azure CLI (recommended):**

```bash
# Create the App Registration
az ad app create --display-name "FabricCICD-ServicePrincipal"

# Note the "appId" value from the output, then create the Service Principal
az ad sp create --id <appId>
```

**Option B — Azure Portal:**

1. Go to **Azure Portal → Microsoft Entra ID → App registrations**
2. Click **New registration**
3. Name: `FabricCICD-ServicePrincipal`
4. Supported account types: **Single tenant**
5. Click **Register**
6. Copy the **Application (client) ID** and **Directory (tenant) ID** from the
   Overview page — you will need these later.

---

### Step 3 — Configure OIDC Federated Credentials

This allows GitHub Actions to authenticate to Azure using a short-lived token
— **no stored passwords or secrets required**.

In **Azure Portal → Entra ID → App Registrations →
FabricCICD-ServicePrincipal → Certificates & secrets → Federated credentials**:

Click **Add credential** and repeat for each branch:

| Field | Value (first credential) | Value (second) | Value (third) |
|---|---|---|---|
| Scenario | GitHub Actions | GitHub Actions | GitHub Actions |
| Organisation | your GitHub org | your GitHub org | your GitHub org |
| Repository | your repo name | your repo name | your repo name |
| Entity type | Branch | Branch | Branch |
| Branch | `dev` | `staging` | `main` |
| Name | `github-dev` | `github-staging` | `github-main` |

---

### Step 4 — Grant the App Registration Access to Each Fabric Workspace

Repeat for **each** of the 3 workspaces (Dev, Staging, Prod):

1. Open the workspace in [app.fabric.microsoft.com](https://app.fabric.microsoft.com)
2. Click the **⋯ menu → Workspace settings → Manage access**
3. Click **Add people or groups**
4. Search for `FabricCICD-ServicePrincipal`
5. Set role to **Contributor** (use **Admin** only if the pipeline needs to
   create Lakehouses or manage workspace membership)
6. Click **Add**

---

### Step 5 — Set GitHub Repository Secrets

Go to your GitHub repository:
**Settings → Secrets and variables → Actions → New repository secret**

Add the following repository-level secrets:

| Secret name | Where to get the value |
|---|---|
| `AZURE_CLIENT_ID` | App Registration → Overview → Application (client) ID |
| `AZURE_TENANT_ID` | App Registration → Overview → Directory (tenant) ID |
| `AZURE_SUBSCRIPTION_ID` | Azure Portal → Subscriptions → Subscription ID |
| `TEAMS_WEBHOOK_URL` | Teams → channel → Connectors → Incoming Webhook (optional) |

---

### Step 6 — Create GitHub Environments and Add Workspace Secrets

Go to: **GitHub → Settings → Environments → New environment**

Create three environments and configure each as below:

#### `development` environment

- **Secrets:**
  - `DEV_FABRIC_WORKSPACE_ID` = Dev workspace GUID (from Step 1)
- **Protection rules:** none (deploys automatically)

#### `staging` environment

- **Secrets:**
  - `STAGING_FABRIC_WORKSPACE_ID` = Staging workspace GUID (from Step 1)
- **Protection rules:** Required reviewers → add 1 reviewer

#### `production` environment

- **Secrets:**
  - `PROD_FABRIC_WORKSPACE_ID` = Prod workspace GUID (from Step 1)
- **Protection rules:**
  - Required reviewers → add 2 reviewers
  - Wait timer → **10 minutes**
  - Deployment branches → allow `main` only

---

### Step 7 — Install Local Dev Dependencies

```powershell
# From the repo root
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

---

### Step 8 — Test Locally (Dry Run)

```powershell
# Validate all config and .platform files (no API calls)
python scripts/validate_config.py

# Test the deploy script without making any real changes
$env:FABRIC_WORKSPACE_ID = "your-dev-workspace-guid"
$env:ENVIRONMENT         = "dev"
$env:DRY_RUN             = "true"
$env:AZURE_CLIENT_ID     = "your-client-id"
$env:AZURE_TENANT_ID     = "your-tenant-id"

python scripts/deploy.py
```

---

### Step 9 — Add Your Fabric Items

Place each Fabric item as a folder inside `fabric_items/`.

**Folder naming convention:** `DisplayName.ItemType/`

```
fabric_items/
├── SalesNotebook.Notebook/
│   ├── .platform
│   └── notebook-content.ipynb
├── SalesPipeline.DataPipeline/
│   ├── .platform
│   └── pipeline-content.json
└── SalesLakehouse.Lakehouse/
    └── .platform
```

**Every folder must have a `.platform` file:**

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
    "logicalId": "paste-a-new-uuid-here"
  }
}
```

Generate a unique `logicalId` for every new item:

```bash
python -c "import uuid; print(uuid.uuid4())"
```

---

### Step 10 — Configure Parameter Substitution (Per-Environment Values)

When an item (e.g. a Notebook) needs to reference different resources in Dev vs
Prod (different lakehouse IDs, different SQL servers), create this file:

**`fabric_items/parameter.yml`**

```yaml
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

Then use `{{lakehouse_id}}` as a placeholder anywhere in your item definition
files. `deploy.py` will substitute the correct value for the target environment
automatically.

---

## 7. Normal Day-to-Day Developer Flow

```bash
# 1. Create a feature branch
git checkout -b feature/add-new-kpi-report

# 2. Add or edit items in fabric_items/
#    (edit notebooks, pipelines, semantic model definitions)

# 3. Push and open a Pull Request → dev
git add .
git commit -m "Add KPI revenue report notebook"
git push origin feature/add-new-kpi-report
# → Open PR to 'dev' on GitHub

# 4. CI validates .platform files and JSON (workflow 1-ci-validate.yml)
# 5. PR approved and merged → auto-deploys to Dev workspace (no action needed)

# 6. Test in Dev workspace

# 7. Open PR: dev → staging
# → 1 reviewer approves → auto-deploys to Staging + smoke tests run

# 8. UAT / QA sign-off in Staging workspace

# 9. Open PR: staging → main
# → 2 reviewers must approve
# → 10-minute safety timer starts
# → auto-deploys to Production
# → smoke tests confirm success
# → Teams notification sent
```

---

## 8. How to Explain This to a Customer

> **"Right now, your team makes Fabric changes manually and copies them between
> environments by hand. That means risk of mistakes, no approval process, and
> no way to know what changed or roll back if something breaks.**
>
> **This solution treats your Fabric items — notebooks, pipelines, semantic
> models — exactly like software code. Everything is stored in Git. Any change
> goes through a pull request, gets reviewed, and is deployed automatically by
> a pipeline.**
>
> **Dev is instant. Staging requires one approval. Production requires two
> approvals and a 10-minute safety window.**
>
> **The result: faster deployments, zero manual errors, a full audit trail for
> compliance, and the ability to roll back any change in minutes."**

### Value Summary for Stakeholders

| Problem today | This solution |
|---|---|
| Manual copy-paste between environments | Fully automated promotion pipeline |
| No approval process | GitHub PR reviews + environment gates |
| "Works in Dev, broken in Prod" | Smoke tests after every deployment |
| No audit trail | Every change tied to a Git commit and PR |
| Hard to roll back | Revert a commit → pipeline redeploys old state |
| Secrets shared in chat / email | Stored securely as GitHub Secrets, never exposed |

---

## 9. What Each Environment Config Does

The files `config/dev.json`, `config/staging.json`, and `config/prod.json`
store **non-sensitive, environment-specific metadata**. Sensitive values
(workspace IDs, credentials) are stored as GitHub Secrets — never in these
files.

Example — `config/dev.json`:

```json
{
  "workspace_name": "Sales-Analytics-Dev",
  "workspace_id": "SET_VIA_SECRET_DEV_FABRIC_WORKSPACE_ID",
  "environment_tier": "dev",
  "item_parameter_overrides": {
    "lakehouse_name": "SalesLakehouse_Dev",
    "sql_connection_string": "Server=dev-sql.database.windows.net;Database=SalesDB_Dev"
  }
}
```

`deploy.py` loads this file to pass the `environment` value into
`FabricWorkspace(environment="dev")`, which tells `fabric-cicd` which set of
parameter substitutions to apply.

---

## 10. Quick Reference

| You want to... | Do this |
|---|---|
| Add a new Fabric item | Create `DisplayName.ItemType/` folder with `.platform` + content file |
| Change a setting for Dev only | Edit `config/dev.json` |
| Change something across all environments | Edit the item file; let CI promote it |
| Roll back production | Revert the Git commit and push — pipeline redeploys old state |
| See deployment history | GitHub → **Actions** tab |
| Find a workspace ID | Fabric portal URL: `.../groups/{WORKSPACE_ID}/...` |
| Generate a logicalId GUID | `python -c "import uuid; print(uuid.uuid4())"` |
| Test locally without deploying | Set `DRY_RUN=true` before running `deploy.py` |
| Check if items are valid before pushing | Run `python scripts/validate_config.py` |

---

## Supported Fabric Item Types

| Type name | What it is |
|---|---|
| `Notebook` | PySpark / SQL notebook |
| `DataPipeline` | Data Factory pipeline |
| `SemanticModel` | Power BI semantic model (dataset) |
| `Report` | Power BI report |
| `Lakehouse` | Delta Lake storage + SQL analytics endpoint |
| `Warehouse` | Fabric SQL warehouse |
| `SparkJobDefinition` | Batch Spark job |
| `MLModel` | Machine learning model |
| `MLExperiment` | ML experiment (MLflow) |
| `Eventstream` | Real-time event stream |
| `KQLDatabase` | Kusto Query Language database |
| `KQLQueryset` | KQL query sets |
