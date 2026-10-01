<#
.SYNOPSIS
    Publish AIOS-0X to a PRIVATE GitHub repository, then verify the remote.

.DESCRIPTION
    The PowerShell equivalent of scripts/publish_private.sh, for environments
    where WSL is unavailable. Both do the same job and both are idempotent.

    Safe by construction:
      - refuses to overwrite a repository that already has commits
      - refuses to replace a remote that already points elsewhere
      - no force-push anywhere
      - prints what it did at every step

    An empty repository that is already the origin is reused rather than
    re-created. That matters because a repository may have been created by hand
    beforehand: creating 'aios-0x-vnext' beside an existing empty 'aios-0x'
    would leave two half-populated repositories and a confusing remote.

.EXAMPLE
    gh auth login
    powershell -ExecutionPolicy Bypass -File scripts\publish_private.ps1
#>

[CmdletBinding()]
param([string]$RepoName = 'aios-0x')

$ErrorActionPreference = 'Stop'
Set-Location (git rev-parse --show-toplevel)

function Say([string]$Message) {
    Write-Host ''
    Write-Host "== $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
    Write-Host "  REFUSING: $Message" -ForegroundColor Red
    exit 1
}

Say 'preconditions'
$head = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { Fail 'not a git repository with commits.' }
$branch = git rev-parse --abbrev-ref HEAD
Write-Host "  HEAD:  $($head.Substring(0, 7)) on $branch"
Write-Host "  total commits: $(git rev-list --count HEAD)"

$dirty = git status --porcelain
if ($dirty) { Fail "working tree is not clean.`n$dirty" }
Write-Host '  working tree: clean'
Write-Host "  author: $(git config user.name) <$(git config user.email)>"

gh auth status *> $null
if ($LASTEXITCODE -ne 0) { Fail 'gh not authenticated. Run: gh auth login' }
$account = gh api user --jq .login
Write-Host "  authenticated as: $account"

# 'absent' | 'empty' | 'populated'
function Get-RepoState([string]$Name) {
    gh repo view "$account/$Name" *> $null
    if ($LASTEXITCODE -ne 0) { return 'absent' }
    $refs = git ls-remote --heads "https://github.com/$account/$Name.git" 2>$null
    if (-not $refs) { return 'empty' }
    return 'populated'
}

Say 'destination repository'
$state = Get-RepoState $RepoName
switch ($state) {
    'absent' {
        Write-Host "  $account/$RepoName does not exist; creating it PRIVATE"
        gh repo create "$account/$RepoName" `
            --private `
            --source=. `
            --remote=origin `
            --description 'Investment operating system: authority chain, evidence fabric, deterministic quant core'
        if ($LASTEXITCODE -ne 0) { Fail 'gh repo create failed.' }
    }
    'empty' {
        Write-Host "  $account/$RepoName already exists and is empty; reusing it"
        $expected = "https://github.com/$account/$RepoName.git"
        $current = git remote get-url origin 2>$null
        if (-not $current) {
            git remote add origin $expected
            Write-Host '  added origin'
        }
        elseif ($current -ne $expected) {
            Fail "origin already points at $current. Nothing changed."
        }
        else {
            Write-Host '  origin already correct'
        }
    }
    'populated' {
        Write-Host "  $ACCOUNT/$RepoName already has commits." -ForegroundColor Red
        Fail ("Pushing here would either collide or require a force-push. Neither happens.`n" +
              "Choose another name if you really mean a second repository:`n" +
              "  powershell -ExecutionPolicy Bypass -File scripts\publish_private.ps1 -RepoName $RepoName-vnext")
    }
}

Say 'push'
git push --set-upstream origin main
if ($LASTEXITCODE -ne 0) { Fail 'push of main failed. Nothing was force-pushed.' }
git push origin master *> $null
if ($LASTEXITCODE -ne 0) { Write-Host '  note: master push skipped (non-blocking)' }
git push origin feat/command-center-ui *> $null
if ($LASTEXITCODE -ne 0) { Write-Host '  note: feature branch push skipped (non-blocking)' }

Say 'visibility (must be PRIVATE)'
$vis = gh repo view "$account/$RepoName" --json visibility --jq .visibility
Write-Host "  visibility: $vis"
if ($vis -ne 'PRIVATE') { Fail "repository is not private ($vis)." }

Say 'remote verification'
$localHead = git rev-parse HEAD
$remoteMain = (git ls-remote origin refs/heads/main) -split '\s+' | Select-Object -First 1
Write-Host "  local HEAD:             $localHead"
Write-Host "  remote refs/heads/main: $remoteMain"
if ($localHead -ne $remoteMain) { Fail 'HEAD mismatch: investigate before trusting the remote.' }
Write-Host '  MATCH: local HEAD is on remote main'

$meta = gh repo view "$account/$RepoName" --json nameWithOwner,isPrivate,defaultBranchRef,url |
    ConvertFrom-Json
Write-Host "  repo:    $($meta.nameWithOwner)"
Write-Host "  private: $($meta.isPrivate)"
Write-Host "  default: $($meta.defaultBranchRef.name)"
Write-Host "  url:     $($meta.url)"
Write-Host '  remote refs:'
git ls-remote origin | ForEach-Object { Write-Host "    $_" }

Say "today's contributions"
$q = 'query { viewer { contributionsCollection { contributionCalendar { totalContributions todayContributions } } } }'
$cal = gh api graphql -f query=$q | ConvertFrom-Json
Write-Host "  total this year: $($cal.data.viewer.contributionsCollection.contributionCalendar.totalContributions)"
Write-Host "  today:           $($cal.data.viewer.contributionsCollection.contributionCalendar.todayContributions)"

Say 'done'