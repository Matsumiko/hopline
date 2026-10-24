# Subscriptions

Subscriptions are the node sources. Hopline parses VMess, VLESS, Trojan, and Shadowsocks share links, including structured Clash YAML and sing-box JSON.

## Single Source of Truth

The SQLite registry is the **only** source of truth for subscriptions. The TOML file carries no subscription list on an established host.

`[[subscriptions]]` exists solely for first-time provisioning: on the very first start it is imported into `managed_subscriptions` and a `subscriptions_seeded` marker is written to `settings`. From then on the import is skipped permanently, so a source deleted in the panel can never be resurrected by a restart or by editing the config.

```text
first start :  config [[subscriptions]] ──seed──▶ managed_subscriptions
later starts:  managed_subscriptions (SQLite) ──▶ sync
```


## Lifecycle

1. **Seed** — config URLs are imported into `managed_subscriptions` exactly once; the marker makes every later start a no-op.
2. **Sync** — the scheduler fetches each source on `interval`, honoring ETag and Last-Modified; a `304` is a no-op.
3. **Parse** — share links are parsed and deduplicated by connection parameters into a stable node ID.
4. **Validate** — malformed entries are counted as `invalid` but a previous valid snapshot is retained (`used_last_valid`).
5. **Retire** — nodes absent from three consecutive valid snapshots are removed; a source deleted from config or panel is reconciled after a full cycle, dropping its orphan nodes.

## Add / Delete via Panel

- **Add** (`POST /subscriptions/add`): inserts the URL into `managed_subscriptions`, triggers a background sync. The source appears immediately with `valid: false` until sync succeeds.
- **Delete** (`POST /subscriptions/delete`): removes the URL from `managed_subscriptions`, triggers a background sync that retires orphan nodes.

Both are non-blocking: the HTTP response returns before fetching completes.

## Limits

| Limit | Default | Effect |
|---|---|---|
| `max_body_bytes` | 10 MiB | Subscription response body cap. Exceeding it raises `subscription response exceeds configured limit`. |
| `max_nodes` | 2000 | Per-source parse cap; further valid entries are ignored. |

Large pools (`limit=19000` style URLs) must keep the body under `max_body_bytes`; the node count itself is clipped to `max_nodes`.

## Source Redaction

The API and panel never return the raw URL. Sources are labeled `hostname#<sha256-prefix>`, and a `digest` field (SHA-256 prefix) identifies a source for delete. This keeps provider hostnames visible for recognition while hiding query parameters and keys.

## Credentials

The raw subscription body, share links, and node UUID/passwords are stored only in the private SQLite registry. They never appear in `/subscriptions`, `/nodes`, metrics, logs, or the panel.
