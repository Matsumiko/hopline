# Hopline

Hopline adalah gateway proxy lokal yang memilih node sehat dari subscription VMess, VLESS, Trojan, atau Shadowsocks, lalu meneruskan koneksi HTTP/HTTPS melalui sing-box.

Hopline ditujukan untuk developer atau tim kecil yang menjalankan script/bot di VPS dan membutuhkan satu endpoint proxy lokal tanpa mengubah routing jaringan VPS.

> **Status:** Fase 1 sedang berjalan. Runtime vertical slice dan snapshot Syncer lokal tersedia; HTTP fetch berkala, CLI, health scoring, dan failover belum selesai.

## Dokumen Utama

- [PRD](PRD_Hopline.md) — tujuan, scope, requirement, dan acceptance criteria.
- [Architecture](ARCHITECTURE.md) — boundary modul, alur runtime, dan invariant.
- [Roadmap](ROADMAP.md) — fase, gate, dan urutan pengerjaan.
- [Progress](PROGRESS.md) — status faktual, bukti, risiko, dan next action.
- [Changelog](CHANGELOG.md) — perubahan yang sudah terjadi.
- [Contributing](CONTRIBUTING.md) — aturan kontribusi dan verifikasi.
- [Security](SECURITY.md) — aturan secret, privasi, dan pelaporan masalah.
- [ADR index](docs/adr/README.md) — keputusan arsitektur yang memiliki konsekuensi jangka panjang.

## Interface Target

```bash
export HTTPS_PROXY=http://rotate:x@127.0.0.1:18770
curl https://api.ipify.org
```

Interface utama adalah HTTP proxy dengan dukungan `CONNECT`. `rotate` memilih node per koneksi proxy, bukan otomatis per HTTP request jika client memakai connection pooling.

## Arsitektur Singkat

```text
Client → Hopline Gateway :18770 → sing-box generation → selected node → target
                                  ├── generation lama: drain koneksi aktif
                                  └── generation baru: koneksi baru
```

Hopline mengelola pemilihan, health, failover sebelum byte client diteruskan, sinkronisasi subscription, dan lifecycle sing-box. Config update memakai generation baru; stream aktif tidak diputus oleh lifecycle Hopline. Hopline tidak melakukan MITM dan tidak mengulang traffic setelah forwarding dimulai.

## Status Saat Ini

Package runtime tersedia di `hopline/`. Parser VLESS, bounded subscription snapshot Syncer, SQLite registry, config generation, generation-aware sing-box engine, HTTP CONNECT gateway, rotate, node routing, drain, dan active-stream preservation sudah diuji offline. Lihat [PROGRESS.md](PROGRESS.md) untuk bukti dan pekerjaan berikutnya.

## Batasan

- Bukan VPN level jaringan.
- Bukan residential proxy atau alat anti-deteksi.
- Tidak memodifikasi isi traffic.
- Pengguna bertanggung jawab memastikan penggunaan node subscription mematuhi ketentuan penyedia.
