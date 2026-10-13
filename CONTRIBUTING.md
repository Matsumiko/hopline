# Contributing to Hopline

## Sebelum Mengubah Proyek

1. Baca `AGENTS.md`.
2. Baca status terbaru di `PROGRESS.md`.
3. Baca bagian PRD dan arsitektur yang terkait.
4. Pastikan pekerjaan masuk fase aktif di `ROADMAP.md`.

## Alur Perubahan

1. Tentukan outcome yang dapat diverifikasi.
2. Pisahkan perubahan dokumentasi, implementasi, dan verifikasi.
3. Gunakan test offline untuk parser, scorer, picker, grammar, dan storage.
4. Gunakan smoke run untuk jalur runtime yang berubah.
5. Catat hasil aktual di `PROGRESS.md`.
6. Update `CHANGELOG.md` jika perubahan terlihat oleh pengguna atau operator.
7. Buat atau update ADR jika keputusan mengubah boundary, dependency, lifecycle, data ownership, atau kontrak publik.

## Aturan Scope

- Jangan melompati gate fase.
- Jangan menambahkan fitur “sekalian” yang tidak ada di PRD atau keputusan tertulis.
- Jangan membuat kompatibilitas palsu, fallback no-op, placeholder, atau TODO implementasi sebagai hasil akhir.
- Jangan retry request setelah byte client diteruskan.
- Jangan menyimpan secret dalam fixture, log, exception, metrics, screenshot, atau dokumentasi.

## Bukti Penyelesaian

Setiap item `done` harus menunjuk minimal satu bukti:

- test command dan hasilnya;
- smoke run dan output yang diamati;
- eksperimen feasibility dan konfigurasi yang dipakai;
- atau alasan eksplisit jika hanya perubahan dokumentasi.

Klaim yang belum diuji harus ditulis sebagai `planned` atau `inference`, bukan `done`.

## Dokumentasi Perubahan

| Perubahan | Dokumen |
|---|---|
| Status, blocker, bukti, next action | `PROGRESS.md` |
| Perilaku atau kontrak publik berubah | `CHANGELOG.md` |
| Keputusan arsitektur baru | `docs/adr/NNN-*.md` dan index |
| Requirement atau acceptance berubah | `PRD_Hopline.md` |
| Boundary atau alur runtime berubah | `ARCHITECTURE.md` |

## Pull Request / Handoff

Deskripsi perubahan harus memuat:

- masalah dan scope;
- file atau modul yang berubah;
- bukti verifikasi;
- risiko dan pekerjaan tersisa;
- update dokumentasi yang dilakukan.
