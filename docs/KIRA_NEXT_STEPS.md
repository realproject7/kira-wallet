# Kira remaining stages

Updated: 2026-10-04. The workspace and Watching connection are separate review
outcomes. PR #2 is ready for maintainer review. PR #3 remains draft for live
extension acceptance. Both local independent reviews are complete. No merge, deployment or registry publication
is authorized by this status document.

| Order | Outcome | Current state | Next action or gate |
| --- | --- | --- | --- |
| 1 | Workspace redesign, PR #2 | Refinement, short-desktop composer correction and isolated fixture checks passed. Independent review of source head `e0a802a` found no remaining actionable findings. | Authorized maintainer review and merge. |
| 2 | Watching connection, PR #3 | Implemented on the reviewed PR #2 base. Independent review of source head `9f3229f` found no remaining actionable findings. 67 Python, 20 lifecycle/controller tests, transport, install and browser checks passed. | Operator extension acceptance, then maintainer review and authorized merge. |
| 3 | Browser extension acceptance | Synthetic providers only. Real extensions were not asked for accounts. | Operator opens the personal workspace in a supported browser, approves its chosen extension and verifies exposed accounts, locking, account changes and disconnect. Registration/research requires its explicit final action. |
| 4 | Model account/session adapter | Not connected. Local Kira notes and browser draft continue to work. | Operator chooses an allowed account/session route and clears its authentication/device gate. Then implement and verify that selected adapter. |
| 5 | Connected Kira chat | Send is unavailable. No portfolio is sent to a model. | Operator chooses the portfolio disclosure scope and destination. Implement explicit disclosure, context selection and conversation/activity persistence against the approved route. |
| 6 | Review and release | Both implementation outcomes remain unmerged. | Authorized maintainer confirms GitHub review requirements and resolves the stacked dependency before merging #2, then #3. Registry publication remains operator-only. |

Work completed without a device gate includes workspace typography/control polish,
short-desktop access, deterministic test fixtures, independent reviews, Watching
provider discovery, manual fallback, explicit account selection, full-address/name
review, session invalidation and durable registration. Submitted request details
remain visible during account changes, close/reopen and uncertain responses. Model-route
choice, credential entry, extension approval and disclosure cannot be inferred
from a handoff.

Keep the operator portfolio and viewer separate from synthetic verification.
The next implementer should read the [Watching ticket](WATCHING_CONNECTION_TICKET.md)
and [implementation report](WATCHING_CONNECTION_REPORT.md), then reconcile the
current branches and PR reviews before changing either outcome. The public
foundation base is `origin/codex/kira-foundation`; the old local branch with that
name is not the public base.

Workspace review: [PR #2](https://github.com/realproject7/kira-wallet/pull/2).
Watching review: [PR #3](https://github.com/realproject7/kira-wallet/pull/3).
This draft is stacked on `codex/kira-workspace-redesign`, so its diff
contains only the next outcome.
