# Hopline Progress

## Status Baseline

- **Status:** `in progress`
- **Fase aktif:** Fase 1 — Vertical slice MVP
- **Baseline:** package runtime Hopline, generation lifecycle, gateway CONNECT, VLESS parser, config generator, bounded Syncer snapshot, dan SQLite registry tersedia; HTTP subscription fetch/CLI belum tersedia.
- **Last verified:** test suite F1 dan sync→SQLite→generation integration lulus tanpa credential live.

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
- Invariant baru dicatat: Hopline tidak boleh memutus active stream karena sync, health, rotasi, config update, generation swap, atau shutdown normal.
- ADR-002 menetapkan generation ownership: generation baru untuk koneksi baru, generation lama di-drain sampai nol koneksi aktif.
- Harness `experiments/f0/generation_swap.py` lulus tiga kali: stream lama tetap hidup dan koneksi baru memakai generation baru.
- Smoke node VLESS live lulus secara ephemeral: IP VPS `103.247.23.141`, IP egress node `131.186.63.89`, dan runtime log tidak mengandung credential.
- Config live membutuhkan penghapusan field legacy `outbounds[0].encryption` agar diterima sing-box 1.14.3; config asli tidak diubah.

## Sedang Dikerjakan

- Melanjutkan Fase 1 dengan HTTP subscription fetch, SQLite migration policy, dan CLI setelah kontrak snapshot runtime stabil.

## Berikutnya

1. Tambahkan HTTP fetch dengan timeout, ETag/If-Modified-Since, dan last-valid body.
2. Tambahkan parser fixture untuk Clash/sing-box JSON tanpa credential live.
3. Tambahkan removed hysteresis setelah tiga sync berturut-turut.
4. Tambahkan CLI `hopline test` dan `hopline doctor`.
5. Uji Gate F1 end-to-end dengan fixture subscription offline dan environment proxy.

## Bukti

Eksperimen berikut dijalankan tiga kali dengan hasil konsisten:

```text
python3 -m py_compile experiments/f0/run.py
timeout 10s python3 experiments/f0/run.py
```

Observed: config check, CONNECT, routing A/B, route baru setelah SIGHUP, proses tetap hidup, dan log secret scan lulus. `active_stream_survived_reload` bernilai `false` pada semua run.

Generation proof dijalankan tiga kali:

```text
python3 -m py_compile experiments/f0/generation_swap.py
timeout 10s python3 experiments/f0/generation_swap.py
```

Observed: `generation_swap=passed active_stream_preserved=passed new_connections_use_new_generation=passed`.

F1 test suite:

```text
python3 -m py_compile hopline/*.py tests/*.py
python3 -W error::ResourceWarning -m unittest discover -s tests -v
Ran 14 tests — OK
```

Sync integration mencakup base64/VLESS snapshot, invalid-entry isolation, dedup lintas source, valid registry fallback, no-op snapshot, dan `Syncer.sync_text_and_apply()` yang mempertahankan generation sama saat parameter node tidak berubah.

Smoke config: `python3 -m tools.smoke_config` menghasilkan `config-generator=passed sing-box-check=passed secret=fixture-only`.

Integration mencakup Gateway → sing-box → target HTTP lokal, upstream Basic Auth, rotate, generation publish, drain, dan active relay setelah listener stop.

Gate F1: **in progress**. Runtime dan snapshot vertical slice lulus; HTTP subscription fetch, Clash/sing-box JSON, SQLite migration policy, CLI, dan acceptance melalui `HTTPS_PROXY` belum selesai.

## Validasi Dokumentasi Baseline

- Seluruh file yang dirujuk PRD dan README tersedia.
- Link ke indeks ADR dan ADR-001 tersedia.
- Placeholder diagram arsitektur di PRD diganti dengan diagram Mermaid yang memuat gateway, picker, sing-box, syncer, checker, scorer, dan SQLite.
- Validasi dokumentasi selesai sebelum eksperimen F0.

## Blocker / Risiko Aktif

| Item | Status | Dampak | Cara membuka |
|---|---|---|---|
| Reload SIGHUP sing-box 1.14.3 menutup stream aktif | mitigated | In-place reload melanggar invariant active stream | Gunakan generation subprocess/listener berbeda; jangan SIGHUP saat stream aktif |
| HTTP subscription fetch belum tersedia | open | F1 belum mengambil URL subscription | Implementasikan timeout, cache body valid, dan conditional request |
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
