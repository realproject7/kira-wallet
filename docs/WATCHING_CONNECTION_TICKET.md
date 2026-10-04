# Watching connection implementation ticket

Status: scoped for review. No provider adapter ships in workspace PR #2.

## Outcome

An operator can select an injected browser wallet, choose an exposed account,
and preview its full public address and exact name before registering it as a
Watching wallet. Registration uses the existing explicit add-and-research action.
The extension session and the saved watching address have separate lifecycles.

## Scope and contract

- Discover providers through EIP-6963 after installing the announcement listener.
  Keep the listener for the page lifetime and deduplicate announcements by
  provider/session identity. Discovery alone does not request accounts.
- Present an explicit chooser even when only one provider is discovered. Request
  accounts only from the chosen provider after a user action. Multiple returned
  accounts need explicit selection. Keep manual address entry available.
- Treat provider names, icons and reverse-domain identifiers as untrusted display
  metadata. Render names as text. Render bounded data-URI icons through `img`,
  with a local fallback. Do not interpret metadata as provider authenticity.
- Validate returned EVM addresses and show the complete selected address and
  exact proposed name in a registration preview. Never add an account directly
  from a provider response or event. Preserve the existing duplicate-address
  behavior and operator names.
- Submit registration only after explicit confirmation through the same-origin
  protected local job API. Preserve its idempotency and writer-lock contract.
  Demo sessions continue to reject provider-consuming registration/research.
- Keep connection state in browser memory. Reload and reconnect must not request
  accounts automatically. Disconnect releases Kira's listeners/session and
  invalidates pending responses; it does not remove a saved watching address
  or promise to revoke extension permissions.
- On `accountsChanged`, invalidate the preview and require a new account choice.
  Do not replace, rename or add saved wallets. An empty account list is visibly
  disconnected. Handle `disconnect` and locked/unavailable providers similarly.
- A `chainChanged` event updates session context without switching the extension
  network or changing recorded portfolio facts. Watching research stays keyed
  by the engine's chain-and-contract identity, not the current extension chain.
- Use an attempt generation to ignore late account responses after disconnect,
  a changed account, a cancelled chooser or selection of another provider.
  Handle EIP-1193 rejection, unauthorized, disconnected and unsupported-method
  errors with bounded public messages.

The first ticket makes no signing, transaction, chain-switch, login-message or
custody calls. Managed wallets, mobile wallet handoff and the connected model
account/session adapter remain separate outcomes. An embedded browser with no
extension offers manual entry and a clear unavailable state.

## Acceptance cases

| Case | Required result |
| --- | --- |
| No extension | Manual entry remains usable; no fabricated connection. |
| One or several providers | Explicit selection; only the selected provider receives an account request. |
| Repeated or late announcements | No duplicate chooser rows or automatic reselection. |
| Hostile metadata or icon | Text stays inert; image fallback works; no script or remote icon request. |
| Account rejection or provider error | Clear retry/cancel state; registry and jobs stay unchanged. |
| Several returned accounts | Explicit account selection precedes the full-address preview. |
| Account change during preview | Preview becomes invalid; confirmation cannot register the old account. |
| Account change after registration | Saved address and exact names remain intact; new registration stays explicit. |
| Empty accounts or disconnect | Session clears; stored watching addresses and snapshots remain intact. |
| Late response after cancellation/provider change | Response is ignored and cannot restore an old preview. |
| Chain change | No network switch or automatic research; current preview/session context stays coherent. |
| Duplicate registered account | No silent rename or replacement; existing wallet can be opened. |
| Double confirmation/retry | One durable job through the existing idempotency mechanism. |
| Demo, foreign origin or expired local session | Existing server protections reject registration. |
| Keyboard and narrow screen | Chooser, account selection, preview and cancellation remain operable. |

Use synthetic EIP-1193 providers and a temporary portfolio for automated and
browser verification. Run `npm test`, the clean install check and the public
history check. Independent review must inspect account-change races and the
registration boundary. Live extension/device acceptance is an operator action;
synthetic verification does not establish that it passed.

Primary contracts checked on 2026-10-04:
[EIP-6963 provider discovery](https://eips.ethereum.org/EIPS/eip-6963),
[EIP-1193 provider API](https://eips.ethereum.org/EIPS/eip-1193),
and the existing [local job contract](JOB_CONTRACT.md).
