# deploy_to_github.ps1
# =============================================================
# One-click script: สร้าง GitHub repo + push โค้ดขึ้น GitHub
# วิธีใช้: .\deploy_to_github.ps1 -Token "ghp_xxxx"
# =============================================================

param(
    [Parameter(Mandatory=$true)]
    [string]$Token
)

$GITHUB_USER = "watt29"
$REPO_NAME   = "shopee-affiliate-bot"
$PROJECT_DIR = "d:\Shopee_Web_Scraping"
$HEADERS = @{
    Authorization = "token $Token"
    Accept        = "application/vnd.github.v3+json"
    "User-Agent"  = "watt29-deploy-script"
}

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Shopee Affiliate Bot - GitHub Deploy Script" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Step 1: Check if repo already exists
Write-Host "`n[1/5] Checking if GitHub repo exists..." -ForegroundColor Yellow
$repoCheck = Invoke-RestMethod -Uri "https://api.github.com/repos/$GITHUB_USER/$REPO_NAME" `
    -Headers $HEADERS -Method GET -ErrorAction SilentlyContinue

if ($repoCheck) {
    Write-Host "     Repo already exists: https://github.com/$GITHUB_USER/$REPO_NAME" -ForegroundColor Green
} else {
    # Step 2: Create new private repo
    Write-Host "[2/5] Creating new GitHub repo '$REPO_NAME'..." -ForegroundColor Yellow
    $body = @{
        name        = $REPO_NAME
        description = "AI Affiliate Marketing Bot with LINE integration - FastAPI + Supabase"
        private     = $false
        auto_init   = $false
    } | ConvertTo-Json

    $newRepo = Invoke-RestMethod -Uri "https://api.github.com/user/repos" `
        -Headers $HEADERS -Method POST -Body $body -ContentType "application/json"

    Write-Host "     Created: $($newRepo.html_url)" -ForegroundColor Green
}

# Step 3: Init git and stage files
Write-Host "`n[3/5] Staging files..." -ForegroundColor Yellow
Set-Location $PROJECT_DIR

# Remove old git if needed
if (Test-Path ".git") {
    Write-Host "     Git repo already initialized." -ForegroundColor DarkGray
} else {
    git init
    Write-Host "     Git initialized." -ForegroundColor Green
}

git add .
$staged = git diff --cached --name-only | Measure-Object | Select-Object -ExpandProperty Count
Write-Host "     $staged files staged." -ForegroundColor Green

# Step 4: Commit
Write-Host "`n[4/5] Committing..." -ForegroundColor Yellow
$commitResult = git commit -m "feat: initial deploy - FastAPI LINE Bot backend for Render + Supabase" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "     Committed successfully." -ForegroundColor Green
} else {
    Write-Host "     $commitResult" -ForegroundColor DarkGray
    Write-Host "     (Nothing new to commit or already committed)" -ForegroundColor DarkGray
}

# Step 5: Push to GitHub
Write-Host "`n[5/5] Pushing to GitHub..." -ForegroundColor Yellow
$remoteUrl = "https://$Token@github.com/$GITHUB_USER/$REPO_NAME.git"

# Remove existing remote if any
git remote remove origin 2>&1 | Out-Null
git remote add origin $remoteUrl
git branch -M main
git push -u origin main 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n==================================================" -ForegroundColor Green
    Write-Host " SUCCESS! Code is now on GitHub:" -ForegroundColor Green
    Write-Host " https://github.com/$GITHUB_USER/$REPO_NAME" -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "`nNext steps:" -ForegroundColor Cyan
    Write-Host " 1. Go to https://supabase.com and create a new project" -ForegroundColor White
    Write-Host " 2. Copy 'Transaction Pooler' URL from Settings > Database" -ForegroundColor White
    Write-Host " 3. Go to https://render.com > New > Web Service" -ForegroundColor White
    Write-Host " 4. Connect GitHub repo: $GITHUB_USER/$REPO_NAME" -ForegroundColor White
    Write-Host " 5. Set ENV variables on Render (DATABASE_URL, LINE tokens, GEMINI_API_KEY)" -ForegroundColor White
    Write-Host " 6. Copy Render URL and update LINE Webhook + Cloudflare Worker" -ForegroundColor White
} else {
    Write-Host "`nPush failed. Check token permissions (needs 'repo' scope)." -ForegroundColor Red
}
