# Routing

The HTTP CONNECT proxy username selects how the gateway picks a node. If no `Proxy-Authorization` header is present or the password does not match `[auth].password`, the gateway returns `407`.

## Grammar

```text
rotate
node-<id>
sticky-<session>
country-<cc>
country-<cc>-sticky-<session>
ipv4
ipv6
ipv4-sticky-<session>
ipv6-sticky-<session>
```

| Route | Behaviour |
|---|---|
| `rotate` | Round-robin across healthy, non-cooldown nodes. Default when username is `hopline` (config `proxy_username`). |
| `node-<id>` | Force a specific node. No fallback; returns `503` if unavailable. |
| `sticky-<session>` | Bind a session to a node until idle TTL expires (default 10 min). Rebinds pre-forward if the bound node is dead or quarantined. |
| `country-<cc>` | Filter to nodes whose geolocation metadata is fresh and matches the two-letter country code. `503` when the pool is empty. |
| `country-<cc>-sticky-<session>` | Sticky within a country pool. Rebinds only within the same country. |
| `ipv4` / `ipv6` | Filter to nodes whose capability probe proved the address family. `503` when no node is fresh. |
| `ipv4-sticky-<session>` / `ipv6-sticky-<session>` | Sticky within a capability family. |

## Health and cooldown

All routes exclude nodes in `dead`, `quarantine`, or cooldown. A node is cooldown for 30 s after a passive failure; three consecutive failures eject it to `dead`. Active probes recover dead nodes with backoff and hysteresis (three consecutive successes back to `healthy`).

See [ADR-005](../docs/adr/005-health-cooldown-recovery.md) and [ADR-006](../docs/adr/006-sticky-routing.md).

## Failover

If a CONNECT to the selected node fails before the gateway sends `200 Connection Established` to the client, the picker moves to the next candidate. No retry occurs after upstream data begins flowing.

## Pool empty

When the filtered candidate pool is empty (e.g. `country-xx` with no matching nodes, or all nodes in cooldown), the gateway returns `503 Service Unavailable` immediately.