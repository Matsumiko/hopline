# Control API

The daemon exposes a localhost-only control API on `127.0.0.1:18772`. It always binds to localhost; every response is JSON. Node credentials, subscription URLs, tokens, and API keys are never returned.

## Conventions

- Read endpoints use `GET`; mutations use `POST`.
- Mutations return `200 OK` on success, `404` on unknown node/subscription, `400` on malformed request, `405` for wrong method, and `501` when the daemon lacks the required wiring (e.g. probe target not configured).

## Endpoints

### `GET /status`

Pool-level aggregates.

| Field | Type | Description |
|---|---|---|
| `nodes` | int | Total nodes in the registry. |
| `schema_version` | int | Registry schema version. |
| `health` | object | Global count per state: `healthy`, `degraded`, `dead`, `quarantine`, `unknown`. |
| `protocols` | object | Per-protocol (`ss`, `trojan`, `vless`, `vmess`) count per state. |
| `countries` | object | Per uppercase country code count per state; nodes without metadata count under `unknown`. |

### `GET /nodes`

`{"nodes": [...]}`. Each entry:

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable node ID. |
| `protocol` | string | `ss`, `trojan`, `vless`, or `vmess`. |
| `server` | string | Node hostname/IP. |
| `port` | int | Node port. |
| `name` | string \| null | Share-link fragment name. |
| `health` | string | `healthy`, `degraded`, `dead`, `quarantine`, or `unknown`. |
| `successes` / `failures` | int | Health counters. |
| `latency_ms` | float \| null | Last observed latency. |
| `capabilities` | object | `ipv4` and `ipv6`, each `{capable, ip, checked_at, last_error}` or `null`. |
| `geolocation` | object \| null | `{ip, country_code, country, asn, organization, provider, checked_at}`. |

### `GET /subscriptions`

`{"subscriptions": [...]}`. Each entry:

| Field | Type | Description |
|---|---|---|
| `digest` | string | Short SHA-256 prefix of the URL; used to identify a source without exposing it. |
| `source` | string | Redacted `hostname#digest` label. |
| `scheme` | string | `https`, `http`, or `static`. |
| `valid` | bool | Whether the last sync produced a valid snapshot. |
| `snapshot_hash` | string \| null | Last valid snapshot hash. |
| `updated_at` | string \| null | Last sync timestamp. |
| `nodes` | int | Number of nodes currently owned by this source. |

### `GET /service`

Daemon runtime info: `{"generation_port": 18771, "started_at": 1792310821.96}`. `generation_port` is the current active sing-box generation port; `started_at` is a Unix timestamp.

## Mutations

### `POST /sync`

Triggers a subscription refresh. Returns `{"synced": 5}` with the number of sources processed.

### `POST /nodes/{id}/probe`

Runs one active probe against the node (using `[health].targets[0]`), records the result in the health state, and returns `{"node_id": "...", "action": "probe", "ok": true, "state": "healthy"}`.

### `POST /nodes/{id}/enable`

Removes a manual quarantine. The node rejoins the candidate pool. Returns `{"node_id": "...", "action": "enable", "state": "degraded"}`.

### `POST /nodes/{id}/disable`

Quarantines the node, removing it from the candidate pool. Returns `{"node_id": "...", "action": "disable", "state": "quarantine"}`.

### `POST /subscriptions/add`

Body: `{"url": "https://..."}`. Validates the URL, adds it to the managed-subscription database, then schedules a background sync.

Returns `{"action": "add", "digest": "83e0a33370"}` (non-blocking; sync runs in background).

### `POST /subscriptions/delete`

Body: `{"digest": "83e0a33370"}`. Resolves the digest to a source URL, deletes it from the database, then schedules a background sync that retires its orphan nodes.

Returns `{"action": "delete", "digest": "83e0a33370"}`.

## Metrics (separate listener)

When `[health].metrics_enabled = true`, a Prometheus text endpoint is exposed on `127.0.0.1:18773/metrics`:

- `hopline_nodes`
- `hopline_health_nodes{state="..."}`
- `hopline_protocol_nodes{protocol="..."}`
- `hopline_active_probe_enabled`

Label cardinality is bounded to enum values; no node ID, host, or credential appears. See [ADR-012](adr/012-metrics-ownership-retention.md).