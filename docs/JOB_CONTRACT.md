# Persisted jobs, version 1

The engine owns financial facts. CLI and protected local browser actions share
this contract. Chat interruption never cancels an engine job.

## Request and identity

Mutations use `{schema_version: 1, operation, input, idempotency_key}`.
Supported operations are `wallet.add` (address, exact tag), `wallet.refresh`
(wallet address or exact tag), `prices.refresh` (same), `wallet.setTags`
(wallet, exact tags), `job.resume` and `job.cancel` (job_id).
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
