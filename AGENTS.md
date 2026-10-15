# Hopline — Agent Guidance

## Sumber Kebenaran

| Kebutuhan | Dokumen |
|---|---|
| Produk dan acceptance criteria | `PRD_Hopline.md` |
| Status faktual dan pekerjaan berikutnya | `PROGRESS.md` |
| Arsitektur dan invariant | `ARCHITECTURE.md` |
| Urutan milestone dan gate | `ROADMAP.md` |
| Keputusan arsitektur | `docs/adr/README.md` |
| Keamanan dan secret handling | `SECURITY.md` |
| Alur kontribusi | `CONTRIBUTING.md` |

## Aturan Sesi

1. Baca dokumen sumber yang relevan sebelum mengubah kode atau spesifikasi.
2. Jangan mengklaim fitur selesai tanpa test, smoke run, atau output eksperimen yang tercatat.
3. Bedakan `planned`, `in progress`, `blocked`, dan `done` di `PROGRESS.md`.
4. Update `PROGRESS.md` setiap sesi yang mengubah status, keputusan, risiko, atau bukti.
5. Update `CHANGELOG.md` untuk perubahan perilaku, kontrak, konfigurasi, atau artefak publik.
6. Catat perubahan boundary, dependency, lifecycle, atau kontrak sebagai ADR.
7. Jangan menambah retry, validasi, telemetry, atau abstraksi di luar scope tanpa keputusan tertulis.
8. Secret subscription, credential node, token, dan API key tidak boleh masuk log, test fixture publik, metrics, atau commit.
9. Retry traffic hanya boleh terjadi sebelum byte client diteruskan; setelah forwarding tidak ada retry otomatis.
10. Hopline MUST NOT memutus active stream karena sync, health, rotation, config update, generation swap, atau shutdown normal.
11. Gunakan generation baru untuk koneksi baru; drain generation lama sampai koneksi aktif nol. Jangan gunakan in-place SIGHUP sebagai primitive stream-preserving.
12. Gunakan pola dan struktur dokumen yang sudah ada; jangan membuat dokumen kedua untuk informasi yang sama.

## Scope Production yang Wajib

- **Production test dan deployment default hanya dilakukan pada production PC lokal ini**, yaitu service systemd `hopline.service` pada listener `127.0.0.1:18770-18773`.
- Agent **MUST NOT** memakai SSH, remote shell, remote copy, remote deployment, atau host lain untuk test, smoke, restart, atau validasi Hopline.
- Agent **MUST NOT** membaca `.env` untuk mencari target remote atau mencoba akses remote sebagai bagian dari validasi default.
- Host remote hanya boleh disentuh jika user meminta secara eksplisit dalam pesan yang sama dan menyebut target serta operasi yang diminta. Tanpa permintaan eksplisit itu, anggap remote out of scope dan jangan melakukan preflight sekalipun.
- Frasa `production`, `production test`, dan `production smoke` di percakapan ini berarti production PC lokal, bukan host remote.

## Urutan Kerja

1. `PROGRESS.md` → PRD/arsitektur yang relevan → implementasi.
2. Implementasi → test atau smoke run yang membuktikan perilaku.
3. Catat bukti dan status → changelog bila perubahan terlihat pengguna.
4. Jika terblokir, catat penyebab, percobaan yang sudah dilakukan, dan prasyarat yang hilang.

## Batas Fase

Jangan mulai fase berikutnya sebelum gate fase aktif di `ROADMAP.md` lulus atau pengecualian dicatat eksplisit. Fase 0 membuktikan routing sing-box; Fase 1 membuktikan vertical slice proxy end-to-end.
