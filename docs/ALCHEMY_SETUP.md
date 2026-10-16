# Connect Alchemy to Kira

Kira works with free public RPC by default. It checks native assets, selected
common token contracts and the Mint Club registry. Other ERC20 holdings may
be missing. For broader token discovery, connect your own Alchemy account.
Kira runs these requests locally and does not operate a hosted relay.

## Create an Alchemy app

1. Sign in to the [Alchemy dashboard](https://dashboard.alchemy.com/).
   A new account may already have a default app. Use it, or open your team
   menu, Team Overview, Apps, then Create new app.
2. Name the app and select the mainnets you want to research. Check that the
   app has Node API and Portfolio API access for those networks. Create it.
3. Copy the app API key. The Endpoints tab shows its network URLs. Kira's
   combined Alchemy setup needs the key, so you do not need to copy each URL.

These steps follow Alchemy's [official API key guide](https://www.alchemy.com/docs/create-an-api-key),
checked on October 9, 2026. Dashboard wording can change.

## Connect the key locally

Create a private directory and file in your terminal:

```sh
mkdir -p ~/.config/kira
touch ~/.config/kira/alchemy.env
chmod 600 ~/.config/kira/alchemy.env
```

Open the file in a local text editor. On macOS, you can use:

```sh
open -e ~/.config/kira/alchemy.env
```

Add this line, replacing `YOUR_KEY` inside the editor:

```dotenv
ALCHEMY_API_KEY=YOUR_KEY
```

Save the file, then run:

```sh
kira config import-env --file ~/.config/kira/alchemy.env
```

For a non-default workspace, supply its existing `--data-dir` before `config`.
Kira stores the file reference. Credentials stay outside the browser, chat and
published analysis. Do not commit this file to a repository. A process
environment variable with the same name overrides the file value; check that
if an old key remains active.

If detailed research is running, import-env queues a Local connection setup
job in Activity. The writer pauses safely, applies the file reference, and
resumes detailed research automatically. Wait for the setup job to complete,
then recheck the connection. The public job contains no key value or file path.
A legacy CLI analysis keeps its writer lock; its queued setup waits until that
analysis finishes or is stopped.

## Check the connection and refresh

Open Workspace settings, then Manage data connection. Select Alchemy and use
"I added my key · check again". Save the connection. Finding the local key
does not prove the account, API or network is working.

For an existing wallet, choose Refresh this wallet's holdings or Refresh
holdings on its page. A new analysis confirms access and coverage. Old saved
analyses retain their original observations and warnings. Saving a connection
does not register a wallet or start research automatically.

## What uses the key

Ordinary balances prefer public RPC. After two failed or unavailable public
providers, Kira tries the configured custom backup within the read deadline.
Advanced settings can choose custom first or require custom only. Existing
explicit custom-only restrictions remain in force.

Alchemy token discovery uses the key directly. Standard public RPC cannot
enumerate arbitrary ERC20 holdings. Kira uses Alchemy's
[Tokens By Wallet endpoint](https://www.alchemy.com/docs/data/portfolio-apis/portfolio-api-endpoints/portfolio-api-endpoints/get-tokens-by-address),
then verifies discovered candidates with on-chain balance reads.

## If tokens are still missing

- **Local key unavailable:** confirm the file exists, its variable name matches
  the connection settings, and you ran the import command in the right workspace.
- **Discovery failed:** check the app's enabled APIs and networks and Alchemy's
  usage dashboard. Correct access or limits, then retry holdings.
- **Some balances could not be checked:** wait briefly and retry. Public and
  custom providers both have outages and limits. Review Advanced read preferences
  if a custom-only endpoint is unavailable.
- **Unsupported network:** broader discovery is unavailable there. Connecting
  Alchemy cannot cover every network or every token. Known-contract reads remain
  useful, and missing holdings remain unknown.

Alchemy has account allowances and throughput limits. Check the current
[plans](https://www.alchemy.com/docs/reference/pricing-plans) and API availability
before selecting a plan. Kira does not create an account, subscribe or upgrade
it. Public-first balance reads reduce ordinary use of the key; discovery still
consumes Alchemy allowance. No connection guarantees a complete token inventory.
