# Hopline Progress

## Status Baseline

- **Status:** `in progress`
- **Fase aktif:** Fase 1 — Vertical slice MVP
- **Baseline:** package runtime Hopline, generation lifecycle, gateway CONNECT, multi-protocol parser, config generator, HTTP fetcher, bounded Syncer snapshot, SQLite registry, scheduler, dan CLI tersedia; health/control plane belum tersedia.
- **Last verified:** test suite F1, live subscription sync 100 node, config check, dan CLI contract lulus tanpa credential live.

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

- Melanjutkan Fase 1 dengan parser Clash/sing-box, removed hysteresis, dan scheduler production lifecycle.

## Berikutnya

1. Tambahkan parser fixture untuk Clash/sing-box JSON tanpa credential live.
2. Tambahkan removed hysteresis setelah tiga sync berturut-turut.
3. Tambahkan konfigurasi scheduler persisten dan systemd packaging.
4. Tambahkan CLI `hopline nodes` dan `hopline status` setelah control API tersedia.
5. Uji Gate F1 end-to-end melalui `HTTPS_PROXY`.

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
Ran 23 tests — OK
```

Sync integration mencakup base64/share-link snapshot, VLESS/Trojan/VMess/Shadowsocks, invalid-entry isolation, valid registry fallback, ETag/Last-Modified metadata, HTTP 304 no-op, fetch failure fallback, redacted headers, scheduler sync, CLI contract, dan generation apply.

Live subscription smoke dilakukan ephemeral dengan URL yang diberikan: `parsed=100`, `invalid=0`, protokol `ss/trojan/vless/vmess`, body tidak dicetak dan tidak disimpan ke repository.

Generated config untuk 100 node subscription lulus `sing-box check`.

CLI smoke lulus: help semua command, `doctor --json`, `sync --json` live, missing URL error pada stderr, dan live doctor dengan 100 node.

Smoke config: `python3 -m tools.smoke_config` menghasilkan `config-generator=passed sing-box-check=passed secret=fixture-only`.

Gate F1: **in progress**. Runtime, HTTP fetch, snapshot, scheduler dasar, dan CLI lulus; Clash/sing-box JSON, removed hysteresis, scheduler production lifecycle, health/control plane, dan acceptance melalui `HTTPS_PROXY` belum selesai.

## Validasi Dokumentasi Baseline

- Seluruh file yang dirujuk PRD dan README tersedia.
- Link ke indeks ADR dan ADR-001 tersedia.
- Placeholder diagram arsitektur di PRD diganti dengan diagram Mermaid yang memuat gateway, picker, sing-box, syncer, checker, scorer, dan SQLite.
- Validasi dokumentasi selesai sebelum eksperimen F0.

## Blocker / Risiko Aktif

| Item | Status | Dampak | Cara membuka |
|---|---|---|---|
| Reload SIGHUP sing-box 1.14.3 menutup stream aktif | mitigated | In-place reload melanggar invariant active stream | Gunakan generation subprocess/listener berbeda; jangan SIGHUP saat stream aktif |
| Scheduler production lifecycle belum tersedia | open | F1 belum berjalan terus-menerus dari konfigurasi/service manager | Tambahkan konfigurasi persisten dan systemd packaging |
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
