# Kira remaining stages

Updated: 2026-10-04. The workspace and Watching connection are separate review
outcomes. Both remain draft work. No merge, deployment or registry publication
is authorized by this status document.

| Order | Outcome | Current state | Next action or gate |
| --- | --- | --- | --- |
| 1 | Workspace redesign, PR #2 | Typography/control refinement and builder checks passed at `b95d470`. No independent final approval. | Read-only independent review of the current diff, then resolve actionable findings. Separate reviewer-agent authorization is pending in the operator chat. |
| 2 | Watching connection | Implemented on `codex/kira-watching-connection`, based on PR #2. Synthetic unit, transport, install and browser checks passed. | Independent review of session races, metadata handling and registration. Rebase on any PR #2 fixes before final review. |
| 3 | Browser extension acceptance | Synthetic providers only. Real extensions were not asked for accounts. | Operator opens the personal workspace in a supported browser, approves its chosen extension and verifies exposed accounts, locking, account changes and disconnect. Registration/research requires its explicit final action. |
| 4 | Model account/session adapter | Not connected. Local Kira notes and browser draft continue to work. | Operator chooses an allowed account/session route and clears its authentication/device gate. Then implement and verify that selected adapter. |
| 5 | Connected Kira chat | Send is unavailable. No portfolio is sent to a model. | Operator chooses the portfolio disclosure scope and destination. Implement explicit disclosure, context selection and conversation/activity persistence against the approved route. |
| 6 | Review and release | Both implementation outcomes remain unmerged. | Authorized maintainer resolves dependencies and final reviews before any merge. Registry publication remains operator-only. |

The actionable work completed without a device gate is Watching provider
discovery, manual fallback, explicit account selection, full-address/name review,
session invalidation and registration through existing local jobs. Model-route
choice, credential entry, extension approval and disclosure cannot be inferred
from a handoff.

Keep the operator portfolio and viewer separate from synthetic verification.
The next implementer should read the [Watching ticket](WATCHING_CONNECTION_TICKET.md)
and [implementation report](WATCHING_CONNECTION_REPORT.md), then reconcile the
current branches and PR reviews before changing either outcome. The public
foundation base is `origin/codex/kira-foundation`; the old local branch with that
name is not the public base.

Workspace review: [PR #2](https://github.com/realproject7/kira-wallet/pull/2).
The Watching draft is stacked on `codex/kira-workspace-redesign`, so its diff
contains only the next outcome.
