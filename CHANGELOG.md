# Changelog

Format mengikuti prinsip Keep a Changelog. Dokumen ini hanya mencatat perubahan yang sudah terjadi, bukan rencana.

## [Unreleased]

### Added

- Baseline dokumentasi proyek: `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `PROGRESS.md`, `CONTRIBUTING.md`, `SECURITY.md`, dan `AGENTS.md`.
- Indeks keputusan arsitektur di `docs/adr/`.

### Changed

- `PRD_Hopline.md` diperbarui dengan urutan vertical slice Fase 0–4, gate verifikasi, keputusan awal, dan protokol pencatatan pembangunan.

### Added

- Eksperimen feasibility lokal Fase 0 di `experiments/f0/run.py` untuk routing `auth_user` tanpa node atau subscription nyata.
- ADR-002 dan kontrak generation ownership untuk menjaga active stream.
- Harness `experiments/f0/generation_swap.py` untuk membuktikan stream lama tetap hidup saat generation baru menerima koneksi baru.

### Verified

- sing-box 1.14.3 memvalidasi config mixed inbound, menerima HTTP CONNECT, dan merutekan dua user ke dua outbound HTTP berbeda.
- SIGHUP menerapkan config route baru setelah downtime singkat dan proses tetap hidup.
- Credential fixture tidak muncul pada output sing-box.
- Generation swap harness lulus tiga kali.
- Smoke node VLESS live lulus secara ephemeral; IP egress berbeda dari IP VPS dan credential tidak masuk repository atau runtime log.

### Known Limitation

- SIGHUP menutup stream aktif saat reload. Graceful reload belum tersedia dan tidak boleh diasumsikan oleh TunnelEngine.
- Config live yang diberikan memiliki field `outbounds[0].encryption` yang ditolak sing-box 1.14.3; validasi sementara menghapus field legacy itu pada temporary config saja.

### Added

- Package runtime `hopline/` dengan model Node, parser VLESS, config generator sing-box, GenerationManager, SingBoxEngine, dan HTTP CONNECT Gateway.
- Mode `rotate`, node-specific routing, upstream Basic Auth, generation publish, drain, dan listener stop tanpa memutus relay aktif.
- Test suite offline dan integration smoke Gateway → sing-box → target lokal.
- `tools/smoke_config.py` untuk memvalidasi generated config melalui `sing-box check`.

### Verified

- Delapan test F1 lulus tanpa `ResourceWarning`.
- Generated config fixture lulus `sing-box check`.

### Added

- `SQLiteRegistry` untuk metadata schema, subscription source, deduplicated nodes, dan node-source ownership.
- `Syncer` untuk bounded VLESS snapshot text/base64, invalid-entry isolation, stable snapshot detection, dan fallback ke node registry valid terakhir.
- `SingBoxEngine.apply_nodes()` dan `Syncer.sync_text_and_apply()` untuk generation publish hanya saat parameter node berubah.

### Verified

- Empat belas test F1 lulus tanpa `ResourceWarning`, termasuk sync snapshot → SQLite → sing-box generation dan no-op sync tanpa generation reload.

### Added

- `SubscriptionFetcher` dengan timeout, batas body, User-Agent, ETag, dan `If-Modified-Since`.
- Registry menyimpan body valid terakhir dan metadata validator.
- Parser snapshot untuk VLESS, Trojan, VMess, dan Shadowsocks.
- Fallback ke registry valid terakhir saat fetch gagal; HTTP 304 menjadi no-op.
- Generator sing-box memetakan outbound Shadowsocks ke tipe `shadowsocks`.

### Verified

- URL subscription pengguna diambil secara ephemeral: 100 node, 0 invalid, empat protokol.
- Generated config 100 node lulus `sing-box check`.
- Sembilan belas test lulus tanpa `ResourceWarning`; credential tidak dicetak, disimpan di fixture publik, atau masuk commit.

### Added

- `SubscriptionScheduler` dengan interval, jitter, cancellation, dan optional generation apply.
- CLI `python3 -m hopline sync`, `test`, dan `doctor` dengan output `--json`, exit code, dan error pada stderr.

### Verified

- Dua puluh tiga test lulus tanpa `ResourceWarning`.
- CLI help, JSON doctor, missing URL error, live sync 100 node, dan live doctor sudah dijalankan.

### Not Implemented Yet

- Health checker, scorer, picker, dan Control API.
- Scheduler production lifecycle dan systemd packaging.

### Added

- Private TOML config loader dengan validasi permission `0600`.
- CLI `run` untuk one-shot sync atau scheduler daemon dengan SIGTERM/SIGINT shutdown.
- Hardened `packaging/hopline.service` dengan user terpisah dan filesystem/network restrictions.

### Verified

- Dua puluh sembilan test lulus tanpa `ResourceWarning`.
- `run --once` live sync menghasilkan 100 node; `systemd-analyze verify` menerima unit service.

### Added

- Structured subscription parser untuk Clash YAML dan sing-box JSON.
- Removed hysteresis per subscription source: node baru dihapus setelah tiga snapshot berturut-turut tidak memuat node tersebut.

### Verified

- Dua puluh enam test lulus tanpa `ResourceWarning`.
- Fixture Clash YAML dan sing-box JSON berhasil diparse; node invalid diabaikan.
- Hysteresis mempertahankan node pada sync pertama/kedua dan menghapusnya setelah sync ketiga.

### Added

- Health registry dengan state `healthy`, `degraded`, `dead`, dan `quarantine`.
- Passive success/failure feedback dan injected active probe seam.
- Localhost-only control API `GET /status` dan `GET /nodes`.
- CLI read-only `status` dan `nodes`.

### Verified

- Tiga puluh dua test lulus tanpa `ResourceWarning`.
- Control API smoke menghasilkan status JSON tanpa credential node.

### Changed

- Gateway sekarang melewati node `dead`/`quarantine`, mencatat feedback passive, dan mencoba kandidat berikutnya sebelum mengirim `200 Connection Established`.
- Retry tetap dibatasi pada fase pre-byte; relay aktif tidak diulang otomatis.

### Verified

- 34 test lulus tanpa `ResourceWarning`.

### Added

- Konfigurasi `[health]` untuk target, interval, dan timeout active probe.
- `ActiveProbeScheduler` dengan timeout per node, cancellation, dan persistence ke SQLite health registry.
- Daemon `run` menjalankan probe berkala atau sekali pada mode `--once` jika target dikonfigurasi.

### Verified

- 37 test lulus tanpa `ResourceWarning`.
- Probe success, failure, timeout seam, dan graceful cancellation teruji.
- Regression smoke membuktikan node pertama ditolak, node kedua berhasil, dan client hanya menerima satu respons `200`.
