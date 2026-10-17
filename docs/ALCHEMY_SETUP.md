# Connect Alchemy to Kira

Alchemy supplies the token index Kira uses across networks. Kira requires your
own Alchemy connection for new holdings and price research. No wallet keys,
seed phrase, signature or spending permission is needed.

The app includes a screenshot guide at `/alchemy-guide.html`, linked from
**Connect Alchemy**. Its dashboard illustration is Alchemy’s published example;
it contains no Kira operator account or key.

## 1. Get your app key

Open the [Alchemy dashboard](https://dashboard.alchemy.com/). A new account may
already have a default app. Use it or choose **Apps → Create new app**. Enable
the networks you use and confirm Node API and Portfolio API access. Copy the
app API key from its details page. You do not need separate endpoint URLs.

These steps follow the [official walkthrough](https://www.alchemy.com/docs/create-an-api-key).
Dashboard labels can change. Review your account’s API access and usage limits.

## 2. Connect locally

Run this in your terminal:

```sh
kira connect alchemy
```

Paste the key at the hidden prompt and press Enter. Kira stores it in a private
local file and queues the connection setup. The key never appears in the
command, browser, chat, public job or analysis.

For another workspace, use `kira --data-dir /path/to/workspace connect alchemy`.
For an existing environment file, `kira config import-env --file PATH` retains
that file reference. Add `--key-env NAME` when its variable has a different name.
The browser’s advanced option accepts the variable name only.

## 3. Add or refresh a wallet

Return to Kira and choose **Check connection**. Add a public wallet, or refresh
holdings for an existing wallet. A found local key does not prove every API or
network is available; the holdings results record actual access and gaps.

Each holdings lookup checks every configured network and all returned token
candidates. Reachable Mint Club registries are enumerated too. There is no
128-candidate cutoff. Unsupported indexes, failed balances and missing prices
or artwork remain unknown.

Price responses also supply artwork by network and contract. Kira reuses that
metadata instead of requiring another successful lookup for the same logo.
Completed reserve-price paths remain usable when a bounded pass pauses;
unfinished paths keep their original unknown state.

**Analyze sell routes** is optional. It uses the saved balances and their
original blocks to estimate a representative sale or redemption. It is not
required for tokens, prices or logos and does not expand the holdings inventory.

## Troubleshooting

- Run the command in the workspace you are viewing.
- Check the app’s networks, Node API, Portfolio API and usage in Alchemy.
- Retry holdings after access or provider errors are resolved.
- An unsupported network can still have native or Mint Club balances. An indexer
  cannot guarantee every arbitrary token, and another provider cannot restart
  a retired network.

Kira makes requests locally through your account. Review Alchemy’s current
[plans and limits](https://www.alchemy.com/docs/reference/pricing-plans).

The research engine spaces its private Alchemy node reads at least 250 ms apart
in one shared lane across Alchemy networks. An Alchemy throughput response cools
that lane before queued reads can use another Alchemy host. Public and other
custom RPC endpoints keep their existing pacing and fallback behavior. Canonical
block checks and provider backoff still apply. This is a local scheduling policy,
not a guarantee about an account's available capacity. Alchemy's
[throughput allowance is shared across apps and chains](https://support.alchemy.com/articles/3788245542-is-alchemy-s-throughput-cu-s-limit-shared-across-all-apps-or-set-per-chain).
