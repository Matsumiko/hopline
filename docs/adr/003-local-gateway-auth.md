# ADR-003: Separate Local Gateway Authentication from Node Credentials

- **Status:** accepted for Hopline Fase 1
- **Scope:** client authentication at the local HTTP CONNECT gateway
- **Evidence:** Gateway regression tests and `tools/smoke_ephemeral.py`; see `PROGRESS.md`

## Context

The Gateway previously interpreted the client Basic Auth username as a node selector and ignored the client password. That exposed node IDs as client-facing credentials and allowed any password value to select a node. Node credentials are an internal Hopline-to-sing-box concern and must not be required from client applications.

## Decision

Hopline requires a local `[auth]` TOML section:

```toml
[auth]
username = "hopline"
password = "a-private-local-password"
```

The Gateway validates the local username/password before selecting a node. The default local username is `hopline`; its route is `rotate`. A username equal to a node ID or prefixed with `node-` remains available for explicit node selection, but it uses the same local password. The local password is never sent to sing-box. Hopline creates the upstream Basic Auth header separately from the selected node ID and node credential.

Missing, malformed, unknown, or wrong-password credentials return `407 Proxy Authentication Required` before any upstream connection attempt.

## Alternatives Considered

### Continue using node credentials as client credentials

Rejected. It leaks provider credentials to every client and makes password validation impossible to separate from routing.

### Accept any password and use only the username

Rejected. It is authentication bypass behavior on a local service and conflicts with the security contract.

### Add a separate auth service

Rejected for Fase 1. A local static credential in the private TOML file is sufficient for the single-user/localhost trust boundary without another process or dependency.

## Consequences

- Client configuration is stable and does not expose subscription credentials.
- Changing node credentials does not require changing client proxy configuration.
- The TOML file remains sensitive and must be permission `0600`.
- The local credential is static until the config is changed and the daemon is restarted.
- Existing external callers using `node-id:node-credential` must migrate to the local credential.

## Confirmation

- Unit/integration coverage rejects a wrong local password and preserves CONNECT failover.
- Ephemeral smoke returns HTTP 200 for all four supported protocols with the local credential, and HTTP 407 for wrong or missing credentials.
- `Gateway` has no usable default password; daemon configuration supplies the credential.
