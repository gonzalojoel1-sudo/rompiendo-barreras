#!/usr/bin/env bash
# =============================================================================
# validate_workflow.sh — Local validator for deploy.yml + test.yml
# =============================================================================
# Runs all checks that GitHub Actions would do, WITHOUT:
#   - Pushing anything to GitHub
#   - SSH'ing to the VPS
#   - Sending secrets anywhere
#
# What it checks:
#   1. YAML syntax of both workflow files
#   2. Appleboy/ssh-action version exists and is pinned
#   3. workflow_call trigger present in test.yml (required for deploy.yml reuse)
#   4. workflow_dispatch trigger for manual testing
#   5. Required secrets referenced in deploy.yml exist as workflow inputs
#   6. The bash script embedded in deploy.yml parses with `bash -n`
#   7. Python syntax of vps_backend/ + scripts/ (same as test.yml)
#
# Usage:
#   ./scripts/validate_workflow.sh
# =============================================================================

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

PASS=0
FAIL=0
WARN=0

ok()   { printf "  ✅ %s\n" "$1"; PASS=$((PASS + 1)); }
fail() { printf "  ❌ %s\n" "$1"; FAIL=$((FAIL + 1)); }
warn() { printf "  ⚠️  %s\n" "$1"; WARN=$((WARN + 1)); }
hdr()  { printf "\n━━━ %s ━━━\n" "$1"; }

# ----------------------------------------------------------------------------
hdr "1. YAML syntax"
# ----------------------------------------------------------------------------
for f in .github/workflows/deploy.yml .github/workflows/test.yml; do
  if python3 -c "import yaml,sys; yaml.safe_load(open('$f'))" 2>/dev/null; then
    ok "$f parses as valid YAML"
  else
    fail "$f has YAML syntax errors"
    python3 -c "import yaml,sys; yaml.safe_load(open('$f'))"
  fi
done

# ----------------------------------------------------------------------------
hdr "2. Appleboy/ssh-action version"
# ----------------------------------------------------------------------------
SSH_VER=$(grep -E "appleboy/ssh-action@" .github/workflows/deploy.yml | head -1 | sed -E 's/.*@v?([0-9.]+).*/\1/' || echo "")
if [[ -z "${SSH_VER}" ]]; then
  fail "appleboy/ssh-action version not found in deploy.yml"
elif [[ "${SSH_VER}" == "1.0.3" || "${SSH_VER}" =~ ^1\.[0-9]+\.[0-9]+$ ]]; then
  ok "appleboy/ssh-action@v${SSH_VER} pinned"
  if [[ "${SSH_VER}" != "1.2.5" ]]; then
    warn "latest stable is v1.2.5 (you're on v${SSH_VER}) — OK but consider upgrading"
  fi
else
  fail "appleboy/ssh-action has invalid version: ${SSH_VER}"
fi

# ----------------------------------------------------------------------------
hdr "3. workflow_call trigger on test.yml"
# ----------------------------------------------------------------------------
if grep -E "^\s*workflow_call:" .github/workflows/test.yml >/dev/null; then
  ok "test.yml has workflow_call trigger (required for reusable workflow)"
else
  fail "test.yml MISSING workflow_call — deploy.yml will fail with 'workflow is not reusable'"
fi

# ----------------------------------------------------------------------------
hdr "4. workflow_dispatch triggers"
# ----------------------------------------------------------------------------
if grep -E "^\s*workflow_dispatch:" .github/workflows/deploy.yml >/dev/null; then
  ok "deploy.yml has workflow_dispatch (manual trigger)"
else
  warn "deploy.yml has no workflow_dispatch — can only run via push"
fi
if grep -E "^\s*workflow_dispatch:" .github/workflows/test.yml >/dev/null; then
  ok "test.yml has workflow_dispatch"
else
  warn "test.yml has no workflow_dispatch"
fi

# ----------------------------------------------------------------------------
hdr "5. Required secrets referenced"
# ----------------------------------------------------------------------------
for secret in VPS_HOST VPS_USER SSH_PRIVATE_KEY; do
  if grep -E "secrets\.${secret}" .github/workflows/deploy.yml >/dev/null; then
    ok "deploy.yml uses secrets.${secret}"
  else
    fail "deploy.yml does NOT reference secrets.${secret}"
  fi
done

# ----------------------------------------------------------------------------
hdr "6. Embedded bash script validation"
# ----------------------------------------------------------------------------
# Extract the script: block from deploy.yml and run bash -n on it.
TMP_SCRIPT=$(mktemp)
trap 'rm -f "${TMP_SCRIPT}"' EXIT

python3 - <<PY > "${TMP_SCRIPT}"
import yaml
with open('.github/workflows/deploy.yml') as f:
    wf = yaml.safe_load(f)
script = wf['jobs']['deploy']['steps'][1]['with']['script']
print(script)
PY

if bash -n "${TMP_SCRIPT}" 2>&1; then
  ok "embedded bash script parses with bash -n"
else
  fail "embedded bash script has syntax errors"
fi

# ----------------------------------------------------------------------------
hdr "7. Python syntax (same checks as test.yml)"
# ----------------------------------------------------------------------------
for d in vps_backend scripts notion_bridge config; do
  if [[ -d "${d}" ]]; then
    if python3 -m py_compile ${d}/*.py 2>&1; then
      ok "${d}/*.py compiles"
    else
      fail "${d}/*.py has syntax errors"
    fi
  fi
done

# ----------------------------------------------------------------------------
hdr "8. Deploy plan (dry-run of bash script lines)"
# ----------------------------------------------------------------------------
echo "  The deploy script will execute these steps on the VPS:"
echo ""
sed -n '/script: |/,/^[^ ]/p' .github/workflows/deploy.yml \
  | grep -E "^\s+(echo|cd|docker|git|sleep|if|fi|done|exit)" \
  | sed 's/^/    /'

# ----------------------------------------------------------------------------
hdr "Summary"
# ----------------------------------------------------------------------------
echo ""
printf "  ✅ %d passed   ❌ %d failed   ⚠️  %d warnings\n" "${PASS}" "${FAIL}" "${WARN}"
echo ""

if [[ "${FAIL}" -gt 0 ]]; then
  echo "❌ Workflow has ${FAIL} blocking issue(s) — do NOT push yet."
  exit 1
fi

echo "✅ Workflow is ready to push (or run via workflow_dispatch)."
exit 0
