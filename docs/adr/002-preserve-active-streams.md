# ADR-002: Preserve Active Streams During Config Changes

- **Status:** accepted for Hopline runtime
- **Scope:** sync, node changes, health changes, config updates, and engine lifecycle
- **Evidence:** F0 harness on sing-box 1.14.3; see `PROGRESS.md`

## Context

The F0 experiment proved that sing-box `SIGHUP` can apply a new route, but it closes an active stream during reload. That behavior violates Hopline's product promise: once client bytes are forwarded, a POST or long-lived stream must not fail because Hopline changed its own configuration.

## Decision

Active streams are immutable after forwarding begins. Hopline MUST NOT close them because of sync, health changes, rotation, config updates, generation changes, or normal shutdown sequencing.

Node configuration changes use generation ownership:

1. Validate and build the next generation before publication.
2. Publish the new generation for new connections only.
3. Keep the previous generation available for connections already bound to it.
4. Drain the old generation after its active connection count reaches zero.
5. If the selected tunnel engine cannot perform this swap without closing streams, defer the update or require explicit maintenance. Never force a reload while active streams exist.

Health changes never reload or restart the tunnel engine.

## Alternatives Considered

### Reload sing-box in place with SIGHUP

Rejected. F0 observed active-stream interruption on sing-box 1.14.3.

### Retry or reconnect an interrupted stream

Rejected. Hopline cannot know whether an opaque HTTPS request or POST was processed upstream. Replaying it can duplicate cost or side effects.

### Keep one permanent sing-box process and never update config

Rejected. It prevents subscription changes and node removal from taking effect. Generation ownership preserves streams while retaining updates for new connections.

## Consequences

Positive:

- Hopline cannot be the cause of an active POST/SSE stream interruption during ordinary config changes.
- New node state can be published without moving existing connections.
- The retry boundary remains explicit and enforceable.

Negative and operational constraints:

- Old generations may retain resources until long-lived streams finish.
- A node removal is not immediate for already-bound connections.
- If sing-box cannot be run as independently swappable generations, Hopline must defer updates or enter explicit maintenance.
- Shutdown and reload require active-connection accounting and bounded operational reporting.

## Confirmation

Required evidence before F1 completion:

- A local generation-swap harness keeps an existing stream alive while new connections use the new generation.
- A live-node smoke test, if run, uses an ephemeral config and records only redacted metadata.
- A negative test proves an in-place SIGHUP is not used as the stream-preserving mechanism.
