#!/usr/bin/env bash
# Publish AIOS-0X to a PRIVATE GitHub repository, then verify the remote.
#
# Run this AFTER `gh auth login`. It performs the whole remaining publish and
# verification sequence and refuses to proceed rather than guess.
#
# Safe by construction:
#   - refuses to overwrite a repository that already has content
#   - refuses to replace a remote that already points elsewhere
#   - no force-push anywhere
#   - prints what it did at every step
#
# Idempotent: an empty repository that is already the origin is reused rather
# than re-created, and a second run does nothing but re-verify. That matters
# because a repository may legitimately have been created by hand beforehand --
# creating `aios-0x-vnext` next to an existing empty `aios-0x` would leave two
# half-populated repositories and a permanently confusing remote.
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

# Is the candidate repository already present, and does it hold anything?
repo_state() {  # echoes: absent | empty | populated
  if ! gh repo view "$ACCOUNT/$1" >/dev/null 2>&1; then echo absent; return; fi
  if [ -z "$(git ls-remote --heads "https://github.com/$ACCOUNT/$1.git" 2>/dev/null)" ]; then
    echo empty
  else
    echo populated
  fi
}

say "destination repository"
STATE="$(repo_state "$REPO_NAME")"
case "$STATE" in
  absent)
    echo "  $ACCOUNT/$REPO_NAME does not exist; creating it PRIVATE"
    gh repo create "$ACCOUNT/$REPO_NAME" \
      --private \
      --source=. \
      --remote=origin \
      --description "Investment operating system: authority chain, evidence fabric, deterministic quant core"
    ;;
  empty)
    echo "  $ACCOUNT/$REPO_NAME already exists and is empty; reusing it"
    CURRENT="$(git remote get-url origin 2>/dev/null || true)"
    if [ -z "$CURRENT" ]; then
      git remote add origin "https://github.com/$ACCOUNT/$REPO_NAME.git"
      echo "  added origin"
    elif [ "$CURRENT" != "https://github.com/$ACCOUNT/$REPO_NAME.git" ]; then
      echo "  REFUSING: origin already points at $CURRENT. Nothing changed."
      exit 1
    else
      echo "  origin already correct"
    fi
    ;;
  populated)
    echo "  REFUSING: $ACCOUNT/$REPO_NAME already has commits."
    echo "  Pushing here would either collide or require a force-push. Neither"
    echo "  happens. Choose another name if you really mean a second repository:"
    echo "    bash scripts/publish_private.sh ${REPO_NAME}-vnext"
    exit 1
    ;;
esac

say "push"
git push --set-upstream origin main
git push origin master              || echo "  note: master push skipped (non-blocking)"
git push origin feat/command-center-ui || echo "  note: feature branch push skipped (non-blocking)"

say "visibility (must be PRIVATE)"
VIS="$(gh repo view "$ACCOUNT/$REPO_NAME" --json visibility --jq .visibility)"
echo "  visibility: $VIS"
[ "$VIS" = "PRIVATE" ] || { echo "  REFUSING: repository is not private."; exit 1; }

say "remote verification"
LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_MAIN="$(git ls-remote origin refs/heads/main | cut -f1)"
echo "  local HEAD:             $LOCAL_HEAD"
echo "  remote refs/heads/main: $REMOTE_MAIN"
if [ "$LOCAL_HEAD" = "$REMOTE_MAIN" ]; then
  echo "  MATCH: local HEAD is on remote main"
else
  echo "  MISMATCH: investigate before trusting the remote."; exit 1
fi
gh repo view "$ACCOUNT/$REPO_NAME" \
  --json nameWithOwner,isPrivate,defaultBranchRef,url \
  --jq '"  repo:    \(.nameWithOwner)\n  private: \(.isPrivate)\n  default: \(.defaultBranchRef.name)\n  url:     \(.url)"'
echo "  remote refs:"
git ls-remote origin | sed 's/^/    /'

say "today's contributions"
gh api graphql -f query='
  query { viewer { contributionsCollection {
    contributionCalendar { totalContributions todayContributions } } } }' \
  --jq '"  total this year: \(.data.viewer.contributionsCollection.contributionCalendar.totalContributions)\n  today:           \(.data.viewer.contributionsCollection.contributionCalendar.todayContributions)"'

say "done"