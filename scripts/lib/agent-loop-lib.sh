#!/bin/bash
# Shared by scripts/agent-loop.sh and scripts/once.sh. Not meant to be run
# directly - source it after `set -euo pipefail` in the caller.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO="hivtools/leapfrog-compare"
LABEL="ready-for-agent"
WORKTREES_DIR="$REPO_DIR/.worktrees"
PROMPT_TEMPLATE="$SCRIPT_DIR/agent-loop-prompt.md"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\n\033[1;33m!!\033[0m %s\n' "$*"; }
fail() { printf '\n\033[1;31mxx\033[0m %s\n' "$*"; exit 1; }

# --- preconditions -----------------------------------------------------

preflight() {
    gh auth status >/dev/null 2>&1 || fail "gh is not authenticated. Run 'gh auth login' first."

    if ! sbx ls >/dev/null 2>&1; then
        fail "sbx is not ready. Run:" \
             "  sbx daemon start" \
             "  sbx login" \
             "then re-run this script."
    fi

    if ! sbx secret ls 2>/dev/null | grep -q '^(global) *service *anthropic'; then
        fail "No global 'anthropic' secret configured, so claude can't authenticate in the sandbox." \
             "Run 'sbx secret set -g anthropic --oauth' (or see 'sbx secret set --help')."
    fi

    # uv needs pypi to install/resolve deps inside the sandbox.
    sbx policy allow network -g "pypi.org,files.pythonhosted.org,*.pythonhosted.org" >/dev/null
}

agent_loop_init() {
    preflight
    mkdir -p "$WORKTREES_DIR"
    GIT_AUTHOR_NAME="$(git -C "$REPO_DIR" config user.name || echo "leapfrog-compare agent")"
    GIT_AUTHOR_EMAIL="$(git -C "$REPO_DIR" config user.email || echo "agent@localhost")"
}

# --- helpers -------------------------------------------------------------

# A real, directly-implementable ticket - as opposed to the parent/spec
# issue that to-tickets split into tickets in the first place (e.g. #3,
# parent of #4-7 here) - always has a "## Blocked by" section, per
# to-tickets's <issue-template>. The parent issue predates that template
# and never gets one. This is a generic test, not specific to any one
# issue number: it holds for whatever spec issue to-tickets is run on next.
is_real_ticket() {
    local n="$1"
    gh issue view "$n" --repo "$REPO" --json body --jq .body | grep -qE '^## Blocked by'
}

# Prints the number of the first open, unassigned, unblocked, non-parent
# ready-for-agent issue (blocker-first ordering falls out of ascending issue
# number here, since to-tickets publishes blockers before what they block),
# or nothing.
frontier_issue() {
    local candidates n blocked
    candidates="$(gh issue list --repo "$REPO" --label "$LABEL" --state open \
        --json number,assignees \
        --jq 'map(select(.assignees | length == 0)) | sort_by(.number) | .[].number')"
    for n in $candidates; do
        is_real_ticket "$n" || continue
        blocked="$(gh api "repos/$REPO/issues/$n" --jq '.issue_dependencies_summary.blocked_by')"
        if [ "$blocked" = "0" ]; then
            echo "$n"
            return 0
        fi
    done
    return 0
}

slugify() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g' | cut -c1-50
}

# Bash's ${var//pattern/replacement} treats a bare '&' in the replacement
# as "insert the matched text" (same convention as sed) - escape it (and
# any literal backslash) so an issue title containing '&' can't corrupt
# the substitution below.
_escape_for_subst() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/&/\\\&/g'
}

# Fills in scripts/agent-loop-prompt.md with this ticket's details. Edit
# that file directly to change what the agent is told - this just does the
# {{PLACEHOLDER}} substitution.
build_prompt() {
    local n="$1" title="$2" branch="$3" body="$4"
    local prompt n_esc title_esc branch_esc repo_esc body_esc
    n_esc="$(_escape_for_subst "$n")"
    title_esc="$(_escape_for_subst "$title")"
    branch_esc="$(_escape_for_subst "$branch")"
    repo_esc="$(_escape_for_subst "$REPO")"
    body_esc="$(_escape_for_subst "$body")"
    prompt="$(cat "$PROMPT_TEMPLATE")"
    prompt="${prompt//\{\{ISSUE_NUMBER\}\}/$n_esc}"
    prompt="${prompt//\{\{ISSUE_TITLE\}\}/$title_esc}"
    prompt="${prompt//\{\{BRANCH\}\}/$branch_esc}"
    prompt="${prompt//\{\{REPO\}\}/$repo_esc}"
    prompt="${prompt//\{\{ISSUE_BODY\}\}/$body_esc}"
    printf '%s' "$prompt"
}

