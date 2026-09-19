# Future Repository Operations — Pending Design

## Status

Status: pending implementation.
Authority: no new runtime authority granted.
Owner approval required for destructive actions: yes.

This document records a future extension of malak-vault-sync-agent. It does
not authorize implementation by itself.

## 1. Architectural boundary

The Agent and Project Vault are external support infrastructure.

Direction of dependency:

Malāk repository -> observed externally by Sync Agent -> maintains Project
Vault -> supports assistant context.

There is no reverse dependency.

Malāk must not import, invoke or query the Agent. Malāk must not import or
query the Vault, and the Vault is not Memory or Knowledge for Malāk. Neither
external component is required for Malāk runtime operation.

The Agent may observe Malāk's repository because that is its external
responsibility. Observation does not make the Agent part of Malāk.

## 2. One-way boundary verification

A future read-only validation should verify the one-way architecture from the
outside.

The Agent may scan the current Malāk tree for forbidden reverse references to
external support infrastructure and report a `BOUNDARY_DRIFT` finding when
such coupling appears.

This check must remain entirely outside Malāk. Malāk must not contain a
reciprocal checker, configuration, import, URL, repository identifier or
runtime hook for the observer.

```text
external observer may verify Malāk isolation
Malāk must not know the observer identity
```

Detection grants no authority to modify Malāk automatically. Any correction
still requires the normal human-reviewed Malāk workflow.

## 3. Future repository operations

A future Agent terminal may provide deterministic repository hygiene for the
repositories under its operational responsibility.

Candidate capabilities:

- repositories status;
- repositories compare;
- repositories sync;
- branches status;
- branches investigate for one exact repository and branch;
- branches cleanup review;
- branches cleanup approve for one exact repository, branch and SHA;
- audit history;
- audit show for one run id.

Command names remain placeholders until a dedicated implementation gate.
No generic shell or arbitrary Git passthrough is allowed.

## 4. Repository compare

The Agent should compare local and remote state and classify at least:

- ALIGNED;
- LOCAL_BEHIND;
- LOCAL_AHEAD;
- DIVERGED;
- DIRTY;
- DETACHED;
- REMOTE_MISMATCH;
- UNKNOWN.

Evidence should include repository identity, local path, branch, local HEAD,
configured remote, remote HEAD, upstream, ahead/behind, worktree state,
default branch, fetch/prune result and classification reason.

Credentials and tokens must never appear in output, reports or evidence.

## 5. Safe local synchronization

The Agent may eventually reconcile only deterministic, non-destructive drift.

An eligible example is a clean local main that is behind origin/main, has the
expected repository and remote identity, and can be advanced by fast-forward.

The Agent must STOP on local-ahead state, divergence, dirty worktree,
detached HEAD, unknown branch, remote mismatch, non-fast-forward requirement,
uncommitted changes or ambiguous identity.

It must never hide drift through reset, forced checkout, force-push or
discarding local changes. Every sync must produce before/after evidence.

## 6. Branch inventory and investigation

If a configured repository has additional branches, the Agent should report
and investigate them instead of deleting them automatically.

For each candidate branch it should gather, where available:

- repository;
- local and remote presence;
- exact branch name;
- branch HEAD SHA;
- default branch and HEAD;
- ancestry against default branch;
- exclusive commits not in default branch;
- changed paths;
- associated Pull Request and state;
- merge or squash relationship when observable;
- whether equivalent content appears incorporated into default branch;
- remaining uncertainty.

Suggested classifications are PROTECTED, ACTIVE, MERGED_VERIFIED,
CONTENT_INTEGRATED_HISTORY_DIFFERS, STALE_UNMERGED, DIVERGED, UNKNOWN and
SAFE_CLEANUP_CANDIDATE.

A summary must explain the evidence behind the classification.

## 7. Human filter before deletion

This boundary is mandatory and non-negotiable.

The Agent investigates, reports and proposes one exact cleanup, then STOPs.
The Owner reviews the evidence. A rejection produces no mutation. An approval
must identify the exact repository, branch, SHA and local/remote scope before
the Agent may execute that cleanup.

The Agent must never approve its own recommendation.

Local and remote deletion are separate scopes. Approval becomes invalid if
repository identity, branch name, branch SHA, remote identity, default branch
or verified merge/ancestry state changes. New evidence requires a new review
and a new approval.

## 8. Protected branches and forbidden operations

Default branch, main, the current checked-out branch and configured protected
branches are always ineligible for cleanup unless a future explicit governance
decision changes that rule.

Forbidden operations include wildcard deletion, pattern deletion, bulk
delete-all, normal use of forced branch deletion, force-push, implicit remote
deletion, deletion inferred only from branch naming and destructive resolution
of ambiguity.

## 9. Audit and traceability

Each repository synchronization or branch cleanup run should produce a run id
and retain:

- requested action;
- repositories inspected;
- before state;
- evidence gathered;
- classification;
- proposed action;
- Owner decision;
- exact approved identity;
- commands executed;
- sanitized command output;
- after state;
- verification result;
- final conclusion;
- hash manifest.

The current evidence/report model may be reused through var/evidence/<run_id>
and var/reports/<run_id>. Every future mutation must have a corresponding
verification step.

## 10. Pull Requests

PR creation for controlled Vault proposals remains part of the Agent's current
responsibility.

PR approval and merge remain outside this future branch-cleanup scope. The
Owner may continue to merge from GitHub on desktop or mobile.

The Agent may inspect PR state as evidence for branch investigation, but PR
state observation never grants permission to delete.

## 11. Current vs future authority

Current baseline permits observation, fetch, comparison, auditing, creation
of controlled Vault proposal branches and opening Draft PRs. It does not permit
branch deletion or automatic cleanup.

Future candidates are repository comparison, safe local fast-forward,
branch investigation and cleanup recommendation. Branch deletion may only be
implemented as an execution of one exact Owner-approved operation.
Automatic destructive cleanup remains forbidden.

## 12. Implementation gate

Before implementation, a dedicated G0/G1 must inventory existing Git inspector
capabilities, define the exact repositories under management, define the safe
synchronization matrix, define branch classification contracts, define
approval binding and invalidation, separate local and remote cleanup, define
audit/evidence format and encode RED tests before mutation code.

No implementation is authorized by this document.
