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
- Harness lokal F0 dibuat di `experiments/f0/run.py`; harness memakai dua fake HTTP CONNECT proxy dan origin lokal tanpa subscription/node nyata.
- F0 routing dan CONNECT berhasil pada sing-box 1.14.3: `user-a → proxy-a`, `user-b → proxy-b`.
- F0 reload berhasil menerapkan route baru setelah retry/downtime singkat; proses tetap hidup.
- F0 redaction scan berhasil; `pass-a` dan `pass-b` tidak muncul di output sing-box.
- F0 menemukan reload SIGHUP menutup stream aktif. Reload belum graceful untuk koneksi berjalan dan harus diperlakukan sebagai maintenance event.

## Sedang Dikerjakan

- Menentukan strategi TunnelEngine dan gateway agar reload config tidak dijanjikan graceful untuk stream aktif.
- Menjalankan Fase 1 hanya setelah keputusan reload dan gate F0 dicatat.

## Berikutnya

1. Tetapkan strategi reload/drain berdasarkan temuan F0.
2. Tambahkan eksperimen atau implementasi TunnelEngine yang tidak reload saat health berubah.
3. Mulai Fase 1 vertical slice setelah batas reload terdokumentasi.

## Bukti

Eksperimen berikut dijalankan tiga kali dengan hasil konsisten:

```text
python3 -m py_compile experiments/f0/run.py
timeout 10s python3 experiments/f0/run.py
```

Observed: config check, CONNECT, routing A/B, route baru setelah reload, proses tetap hidup, dan log secret scan lulus. `active_stream_survived_reload` bernilai `false` pada semua run.

Gate F0: **partial pass**. Routing, CONNECT, reload route application, dan redaction pass. Graceful active-stream preservation gagal dan menjadi batas operasional eksplisit.

## Validasi Dokumentasi Baseline

- Seluruh file yang dirujuk PRD dan README tersedia.
- Link ke indeks ADR dan ADR-001 tersedia.
- Placeholder diagram arsitektur di PRD diganti dengan diagram Mermaid yang memuat gateway, picker, sing-box, syncer, checker, scorer, dan SQLite.
- Validasi dokumentasi selesai sebelum eksperimen F0.

## Blocker / Risiko Aktif

| Item | Status | Dampak | Cara membuka |
|---|---|---|---|
| Reload SIGHUP sing-box 1.14.3 menutup stream aktif | open | Reload node dapat mengganggu koneksi berjalan | Jangan reload karena health; uji strategi drain/restart pada F1 |
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
