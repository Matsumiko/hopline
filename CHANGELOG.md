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

### Verified

- sing-box 1.14.3 memvalidasi config mixed inbound, menerima HTTP CONNECT, dan merutekan dua user ke dua outbound HTTP berbeda.
- SIGHUP menerapkan config route baru setelah downtime singkat dan proses tetap hidup.
- Credential fixture tidak muncul pada output sing-box.

### Known Limitation

- SIGHUP menutup stream aktif saat reload. Graceful reload belum tersedia dan tidak boleh diasumsikan oleh TunnelEngine.

### Not Implemented Yet

- Runtime gateway.
- Parser subscription.
- Storage SQLite.
- Adapter dan subprocess sing-box.
- Health checker, scorer, picker, Control API, dan CLI.
