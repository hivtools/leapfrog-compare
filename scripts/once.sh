#!/bin/bash
# Runs exactly one iteration of scripts/agent-loop.sh's per-ticket flow, for
# testing/development. Picks the next frontier ticket unless one is given.
#
# Usage:
#   scripts/once.sh          # next unclaimed, unblocked ready-for-agent ticket
#   scripts/once.sh 4        # a specific issue number, skipping the frontier check
set -euo pipefail

# shellcheck source=lib/agent-loop-lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/agent-loop-lib.sh"

agent_loop_init

if [ $# -ge 1 ]; then
    n="$1"
else
    n="$(frontier_issue)"
    if [ -z "$n" ]; then
        log "No unclaimed, unblocked $LABEL tickets to run."
        exit 0
    fi
fi

process_ticket "$n"
