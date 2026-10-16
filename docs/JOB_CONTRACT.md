# Persisted jobs, version 1

The engine owns financial facts. CLI and protected local browser actions share
this contract. Chat interruption never cancels an engine job.

## Request and identity

Mutations use `{schema_version: 1, operation, input, idempotency_key}`.
Supported operations are `wallet.add` (address, exact tag), `wallet.refresh`
(wallet address or exact tag), `prices.refresh` (same), `wallet.setTags`
(wallet, exact tags), `settings.rpc`, `settings.discovery`, `settings.provider`,
`job.resume` and `job.cancel` (job_id).
Read operations are `job.read`, `job.list`, `snapshot.read`, and
`snapshots.compare`. The portfolio projection retains its existing schema.

Inputs reject unknown fields and invalid identifiers. Wallet selectors resolve
to a unique registered address before persistence. Ambiguous tags fail.
Idempotency keys are private, bounded strings. Persist only their SHA-256 hash.
The hash maps to one job across operations. Reusing it with different normalized
input fails with `idempotency_conflict`. Terminal duplicate submission returns
the same job without rerunning providers. Resume requeues the same job ID and
increments its attempt on execution. Retain the key until the job is removed
by a future explicit retention policy. Version mismatches fail closed.

`settings.provider` accepts exactly `{provider: "public" | "alchemy", key_env}`.
The key reference is a bounded environment variable name, never a credential.
One writer-locked atomic replacement changes RPC mode and discovery together.
Alchemy updates generated network references while preserving explicit custom
chain overrides, unrelated chains, explorer choice and public fallback policy.
A missing local key fails before replacement. Public mode keeps inactive custom
references for later use. A detected key is not a validated provider or complete
holdings result. Existing settings.rpc and settings.discovery requests remain
compatible. The browser waits for terminal settings results; retrying a lost
result checks the same accepted job instead of submitting another change.

## Envelope

Each private `jobs/<uuid>.json` records schema_version, job_id, operation,
input, request_hash, key_hash, state, attempt, created_at, updated_at,
sequence, cancel_requested, stage, events, checkpoint, result, errors and
previous_result. Events contain only allowed stage names and real counts.
Unknown totals stay null. Result references use paths relative to snapshots/;
no absolute paths or arbitrary file reads are supported.

The optional `started_at` timestamp records when the current attempt was
claimed by the worker. Resuming replaces it on the next claim. Older envelopes
remain valid without it. The viewer then labels its timer "Since request"
instead of claiming an exact execution time. Terminal timers stop at the last
recorded update. A queued job uses its latest queue transition, not a previous
attempt's start.

States: queued -> running -> succeeded | partial | failed | cancelled.
Recovery converts unfinished running jobs to interrupted. Explicit resume may
move interrupted, failed or cancelled to queued. Succeeded and partial jobs
retain their result; a new refresh is a new job. Partial is a published result
with documented coverage gaps, not a failed result or proof of zero holdings.

Updates use private files, replace, file fsync and directory fsync under a
process lock. One worker owns a portfolio. Existing analysis/config locks
serialize writers. A worker lease is inherited by its engine child, preventing
another worker from replaying a still-running orphan engine after a supervisor
crash. A busy legacy writer leaves the new job queued.

## Publication and recovery

Analysis jobs allocate `snapshots/jobs/<job_id>` before executing. The existing
engine resumes only matching, unpublished evidence; completed per-chain reads
retain their recorded blocks. Partial stages retain missing information.
No global block is invented. Engine publication atomically updates the registry
pointer after results exist. A saved result plus a matching registry pointer
or research-history entry is authoritative even if the final manifest update
was interrupted. A published result whose
pointer has since moved remains readable from its immutable directory.

Price jobs save an immutable overlay and publication receipt before replacing
the viewer's market-prices projection. Recovery can finish this projection
without provider calls. Failed or cancelled work retains previous_result and
saved evidence. Cancellation stops the subprocess group, waits for the writer
to release, then records its outcome. If publication won the race, record the
published result rather than claim it was cancelled.

Provider exception text, URLs and credentials never enter public job events.
Safe errors use fixed codes and messages. Pinned blocks and coverage remain in
the engine result. Stage progress is evidence from emitted engine events;
there is no simulated timer or fabricated percentage.

