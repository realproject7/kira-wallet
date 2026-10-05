# Local live acceptance, 2026-10-05

The operator requested thorough local product testing while npm publication
remained unavailable. Testing used a separate empty workspace, the supplied
public watching address, a separate disposable encrypted OWS vault, configured
research providers and the installed native Claude CLI. Existing operator
workspaces and their conversations were preserved.

## Real agent questions

Ten questions completed with real native model calls. One additional real turn
was deliberately stopped through the UI. The connection test is separate from
this count. No fixture response was substituted for a live answer.

| Case | Request | Observed result |
| --- | --- | --- |
| 1 | Research progress while the first wallet is still being scanned | Distinguished pending work from saved results and unknown balances. |
| 2 | Newly created wallet state and available actions | Found an incorrect duplicate-name explanation for an unregistered queued wallet. Fixed the lookup error. |
| 3 | Recheck wallet identity and native ETH by chain | Corrected the duplicate-name claim. Kept native ETH separate from ERC20 assets and testnets. |
| 4 | Dormant tokens, market prices, pools and possible sale proceeds | Returned dated balances, prices and recorded burn outputs. Did not invent inactivity or executable DEX quotes. |
| 5 | Blast mainnet versus Blast Sepolia | Kept networks and wallets separate. Did not infer ownership of popular tokens missing from the record. |
| 6 | LP ownership versus market links | Identified distinct unpriced token contracts without inventing LP redemption. Exposed an incorrect retraction caused by omitted market details. |
| 7 | Read specific token market details again | Verified recorded, displayed and omitted pool counts. Corrected the summary/detail misunderstanding after the projection fix. |
| 8 | Queue exactly one holdings refresh | Created one real durable job. Reported queued/running status without claiming it had already completed. |
| 9 | Verify the final publication and compare saved analyses | Located the published snapshot. Exposed ambiguous interpretation of coverage metadata and ERC20 versus native RPC checks. |
| 10 | Recheck ERC20 discovery versus native RPC coverage | Corrected the coverage interpretation and identified unknown native balances. Both snapshots retained the same per-chain completeness/availability flags. |

These were not uniformly correct on the first attempt. Cases 2, 6 and 9 drove
implementation changes and follow-up questions. Case 10 still described the
exact cause of metadata differences as a possibility rather than using the
comparison definition; its per-chain conclusion matched the records. Model
answers remain interpretations of recorded evidence.

## Second question round

Ten additional Korean questions completed through the real native Claude CLI.
All ten received answers without a transport or model-process failure. This
does not mean every initial answer was factually correct. No new research job,
wallet, signature or trade was requested by this round.

| Case | Request | Observed result |
| --- | --- | --- |
| 1 | Mainnet totals, priced/unpriced counts and testnet exclusion | Counts and totals matched. Native observation times were missing from the supplied projection. |
| 2 | Same-symbol LP tokens and recorded market routes | Kept distinct contracts and quantities separate. Did not infer LP ownership or redemption from a market link. |
| 3 | Dormant tokens and full-balance disposal | Did not invent transfer history, inactivity or executable dollar proceeds. Preserved historical burn outputs. |
| 4 | ETH, WETH, Blast mainnet and Blast Sepolia | Kept identities, quantities and valuation scope separate. Exposed the same missing native observations. |
| 5 | Compare two saved analyses | Incorrectly described changes as timestamps only and treated an empty positive inventory as missing native evidence. |
| 6 | Verify the comparison flags | Corrected the flag interpretation, but normalized reads still omitted native observations and underlying reference values. |
| 7 | Read an unregistered wallet name | Returned wallet_not_registered. Did not substitute another wallet or invent a duplicate-name problem. |
| 8 | Detailed stablecoin markets and best exit | Distinguished recorded/displayed/omitted pools, quote-token prices and absent execution quotes. |
| 9 | Wallet-specific ERC20 discovery versus native RPC | Correctly separated coverage flags and known holdings from unknown networks. Native observation times remained omitted. |
| 10 | Chat capabilities and actual research completion | Correctly reported published partial jobs and unsupported creation/trading tools. Job-to-wallet identity required inference because the field was omitted. |

The follow-up fix includes explicit native balance observations, their times
and blocks, registry scan blocks and safe snapshot price-reference values.
An observed zero remains evidence without becoming a positive holding or
changing portfolio totals. Unavailable RPC balances remain null. Reference
source/debug fields remain excluded, including for mixed-case cbBTC references.
Scoped research job reads now name their approved wallet explicitly.

