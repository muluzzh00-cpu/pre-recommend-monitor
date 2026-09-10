param([Parameter(Mandatory=$true)][string]$Repository)
$ErrorActionPreference = 'Stop'
if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') {
    throw 'Repository must be OWNER/REPO'
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'Install GitHub CLI from https://cli.github.com/ and run gh auth login first.'
}
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
gh auth status
if ($LASTEXITCODE -ne 0) { throw 'Please run gh auth login in your own terminal.' }
if (-not (Test-Path -LiteralPath '.git')) {
    git init -b main
    if ($LASTEXITCODE -ne 0) { throw 'git init failed' }
}
git add .
if ($LASTEXITCODE -ne 0) { throw 'git add failed' }
$changes = git diff --cached --name-only
if ($changes) {
    git commit -m 'Add admission monitoring system'
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed; configure your Git name/email' }
}
gh repo view $Repository --json name *> $null
if ($LASTEXITCODE -eq 0) {
    throw 'Repository already exists. Use the README existing-repository steps to avoid overwriting it.'
}
gh repo create $Repository --private --source . --remote origin --push
if ($LASTEXITCODE -ne 0) { throw 'Repository creation/upload failed' }
Write-Host 'Project uploaded. Next configure the five EMAIL_* repository Secrets in GitHub.'
Write-Host "Open: https://github.com/$Repository/settings/secrets/actions"
Write-Host 'Then Actions -> 2027 Admission Monitor -> Run workflow -> test-email -> run.'
Write-Host 'This script does not claim successful scheduled deployment before those checks.'