## Local transport

Writes require the exact loopback Host, same Origin, JSON content type and an
in-memory session token obtained from the same-origin session endpoint. No
CORS or credential files are exposed. Session tokens rotate on server restart.
Bound request size and reject foreign origins and DNS-rebinding Host values.
The legacy viewer remains read-only unless explicitly launched with --controls.
Synthetic demo controls never start provider requests.

## Acceptance cases

Synthetic tests cover duplicate requests, key conflicts, invalid versions and
fields, concurrent submit, restart before execution, interruption before and
after publication, immutable partial results, previous-result preservation,
cancel/resume, independent worker leases, snapshot path escape, ambiguous tags,
unknown values and cross-chain coin identity. HTTP checks cover unauthorized
writes, foreign origins/Host, malformed bodies and safe static allowlists.
No operator wallet is analysed by this verification.

## Implemented adapters

`kira_jobs.py` contains typed request and persisted envelope definitions, strict
operation validation and the worker. `sources/job-envelope-v1.schema.json`
is the versioned envelope artifact. `sources/job-request-v1.schema.json`
defines the typed mutation request variants. `settings.rpc` and `settings.discovery`
are also durable operations; they accept environment references only and share
the portfolio writer lock. `wallet.setTags` records exact tag changes.

Chain events retain actual endpoint ordinal, configured reference identity,
status and pinned block as a decimal string. Completed cached chain stages emit
the same saved block on resume. Recorded stage details stay available in the
browser. A registry publication receipt is authoritative even if a crash
precedes the final run manifest update. A completed price overlay can reconstruct
its projection receipt without another provider request.

The read-only stdio MCP adapter uses the same job and snapshot service. It has
no mutation tools and requires separate operator-approved client setup.

## Initial evidence and continuations in 0.1.7

A valid wallet admission records its identity under a short registry lock.
Idempotent replay repairs missing admission without undoing later name edits.
New analysis jobs have `analysis_phase: baseline`. The first usable chain
publishes an immutable `initial/` snapshot; the running job can reference it
without claiming that the job is finished. The baseline publishes its own final
partial snapshot and admits exactly one durable `enrichment` continuation with
`parent_job_id`. The parent records `continuation_id`.

Baseline work runs before enrichment. New baseline admission can preempt a
running continuation. Saved chain evidence and verified registry identity
prefixes survive; an interrupted registry batch is read again. A newer request
for the same wallet supersedes older detailed work. Generation checks prevent
an older result from replacing the latest pointer, while preserving historical
evidence. Explicit cancellation of baseline prevents automatic continuation.

`onchain_progress` events identify the actual operation, chain, checked count
and known total. `chain.status: complete` concerns the on-chain checkpoint.
Normalized wallet `complete` concerns general token discovery. Registry coverage,
candidate failures, deferred candidates and pending RPC reads are separate facts.
These flags do not prove exhaustive holdings. First results can be read while
background work remains active.

## Responsive research in 0.1.8

Queued initial reports, prices.refresh and settings operations can preempt
enrichment. The single writer remains exclusive. Successful balance batches
are checkpointed per job, wallet, candidate fingerprint and fixed block hash.
Fresh holdings research never reuses another job's quantities. Completed pool
checks and RPC prefixes also survive a resume at their original market block.

The market phase has a 180-second budget including DEX indexer discovery and
official pool verification. Progress reports completed discovery items,
factory-query counts and pool-check counts. At the budget boundary, the engine
publishes a new immutable market-initial-NNNN snapshot with recorded balances,
actual registry coverage and market_pending. It pauses in interrupted state
with market_budget and an explicit Resume action. A resume continues saved
checks and never overwrites an earlier interim snapshot. Pending pools remain
unknown. This budget is distinct from failed provider reads.

settings.importEnv is a CLI-created request containing import_id and key_env.
The environment file path stays in a private local reference record. The job
worker applies it under the writer lock and records a settings receipt. No
secret value is copied into the request, receipt, viewer or model context.
Explicit cancellation survives recovery and exception boundaries as stopped.
A completed publication receipt still wins a cancellation race.
