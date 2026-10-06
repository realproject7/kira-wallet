# Token discovery patch acceptance

Version: 0.1.4 candidate. Published npm 0.1.3 remains immutable.

## Problem and correction

A new personal data directory defaults to public RPC and no general ERC20
indexer. The installed app does not inherit discovery settings from a separate
research workspace. Public RPC reads native balances and enumerates Mint Club
assets, but cannot identify arbitrary ERC20 contracts for a wallet. Previously,
a finished analysis could show only native holdings without explaining this
configuration at the point of use.

The wallet registration dialog now explains limited discovery and offers a
connection action before research. The wallet overview explains disabled
discovery, missing credentials, stale analysis or incomplete provider checks.
It labels incomplete portfolio estimates as partial. Network details retain
separate discovery, RPC and registry coverage. Read-only and sample views do
not acquire research permissions.

Connecting an indexer does not change an immutable saved analysis. Refresh
holdings runs discovery again. Refresh prices only updates existing holdings.
Discovery settings preserve existing explorer preferences, and the UI rereads
readiness after the settings job succeeds.

Registry diagnostics now retain up to five redacted error examples and numeric
HTTP or RPC codes in local evidence. The public model exposes only status and
counts. Oversized multicalls split at the same observed block, including errors
that viem converts into failed result rows. Transport outages and throttling
remain bounded instead of retrying every contract separately.

## Verification

- Required `npm test` suite passed: 150 Python tests, required Node behavior
  checks and browser script syntax checks.
- `scripts/check-install.py` passed with a fresh 73-member package installation
  and startup/shutdown lifecycle in a temporary synthetic workspace.
- The tracked-source privacy scan passed with the active private data directory
  included. The full-history scan retains the previously recorded non-noreply
  merge identity at `2ed52a2`; no new finding was introduced. That historical
  identity is not reproduced here and public history was not rewritten.
- Actual viem with an in-memory aggregate3 transport: eight calls rejected
  above two calls per batch succeed in seven requests, all at block 103.
  Independent review also checked that HTTP 429 and 503 stay at one request
  and isolated contract failures remain isolated. No live RPC is used by this
  regression.
- Missing, unreadable and disabled discovery credentials produce explicit
  coverage status without exposing credentials or attempting discovery.
- Viewer projection keeps raw provider diagnostics private and preserves
  unknown prices. UI behavior checks cover disabled discovery, missing
  credentials, stale analysis after connection, read-only actions and
  partially successful explorer coverage.
- Chrome fixture checks at 1440 x 900 and 390 x 844: partial estimate and
  discovery notice render without horizontal overflow. Both connection actions
  open Research connections. The add-wallet dialog says Add with limited
  discovery when the provider is absent. Fixture actions submitted no research,
  account authorization or provider requests.

The design reference was Mixpanel's dashboard connection guidance, retrieved
with [Lazyweb](https://www.lazyweb.com/agentic-search/51280761-491a-4a3f-a78e-ed2dcd427ee8).
No operator wallet information or screenshots were submitted to that service.

Independent review found a viem failed-result handling defect during
implementation. The correction and actual-client regression were reviewed
again and the finding was closed. Screenshots and operator test evidence
remain in the ignored local ticket ledger.

## Acceptance limits and release boundary

Operator-approved reuse of an existing discovery connection recovered
non-native holdings in a new saved analysis. Some provider and network gaps
remain; this does not establish complete holdings or verify every expected
token. Those limits remain visible in coverage. The existing operator server
was not restarted or globally upgraded during patch verification.

The source/package privacy scan is required before preparation.
`scripts/prepare-release.py`
pins the clean source commit and archive checksum. Registry publication
remains operator-only. No npm publication, GitHub release publication or PR
merge is part of preparing this candidate.
