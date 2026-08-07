Run /implement on GitHub issue #{{ISSUE_NUMBER}} ("{{ISSUE_TITLE}}") in {{REPO}}. You
are already on branch "{{BRANCH}}" with a clean worktree checked out from
main - do not switch branches.

The sandbox has no GitHub read access, so the full issue is inlined below -
do not run `gh issue view` or any other `gh`/GitHub API call to fetch it.

## Issue #{{ISSUE_NUMBER}}: {{ISSUE_TITLE}}

{{ISSUE_BODY}}

---

Follow /implement's process exactly (TDD at agreed seams, typecheck and run
tests regularly, /code-review before finishing), with ONE change to its last
step: commit to the current branch ("{{BRANCH}}") instead of main, and stop
there. Do not push and do not open a pull request - the sandbox has no
GitHub write access; agent-loop.sh handles push and PR creation from the
host after this session ends.

## Commit message

One commit (or a small number of logical commits) on "{{BRANCH}}". Each
commit message must cover:

1. What was completed, with a reference to #{{ISSUE_NUMBER}}
2. Key decisions made along the way
3. Files changed
4. Any blockers or notes for whoever picks this up next

If the work fully satisfies #{{ISSUE_NUMBER}}'s acceptance criteria, add a
line `CLOSES #{{ISSUE_NUMBER}}` on its own line in the commit body - GitHub
closes the issue itself once this commit reaches main (i.e. once the PR,
and anything it's stacked under, is reviewed and merged). Leave it out if
the ticket isn't fully done.

End every commit message with the trailer:
Co-Authored-By: Claude <noreply@anthropic.com>

Keep messages concise.

## If you get stuck

If at any point you get stuck on something only a human can resolve - an
ambiguous product decision not settled by the issue's spec, missing
credentials or access, a failing external dependency, a test that reveals
the acceptance criteria conflict with existing behaviour - do NOT guess, and
do NOT commit. Instead stop and make the last line of your final message
exactly:

MANUAL_WORK_REQUIRED: <one-sentence reason>

## Stop condition

Work on #{{ISSUE_NUMBER}} only. Once you've committed (or hit
MANUAL_WORK_REQUIRED), stop - do not start on another ticket. This session
is scoped to this one issue.
