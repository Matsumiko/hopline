# Hopline Progress

## Status Baseline

- **Status:** `in progress`
- **Fase aktif:** Fase 1 — Vertical slice MVP
- **Baseline:** package runtime Hopline, generation lifecycle, gateway CONNECT, health-aware picker/failover pre-byte, active probe scheduler, HTTP-over-CONNECT probe mode, per-node active connection limit, load/acceptance harness, optional localhost Prometheus metrics, Linux installation runbook, hardened systemd unit, multi-protocol/structured parser, config generator, HTTP fetcher, bounded Syncer snapshot, SQLite registry dengan hysteresis, scheduler, CLI, persistent config, health registry, localhost control API, serta daemon wiring engine/gateway tersedia; staging runtime lulus dengan subscription nyata dan sing-box system-wide.
- **Last verified:** 51 test F1, subscription nyata ter-fetch dan ter-parse menjadi 300 node (75 per protocol), parser/generator mempertahankan WS/TLS, VLESS `packet_encoding`/`flow`, VMess `alter_id`, Reality/uTLS/ALPN metadata, gRPC `service_name`, `h2` mapping, dan WebSocket early-data; generated parity config lulus `sing-box check`, daemon systemd tetap active dengan 901 registry nodes; smoke egress VLESS masih timeout dan VMess masih `SSL_ERROR_SYSCALL`.

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

- Menentukan apakah parameter VLESS/VMess export juga perlu penyesuaian transport/runtime tambahan.

## Berikutnya

