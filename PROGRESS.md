# Hopline Progress

## Status Baseline

- **Status:** `in progress`
- **Fase aktif:** Fase 1 — Vertical slice MVP
- **Baseline:** package runtime Hopline, generation lifecycle, gateway CONNECT, health-aware picker/failover pre-byte, active probe scheduler, HTTP-over-CONNECT probe mode, per-node active connection limit, load/acceptance harness, optional localhost Prometheus metrics, Linux installation runbook, hardened systemd unit, multi-protocol/structured parser, config generator, HTTP fetcher, bounded Syncer snapshot, SQLite registry dengan hysteresis, scheduler, CLI, persistent config, health registry, localhost control API, serta daemon wiring engine/gateway tersedia; staging runtime lulus dengan sing-box system-wide.
- **Last verified:** 45 test F1, live subscription sync 100 node, config check, CLI contract, daemon once dengan engine/gateway aktif, systemd verify, deployment hardening smoke, staging systemd start/control/metrics/state-path checks, sing-box doctor, listener check, dan CONNECT handshake lulus tanpa credential live.

## Selesai

- PRD awal dibaca dan dirapikan menjadi roadmap vertical slice.
- Fase 0–4 memiliki output dan gate eksplisit.
- Keputusan awal tentang HTTP CONNECT, retry boundary, modular monolith, dan reload health dicatat di PRD.
- Dokumen operasional awal dibuat: README, architecture, roadmap, contribution, security, changelog, ADR index, dan agent guidance.
- Harness lokal F0 dibuat di `experiments/f0/run.py`; harness memakai dua fake HTTP CONNECT proxy dan origin lokal tanpa subscription/node nyata.
- F0 routing dan CONNECT berhasil pada sing-box 1.14.3: `user-a → proxy-a`, `user-b → proxy-b`.
- F0 reload berhasil menerapkan route baru setelah retry/downtime singkat; proses tetap hidup.
- F0 redaction scan berhasil; `pass-a` dan `pass-b` tidak muncul di output sing-box.
- F0 menemukan reload SIGHUP menutup stream aktif. Reload belum graceful untuk koneksi berjalan dan harus diperlakukan sebagai maintenance event.
- Invariant baru dicatat: Hopline tidak boleh memutus active stream karena sync, health, rotasi, config update, generation swap, atau shutdown normal.
- ADR-002 menetapkan generation ownership: generation baru untuk koneksi baru, generation lama di-drain sampai nol koneksi aktif.
- Harness `experiments/f0/generation_swap.py` lulus tiga kali: stream lama tetap hidup dan koneksi baru memakai generation baru.
- Smoke node VLESS live lulus secara ephemeral: IP VPS `103.247.23.141`, IP egress node `131.186.63.89`, dan runtime log tidak mengandung credential.
- Config live membutuhkan penghapusan field legacy `outbounds[0].encryption` agar diterima sing-box 1.14.3; config asli tidak diubah.

- Menjalankan acceptance egress melalui node subscription nyata atau fixture outbound yang valid.

## Berikutnya

1. Jalankan proxy egress smoke dengan node subscription yang dapat dijangkau.
2. Tetapkan production provider probe target dan retention metrics.

## Bukti

Eksperimen berikut dijalankan tiga kali dengan hasil konsisten:

```text
python3 -m py_compile experiments/f0/run.py
timeout 10s python3 experiments/f0/run.py
```

Observed: config check, CONNECT, routing A/B, route baru setelah SIGHUP, proses tetap hidup, dan log secret scan lulus. `active_stream_survived_reload` bernilai `false` pada semua run.

Generation proof dijalankan tiga kali:

```text
python3 -m py_compile experiments/f0/generation_swap.py
timeout 10s python3 experiments/f0/generation_swap.py
```

Observed: `generation_swap=passed active_stream_preserved=passed new_connections_use_new_generation=passed`.

F1 test suite:
```text
python3 -W error::ResourceWarning -m unittest discover -s tests -v
Ran 43 tests — OK
```

Health/control integration mencakup passive success/failure transitions, active probe seam, SQLite health persistence, localhost-only `/status` dan `/nodes`, CLI `status`/`nodes`, dan response redaction.

Picker/failover integration mencakup skip `dead`/`quarantine`, feedback passive dari CONNECT, retry kandidat berikutnya saat upstream gagal sebelum `200`, dan larangan retry setelah relay dimulai.

Active probe integration mencakup `[health]` target/interval/timeout/mode/proxy configuration, target validation tanpa credential, per-node timeout/error persistence, scheduler cancellation, HTTP-over-CONNECT response validation, dan daemon lifecycle wiring.

Connection/load integration mencakup per-node active admission, release setelah relay berakhir, `503` saat limit penuh, 16-concurrent/4-limit harness, serta local origin relay acceptance melalui upstream proxy.

Deployment integration mencakup private config/state paths, `/opt/hopline/app` PYTHONPATH, systemd hardening, rollback instructions, and `systemd-analyze verify`.

Load smoke: `concurrency=16`, `limit=4`, `admitted=4`, `rejected=12`.

HTTPS proxy acceptance: CONNECT gateway → upstream proxy → local origin, payload `pong` kembali end-to-end.

Gate F1: **in progress**. Runtime daemon kini menjalankan sync → sing-box generation → gateway; staging systemd, control API, metrics, listeners, dan CONNECT handshake lulus. Egress IP nyata belum diverifikasi karena fixture node staging tidak menyediakan outbound VLESS yang valid.
- Seluruh file yang dirujuk PRD dan README tersedia.
- Link ke indeks ADR dan ADR-001 tersedia.
- Placeholder diagram arsitektur di PRD diganti dengan diagram Mermaid yang memuat gateway, picker, sing-box, syncer, checker, scorer, dan SQLite.
- Validasi dokumentasi selesai sebelum eksperimen F0.

## Blocker / Risiko Aktif

| Egress IP nyata belum diverifikasi | open | CONNECT handshake ke generation lulus, tetapi fixture VLESS staging bukan node yang dapat dijangkau | Gunakan subscription/node uji valid lalu cek target IP melalui proxy |
| Real production-host installation belum dijalankan | open | Staging host berbeda dari production target | Jalankan runbook pada target production/staging yang disepakati |
| Metrics retention dan scrape owner belum ditetapkan | deferred | Endpoint tersedia tetapi policy operasi belum final | Tetapkan Prometheus scrape/retention sebelum production |


## Keputusan Terbuka

- SOCKS5 tidak masuk scope awal; evaluasi setelah HTTP CONNECT stabil.
- Dashboard web tidak diperlukan untuk baseline; CLI dan Prometheus menjadi default operasi.

## Format Pembaruan

Setiap sesi tambahkan atau ubah bagian berikut secara faktual:

```text
Tanggal/sesi:
Scope:
Perubahan:
Bukti:
Status gate:
Risiko baru:
Next action:
```

Jangan menghapus bukti historis. Koreksi fakta dengan catatan koreksi yang jelas.
