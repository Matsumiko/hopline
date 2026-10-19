# Web Panel

Hopline includes a React control panel in `webui/`. It runs fully client-side and calls the control API on `127.0.0.1:18772`. No subscription URLs, node credentials, or passwords are ever sent to the browser.

## Access

Production: set `webui_dir` in the config and open `http://127.0.0.1:18772`. The panel is protected by a login screen when `[hopline].panel_auth` is enabled (default). Log in with the same username/password as `[auth]`. Remote access requires an SSH tunnel:

```bash
ssh -L 18772:127.0.0.1:18772 user@vps
```

Sessions use an HttpOnly, SameSite=Strict cookie valid for 12 hours. Use the **Logout** button in the top bar to end the session. Disable the login gate with `panel_auth = false` in `[hopline]` (not recommended).

Dev: `cd webui && npm ci && npm run dev -- --host 127.0.0.1`. Vite proxies `/status`, `/nodes`, `/sync`, `/subscriptions`, and `/service` to the control API.

## Sections

### Overview (top)

Four stat cards: total nodes, healthy pool, protocol count, country groups. Auto-refreshes every 30 seconds. The runtime note shows the generation port and daemon uptime (fetched from `GET /service`).

### Pool Health

Coloured bar showing the global health distribution. Legend with per-state node counts.

### Sources (new)

Lists all subscription sources with their source label, scheme, validity, node count, snapshot hash, and last update timestamp.

- **Add subscription**: form above the table. Enter a full HTTPS URL and click *Add subscription*. The service returns immediately; a background fetch follows.
- **Delete**: red *Delete* button on each row. Removes the source and retires its nodes in a background sync.

### Inventory — Nodes

Full table with search (matches ID, server name, and country code) and protocol/health filters.

Click a row to expand a detail section showing geolocation data (country, ASN, organisation, exit IP, check time), IPv4/IPv6 capability status, and health counters (successes / failures).

### Per-Node Actions

Three buttons in each row:

| Button | Action | Effect |
|---|---|---|
| **Probe** | `POST /nodes/{id}/probe` | Runs one active probe through the current generation and records the result. |
| **Enable** | `POST /nodes/{id}/enable` | Removes quarantine; the node rejoins the candidate pool. |
| **Disable** | `POST /nodes/{id}/disable` | Quarantines the node; excluded from rotation until enabled. |

All three are immediate (health state updates synchronously) and show an inline result.

### Global Actions

**Sync now** (top bar) triggers a full subscription refresh via `POST /sync`. The response shows how many sources were processed. Data then refreshes automatically.

**Refresh data** re-fetches `/status` and `/nodes` without triggering a sync.

## Error States

- **Panel cannot load live data**: the control API is unreachable. A retry button prompts a re-fetch.
- **No nodes match these filters**: the current search/filter combination returned an empty result.
- **Sync failed**: the `POST /sync` request returned an error (shown below the sync button).

## Build & Deploy

```bash
cd webui
npm ci
npm run build
```

Copy `webui/dist/` to the path set in `[hopline].webui_dir` (e.g. `/opt/hopline/app/webui/dist`). No web server is needed; the control API serves the static files directly.