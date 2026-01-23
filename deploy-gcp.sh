#!/bin/bash
#=============================================================================
# Second Brain - Google Cloud Platform Deployment Script
#=============================================================================
# This script deploys the full stack to Google Cloud:
# - Cloud SQL (PostgreSQL)
# - Cloud Run (Backend)
# - Cloud Run (Frontend)
#=============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "=============================================="
echo "   Second Brain - GCP Deployment"
echo "=============================================="
echo -e "${NC}"

#=============================================================================
# Configuration - UPDATE THESE VALUES
#=============================================================================
PROJECT_ID="${GCP_PROJECT_ID:-your-project-id}"
REGION="${GCP_REGION:-us-central1}"
DB_INSTANCE_NAME="secondbrain-db"
DB_NAME="secondbrain"
DB_USER="secondbrain"
BACKEND_SERVICE_NAME="secondbrain-backend"
FRONTEND_SERVICE_NAME="secondbrain-frontend"

#=============================================================================
# Check Prerequisites
#=============================================================================
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check gcloud CLI
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI not installed${NC}"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker not installed${NC}"
    exit 1
fi

echo -e "${GREEN}Prerequisites OK${NC}"

#=============================================================================
# Authenticate & Set Project
#=============================================================================
echo -e "${YELLOW}Setting up GCP project...${NC}"

# Set project
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com

echo -e "${GREEN}APIs enabled${NC}"

#=============================================================================
# Create Artifact Registry Repository
#=============================================================================
echo -e "${YELLOW}Creating Artifact Registry...${NC}"

gcloud artifacts repositories create secondbrain \
    --repository-format=docker \
    --location=$REGION \
    --description="Second Brain container images" \
    2>/dev/null || echo "Repository already exists"

# Configure Docker to use Artifact Registry
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

echo -e "${GREEN}Artifact Registry ready${NC}"

#=============================================================================
# Create Cloud SQL Instance
#=============================================================================
echo -e "${YELLOW}Setting up Cloud SQL...${NC}"

# Check if instance exists
if ! gcloud sql instances describe $DB_INSTANCE_NAME --project=$PROJECT_ID &>/dev/null; then
    echo "Creating Cloud SQL instance (this takes ~5 minutes)..."

    gcloud sql instances create $DB_INSTANCE_NAME \
        --database-version=POSTGRES_15 \
        --tier=db-f1-micro \
        --region=$REGION \
        --root-password=$(openssl rand -base64 24) \
        --storage-auto-increase

    # Create database
    gcloud sql databases create $DB_NAME --instance=$DB_INSTANCE_NAME

    # Create user
    DB_PASSWORD=$(openssl rand -base64 24)
    gcloud sql users create $DB_USER \
        --instance=$DB_INSTANCE_NAME \
        --password=$DB_PASSWORD

    # Store password in Secret Manager
    echo -n "$DB_PASSWORD" | gcloud secrets create db-password --data-file=-

    echo -e "${GREEN}Cloud SQL instance created${NC}"
else
    echo "Cloud SQL instance already exists"
fi

# Get connection name
CONNECTION_NAME=$(gcloud sql instances describe $DB_INSTANCE_NAME --format="value(connectionName)")
echo "Connection Name: $CONNECTION_NAME"

#=============================================================================
# Build and Push Backend Image
#=============================================================================
echo -e "${YELLOW}Building Backend...${NC}"

BACKEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/secondbrain/backend:latest"

cd backend
docker build -t $BACKEND_IMAGE .
docker push $BACKEND_IMAGE
cd ..

echo -e "${GREEN}Backend image pushed${NC}"

#=============================================================================
# Build and Push Frontend Image
#=============================================================================
echo -e "${YELLOW}Building Frontend...${NC}"

FRONTEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/secondbrain/frontend:latest"

cd frontend
docker build -t $FRONTEND_IMAGE .
docker push $FRONTEND_IMAGE
cd ..