# Prints this issue's blocking issue numbers, one per line (may be empty).
blocker_numbers() {
    local n="$1"
    gh api "repos/$REPO/issues/$n/dependencies/blocked_by" --jq '.[].number' 2>/dev/null
}

# Claims, builds, and (on success) pushes + opens a PR for one ticket. Exits
# the whole script (via fail()) on any stopping condition - manual work
# needed, a sandbox failure, or an unexplained no-commit finish - since both
# callers (the loop and the single-shot test script) want to stop there
# rather than silently skip to something else.
process_ticket() {
    local n="$1"
    local title body slug branch worktree_dir sandbox_name

    title="$(gh issue view "$n" --repo "$REPO" --json title --jq .title)"
    body="$(gh issue view "$n" --repo "$REPO" --json body --jq .body)"
    slug="$(slugify "$title")"
    branch="agent/issue-$n"
    worktree_dir="$WORKTREES_DIR/issue-$n"
    sandbox_name="issue-$n"

    log "Claiming #$n: $title"
    gh issue edit "$n" --repo "$REPO" --add-assignee "@me"

    if [ -e "$worktree_dir" ]; then
        fail "$worktree_dir already exists (likely left over from a previous stopped run)." \
             "Resolve or 'git worktree remove $worktree_dir --force' it, then re-run."
    fi

    git -C "$REPO_DIR" fetch origin
    git -C "$REPO_DIR" worktree prune

    # Stack on a still-unmerged blocker's branch, so this ticket can see its
    # code before that PR lands on main - the whole reason to stack rather
    # than always branching from main. Whether to stack is decided by
    # ancestry (is the blocker branch's tip already on main?), not by
    # whether the ref still exists - GitHub doesn't always delete a branch
    # on merge, so a merged-but-not-deleted branch must still fall back to
    # main or every ticket after it stacks on dead history forever. If a
    # ticket ever ends up with >1 blocker, bail out loudly rather than
    # guess how to stack on more than one.
    local -a blockers=()
    while read -r b; do [ -n "$b" ] && blockers+=("$b"); done < <(blocker_numbers "$n")

    local base_branch="main"
    if [ "${#blockers[@]}" -gt 1 ]; then
        fail "#$n has more than one blocker (${blockers[*]}) - can't auto-stack a branch on" \
             "multiple parents. Resolve this ticket's branch by hand, or extend" \
             "process_ticket() in scripts/lib/agent-loop-lib.sh to handle it."
    elif [ "${#blockers[@]}" -eq 1 ]; then
        local candidate="agent/issue-${blockers[0]}"
        if git -C "$REPO_DIR" show-ref --verify --quiet "refs/remotes/origin/$candidate" \
            && ! git -C "$REPO_DIR" merge-base --is-ancestor "origin/$candidate" origin/main; then
            base_branch="$candidate"
            log "#$n is blocked by #${blockers[0]}: stacking $branch on $candidate (its PR isn't merged yet)."
        else
            log "#$n's blocker #${blockers[0]} is already merged into main - branching from main."
        fi
    fi

    git -C "$REPO_DIR" worktree add -b "$branch" "$worktree_dir" "origin/$base_branch"

    log "Creating sandbox $sandbox_name..."
    # A worktree's .git is just a pointer file into $REPO_DIR/.git/worktrees/<n>/
    # - the actual objects, refs, and this worktree's HEAD/index all live under
    # $REPO_DIR/.git, so it has to be mounted too (read-write: committing writes
    # new objects and updates this worktree's HEAD there). This does NOT expose
    # the main checkout's working files - those live directly in $REPO_DIR,
    # a separate, unmounted path from $REPO_DIR/.git.
    sbx create --quiet --name "$sandbox_name" claude "$worktree_dir" "$REPO_DIR/.git"

    # Container-local git config only (writes to the sandbox's own $HOME,
    # not the bind-mounted repo's shared .git/config). The agent commits
    # but never pushes (see the prompt template), so no GitHub credentials
    # are needed inside the sandbox at all - push and PR creation happen
    # below, on the host, using the host's own gh/git auth.
    sbx exec "$sandbox_name" git config --global user.name "$GIT_AUTHOR_NAME"
    sbx exec "$sandbox_name" git config --global user.email "$GIT_AUTHOR_EMAIL"
    sbx exec "$sandbox_name" git config --global --add safe.directory "*"

    local prompt
    prompt="$(build_prompt "$n" "$title" "$branch" "$body")"

    log "Running /implement for #$n in the sandbox (this can take a while)..."
    set +e
    sbx exec -w "$worktree_dir" "$sandbox_name" \
        claude -p "$prompt" --dangerously-skip-permissions --output-format json \
        | tee "$worktree_dir/.agent-result.json"
    local run_status=${PIPESTATUS[0]}
    set -e

    sbx rm --force "$sandbox_name" >/dev/null

    if [ "$run_status" -ne 0 ]; then
        warn "Sandbox run for #$n exited non-zero ($run_status)."
        gh issue comment "$n" --repo "$REPO" \
            --body "agent-loop: sandbox run failed (exit $run_status), see \`$worktree_dir/.agent-result.json\`. Stopping the loop here."
        fail "Stopping. Worktree left at $worktree_dir for inspection."
    fi

    local result_text manual_reason
    result_text="$(jq -r '.result // empty' "$worktree_dir/.agent-result.json" 2>/dev/null || true)"
    manual_reason="$(printf '%s\n' "$result_text" | grep -o 'MANUAL_WORK_REQUIRED:.*' | tail -1 || true)"

    if [ -n "$manual_reason" ]; then
        warn "#$n needs a human: $manual_reason"
        gh issue comment "$n" --repo "$REPO" --body "agent-loop stopped here: $manual_reason"
        fail "Stopping. Worktree left at $worktree_dir — pick it up manually on branch $branch."
    fi

    # Compared against this ticket's actual base (origin/main, or a still-open
    # blocker's branch when stacked) - not always origin/main - so a stacked
    # ticket's inherited commits from its blocker don't masquerade as "new".
    local new_commits
    new_commits="$(git -C "$worktree_dir" log --oneline "origin/$base_branch..$branch")"
    if [ -z "$new_commits" ]; then
        warn "#$n finished without committing anything and without a MANUAL_WORK_REQUIRED line."
        printf '%s\n' "$result_text"
        gh issue comment "$n" --repo "$REPO" \
            --body "agent-loop: run finished with nothing committed on $branch and no MANUAL_WORK_REQUIRED signal was given. Stopping the loop here."
        fail "Stopping. Worktree left at $worktree_dir for inspection."
    fi

    log "Pushing $branch and opening a PR for #$n against $base_branch..."
    git -C "$worktree_dir" push -u origin "$branch" \
        || fail "Failed to push $branch. Worktree left at $worktree_dir for inspection."

    # If $base_branch is itself an agent/issue-* branch, GitHub retargets
    # this PR to main automatically once that branch's PR is merged and the
    # branch deleted - no extra bookkeeping needed here for that handoff.
    local pr_url
    pr_url="$(gh pr create --repo "$REPO" --base "$base_branch" --head "$branch" --fill)" \
        || fail "Failed to open a PR for $branch. Worktree left at $worktree_dir for inspection."

    # We don't close issues here - a commit message "CLOSES #N" (or
    # Close/Closes/Fixes/Resolves etc, GitHub's own keyword set) is a
    # closing reference GitHub itself acts on once that commit lands on
    # the repo's default branch, i.e. when this PR (and, if it's stacked,
    # everything beneath it) actually gets merged to main - not before.
    # We just leave a traceability comment on the issue either way.
    local commit_body
    commit_body="$(git -C "$worktree_dir" log "origin/$base_branch..$branch" --pretty=%B)"
    local -a marked=()
    while read -r x; do [ -n "$x" ] && marked+=("$x"); done \
        < <(printf '%s\n' "$commit_body" | grep -oiE 'CLOSES #[0-9]+' | grep -oE '[0-9]+' | sort -un)

    if [ "${#marked[@]}" -gt 0 ]; then
        local marked_list="" sep=""
        for x in "${marked[@]}"; do
            marked_list+="${sep}#${x}"
            sep=", "
        done
        gh issue comment "$n" --repo "$REPO" \
            --body "agent-loop: opened $pr_url (marks $marked_list closed once this reaches main)"
    else
        gh issue comment "$n" --repo "$REPO" \
            --body "agent-loop: opened $pr_url (not marked complete - left open for another pass)"
    fi

    log "#$n done: $pr_url"
    git -C "$REPO_DIR" worktree remove "$worktree_dir" --force
}
