# Hopline Roadmap

Roadmap ini mengatur urutan pembangunan. Status aktual dan bukti berada di [PROGRESS.md](PROGRESS.md), bukan di dokumen ini.

## Fase 0 — Feasibility sing-box

**Tujuan:** membuktikan routing `auth_user`, CONNECT, lifecycle, dan batas dependency sing-box.

**Output:** eksperimen minimal dengan dua outbound dan dua user.

**Gate:**

- routing user A/B benar;
- CONNECT berhasil;
- versi binary dan config eksperimen tercatat;
- stream aktif tidak rusak saat reload sesuai perilaku yang dipilih;
- secret tidak bocor.

## Fase 1 — Vertical slice MVP

**Tujuan:** request nyata melewati node dari subscription sampai gateway.

**Output:** parser, SQLite registry, stable ID, generated config, `TunnelEngine`, gateway CONNECT, `rotate`, `node-<id>`, `hopline test`, `hopline doctor`.

**Gate:**

- IP egress adalah IP node;
- forced node bekerja;
- pool kosong menghasilkan 503 cepat;
- sync tanpa perubahan tidak reload;
- tests offline lulus;
- secret redaction terverifikasi.

## Fase 2 — Health dan failover

**Tujuan:** menghindari node buruk dan menyembunyikan kegagalan sebelum forwarding.

**Output:** active/passive check, state machine, cooldown, hysteresis, retry budget, pre-forward failover, stream handling.

**Gate:**

- node gagal dieject;
- kandidat berikutnya dicoba hanya sebelum byte diteruskan;
- POST yang sudah diteruskan tidak diulang;
- 503 bounded ketika semua node tidak tersedia;
- stream tidak dibuffer.

## Fase 3 — Routing dan control plane

**Tujuan:** routing berbasis sesi/negara/tujuan dan operasi melalui API/CLI.

**Output:** sticky TTL, country filter, per-target health, Control API, status/nodes, Prometheus metrics.

**Gate:** grammar username, sticky rebind, token auth, dan metrik dapat diverifikasi.

## Fase 4 — Operasional

**Tujuan:** service siap dipelihara di VPS.

**Output:** systemd, Dockerfile, restart/crash recovery, migration, load test, installer, quickstart.

**Gate:** recovery, load report, secret scan, dan dokumentasi deployment lengkap.

## Aturan Gate

- Gate yang belum dibuktikan berstatus `planned`.
- Risiko yang diterima harus dicatat di `PROGRESS.md` dengan owner dan kondisi review.
- Fitur fase berikutnya tidak boleh menyamarkan kegagalan gate fase aktif.