Two additional real questions verify the fix. One continued the original chat
and checked observations, reference changes and job identities. A separate
fresh-conversation test repeated the saved-analysis question without older
answers. Both returned the recorded zero/unknown distinction and correct
block/reference changes. The continued-chat check also matched every explicit
job-to-wallet identity. These verification questions are separate from the ten-case count.
Raw responses, original failures and financial evidence remain private.

The final regression suites passed 94 root Python tests and 46 viewer Python
tests, plus the declared Node and syntax checks. Two independent read-only
reviews checked the final projection delta. Their mixed-case reference finding
was corrected and rechecked.

## Wallet and research flows

- Added the exact operator-supplied watching address through the real form,
  review step and submission. The research job published after 4m 55s.
- Created a real encrypted wallet with the pinned OWS SDK through the protected
  local creation endpoint. The disposable passphrase was generated in memory.
  Replaying the same creation identity recovered the same wallet and job.
  No plaintext passphrase was found in the test workspace files.
- Checked the creation UI and required password validation. No new credential
  was entered through browser automation. Human passphrase entry remains a
  separate device acceptance step.
- Exercised OWS disconnect, existing-wallet selection and public-account
  relinking through the UI. These preserved the existing registered wallet.
- The new-wallet research and agent-requested refresh each published after
  roughly 37 seconds. Both retained coverage gaps. Three real research jobs
  were saved, with no duplicate refresh admission.
- Opened both saved analyses and ran the actual comparison UI. Missing records
  remained unknown. Coverage observations and price references were separate
  from token balance changes.
- Tested a fresh unregistered-wallet deep link. It now opens Activity instead
  of an empty or stale wallet panel.

## UI and design checks

Real browser checks covered Overview, watching and newly created wallet pages,
All tokens, Activity, token and network details, research notes, settings,
OWS forms, chat history, new chat, expanded chat and the mobile pane switch.
The actual browser sizes were 1728 by 941 and 537 by 941. The automation viewport
setting did not produce 390px, so phone-sized device acceptance is not claimed.

The catalog retained unpriced assets, supported testnet inclusion, reset search
pagination, paged after 50 rows and showed an explicit no-results state.
A token with many markets showed two pools initially and exposed all remaining
routes through disclosure. Token artwork loaded for the previously missing
contract. Token-specific wallet rows measured about 170px with a position and
107px without one. Neither browser width had page-level horizontal overflow.

The chat header, separate floating composer and background remained aligned.
Opening hidden mobile chat now follows the latest answer. Switching away and
back preserves an existing reading position. Clicking the already-active pane
and resizing the composer do not discard that position. Draft text survived
page navigation. Deliberate Stop returned an editable draft and no late answer.
Research notes currently open as the plain Markdown export in another tab.

## Fixes delivered

1. Allow exact-host top-level navigation to the public HTML shell from a link.
   Cross-site API, session, asset and mutation access remain rejected.
2. Distinguish an absent wallet from multiple wallets sharing a name.
3. Route missing/pending wallet details through Activity, including initial
   state polling.
4. Refresh custom dropdown labels after loading saved connection settings.
5. Keep code spans opaque inside Markdown emphasis, including literal stars.
6. Preserve recorded pool counts and summary notes in scoped agent reads.
   Explain that omitted detail is available through a token-specific read.
7. Display registered OWS names or pending connection tags instead of internal
   creation identities, without changing wallet IDs or SDK names.
8. Clarify empty holdings, ERC20 discovery versus native RPC availability, and
   timestamp/block changes in comparison evidence.
9. Follow the latest mobile answer initially while preserving historical
   reading positions through pane switches and composer resizing.
10. Retain scoped native zero/time/block observations and safe historical
    price-reference evidence for accurate saved-analysis comparisons.
11. Name the approved wallet in research job reads instead of requiring
    inference from blocks or receipts.

## Verification and release boundaries

`npm test` passed: 94 root Python tests, 46 viewer Python tests, all declared
Node suites and syntax checks. Independent backend and frontend reviewers
rechecked the final functional deltas. Their findings were fixed and verified.
A clean 71-member installation passed, including real encrypted OWS creation
with the pinned SDK and the installed viewer lifecycle. Package privacy checks
run before packing; the candidate manifest records the exact reviewed source commit.

The new candidate is 0.1.2. GitHub v0.1.1 and its archive remain immutable.
npm latest was still 0.1.0 when checked during this run. No registry publication,
PR merge, direct default-branch push or production deployment was performed.
Private screenshots, transcripts, wallet addresses and financial observations
remain outside the public source and package. The test vault received no funds,
and no signing or trading was performed.
