# Second Brain - Google Cloud Deployment Guide

## Architecture Overview

```
                    Internet
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
    ┌──────────────┐       ┌──────────────┐
    │  Cloud Run   │       │  Cloud Run   │
    │  (Frontend)  │──────▶│  (Backend)   │
    │   Next.js    │       │    Flask     │
    └──────────────┘       └──────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
            ┌────────────┐  ┌──────────┐  ┌─────────────┐
            │ Cloud SQL  │  │ Pinecone │  │ Azure OpenAI│
            │ PostgreSQL │  │ (Vector) │  │    (LLM)    │
            └────────────┘  └──────────┘  └─────────────┘
```

## Prerequisites

1. **Google Cloud Account** with billing enabled
2. **gcloud CLI** installed ([Install Guide](https://cloud.google.com/sdk/docs/install))
3. **Docker** installed ([Install Guide](https://docs.docker.com/get-docker/))
4. **API Keys** for external services (Azure OpenAI, Pinecone, Box, Slack)

## Quick Start (5 Minutes)

### Step 1: Set Up Environment

```bash
# Clone or navigate to project
cd 2nd-brain

# Copy environment template
cp .env.template .env

# Edit .env and fill in your values
nano .env  # or your preferred editor
```

### Step 2: Authenticate with Google Cloud

```bash
# Login to GCP
gcloud auth login

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    sqladmin.googleapis.com \
    artifactregistry.googleapis.com
```

### Step 3: Deploy

```bash
# Make script executable
chmod +x deploy-gcp.sh

# Set environment variables
export GCP_PROJECT_ID=your-project-id
export GCP_REGION=us-central1  # or your preferred region

# Export your API keys
export AZURE_OPENAI_ENDPOINT=your-endpoint
export AZURE_OPENAI_API_KEY=your-key
export PINECONE_API_KEY=your-key
# ... (see .env.template for all required vars)

# Run deployment
./deploy-gcp.sh
```

## Manual Deployment Steps

If you prefer to deploy manually:

### 1. Create Artifact Registry

```bash
gcloud artifacts repositories create secondbrain \
    --repository-format=docker \
    --location=us-central1

gcloud auth configure-docker us-central1-docker.pkg.dev
```

### 2. Create Cloud SQL Instance

```bash
gcloud sql instances create secondbrain-db \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region=us-central1

gcloud sql databases create secondbrain --instance=secondbrain-db

gcloud sql users create secondbrain \
    --instance=secondbrain-db \
    --password=YOUR_SECURE_PASSWORD
```

### 3. Build and Push Backend

```bash
cd backend

docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT/secondbrain/backend:latest .

docker push us-central1-docker.pkg.dev/YOUR_PROJECT/secondbrain/backend:latest
```

### 4. Build and Push Frontend

```bash
cd frontend

docker build -t us-central1-docker.pkg.dev/YOUR_PROJECT/secondbrain/frontend:latest .

docker push us-central1-docker.pkg.dev/YOUR_PROJECT/secondbrain/frontend:latest
```

### 5. Deploy Backend to Cloud Run

```bash
gcloud run deploy secondbrain-backend \
    --image=us-central1-docker.pkg.dev/YOUR_PROJECT/secondbrain/backend:latest \
    --platform=managed \
    --region=us-central1 \
    --allow-unauthenticated \
    --add-cloudsql-instances=YOUR_PROJECT:us-central1:secondbrain-db \
    --set-env-vars="DATABASE_TYPE=postgresql,POSTGRES_HOST=/cloudsql/YOUR_PROJECT:us-central1:secondbrain-db" \
    --memory=2Gi
```

### 6. Deploy Frontend to Cloud Run

```bash
# Get backend URL first
BACKEND_URL=$(gcloud run services describe secondbrain-backend --region=us-central1 --format="value(status.url)")

gcloud run deploy secondbrain-frontend \
    --image=us-central1-docker.pkg.dev/YOUR_PROJECT/secondbrain/frontend:latest \
    --platform=managed \
    --region=us-central1 \
    --allow-unauthenticated \
    --set-env-vars="NEXT_PUBLIC_API_URL=${BACKEND_URL}" \
    --memory=512Mi
```

## Local Development with Docker

### Start All Services

```bash
# Start PostgreSQL + Backend + Frontend
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

### Individual Services

```bash
# Backend only
cd backend
docker build -t secondbrain-backend .
docker run -p 5003:5003 --env-file ../.env secondbrain-backend

# Frontend only
cd frontend
docker build -t secondbrain-frontend .
docker run -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://localhost:5003 secondbrain-frontend
```

## Post-Deployment Configuration

### 1. Update OAuth Redirect URLs

After deployment, update your OAuth apps:

**Box Developer Console:**
- Redirect URI: `https://YOUR_BACKEND_URL/api/auth/box/callback`

**Slack API Dashboard:**
- Redirect URLs: `https://YOUR_BACKEND_URL/api/auth/slack/callback`

### 2. Initialize Database

The database schema is auto-created on first run. If needed:

```bash
# Connect to Cloud SQL
gcloud sql connect secondbrain-db --user=secondbrain

# Run any migrations manually if needed
```

### 3. Test the Deployment

```bash
# Check backend health
curl https://YOUR_BACKEND_URL/api/health

# Open frontend
open https://YOUR_FRONTEND_URL
```

## Cost Estimates

| Service | Configuration | Estimated Cost |
|---------|--------------|----------------|
| Cloud Run (Backend) | 2 vCPU, 2GB RAM, min 0 | ~$5-20/month |
| Cloud Run (Frontend) | 1 vCPU, 512MB RAM, min 0 | ~$2-10/month |
| Cloud SQL | db-f1-micro | ~$7/month |
| **Total** | | **~$15-40/month** |

*Note: Costs depend on usage. Cloud Run scales to zero when not in use.*

## Troubleshooting

### Backend won't start

```bash
# Check logs
gcloud run services logs read secondbrain-backend --region=us-central1

# Common issues:
# - Missing environment variables
# - Database connection issues
# - Memory limits too low
```

### Frontend can't connect to backend

```bash
# Verify NEXT_PUBLIC_API_URL is set correctly
gcloud run services describe secondbrain-frontend --region=us-central1

# Check CORS settings in backend
```

### Database connection issues

```bash
# Check Cloud SQL instance status
gcloud sql instances describe secondbrain-db

# Verify connection name format: PROJECT:REGION:INSTANCE
```

## Cleanup

To delete all resources:

```bash
# Delete Cloud Run services
gcloud run services delete secondbrain-backend --region=us-central1
gcloud run services delete secondbrain-frontend --region=us-central1

# Delete Cloud SQL (WARNING: deletes all data)
gcloud sql instances delete secondbrain-db

# Delete Artifact Registry
gcloud artifacts repositories delete secondbrain --location=us-central1
```
