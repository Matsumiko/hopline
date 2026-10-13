# Hopline Progress

## Status Baseline

- **Status:** `in progress`
- **Fase aktif:** Fase 0 — Feasibility sing-box
- **Baseline:** dokumentasi dan PRD awal tersedia; implementasi runtime belum dimulai.
- **Last verified:** struktur repository hanya berisi `PRD_Hopline.md` sebelum penambahan dokumentasi baseline.

## Selesai

- PRD awal dibaca dan dirapikan menjadi roadmap vertical slice.
- Fase 0–4 memiliki output dan gate eksplisit.
- Keputusan awal tentang HTTP CONNECT, retry boundary, modular monolith, dan reload health dicatat di PRD.
- Dokumen operasional awal dibuat: README, architecture, roadmap, contribution, security, changelog, ADR index, dan agent guidance.

## Sedang Dikerjakan

- Menyiapkan eksperimen Fase 0 untuk memverifikasi routing sing-box berdasarkan `auth_user`.

## Berikutnya

1. Tentukan versi binary sing-box yang akan diuji.
2. Siapkan config eksperimen dengan dua outbound sintetis atau node uji yang sah.
3. Verifikasi dua username menghasilkan dua jalur outbound.
4. Verifikasi HTTP CONNECT dan lifecycle reload.
5. Catat command, config yang sudah diretifikasi tanpa secret, output, dan hasil gate F0.

## Bukti

Belum ada smoke run atau test runtime. Semua acceptance runtime masih `planned`.

## Validasi Dokumentasi Baseline

- Seluruh file yang dirujuk PRD dan README tersedia.
- Link ke indeks ADR dan ADR-001 tersedia.
- Placeholder diagram arsitektur di PRD diganti dengan diagram Mermaid yang memuat gateway, picker, sing-box, syncer, checker, scorer, dan SQLite.
- Tidak ada smoke run runtime; Gate F0 tetap `planned`.

## Blocker / Risiko Aktif

| Item | Status | Dampak | Cara membuka |
|---|---|---|---|
| Dukungan dan perilaku `auth_user` pada versi sing-box belum diverifikasi | open | Fase 1 tidak boleh dimulai sebelum routing terbukti | Jalankan eksperimen F0 |
| Batas koneksi aktif per node belum ditetapkan | deferred | Parameter operasi belum final | Load test F4 |
| Target provider probe belum dipilih | deferred | Active probe F2 belum memiliki target final | Putuskan sebelum F2 |

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
