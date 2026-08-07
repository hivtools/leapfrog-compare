#!/bin/bash
# Works the ready-for-agent frontier on GitHub, one ticket at a time, each in
# its own Docker Sandboxes (`sbx`) container. Skips parent/spec issues (e.g.
# #3, which #4-7 were split from) automatically - see is_real_ticket() in
# scripts/lib/agent-loop-lib.sh. For each real ticket it:
#   1. claims the issue (assigns it to the authenticated gh user)
#   2. creates a git worktree + branch (agent/issue-<n>) on the host, based
#      on main - or, if this ticket is blocked by another whose PR hasn't
#      merged yet, stacked on that blocker's branch instead (see
#      process_ticket()'s base_branch logic in scripts/lib/agent-loop-lib.sh)
#   3. runs `claude -p "/implement #<n> ..."` in a fresh sandbox (prompt in
#      scripts/agent-loop-prompt.md - edit that file to change what it's
#      told), which commits locally but never pushes or opens a PR itself
#   4. on the host: pushes the branch and opens the PR (gh pr create --fill)
#   5. stops the loop (without touching further tickets) the moment a run
#      signals it needs a human, fails outright, or the frontier is empty
#
# This script never closes issues - a commit message "CLOSES #N" is a
# closing reference GitHub itself honours once that commit actually lands
# on main (i.e. once you review and merge the PR, and if it was stacked,
# everything beneath it too). Merging is what unblocks anything the closed
# issue was blocking, so re-run this script after merging to pick up the
# next batch.
#
# Runs at most min(open ready-for-agent tickets, 10) iterations per invocation
# - re-run the script to keep going past that cap once you've checked in.
#
# Usage: scripts/agent-loop.sh
# For a single iteration (testing/development), use scripts/once.sh instead.
#
# One-time setup (see preflight() in scripts/lib/agent-loop-lib.sh for the
# exact commands):
#   - sbx daemon start && sbx login   (Docker sign-in, interactive)
#   - claude's "anthropic" secret must already be configured (`sbx secret ls`)
#   - gh auth login on the host (push/PR both run on the host, not in the
#     sandbox, so they use your existing gh/git auth)
set -euo pipefail

# shellcheck source=lib/agent-loop-lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/agent-loop-lib.sh"

agent_loop_init

open_count="$(gh issue list --repo "$REPO" --label "$LABEL" --state open --json number --jq 'length')"
if [ "$open_count" -eq 0 ]; then
    log "No open $LABEL tickets."
    exit 0
fi
max_iterations=$(( open_count < 10 ? open_count : 10 ))

for ((i = 1; i <= max_iterations; i++)); do
    n="$(frontier_issue)"
    if [ -z "$n" ]; then
        log "No unclaimed, unblocked $LABEL tickets left. Remaining ones are either" \
            "already claimed or waiting on an open PR to be reviewed and merged" \
            "(merging closes its issue and unblocks what it was blocking)."
        exit 0
    fi

    process_ticket "$n"
done

warn "Hit this run's cap of $max_iterations iterations (min of 10 and the open $LABEL count)." \
     "Re-run the script to keep going."
