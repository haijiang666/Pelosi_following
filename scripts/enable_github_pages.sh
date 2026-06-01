#!/usr/bin/env bash
# Enable GitHub Pages for this repo (fixes 404 on *.github.io/REPO/).
# Usage:
#   export GITHUB_TOKEN=ghp_xxxx
#   bash scripts/enable_github_pages.sh

set -euo pipefail
cd "$(dirname "$0")/.."

REPO="${GITHUB_REPO:-Pelosi_following}"
USER="${GITHUB_USER:-haijiang666}"
API="https://api.github.com"
AUTH=(-H "Authorization: Bearer ${GITHUB_TOKEN}" -H "Accept: application/vnd.github+json")

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: export GITHUB_TOKEN=ghp_xxxx first (repo scope)."
  exit 1
fi

status=$(curl -s -o /tmp/pages.json -w "%{http_code}" "${AUTH[@]}" "${API}/repos/${USER}/${REPO}/pages")
if [[ "$status" == "200" ]]; then
  echo "Pages already configured:"
  python3 -m json.tool /tmp/pages.json 2>/dev/null || cat /tmp/pages.json
  exit 0
fi

echo "Enabling Pages: main branch, /docs ..."
resp=$(curl -s -w "\n%{http_code}" -X POST "${AUTH[@]}" \
  -d '{"build_type":"legacy","source":{"branch":"main","path":"/docs"}}' \
  "${API}/repos/${USER}/${REPO}/pages")
http=$(echo "$resp" | tail -n1)
body=$(echo "$resp" | sed '$d')

if [[ "$http" == "201" || "$http" == "200" ]]; then
  echo "OK — Pages enabled (legacy: main /docs)."
  echo "URL: https://${USER}.github.io/${REPO}/"
  echo "Allow 1–3 minutes for the first deploy."
  exit 0
fi

echo "Legacy enable failed (HTTP ${http}). Trying workflow build_type ..."
resp2=$(curl -s -w "\n%{http_code}" -X POST "${AUTH[@]}" \
  -d '{"build_type":"workflow"}' \
  "${API}/repos/${USER}/${REPO}/pages")
http2=$(echo "$resp2" | tail -n1)
body2=$(echo "$resp2" | sed '$d')

if [[ "$http2" == "201" || "$http2" == "200" ]]; then
  echo "OK — Pages set to GitHub Actions workflow."
  echo "Push to main or run: gh workflow run deploy-pages.yml"
  echo "Then: Settings → Pages → Source should show 'GitHub Actions'"
  exit 0
fi

echo "ERROR: Could not enable Pages automatically."
echo "$body2" | python3 -m json.tool 2>/dev/null || echo "$body2"
echo ""
echo "Manual fix:"
echo "  https://github.com/${USER}/${REPO}/settings/pages"
echo "  Source: Deploy from branch → main → /docs"
echo "  OR: GitHub Actions → workflow 'Deploy GitHub Pages'"
exit 1
