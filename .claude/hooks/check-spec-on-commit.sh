#!/usr/bin/env bash
# Blocks git commit if code files are staged but the spec has not been updated.
staged=$(git diff --cached --name-only 2>/dev/null)
code=$(echo "$staged" | grep -E '^(src/|app\.py|requirements\.txt)')
spec=$(echo "$staged" | grep -E '^docs/superpowers/specs/')
if [ -n "$code" ] && [ -z "$spec" ]; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Code files staged without spec update. Please update docs/superpowers/specs/ before committing."}}'
fi