1. Uji VLESS/VMess export dengan trace sing-box dan bandingkan dengan runtime Nekobox.
2. Jalankan sampel egress berulang pada SS plugin yang berhasil.
3. Tetapkan production provider probe target dan retention metrics.

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
python3 -W error::ResourceWarning -m unittest discover -s tests -v
Ran 43 tests — OK
```

Health/control integration mencakup passive success/failure transitions, active probe seam, SQLite health persistence, localhost-only `/status` dan `/nodes`, CLI `status`/`nodes`, dan response redaction.

Picker/failover integration mencakup skip `dead`/`quarantine`, feedback passive dari CONNECT, retry kandidat berikutnya saat upstream gagal sebelum `200`, dan larangan retry setelah relay dimulai.

Active probe integration mencakup `[health]` target/interval/timeout/mode/proxy configuration, target validation tanpa credential, per-node timeout/error persistence, scheduler cancellation, HTTP-over-CONNECT response validation, dan daemon lifecycle wiring.

Connection/load integration mencakup per-node active admission, release setelah relay berakhir, `503` saat limit penuh, 16-concurrent/4-limit harness, serta local origin relay acceptance melalui upstream proxy.

Deployment integration mencakup private config/state paths, `/opt/hopline/app` PYTHONPATH, systemd hardening, rollback instructions, and `systemd-analyze verify`.

Load smoke: `concurrency=16`, `limit=4`, `admitted=4`, `rejected=12`.

HTTPS proxy acceptance: CONNECT gateway → upstream proxy → local origin, payload `pong` kembali end-to-end.

Gate F1: **in progress**. Fix `v2ray-plugin` sudah membuat direct export Shadowsocks Nekobox berhasil melalui Hopline dan menghasilkan egress IPv6 `2a01:4f8:c010:6c95::1`. Direct export VLESS/VMess masih timeout; production go/no-go belum lulus.

Parity NekoBox terbaru: source NekoBox `TrojanVLESSBean.cpp`, `VMessBean.cpp`, dan `Bean2CoreObj_box.cpp` menjadi acuan untuk Reality/uTLS, ALPN, gRPC `service_name`, `h2→http`, flow normalization, dan WS early-data. Hopline mengadopsi field upstream-compatible; fork-only xhttp/TLS fragment tidak diaktifkan.
Smoke terbaru dengan source Hopline: subscription 300 node / invalid 0; generated VLESS dan VMess config masing-masing `sing-box check=0`; VLESS relay timeout dan VMess relay `SSL_ERROR_SYSCALL` tetap terjadi pada sampel provider yang sama.
- Seluruh file yang dirujuk PRD dan README tersedia.
- Link ke indeks ADR dan ADR-001 tersedia.
- Placeholder diagram arsitektur di PRD diganti dengan diagram Mermaid yang memuat gateway, picker, sing-box, syncer, checker, scorer, dan SQLite.

Deployment VPS authorized: Debian 12, systemd, `/usr/local/bin/sing-box` 1.14.3, private `/etc/hopline/hopline.toml`, and four `static_nodes` from `.env`; service active with localhost gateway/control/metrics listeners. Remote smoke loaded four nodes. Shadowsocks returned egress IP `139.162.133.162`; VLESS, VMess, and Trojan returned HTTP 000/SSL relay failures on this VPS and remain unproven.

DNS audit: generation config now declares `dns-local` as the default resolver and explicitly assigns it to relay/node outbounds. NekoBox's `dns-remote=8.8.8.8` detoured through one `proxy` outbound was not copied globally: Hopline selects among multiple outbounds, so that design would be node-incorrect and potentially recursive. Target CONNECT hostnames are left to the selected protocol outbound rather than resolved by Hopline Python.
- Implemented DNS split in generated config: relay/node domains use `dns-direct`; `dns-remote` uses `8.8.8.8` through `proxy-auto`; mixed inbound applies `sniff` and `hijack-dns`; node outbounds bootstrap through `dns-direct`.
- Targeted parser/config tests passed (9 tests), `tools/smoke_config.py` passed, and ephemeral egress smoke returned HTTP 200 for VLESS, VMess, Trojan, and Shadowsocks. Production service was not changed or restarted.
- Refined target DNS routing to one `dns-remote-<node-id>` per node, with DNS rules matched by `auth_user` and direct detour to that node outbound. Inbound usernames/passwords and CONNECT `auth_user` rules remain intact.
- Per-node DNS regression tests, multi-node `sing-box check`, and ephemeral egress smoke passed for VLESS, VMess, Trojan, and Shadowsocks. Production service was not restarted.
- `tools/smoke_ephemeral.py --fixture-dir . --timeout 20` passed: VLESS, VMess, Trojan, and Shadowsocks each returned authenticated HTTP 200 and missing-credential HTTP 407. DNS bootstrap checks passed and output reported `production_service_touched: false`.
- The smoke runner starts only ephemeral sing-box and Hopline Gateway listeners; production service was not restarted or reconfigured.
- Production deployment of commit `7b02aef` completed on the authorized Debian 12 VPS after artifact checksum verification, generated four-node `sing-box check`, and rollback backup creation. `hopline.service` restarted successfully and remained active with localhost listeners on ports 18770–18773.
- Production gateway smoke passed: VLESS, VMess, Trojan, and Shadowsocks each returned HTTP 200 through `127.0.0.1:18770`; missing `Proxy-Authorization` returned HTTP 407. Control status reported 4 nodes healthy and metrics returned HTTP 200. Rollback tree remains available.
Local Gateway auth: `[auth]` username/password sekarang wajib, client memakai credential lokal, dan Gateway tidak lagi menerima password node sebagai autentikasi client. Wrong/missing credentials menghasilkan 407; local auth diteruskan sebagai credential terpisah dari credential node.
Verification: 51 regression tests tanpa daemon control-port collision lulus; `PYTHONPATH=. python3 tools/smoke_ephemeral.py --fixture-dir . --timeout 20` lulus untuk VLESS, VMess, Trojan, dan Shadowsocks dengan authenticated HTTP 200 serta wrong/missing local credential HTTP 407. Production service tidak disentuh.
Daemon tests yang menjalankan control listener tidak dapat dijalankan pada workspace ini karena `127.0.0.1:18772` sedang dipakai service production; ini environment collision, bukan failure assertion auth.
Production auth rollout (VPS target dari `.env`, Debian 12): commit `70c6cb7` staged ke `/opt/hopline/app`, config backup dibuat dengan mode `0600`, `[auth]` diterapkan atomik, dan `hopline.service` restart tetap active. Rollback app tree dan config backup dipertahankan.
NekoBox test-mode research: source review mapped URL test, full, download, upload, country, and simple-download. Hopline keeps only bounded HTTP/URL probing in periodic active health; speed and country modes remain on-demand diagnostics. See `docs/research/nekobox-testing-modes.md` and ADR-004.
Fase 2 implementation: health persistence now stores cooldown/probe deadlines and consecutive counters. Passive failure applies 30-second cooldown; three consecutive failures eject to `dead`; active probes use bounded backoff and three-success hysteresis. Picker excludes unavailable nodes, valid empty pool returns fast 503, and streaming relay remains incremental.
Fase 2 offline verification: 21 focused health/failover/generation tests passed, including pre-forward failover, forced-node no-fallback, empty-pool 503, cooldown/backoff recovery, active-stream preservation, no-retry after upstream 200, and incremental streaming. Full discovery suite ran 63 tests: 61 passed; 2 daemon tests were blocked by the active production control port `127.0.0.1:18772`. See ADR-005.
Fase 3 geolocation diagnostic: resolver provider berbasis IP dengan fallback `checkip.com` → `ip.cc` → `cekipsaya.com?action=lookup&target=...`, normalisasi country/ASN, IP mismatch rejection, freshness helper, SQLite persistence terpisah dari health, dan metadata read-only pada `/nodes`. Unit tests offline lulus; resolver belum dijalankan melalui outbound node dan grammar `country-*` belum diaktifkan.
Fase 3 sticky slice: process-local `sticky-<sessionId>` binding with idle TTL default 10 minutes, bind/renew only after upstream CONNECT 200, pre-forward rebind when bound node is unavailable, and preserved `rotate`/forced-node semantics. Sticky, rotate, generation, and incremental-stream tests passed locally. Local harness load and HTTPS acceptance passed. Ephemeral protocol smoke passed for VLESS, VMess, Trojan, and Shadowsocks with the refreshed VMess WS/TLS fixture.
Validasi sesi geolocation: 22 targeted tests lulus; 72 offline non-daemon tests lulus; smoke schema upgrade dari v1 ke v2, parser/config, dan persistence lulus. Validasi awal sempat terblokir dua daemon test oleh control production `127.0.0.1:18772`; setelah `control_port = 0` diterapkan pada fixture test, semua lima daemon tests lulus tanpa menghentikan service production.
## Blocker / Risiko Aktif

| VLESS production sample masih timeout | open | Local ephemeral VLESS smoke lulus; sample node/provider production sebelumnya masih timeout | Bandingkan parameter node dan endpoint yang sama dari NekoBox dan Hopline, lalu ambil trace handshake sing-box |
| Egress production belum stabil per protocol | open | Local ephemeral VLESS, VMess, Trojan, dan Shadowsocks lulus; bukti production terpisah tetap perlu jika deployment dilakukan | Validasi nanti setelah local feature set dan acceptance selesai |
| Country lookup melalui outbound node belum terintegrasi | open | Resolver dan persistence tersedia, tetapi adapter belum dipanggil melalui tunnel per-node | Tambahkan diagnostic CONNECT/self-IP melalui credential node; setelah itu baru aktifkan filter `country-*` |
| Provider geolocation gratis memiliki rate limit dan perubahan response | open | Fallback chain dan parser response sudah ada; policy refresh/retention runtime belum ditetapkan | Tetapkan scheduler/on-demand policy dan cache freshness sebelum production |
| Metrics retention dan scrape owner belum ditetapkan | deferred | Endpoint tersedia tetapi policy operasi belum final | Tetapkan Prometheus scrape/retention sebelum production |


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
