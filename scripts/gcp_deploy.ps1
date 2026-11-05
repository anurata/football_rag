<#
.SYNOPSIS
    Deploy Football RAG to Google Cloud Run with Cloud Storage volume mount.
.DESCRIPTION
    Automates:
      1. GCS Bucket creation & data sync (data/ -> gs://<bucket>)
      2. Secret Manager auto-detection (GEMINI_API_KEY)
      3. Container build with Cloud Build / Artifact Registry
      4. Cloud Run deployment with GCS volume mount for either Streamlit or FastAPI
.PARAMETER ProjectId
    GCP Project ID.
.PARAMETER Region
    GCP Region (Default: asia-northeast1).
.PARAMETER AppMode
    Application mode to deploy: "streamlit" (Web UI) or "api" (Mobile FastAPI). Default: streamlit.
.PARAMETER ServiceName
    Cloud Run service name (Default: football-rag-app for streamlit, football-rag-api for api).
.PARAMETER BucketName
    GCS Bucket name for persistent data (Default: <ProjectId>-football-rag-data).
.PARAMETER SkipDataSync
    Skip uploading local data/ directory to GCS.
.PARAMETER SkipBuild
    Skip container image build with Cloud Build (reuse latest existing image).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [Parameter(Mandatory = $false)]
    [string]$Region = "asia-northeast1",

    [Parameter(Mandatory = $false)]
    [ValidateSet("streamlit", "api")]
    [string]$AppMode = "streamlit",

    [Parameter(Mandatory = $false)]
    [string]$ServiceName = "",

    [Parameter(Mandatory = $false)]
    [string]$BucketName = "",

    [Parameter(Mandatory = $false)]
    [switch]$SkipDataSync,

    [Parameter(Mandatory = $false)]
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

# Ensure Google Cloud SDK is in PATH if newly installed
$cloudSdkBin = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin"
if ((Test-Path $cloudSdkBin) -and ($env:Path -notlike "*$cloudSdkBin*")) {
    $env:Path = "$cloudSdkBin;$env:Path"
}

if ([string]::IsNullOrWhiteSpace($ServiceName)) {
    if ($AppMode -eq "api") {
        $ServiceName = "football-rag-api"
    } else {
        $ServiceName = "football-rag-app"
    }
}

if ([string]::IsNullOrWhiteSpace($BucketName)) {
    $BucketName = "${ProjectId}-football-rag-data"
}

# Container image tag is shared across services since docker_entrypoint.sh routes via APP_MODE
$ImageTag = "${Region}-docker.pkg.dev/${ProjectId}/football-rag/football-rag-app:latest"
$RepoName = "football-rag"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Football RAG - GCP Cloud Run Deployment" -ForegroundColor Cyan
Write-Host " Project:     $ProjectId" -ForegroundColor Green
Write-Host " Region:      $Region" -ForegroundColor Green
Write-Host " App Mode:    $AppMode" -ForegroundColor Green
Write-Host " Service:     $ServiceName" -ForegroundColor Green
Write-Host " Bucket:      $BucketName" -ForegroundColor Green
Write-Host " Image:       $ImageTag" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Set active project and enable required services
Write-Host "`n[1/5] Enabling GCP APIs..." -ForegroundColor Yellow
gcloud config set project $ProjectId
gcloud services enable `
    run.googleapis.com `
    artifactregistry.googleapis.com `
    cloudbuild.googleapis.com `
    secretmanager.googleapis.com `
    storage.googleapis.com

# 2. Setup GCS bucket & Sync data
Write-Host "`n[2/5] Checking GCS Bucket: gs://$BucketName..." -ForegroundColor Yellow
$existingBuckets = gcloud storage buckets list --project=$ProjectId --format="value(name)"
if ($existingBuckets -notcontains $BucketName) {
    Write-Host "Creating GCS Bucket: gs://$BucketName..." -ForegroundColor Green
    gcloud storage buckets create "gs://$BucketName" --location=$Region
} else {
    Write-Host "Bucket gs://$BucketName already exists." -ForegroundColor Gray
}

# Grant Cloud Run default service account permission to access the GCS bucket
$projectNumber = gcloud projects describe $ProjectId --format="value(projectNumber)"
$computeServiceAccount = "${projectNumber}-compute@developer.gserviceaccount.com"
Write-Host "Granting Storage Object Admin to $computeServiceAccount on gs://$BucketName..." -ForegroundColor Gray
gcloud storage buckets add-iam-policy-binding "gs://$BucketName" `
    --member="serviceAccount:${computeServiceAccount}" `
    --role="roles/storage.objectAdmin" 2>$null

if (-not $SkipDataSync) {
    Write-Host "Syncing local data/ to gs://$BucketName/..." -ForegroundColor Green
    if (Test-Path "data") {
        gcloud storage rsync -r "data" "gs://${BucketName}"
    } else {
        Write-Warning "Local data/ directory not found. Skipping initial sync."
    }
}

# 3. Setup Artifact Registry Repository
Write-Host "`n[3/5] Checking Artifact Registry repository..." -ForegroundColor Yellow
$existingRepos = gcloud artifacts repositories list --location=$Region --format="value(name)"
$repoFound = $false
foreach ($r in $existingRepos) {
    if ($r -match $RepoName) { $repoFound = $true; break }
}
if (-not $repoFound) {
    Write-Host "Creating Artifact Registry repository: $RepoName..." -ForegroundColor Green
    gcloud artifacts repositories create $RepoName `
        --repository-format=docker `
        --location=$Region `
        --description="Football RAG Container Repository"
    if ($LASTEXITCODE -ne 0) { throw "Failed to create Artifact Registry repository." }
} else {
    Write-Host "Artifact Registry repository $RepoName already exists." -ForegroundColor Gray
}

# 4. Build and Submit Container Image
if (-not $SkipBuild) {
    Write-Host "`n[4/5] Building container image with Cloud Build..." -ForegroundColor Yellow
    gcloud builds submit --tag $ImageTag .
    if ($LASTEXITCODE -ne 0) { throw "Cloud Build failed." }
} else {
    Write-Host "`n[4/5] Skipping container build as requested (-SkipBuild)." -ForegroundColor Gray
}

# 5. Deploy to Cloud Run with GCS Volume Mount
Write-Host "`n[5/5] Deploying service '$ServiceName' to Cloud Run (APP_MODE=$AppMode)..." -ForegroundColor Yellow

# Check if GEMINI_API_KEY secret exists in Secret Manager
$secretArgs = @()
$existingSecrets = gcloud secrets list --project=$ProjectId --format="value(name)" 2>$null
if ($existingSecrets -match "GEMINI_API_KEY") {
    Write-Host "Detected Secret 'GEMINI_API_KEY'. Adding secret binding..." -ForegroundColor Green
    $secretArgs = @("--set-secrets=GEMINI_API_KEY=GEMINI_API_KEY:latest")
}

$deployArgs = @(
    "run", "deploy", $ServiceName,
    "--image=$ImageTag",
    "--region=$Region",
    "--platform=managed",
    "--allow-unauthenticated",
    "--execution-environment=gen2",
    "--memory=2Gi",
    "--cpu=1",
    "--min-instances=0",
    "--max-instances=1",
    "--set-env-vars=FOOTBALL_DB_PATH=/mnt/gcs/football.db,CHROMA_PERSIST_DIR=/mnt/gcs/chroma_db,APP_MODE=$AppMode",
    "--add-volume=name=gcs-data,type=cloud-storage,bucket=${BucketName}",
    "--add-volume-mount=volume=gcs-data,mount-path=/mnt/gcs"
) + $secretArgs

& gcloud @deployArgs
if ($LASTEXITCODE -ne 0) { throw "Cloud Run deployment failed." }

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host " Deployment of '$ServiceName' ($AppMode) completed successfully!" -ForegroundColor Green
$serviceUrl = gcloud run services describe $ServiceName --project=$ProjectId --region=$Region --format="value(status.url)"
Write-Host " Service URL: $serviceUrl" -ForegroundColor Cyan
if ($AppMode -eq "api") {
    Write-Host " Swagger UI:  ${serviceUrl}/docs" -ForegroundColor Yellow
    Write-Host " Health API:  ${serviceUrl}/api/health" -ForegroundColor Yellow
}
Write-Host "==========================================================" -ForegroundColor Cyan
