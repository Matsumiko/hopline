# Hopline Progress

## Status Baseline

- **Status:** `in progress`
- **Fase aktif:** Fase 1 — Vertical slice MVP
- **Baseline:** package runtime Hopline, generation lifecycle, gateway CONNECT, multi-protocol/structured parser, config generator, HTTP fetcher, bounded Syncer snapshot, SQLite registry dengan hysteresis, scheduler, CLI, persistent config, dan systemd unit tersedia; health/control plane belum tersedia.
- **Last verified:** 29 test F1, live subscription sync 100 node, config check, CLI contract, daemon once, dan systemd unit verify lulus tanpa credential live.

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

- Melanjutkan Fase 1 dengan health checker passive/active dan control-plane groundwork.

## Berikutnya

1. Tambahkan health checker passive/active setelah node registry stabil.
2. Tambahkan control API dan CLI `nodes`/`status`.
3. Tambahkan load test untuk batas koneksi aktif per node.
4. Uji Gate F1 end-to-end melalui `HTTPS_PROXY`.
5. Siapkan systemd install/runbook setelah review service host.

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
Ran 29 tests — OK
```

Sync integration mencakup base64/share-link, Clash YAML, sing-box JSON, VLESS/Trojan/VMess/Shadowsocks, invalid-entry isolation, valid registry fallback, ETag/Last-Modified metadata, HTTP 304 no-op, fetch failure fallback, redacted headers, removed hysteresis tiga sync, scheduler sync, CLI contract, persistent TOML permission validation, daemon once, dan generation apply.

Live subscription smoke: `parsed=100`, `invalid=0`, protokol `ss/trojan/vless/vmess`; body tidak dicetak dan tidak disimpan ke repository.

Generated config 100 node lulus `sing-box check`.

CLI/daemon smoke lulus: help command, `doctor --json`, `sync --json` live, `run --once` live menghasilkan 100 node, missing URL error pada stderr, dan `systemd-analyze verify` menerima unit.

Gate F1: **in progress**. Runtime, fetch, snapshot, structured parser, hysteresis, scheduler, CLI, persistent config, dan systemd unit lulus; health/control plane, acceptance melalui `HTTPS_PROXY`, dan host installation runbook belum selesai.

## Validasi Dokumentasi Baseline

- Seluruh file yang dirujuk PRD dan README tersedia.
- Link ke indeks ADR dan ADR-001 tersedia.
- Placeholder diagram arsitektur di PRD diganti dengan diagram Mermaid yang memuat gateway, picker, sing-box, syncer, checker, scorer, dan SQLite.
- Validasi dokumentasi selesai sebelum eksperimen F0.

## Blocker / Risiko Aktif

| Item | Status | Dampak | Cara membuka |
|---|---|---|---|
| Reload SIGHUP sing-box 1.14.3 menutup stream aktif | mitigated | In-place reload melanggar invariant active stream | Gunakan generation subprocess/listener berbeda; jangan SIGHUP saat stream aktif |
| Health/control plane belum tersedia | open | F1 belum memilih node berdasarkan health atau menyediakan status API | Implementasikan checker dan control API |
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
