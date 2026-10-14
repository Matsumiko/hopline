# ADR-004: Separate Active Health Probes from Diagnostic Tests

- **Status:** accepted for Hopline Fase 1–2 boundary
- **Scope:** periodic node health and future diagnostic test commands
- **Evidence:** NekoBox source review in `docs/research/nekobox-testing-modes.md`; Hopline probe implementation in `hopline/probe.py`

## Context

NekoBox exposes six test actions, but they do not have the same operational meaning. URL test performs a small request through the selected outbound and is used by NekoBox's active autotester. Full, download, and upload tests generate meaningful traffic through Speedtest servers. Country test reports the country of the selected Speedtest server, which is not necessarily the exit IP country. Simple download consumes a bounded but non-zero payload from one configured URL.

Treating every test as a periodic health probe would increase bandwidth usage, couple liveness to third-party speed-test infrastructure, and mix latency, throughput, and location semantics into one health state.

## Decision

Hopline's periodic `ActiveProbeScheduler` uses only a bounded HTTP/URL probe per node. The probe must traverse the node's authenticated sing-box outbound, complete CONNECT, and receive a syntactically valid HTTP status line within the configured timeout. The target status is diagnostic output, not a liveness filter: any completed numeric HTTP response is transport-successful. Latency is recorded independently from health state.

The following remain diagnostic modes and are not scheduled periodically:

- full download + upload;
- download-only;
- upload-only;
- country lookup;
- simple download.

Future CLI/API support for these modes must report separate results, traffic cost, endpoint, and cancellation state. They must not mutate node health without an explicit policy decision.

Country verification, if required, uses an endpoint that returns the actual observed IP/country. Speedtest server metadata is not treated as exit-country proof.

Forced-node routing is a separate invariant: `node-<id>` may attempt only that node and must not fall back to another candidate.

## Alternatives Considered

### Use full speed tests for periodic health

Rejected. They consume bandwidth, rely on external server discovery, and measure capacity rather than basic liveness.

### Use country test as country health

Rejected. The reported country belongs to the selected test server metadata, not necessarily the node's egress IP.

### Treat any HTTP response as healthy
Accepted for periodic liveness. A completed target response proves that the proxy tunnel and target exchange completed; target semantics belong to a separate diagnostic. CONNECT rejection, timeout, malformed response, and TLS/relay errors remain unhealthy.

## Consequences

- Periodic health is cheap and predictable.
- Throughput and country diagnostics can evolve without corrupting liveness state.
- The configured URL and expected status policy become operational configuration that needs ownership.
- A node can be healthy for liveness while having poor throughput; these are intentionally separate facts.

## Confirmation

- URL probe tests route through node credentials and accept expected HTTP responses.
- Forced-node regression proves no fallback after a forced node rejects the tunnel.
- NekoBox mode mapping and source citations are retained in `docs/research/nekobox-testing-modes.md`.
