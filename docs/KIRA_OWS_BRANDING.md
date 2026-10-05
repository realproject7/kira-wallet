# Open Wallet Standard attribution, 2026-10-06

The showcase's new-wallet capability and the local app's Create wallet dialog
now identify Open Wallet Standard with its official wordmark and a link to
https://openwallet.sh/. The copy describes the actual Kira integration:
OWS creates and encrypts the wallet in a local vault; Kira links a public EVM
account for holdings research. Watching an existing address does not use this
creation flow. Chat signing and trading permissions have not changed.

The original SVG comes from https://openwallet.sh/footer-logo.svg. Identical
copies are served from each surface's own origin. They contain only SVG and
path elements, without scripts, remote references or event handlers. The
original white mark is rendered in dark monochrome through CSS. Its source,
checksum and ownership are recorded in site/assets/ows-artwork-source.json
and THIRD_PARTY_NOTICES.md. Attribution does not imply endorsement.

The dialog retains the existing field IDs, form submission, recovery handling
and passphrase rules. Scoped spacing hides an empty wallet list and keeps the
complete blank creation form visible at 1440 × 900. At 390 × 844, its contents
scroll inside the modal and keyboard focus reaches the creation button.
The official link has a 44px touch target. Both surfaces have no horizontal
overflow at those checked viewport sizes. Logos loaded in actual Chrome.

Verification passed: all 147 Python tests and required Node checks through
npm test, plus a fresh isolated installation containing 72 archive members.
HTTP checks confirm that /ows-logo.svg is served as image/svg+xml. The existing
OWS SDK test creates an encrypted disposable wallet and recovers the same
public identity; no operator vault or portfolio was used. Browser checks used
a separate synthetic portfolio, and no passphrase was entered in the browser.

Lazyweb evidence informed scoped security copy and provider attribution. The
Coinbase Prime result was a weak match for a creation dialog; it was used only
for the feature-specific framing, not as evidence for Kira's security behavior.
Research: https://www.lazyweb.com/agentic-search/9bde7e00-d871-4aee-ac36-77aeffd6df08

The showcase is deployed independently. App changes are in the unpublished
0.1.3 candidate and draft PR21. Independent review, merge authorization and
operator registry publication remain pending. Existing installed 0.1.2 apps
and operator wallet servers have not been changed.
