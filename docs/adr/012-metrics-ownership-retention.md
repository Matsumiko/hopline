# ADR-012: Metrics Ownership dan Retention

- **Status:** accepted untuk observability operasional Fase 3–4
- **Scope:** kepemilikan scrape/retention metrik Prometheus dan batas cardinality. Bukan penambahan storage time-series di dalam Hopline
- **Evidence:** endpoint `GET /metrics` production mengembalikan gauge current-state (`hopline_nodes`, `hopline_health_nodes`, `hopline_active_probe_enabled`) tanpa storage historis

## Context

Hopline mengekspos metrik Prometheus di localhost `18773`, tetapi perannya terhadap retention belum ditetapkan. Hopline tidak mempertahankan time-series sendiri: metrik yang ditampilkan adalah gauge yang dihitung dari SQLite registry saat di-scrape. Tanpa scraper eksternal, tidak ada histori, sehingga observasi drift pool (health, komposisi protocol) hilang.

Label berbasis `node_id` tidak dipakai karena pool production berisi ribuan node; cardinality per-node akan meledakkan TSDB tanpa nilai prediktif untuk alerting pool-level.

## Decision

Hopline hanya meng-ekspor current-state gauge, bukan counter time-series, dan tidak menyimpan retention di dalam dirinya. Storage dan retention dimiliki scraper eksternal (Prometheus). Endpoint tetap bind localhost dan disabled-by-default melalui `[health].metrics_enabled`.

Rekomendasi operasional untuk satu VPS:

```text
scrape interval      15s
retention            --storage.tsdb.retention.time=15d
```

Label dibatasi pada enum stabil: `state` untuk `hopline_health_nodes` dan `protocol` untuk `hopline_protocol_nodes` (ss, trojan, vless, vmess). Tidak ada label berbasis `node_id`, server, country, atau credential.

## Consequences

- Operator harus menyediakan Prometheus untuk mendapatkan histori; Hopline tidak menambah dependency TSDB.
- Drift composition pool terlihat dari time-series `hopline_nodes`, `hopline_health_nodes{state}`, `hopline_protocol_nodes{protocol}`.
- Cardinality rendah dan deterministik, tidak bergantung pada jumlah atau identitas node.
- Metrik tetap non-secret dan tidak membocorkan node, host, port, atau credential.
- Retention ditentukan di sisi Prometheus; perubahan kebijakan tidak mengubah kode Hopline.
- Gauge bukan counter: laju (rate) retry, 503, dan hasil sync belum tersedia; itu bagian observability lanjut, bukan scope retention ini.

## Alternatives rejected

- Embedded TSDB di Hopline: menambah storage, lifecycle, dan migration tanpa kebutuhan terbukti.
- Label per-node (`node_id`): cardinality meledak, tidak berguna untuk alerting pool.
- Metrics always-on: memperluas surface default tanpa kebutuhan; disabled-by-default lebih rendah risiko.
- Menganggap Hopline sebagai owner retention: bertentangan dengan role Hopline sebagai emitter tanpa storage historis.

## Confirmation

- `GET /metrics` production mengembalikan gauge yang diharapkan, termasuk `hopline_protocol_nodes{protocol}`.
- Regression menegaskan label hanya enum state/protocol dan tidak pernah menyertakan credential atau host.
