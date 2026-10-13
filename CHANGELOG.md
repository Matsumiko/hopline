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

### Not Implemented Yet

- Runtime gateway.
- Parser subscription.
- Storage SQLite.
- Adapter dan subprocess sing-box.
- Health checker, scorer, picker, Control API, dan CLI.
