# Configuration Reference

The Hopline daemon reads a single TOML file (default `hopline.toml`). The file must be mode `0600` — group and other must have no read/write access. The `HOPLINE_CONFIG` environment variable can override the path.

## Sections

### `[hopline]`

| Field | Type | Default | Description |
|---|---|---|---|
| `database` | string | `"hopline.db"` | SQLite registry path. Use an absolute path for production (`/var/lib/hopline/hopline.db`). |
| `interval` | float | `2700` | Seconds between scheduler subscription sync cycles. |
| `jitter` | float | `0` | Random ± seconds applied to each interval. Must be < `interval`. |
| `gateway_host` | string | `"127.0.0.1"` | HTTP CONNECT proxy bind address. Use `0.0.0.0` only to expose the proxy deliberately; control, metrics, and tunnel remain localhost. |
| `gateway_port` | int | `18770` | Gateway listener port. |
| `tunnel_port` | int | `18771` | First generation sing-box mixed inbound port. |
| `control_port` | int | `18772` | Control API listener. Set to `0` for ephemeral (test only). |
| `country_max_age` | float | `3600` | Seconds before geolocation metadata is considered stale. |
| `sing_box_binary` | string | `"sing-box"` | Path or command name for the sing-box binary. |
| `engine_workdir` | string | `""` | If set, sing-box working directories are created under this path instead of a tempdir. Use for production (`/var/lib/hopline/engine`). |
| `webui_dir` | string | `""` | Path to a built React panel (`webui/dist`). When set, the control API serves the static files at `/`. Leave empty to disable. |
| `panel_auth` | bool | `true` | Require login to open the panel. Credentials reuse `[auth]`. Sessions last 12 h via HttpOnly cookie. |
| `max_active_connections` | int | `64` | Per-node max concurrent active CONNECT relays. Above this, `503` is returned before tunnel allocation. |

### `[auth]`

| Field | Type | Description |
|---|---|---|
| `username` | string | Local proxy authentication username. Default `"hopline"`. |
| `password` | string | Local proxy authentication password. Must be non-empty. |

Client uses these credentials in `Proxy-Authorization` to the gateway. Node credentials are never shared with the client.

### `[[subscriptions]]`

An array of tables. Each entry declares one subscription source.

| Field | Type | Description |
|---|---|---|
| `url` | string | Full HTTP(S) subscription URL. Must not contain inline credentials in userinfo (use query params or headers as appropriate). |

```toml
[[subscriptions]]
url = "https://example.invalid/sub"
```

Subscription URLs are seeded once into the managed-subscription database. After the first startup, the panel manages subscriptions; the config entries serve only as a bootstrap seed.

### `static_nodes`

A TOML array of share-link strings. These create persistent single-node sources that do not participate in subscription retirement.

```toml
static_nodes = [
  "vless://uuid@host:443?security=tls&type=ws&path=/x#label",
  "vmess://uuid@host:443?security=tls&sni=host.test#label",
]
```

### `[health]`

| Field | Type | Default | Description |
|---|---|---|---|
| `targets` | string[] | `[]` | One or more HTTP(S) probe URLs. Must not contain credentials or fragments. |
| `interval` | float | `300` | Seconds between active probe queue runs. |
| `timeout` | float | `5` | Probe timeout in seconds. |
| `concurrency` | int | `10` | Max concurrent probe tasks. |
| `mode` | string | `"tcp"` | Probe mode: `"tcp"` or `"http"`. `"http"` uses CONNECT through the sing-box generation and validates a response completes. |
| `proxy_host` | string | `"127.0.0.1"` | Sing-box mixed inbound address for HTTP-probe CONNECT. |
| `proxy_port` | int | tunnel port | Sing-box mixed inbound port (defaults to `tunnel_port`). |
| `metrics_enabled` | bool | `false` | Start a Prometheus metrics endpoint. |
| `metrics_host` | string | `"127.0.0.1"` | Metrics listener address (localhost only). |
| `metrics_port` | int | `18773` | Metrics listener port. |

### `[capability]`

| Field | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable per-node IPv4/IPv6 capability probing. |
| `max_age` | float | `3600` | Seconds after which capability results are stale. |
| `interval` | float | `900` | Seconds between capability refresh cycles. |
| `timeout` | float | `20` | Per-probe timeout. Must be < `interval`. |
| `concurrency` | int | `1` | Max concurrent capability probe tasks. |
| `ipv4_url` | string | `"https://api4.ipify.org?format=json"` | IPv4 exit-IP target. Must be HTTPS. |
| `ipv6_url` | string | `"https://api6.ipify.org?format=json"` | IPv6 exit-IP target. Must be HTTPS. |

## Environment

| Variable | Purpose |
|---|---|
| `HOPLINE_CONFIG` | Override the config file path (default `hopline.toml`). |
| `HOPLINE_SUBSCRIPTION_URL` | Fallback subscription URL for `hopline sync --url` (CLI only). |
## Health vs performance

Probe results (`successes`, `failures`, `latency_ms`) determine node liveness only. Relay outcomes are stored separately in `performance` (`conn_successes`, `conn_failures`, `latency_ewma_ms`) and never change the health state, so a node that relays slowly is not marked dead and a node that passes probes is not hidden by relay errors.

Failures are recorded as stable categories (`connect_timeout`, `connect_refused`, `connect_reset`, `tls_error`, `handshake_timeout`, `auth_rejected`, `upstream_rejected`, `probe_timeout`, `probe_failed`, `node_mismatch`, `io_error`, `unknown`) with any credential material redacted.