echo -e "${GREEN}Frontend image pushed${NC}"

#=============================================================================
# Deploy Backend to Cloud Run
#=============================================================================
echo -e "${YELLOW}Deploying Backend to Cloud Run...${NC}"

# Get database password from Secret Manager
DB_PASSWORD=$(gcloud secrets versions access latest --secret=db-password)

gcloud run deploy $BACKEND_SERVICE_NAME \
    --image=$BACKEND_IMAGE \
    --platform=managed \
    --region=$REGION \
    --allow-unauthenticated \
    --add-cloudsql-instances=$CONNECTION_NAME \
    --set-env-vars="DATABASE_TYPE=postgresql" \
    --set-env-vars="POSTGRES_HOST=/cloudsql/${CONNECTION_NAME}" \
    --set-env-vars="POSTGRES_DB=${DB_NAME}" \
    --set-env-vars="POSTGRES_USER=${DB_USER}" \
    --set-env-vars="POSTGRES_PASSWORD=${DB_PASSWORD}" \
    --set-env-vars="AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}" \
    --set-env-vars="AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}" \
    --set-env-vars="AZURE_API_VERSION=${AZURE_API_VERSION}" \
    --set-env-vars="PINECONE_API_KEY=${PINECONE_API_KEY}" \
    --set-env-vars="PINECONE_INDEX_NAME=${PINECONE_INDEX_NAME}" \
    --set-env-vars="BOX_CLIENT_ID=${BOX_CLIENT_ID}" \
    --set-env-vars="BOX_CLIENT_SECRET=${BOX_CLIENT_SECRET}" \
    --set-env-vars="SLACK_CLIENT_ID=${SLACK_CLIENT_ID}" \
    --set-env-vars="SLACK_CLIENT_SECRET=${SLACK_CLIENT_SECRET}" \
    --set-env-vars="LLAMA_CLOUD_API_KEY=${LLAMA_CLOUD_API_KEY}" \
    --memory=2Gi \
    --cpu=2 \
    --timeout=300 \
    --min-instances=0 \
    --max-instances=10

# Get backend URL
BACKEND_URL=$(gcloud run services describe $BACKEND_SERVICE_NAME --region=$REGION --format="value(status.url)")
echo -e "${GREEN}Backend deployed: ${BACKEND_URL}${NC}"

#=============================================================================
# Deploy Frontend to Cloud Run
#=============================================================================
echo -e "${YELLOW}Deploying Frontend to Cloud Run...${NC}"

gcloud run deploy $FRONTEND_SERVICE_NAME \
    --image=$FRONTEND_IMAGE \
    --platform=managed \
    --region=$REGION \
    --allow-unauthenticated \
    --set-env-vars="NEXT_PUBLIC_API_URL=${BACKEND_URL}" \
    --memory=512Mi \
    --cpu=1 \
    --timeout=60 \
    --min-instances=0 \
    --max-instances=10

# Get frontend URL
FRONTEND_URL=$(gcloud run services describe $FRONTEND_SERVICE_NAME --region=$REGION --format="value(status.url)")
echo -e "${GREEN}Frontend deployed: ${FRONTEND_URL}${NC}"

#=============================================================================
# Summary
#=============================================================================
echo ""
echo -e "${BLUE}=============================================="
echo "   Deployment Complete!"
echo "=============================================="
echo -e "${NC}"
echo -e "${GREEN}Frontend URL:${NC} ${FRONTEND_URL}"
echo -e "${GREEN}Backend URL:${NC}  ${BACKEND_URL}"
echo -e "${GREEN}Database:${NC}     Cloud SQL (${CONNECTION_NAME})"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Update Box OAuth redirect URL to: ${BACKEND_URL}/api/auth/box/callback"
echo "2. Update Slack OAuth redirect URL to: ${BACKEND_URL}/api/auth/slack/callback"
echo "3. Test the application at: ${FRONTEND_URL}"
echo ""
echo -e "${BLUE}===============================================${NC}"
