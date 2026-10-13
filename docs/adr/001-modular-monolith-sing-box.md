# ADR-001: Modular Monolith Python dengan sing-box sebagai Tunnel Subprocess

- **Status:** accepted untuk baseline Fase 0–1
- **Scope:** deployment awal Hopline pada satu VPS
- **Tanggal:** baseline awal proyek

## Context

Hopline perlu mengoordinasikan gateway, pemilihan node, health state, subscription sync, storage, dan lifecycle tunnel engine. Target pengguna adalah developer atau tim kecil pada satu VPS. Sebagian besar state tersebut perlu konsisten di dalam satu proses, sementara sing-box sudah menyediakan implementasi protokol tunnel yang tidak perlu ditulis ulang.

Hopline dibangun sebagai modular monolith Python 3.11+ berbasis asyncio. sing-box dijalankan sebagai subprocess dan diakses melalui adapter `TunnelEngine` yang memiliki tanggung jawab membuat config generation, start, healthcheck, publish, drain, dan stop.

Perubahan config tidak memakai in-place reload sebagai primitive stream-preserving. Generation sing-box memakai listener localhost terpisah; generation lama tetap hidup sampai koneksi aktifnya selesai. Detail invariant active-stream ada di [ADR-002](002-preserve-active-streams.md).

Modul internal memiliki boundary kode yang jelas, tetapi tidak dipisahkan menjadi service atau network process pada fase awal.

## Alternatives Considered

### Microservices sejak awal

Ditolak untuk baseline karena menambah deployment, koordinasi, dan failure mode tanpa kebutuhan skala yang sudah terbukti.

### Implementasi protokol tunnel di Python

Ditolak karena memperbesar scope dan risiko; sing-box sudah menjadi dependency yang direncanakan.

### Mihomo sebagai engine utama

Tidak dipilih pada baseline karena syncer Hopline sudah perlu mem-parse format subscription sendiri dan PRD menjadikan sing-box dependency awal. Mihomo tetap dapat dipertimbangkan melalui adapter jika bukti kebutuhan muncul.

## Consequences

Positif:

- deployment sederhana;
- state picker/scorer/storage lebih mudah dikoordinasikan;
- pengujian modul dapat dilakukan tanpa network;
- engine tunnel dapat diganti di belakang interface kecil.

Negatif dan risiko:

- crash atau perubahan perilaku sing-box memengaruhi Hopline;
- satu proses membatasi isolasi resource antar modul;
- kemampuan routing `auth_user` harus diverifikasi pada versi binary yang dipilih;
- reload semantics perlu diuji dengan koneksi aktif.

## Confirmation

Keputusan ini dianggap terkonfirmasi untuk implementasi awal jika Gate F0 membuktikan routing `auth_user`, CONNECT, dan lifecycle sing-box. Evidence dicatat di `PROGRESS.md`; hasil F0 yang gagal harus memicu ADR perubahan atau pembatasan scope.
