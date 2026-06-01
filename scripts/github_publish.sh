#!/usr/bin/env bash
# Publish this repo to GitHub (requires Personal Access Token, NOT account password).
# Usage:
#   export GITHUB_TOKEN=ghp_xxxxxxxx   # from https://github.com/settings/tokens
#   bash scripts/github_publish.sh

set -euo pipefail
cd "$(dirname "$0")/.."

REPO="${GITHUB_REPO:-Pelosi_following}"
API="https://api.github.com"
AUTH=(-H "Authorization: Bearer ${GITHUB_TOKEN}" -H "Accept: application/vnd.github+json")

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: Set GITHUB_TOKEN first (repo scope)."
  echo "  GitHub no longer accepts account password for git push."
  echo "  Create token: https://github.com/settings/tokens → classic (repo) or fine-grained (Contents: Read/Write)"
  exit 1
fi

whoami=$(curl -s "${AUTH[@]}" "${API}/user" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('login','')) if 'login' in d else sys.exit(1)" 2>/dev/null || true)
if [[ -z "$whoami" ]]; then
  echo "ERROR: GITHUB_TOKEN is invalid or expired."
  exit 1
fi
echo "Authenticated as: ${whoami}"

USER="${GITHUB_USER:-$whoami}"
if [[ "$whoami" != "$USER" ]]; then
  echo "ERROR: GITHUB_USER=${USER} but token belongs to ${whoami}."
  exit 1
fi

git branch -M main
if git remote get-url origin &>/dev/null; then
  git remote set-url origin "https://github.com/${USER}/${REPO}.git"
else
  git remote add origin "https://github.com/${USER}/${REPO}.git"
fi

repo_status=$(curl -s -o /dev/null -w "%{http_code}" "${AUTH[@]}" "${API}/repos/${USER}/${REPO}")
if [[ "$repo_status" == "404" ]]; then
  echo "Creating github.com/${USER}/${REPO} ..."
  create_body=$(curl -s -w "\n%{http_code}" "${AUTH[@]}" \
    -d "{\"name\":\"${REPO}\",\"private\":false,\"description\":\"Pelosi House STOCK Act PTR equity & options trade analysis\"}" \
    "${API}/user/repos")
  create_http=$(echo "$create_body" | tail -n1)
  create_json=$(echo "$create_body" | sed '$d')
  if [[ "$create_http" == "422" ]] && echo "$create_json" | grep -q "name already exists"; then
    echo "Repository already exists on ${USER} (create skipped)."
  elif [[ "$create_http" != "201" ]]; then
    echo "ERROR: Failed to create repository (HTTP ${create_http})."
    echo "$create_json" | python3 -m json.tool 2>/dev/null || echo "$create_json"
    exit 1
  else
    echo "Repository created."
  fi
elif [[ "$repo_status" != "200" ]]; then
  echo "ERROR: Cannot access github.com/${USER}/${REPO} (HTTP ${repo_status})."
  exit 1
else
  echo "Repository already exists."
fi

echo "Pushing to origin main ..."
git -c credential.helper='!f() { echo "username=${USER}"; echo "password=${GITHUB_TOKEN}"; }; f' \
  push -u origin main

echo ""
echo "Enabling GitHub Pages (main /docs) ..."
if bash "$(dirname "$0")/enable_github_pages.sh"; then
  :
else
  echo "Pages enable skipped or failed — run: bash scripts/enable_github_pages.sh"
fi

echo ""
echo "Done: https://github.com/${USER}/${REPO}"
echo "Report URL: https://${USER}.github.io/${REPO}/"
echo "Mobile: reports/FINAL_REPORT.mobile.html"
