#!/bin/bash
# TaskCompleted hook — runs linter + type check on Builder output.
# exit 0 = pass (task may be marked complete)
# exit 2 = block (task stays open, stderr becomes feedback to Builder)
# JSON stdout with continue:false = circuit breaker (escalate to lead)

set -euo pipefail

INPUT=$(cat)
TASK_ID=$(echo "$INPUT" | jq -r '.task_id // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

# --- Circuit breaker: track retries per task ---
ATTEMPT_DIR="${CWD}/.claude/hooks/.attempts"
mkdir -p "$ATTEMPT_DIR"
ATTEMPT_FILE="${ATTEMPT_DIR}/task-${TASK_ID}"

ATTEMPTS=$(cat "$ATTEMPT_FILE" 2>/dev/null || echo "0")
ATTEMPTS=$((ATTEMPTS + 1))
echo "$ATTEMPTS" > "$ATTEMPT_FILE"

MAX_RETRIES=3

# --- Detect project tooling ---
ERRORS=""

run_check() {
  local name="$1"
  shift
  local output
  if ! output=$("$@" 2>&1); then
    ERRORS="${ERRORS}\n--- ${name} failed ---\n${output}\n"
  fi
}

cd "$CWD"

# JavaScript/TypeScript projects
if [[ -f "package.json" ]]; then
  # Check for lint script
  if jq -e '.scripts.lint' package.json > /dev/null 2>&1; then
    run_check "Linter (npm run lint)" npm run lint
  elif command -v npx > /dev/null 2>&1 && [[ -f ".eslintrc" || -f ".eslintrc.js" || -f ".eslintrc.json" || -f ".eslintrc.yml" || -f "eslint.config.js" || -f "eslint.config.mjs" ]]; then
    run_check "ESLint" npx eslint .
  fi

  # Check for type-check / typecheck script
  if jq -e '.scripts["type-check"]' package.json > /dev/null 2>&1; then
    run_check "Type check (npm run type-check)" npm run type-check
  elif jq -e '.scripts.typecheck' package.json > /dev/null 2>&1; then
    run_check "Type check (npm run typecheck)" npm run typecheck
  elif [[ -f "tsconfig.json" ]] && command -v npx > /dev/null 2>&1; then
    run_check "TypeScript (tsc --noEmit)" npx tsc --noEmit
  fi

  # Check for build script (catches compile errors)
  if jq -e '.scripts.build' package.json > /dev/null 2>&1; then
    run_check "Build (npm run build)" npm run build
  fi
fi

# Python projects
if [[ -f "pyproject.toml" || -f "setup.py" || -f "requirements.txt" ]]; then
  if command -v ruff > /dev/null 2>&1; then
    run_check "Ruff (linter)" ruff check .
  elif command -v flake8 > /dev/null 2>&1; then
    run_check "Flake8" flake8 .
  fi

  if command -v mypy > /dev/null 2>&1 && [[ -f "pyproject.toml" || -f "mypy.ini" || -f ".mypy.ini" ]]; then
    run_check "Mypy (type check)" mypy .
  fi
fi

# Go projects
if [[ -f "go.mod" ]]; then
  if command -v go > /dev/null 2>&1; then
    run_check "Go vet" go vet ./...
    run_check "Go build" go build ./...
  fi
fi

# Rust projects
if [[ -f "Cargo.toml" ]]; then
  if command -v cargo > /dev/null 2>&1; then
    run_check "Cargo check" cargo check
    if command -v cargo-clippy > /dev/null 2>&1 || cargo clippy --version > /dev/null 2>&1; then
      run_check "Clippy" cargo clippy -- -D warnings
    fi
  fi
fi

# --- Evaluate results ---
if [[ -n "$ERRORS" ]]; then
  if [[ $ATTEMPTS -ge $MAX_RETRIES ]]; then
    # Circuit breaker — escalate to lead
    rm -f "$ATTEMPT_FILE"
    jq -n --arg reason "$(echo -e "Task failed $MAX_RETRIES attempts. Quality checks still failing:\n${ERRORS}\nEscalating to lead for manual intervention.")" \
      '{"continue": false, "stopReason": $reason}'
    exit 0
  fi

  echo -e "Quality checks failed (attempt ${ATTEMPTS}/${MAX_RETRIES}). Fix and retry:\n${ERRORS}" >&2
  exit 2
fi

# All checks passed — clean up attempt tracker
rm -f "$ATTEMPT_FILE"
exit 0
