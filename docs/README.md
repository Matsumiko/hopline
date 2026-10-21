# Documentation

Hopline documentation is structured by topic. Each page is self-contained and references the Architecture Decision Records when a design decision has lasting consequences.

## Index

| Document | Content |
|---|---|
| [Configuration](configuration.md) | Full TOML file reference: every section, field, default, and constraint |
| [Control API](control-api.md) | All HTTP endpoints exposed by the daemon on `127.0.0.1:18772` |
| [Web Panel](web-panel.md) | The React control panel: overview, node explorer, subscriptions, and actions |
| [Subscriptions](subscriptions.md) | Subscription lifecycle, DB model, seeding from config, add/delete via panel, and node retirement |
| [Routing](routing.md) | Proxy CONNECT username grammar: rotate, node, sticky, country, and IP-family routes |
| [Acceptance status](acceptance-status.md) | Latest measured acceptance per protocol and address family, and what it does not prove |
| [Routing limits](routing-limits.md) | Explicit limits of failover, rotation, routing, and lifecycle |
| [Generation recovery](generation-recovery.md) | What to do when a generation fails to start or drains slowly |
| [Benchmark](benchmark.md) | Reproducible in-process benchmarks and how to read them |

## Architecture Decisions

| ID | Decision |
|---|---|
| [ADR-001](../docs/adr/001-modular-monolith-sing-box.md) | Modular monolith Python with sing-box as tunnel subprocess |
| [ADR-005](../docs/adr/005-health-cooldown-recovery.md) | Cooldown, backoff, and hysteresis for health states |
| [ADR-006](../docs/adr/006-sticky-routing.md) | Process-local sticky routing with TTL and rebind |
| [ADR-011](../docs/adr/011-node-compatibility-isolation.md) | Node compatibility isolation and uTLS fingerprint normalization |
| [ADR-012](../docs/adr/012-metrics-ownership-retention.md) | Metrics ownership, scrape policy, and cardinality bounds |

## Project Documents

- [PRD](../PRD_Hopline.md)
- [Architecture](../ARCHITECTURE.md)
- [Roadmap](../ROADMAP.md)
- [Progress](../PROGRESS.md)
- [Changelog](../CHANGELOG.md)
- [Contributing](../CONTRIBUTING.md)
- [Security](../SECURITY.md)