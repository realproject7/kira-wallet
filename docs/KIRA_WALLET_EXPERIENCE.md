# Connected wallet and agent experience

The operator requested automatic RPC fallback, clear chain filtering, a separate
Kira composer, real showcase cases, browser-wallet controls, local OWS onboarding
and an agent that can inspect wallet records and carry out research.
The previous integrated source `876a4a2b145b89ad77c49fd7fee14f4a99b2cef6` is the
rollback baseline. Original character assets and previous release archives remain.

## Result

- New configurations use public RPC automatically. Missing, invalid, wrong-chain
  or failed custom endpoints fall back to chain-verified public endpoints, also
  after a successful handshake. Fixed-block calls retain their block. Successful
  endpoint ordinals are recorded without exposing URLs. Explicit custom-only
  settings are preserved. RPC alone does not discover every ERC20 holding.
- All tokens has a visible Chain column and chain selector. Chain-plus-contract
  identity, unpriced records and testnet exclusions are unchanged.
- The sidebar says “All your tokens. Your own AI.” The ambiguous plus now says
  “New chat”. The composer is a separate floating surface. Its shadow moves at
  eight seconds while idle and 1.8 seconds during real chat or research work.
  Reduced-motion CSS disables the wave. The conversation scrolls independently.
- Connect wallet opens the existing EIP-6963 wallet chooser. Account review,
  provider/account state and disconnect are visible. Missing-extension help points
  to MetaMask and explains how to use a compatible browser on the same computer.
  The public-only connection never requests a signature.
- Human-submitted OWS creation uses the optional pinned official SDK 1.4.3 and a
  required encryption passphrase. Listing and creation return public EVM
  descriptors only. Full UUID receipts in the shared vault serialize and recover
  interrupted creation. A retry cannot change the original encryption passphrase.
  Browser session storage holds only the public request identity. Keys and
  passphrases never enter the conversation or research job store.
- The user's own agent can read current and historical records, compare analyses
  and submit typed holdings/price jobs when wallet research is enabled. Tools are
  scoped and admission rechecks current permissions and cancellation. Native shell,
  files, browser and MCP execution remain disabled. Legacy permissions are
  preserved. New setup recommends the whole portfolio and wallet research.
- The restored showcase has three continuous, independent recorded cases:
  CHICKEN/Mint Club, WETH/Aerodrome and APE/Uniswap. Public examples omit wallet
  identifiers and use rounded figures and day-level dates. Shared backing,
  headline pool liquidity and recorded burn output are distinguished. Historical
  evidence does not promise executable proceeds. Detailed provenance stays private.

## Product evidence

The [Lazyweb financial assistant study](https://www.lazyweb.com/agentic-search/2bfef4a4-ae62-4682-8a7b-b58591f7e0d3)
compares Monarch, Copilot and Midday assistant patterns. Composer separation,
explicit connection state and short actionable question starters follow that
research. Motion follows [Emil Kowalski's design engineering guidance](https://raw.githubusercontent.com/emilkowalski/skills/main/skills/emil-design-eng/SKILL.md).
Browser-wallet controls were benchmarked against lpTOKEN.fun's wallet chooser,
connection button and handoff behavior. Phone handoff was adapted to loopback:
a phone cannot reach this computer's local application URL.

OWS source: [official documentation](https://docs.openwallet.sh/),
[Node SDK](https://github.com/open-wallet-standard/core/blob/main/docs/sdk-node.md).

## Verification

Full Python and Node verification, real HTTP authentication/asset checks and clean
installed-package lifecycle pass. RPC regression covers a live read failure,
wrong-chain rejection, unchanged pinned block and actual client endpoint ordinals.
A failing secret-file read still permits public child-process configuration.

A real installed Codex CLI passed its generic connection check, called
snapshots_list and snapshot_read on a synthetic portfolio and answered the saved
balance/date without starting a provider job. A browser turn also used saved
records. The working wave was 1.8 seconds and returned to eight seconds afterward.
A real New chat action cleared the completed conversation.

The pinned native OWS SDK created only disposable test wallets. Wrong-passphrase
export failed; correct decryption succeeded. Neither the mnemonic nor passphrase
appeared in stored files or public descriptors. Recovery reused the same wallet.
Different full UUIDs with the same prefix create different wallets. Unknown
outcomes retain their public request ID across page reload. No operator wallet
was created, exported, signed or deleted.

CUA checks cover 1728-pixel desktop and 390-pixel mobile screens, chain filtering
from two records to one, separate panel/input bounds, clear new-chat text,
visible browser-wallet choice, OWS creation form, three script-free showcase
cases and zero horizontal overflow. Screenshots use synthetic app holdings;
showcase illustrations use the authorized anonymized recorded cases.

- [Desktop app](screenshots/kira-wallet-experience-desktop.png)
- [Mobile app](screenshots/kira-wallet-experience-mobile.png)
- [Showcase](screenshots/kira-showcase-real-cases.png)
- [Mobile showcase](screenshots/kira-showcase-real-cases-mobile.png)

Actual MetaMask extension approval, locking, account events and human OWS
passphrase entry remain device acceptance checks. Financial signing and execution
are outside this change. Full-balance DEX exit quoting remains issue 11.
The registry still serves 0.1.0; the reviewed source candidate is 0.1.1.
Publication remains operator-only. No npm publish is run.
