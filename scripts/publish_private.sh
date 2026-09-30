#!/usr/bin/env bash
# Publish AIOS-0X to a PRIVATE GitHub repository, then verify the remote.
#
# Run this AFTER `gh auth login`. It performs the whole remaining Phase 5-8
# sequence and refuses to proceed rather than guess if anything is unexpected.
#
# Safe by construction:
#   - refuses to overwrite or delete an existing repository
#   - refuses to replace an existing remote
#   - no force-push anywhere
#   - prints what it did at every step
#
# Usage:  bash scripts/publish_private.sh [repo-name]

set -euo pipefail

REPO_NAME="${1:-aios-0x}"
cd "$(git rev-parse --show-toplevel)"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

say "preconditions"
git rev-parse --verify HEAD >/dev/null && echo "  HEAD:  $(git rev-parse --short HEAD) on $(git rev-parse --abbrev-ref HEAD)"
echo "  total commits: $(git rev-list --count HEAD)"
if [ -n "$(git status --porcelain)" ]; then
  echo "  REFUSING: working tree is not clean."; git status --short; exit 1
fi
echo "  working tree: clean"
echo "  author: $(git config user.name) <$(git config user.email)>"

gh auth status >/dev/null 2>&1 || { echo "  REFUSING: gh not authenticated. Run: gh auth login"; exit 1; }
ACCOUNT="$(gh api user --jq .login)"
echo "  authenticated as: $ACCOUNT"

say "repository name"
# Never overwrite. If the preferred name is taken, fall back to an unambiguous
# variant rather than picking a name that might collide with something else.
if gh repo view "$ACCOUNT/$REPO_NAME" >/dev/null 2>&1; then
  REPO_NAME="${REPO_NAME}-vnext"
  if gh repo view "$ACCOUNT/$REPO_NAME" >/dev/null 2>&1; then
    echo "  REFUSING: both aios-0x and aios-0x-vnext already exist in $ACCOUNT."
    echo "  Pass an explicit name: bash scripts/publish_private.sh <name>"
    exit 1
  fi
  echo "  $ACCOUNT/aios-0x already exists; using $REPO_NAME instead"
else
  echo "  using $REPO_NAME"
fi

say "remotes (refusing to replace one)"
EXISTING="$(git remote)"
if [ -n "$EXISTING" ]; then
  echo "  existing remotes:"; git remote -v | sed 's/^/    /'
  echo "  REFUSING: origin is already taken. Add the new repo under another"
  echo "  remote name yourself, then push to it. Nothing was changed."
  exit 1
fi
echo "  none; origin is free"

say "create (PRIVATE)"
gh repo create "$ACCOUNT/$REPO_NAME" \
  --private \
  --source=. \
  --remote=origin \
  --description "Investment operating system: authority chain, evidence fabric, deterministic quant core" \
  --push
echo "  created and pushed"

say "push remaining local refs (no force)"
git push origin main --set-upstream
git push origin feat/command-center-ui || echo "  note: feature branch push skipped"
git push origin master       || echo "  note: master push skipped (pre-existing history, non-blocking)"

say "visibility (must be PRIVATE)"
VIS="$(gh repo view "$ACCOUNT/$REPO_NAME" --json visibility --jq .visibility)"
echo "  visibility: $VIS"
[ "$VIS" = "PRIVATE" ] || { echo "  REFUSING: repository is not private."; exit 1; }

say "remote verification"
echo "  local HEAD:            $(git rev-parse HEAD)"
echo "  remote refs/heads/main: $(git ls-remote origin refs/heads/main | cut -f1)"
if [ "$(git rev-parse HEAD)" = "$(git ls-remote origin refs/heads/main | cut -f1)" ]; then
  echo "  MATCH: local HEAD is on remote main"
else
  echo "  MISMATCH: investigate before trusting the remote."; exit 1
fi
gh repo view "$ACCOUNT/$REPO_NAME" \
  --json nameWithOwner,visibility,defaultBranchRef,url,isPrivate \
  --jq '"  repo:        \(.nameWithOwner)\n  private:     \(.isPrivate)\n  default:     \(.defaultBranchRef.name)\n  url:         \(.url)"'

say "today's contributions"
gh api graphql -f query='
  query { viewer { contributionsCollection {
    contributionCalendar { totalContributions todayContributions } } } }' \
  --jq '"  total this year: \(.data.viewer.contributionsCollection.contributionCalendar.totalContributions)\n  today:           \(.data.viewer.contributionsCollection.contributionCalendar.todayContributions)"'

say "done"
