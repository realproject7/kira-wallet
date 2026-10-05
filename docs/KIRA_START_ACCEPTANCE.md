# Simple app startup, 2026-10-05

## Result

From 0.1.3, `kira start` launches the full loopback app and opens its URL in
the browser. Initial account and context setup still uses `kira setup`.
`--read-only` selects a viewer without browser actions. `--no-open` supports
terminal-only use. Existing `--controls` commands remain accepted.

A live instance is reused only when its control mode matches the request.
Switching modes requires an explicit stop and restart. This prevents a
read-only command from reusing a writable app, or a normal start from silently
enabling controls on an existing read-only process. Another portfolio cannot
reuse the same process. Both the live instance and OS process identity are
still checked before stopping it.

Local controls do not grant signing, trading, AI context disclosure or native
wallet access automatically. Existing local-session, same-origin, account
selection and wallet-operation gates remain in the viewer. The startup change
leaves viewer permissions and provider behavior unchanged. CLI lifecycle locks now close in the command's
finally block, including early returns and initialization errors.

## Verification

- Seven CLI regressions cover plain start, explicit read-only/headless use,
  old controls scripts, setup URL, conflicting flags, same-mode reuse and
  refusal to switch a running instance's mode. They pass with ResourceWarning
  treated as an error.
- `npm test` passed all 147 Python tests and the required Node checks.
- `python3 scripts/check-install.py` packed and installed the candidate into
  a fresh temporary prefix with a separate data directory. Its 72 archive
  members contained no private runtime data. Demo mode remained read-only;
  default start enabled local controls. Switching a live mode was refused in
  both directions, and explicit read-only startup worked after stopping.
- The installed app rejected an unauthenticated action with HTTP 403. An
  authenticated synthetic naming job completed with its expected public tags.
  Private paths remained unavailable. Status, repeated start and stop passed.
- Browser-opening behavior was verified through the CLI's webbrowser call.
  Installation acceptance used `--no-open` to avoid opening unsolicited tabs.

Installation QA used disposable data and an encrypted disposable OWS vault.
No operator wallet, chat, provider credential or local app process was changed.
This is implementer acceptance, not an independent review or native device
wallet acceptance. PR review and operator registry publication remain pending.

## Distribution

The source version is 0.1.3. Its prepared candidate is tied to the clean source
commit by the ignored release manifest and SHA-256. Published 0.1.2 bytes and
tags remain immutable. This candidate also includes the OWS attribution
described in [OWS branding acceptance](KIRA_OWS_BRANDING.md). Registry publication is operator-only. The separately
deployed HTML showcase needs no npm publication.
