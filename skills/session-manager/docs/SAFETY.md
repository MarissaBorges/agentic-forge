# Safety and autonomy policy

## Autonomous actions

Allowed without confirmation when scoped and recoverable:

- Read files and inspect repository state.
- Create missing Session Manager directories/templates.
- Update Session Manager-owned Markdown files.
- Rebuild the local SQLite index.
- Run non-destructive validation and focused tests.
- Make small, reversible edits to Session Manager metadata.
- Diagnose performance and propose/implement a measured, scoped fix when
  application-code edits are within the user's task request and tests exist.

## Approval required

Ask before:

- Deleting files, directories, branches, records, or user data.
- Overwriting existing user-authored content or resolving conflicting facts.
- Running destructive database migrations or data transformations.
- Force-pushing, rewriting shared Git history, or changing remote refs.
- Deploying, publishing, releasing, or changing production systems.
- Modifying secrets, credentials, access policies, or security controls.
- Sending messages, making purchases, or creating external records.
- Bulk edits with broad or uncertain impact.

## Safe execution protocol

1. Explain the exact target and expected impact.
2. Prepare a diff or dry-run where possible.
3. Ask for explicit approval.
4. Execute only the approved scope.
5. Verify and report the result.

A general request such as “fix everything” is not approval for destructive
actions. Silence is not approval.

## Data hygiene

Never persist credentials, API keys, access tokens, private keys, or secrets.
Avoid personal or sensitive data in context files. Store only project-relevant
technical context.
