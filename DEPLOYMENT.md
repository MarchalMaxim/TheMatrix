# Deploying TheMatrix to Cloud Run

One-time setup checklist for running the site on GCP Cloud Run with auto-deploy
from GitHub Actions. Expected time: **~20-30 minutes**. You only do this once.

After setup, the flow is:

```
Click "⚡ Trigger cycle"   ──► matrix-handoff.yml runs
                                 └─ calls Claude, commits rewritten public/ to main
                              ──► push to main triggers deploy.yml
                                   └─ builds Docker image → deploys to Cloud Run
                              ──► new revision live at the public URL ~1-2 min later
```

---

## 0. Prerequisites

- A Google Cloud account with billing enabled
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Admin rights on the GitHub repo (to add Actions secrets)

Set these shell variables once and reuse them below:

```bash
export PROJECT_ID="your-gcp-project-id"     # pick an ID, e.g. "themaxtrix-1234"
export REGION="europe-west1"                # or us-central1, etc.
export BUCKET="${PROJECT_ID}-matrix-data"   # globally unique bucket name
export REPO="matrix"                        # Artifact Registry repo name
export SA_NAME="matrix-deployer"            # the service account GH Actions uses
```

---

## 1. Create the GCP project and enable APIs

```bash
# Create project (or skip if you already have one)
gcloud projects create "${PROJECT_ID}" --set-as-default
gcloud config set project "${PROJECT_ID}"

# Link billing — do this in the console:
# https://console.cloud.google.com/billing/linkedaccount?project=${PROJECT_ID}

# Enable the services we need
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com
```

## 2. Create a GCS bucket for persistent data

```bash
gcloud storage buckets create "gs://${BUCKET}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --uniform-bucket-level-access
```

This bucket will be mounted at `/app/data` inside Cloud Run. Your notes,
cycle archives, runs, and daily salt will live here.

## 3. Create an Artifact Registry Docker repo

```bash
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker \
  --location="${REGION}" \
  --description="TheMatrix images"
```

## 4. Store secrets in Secret Manager

The Cloud Run container will read these at runtime. For each, paste the value
when prompted (or pipe `echo -n`):

```bash
# Your Anthropic API key (console.anthropic.com → API keys)
echo -n "sk-ant-…" | gcloud secrets create ANTHROPIC_API_KEY --data-file=-

# A fine-grained GitHub PAT the server uses to dispatch the handoff workflow
# Scopes: Actions Read&Write, Contents Read&Write, Metadata Read
echo -n "github_pat_…" | gcloud secrets create MATRIX_GITHUB_TOKEN --data-file=-

# A random string to gate the /logs operator page
echo -n "$(openssl rand -hex 16)" | gcloud secrets create LOGS_TOKEN --data-file=-
```

## 5. Create a service account for GitHub Actions

This is the identity the deploy workflow uses to push Docker images and deploy
to Cloud Run.

```bash
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="TheMatrix GitHub Actions deployer"

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Grants: build/push images, deploy Cloud Run, act as service account user,
# read secrets that the service uses.
for role in \
  roles/run.admin \
  roles/artifactregistry.writer \
  roles/iam.serviceAccountUser \
  roles/secretmanager.secretAccessor \
  roles/storage.objectAdmin ; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${role}"
done

# Download a JSON key for this SA — this goes into GitHub as a secret.
# Treat this file like a password. Delete it after uploading.
gcloud iam service-accounts keys create matrix-deployer.json \
  --iam-account="${SA_EMAIL}"
```

Now the Cloud Run service also needs permission to read the secrets it gets
injected into env vars. The service runs under the default Compute Engine SA
unless you specify otherwise — grant it `secretmanager.secretAccessor` too:

```bash
COMPUTE_SA="$(gcloud iam service-accounts list \
  --filter='email ~ compute@developer.gserviceaccount.com' \
  --format='value(email)')"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role="roles/secretmanager.secretAccessor"

# And to mount the GCS bucket:
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${COMPUTE_SA}" \
  --role="roles/storage.objectAdmin"
```

## 6. Add secrets and variables to the GitHub repo

Go to `https://github.com/<you>/<repo>/settings`:

### Secrets (Settings → Secrets and variables → Actions → Secrets)

| Name | Value |
|---|---|
| `GCP_SA_KEY` | Full contents of `matrix-deployer.json` from step 5 |
| `ANTHROPIC_API_KEY` | Same API key you stored in Secret Manager (used by `matrix-handoff.yml`) |

### Variables (Settings → Secrets and variables → Actions → Variables)

| Name | Value |
|---|---|
| `GCP_PROJECT_ID` | `${PROJECT_ID}` from above |
| `GCP_REGION` | `${REGION}` from above |
| `GCS_BUCKET_NAME` | `${BUCKET}` from above |

Delete the local `matrix-deployer.json` file now:

```bash
shred -u matrix-deployer.json 2>/dev/null || rm matrix-deployer.json
```

## 7. Trigger the first deploy

Any push to `main` triggers `deploy.yml`. Either push an empty commit or wait
for the next chaos cycle:

```bash
git commit --allow-empty -m "chore: kick off first Cloud Run deploy"
git push origin main
```

Watch it go at:
`https://github.com/<you>/<repo>/actions/workflows/deploy.yml`

First build takes 3-5 minutes. When it finishes the summary will include
the service URL, something like:

```
Deployed to https://matrix-server-xxxxxxx-ew.a.run.app
```

Open that URL — you should see TheMatrix running, backed by GCS-persistent data.

## 8. Sanity-check the chaos loop

1. Visit the Cloud Run URL
2. Post a note or two (PoW will work, just slower than localhost)
3. Click **⚡ Trigger cycle**
4. Check `https://github.com/<you>/<repo>/actions` — you should see a
   `matrix-handoff` run start. Once it finishes, a commit appears on `main`.
5. That push triggers `deploy.yml`, which rebuilds + redeploys.
6. ~2 minutes later the site looks different. History panel shows the commit.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `deploy.yml` fails at "Authenticate to GCP" | `GCP_SA_KEY` secret is malformed — should be the raw JSON, no extra quotes |
| Cloud Run service boots but HTTP 500s immediately | GCS volume mount failed — check the run has `execution-environment=gen2` (the workflow sets this) and that the compute SA has `storage.objectAdmin` |
| Service starts but `/api/history` is empty | No commits yet matching `cycle-*` prefix, or `GITHUB_TOKEN` env not set. Check Cloud Run logs for `history fetch failed` warnings. |
| `matrix-handoff.yml` fails at "Commit and push" with permission denied | Workflow doesn't have `contents: write` — already set in the YAML, but confirm in the repo's Settings → Actions → Workflow permissions → "Read and write permissions" |
| Cycle agent commits non-sense HTML that breaks the page | Expected under chaos rules. `git revert <sha>` on main → auto-redeploys the previous version. |

## Costs

Rough monthly cost for the setup in `deploy.yml`:

- Cloud Run (1 vCPU, 512MB, min-instances=1, always on): **~$15/mo**
- Artifact Registry storage (a few images): **<$1/mo**
- GCS bucket (a few MB of JSON): **<$0.10/mo**
- GitHub Actions minutes (only on-demand): **free for public repos, otherwise your plan allowance**
- Anthropic API calls (one per 4h = 180/mo): **depends on prompt size, likely $1-5/mo**

Scale to zero (min-instances=0) saves ~$15/mo but the cycle worker stops
running between requests. If you go that route, move the scheduled cycle to
Cloud Scheduler + a dedicated Cloud Run Job.
