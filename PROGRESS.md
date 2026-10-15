# Hopline Progress

## Status Baseline

- **Status:** `in progress`
- **Fase aktif:** Fase 1 — Vertical slice MVP; gate production masih terbuka
- **Baseline:** package runtime Hopline, generation lifecycle, gateway CONNECT, health-aware picker/failover pre-byte, active probe scheduler, HTTP-over-CONNECT probe mode, per-node active connection limit, load/acceptance harness, optional localhost Prometheus metrics, Linux installation runbook, hardened systemd unit, multi-protocol/structured parser, config generator, HTTP fetcher, bounded Syncer snapshot, SQLite registry dengan hysteresis, scheduler, CLI, persistent config, health registry, localhost control API, serta daemon wiring engine/gateway tersedia; staging runtime lulus dengan subscription nyata dan sing-box system-wide.
- **Production validation scope:** seluruh test/deployment/smoke default wajib memakai systemd production PC lokal pada `127.0.0.1:18770-18773`. Host lain tidak termasuk scope dan tidak boleh disentuh tanpa permintaan eksplisit user pada pesan yang sama.
- **Subscription cutover on this PC:** old provider URL was removed from production config and registry. The active config contains four private subscription sources with protocol/country filters. Subscription keys and provider hostnames are not printed or committed.
- Clean cutover cleared the old registry before restart. Production now has 631 nodes: 203 SS, 205 Trojan, 215 VLESS, and 8 VMess. Schema is 2; active HTTP probe is enabled. Health progressed to 145 healthy, 58 degraded, 428 unknown while the 631-node probe queue was still running.
- Actual post-cutover gateway smoke on `18770`: healthy SS, Trojan, and VLESS forced routes returned HTTPS `200`; no VMess node was healthy yet, so no VMess success is claimed. Rotate returned 2/3 successes in the sample. Listeners remained `18770` gateway, `18771` tunnel, `18772` control, and `18773` metrics.
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

1. Ulangi acceptance protocol-specific pada `api.ipify.org` dan `api64.ipify.org`, pisahkan hasil IPv4/IPv6, dan ukur success rate per node.
2. Tetapkan production provider probe target dan retention metrics.

Trace VMess dan forced-route production smoke sudah selesai; tidak ada perubahan parser/generator yang diperlukan dari bukti ini. Acceptance berulang belum cukup stabil untuk menutup Gate F1.

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
- Koreksi validasi VMess production: generated config VMess WS/TLS dan WS tanpa TLS masing-masing lulus `sing-box check=0`; forced-route smoke awal berhasil `2/3` VMess, lalu rerun berhasil `3/3` VMess. Dalam rerun yang sama, VLESS `3/3`, Trojan `3/3`, dan Shadowsocks `3/3` mengembalikan HTTP `200` serta exit IP.
- Trace redacted mengisolasi satu kegagalan transient pada node VMess `483b5b097c2c`: hostname node menghasilkan `NXDOMAIN`, lalu koneksi reset. Ini masalah runtime/provider node, bukan penolakan parser atau generator; tidak ada perubahan service production.
- Acceptance berulang production selama tiga putaran setelah health cycle: VLESS `9/9` berhasil; VMess `8/9`; Trojan `6/9`; Shadowsocks `4/9`. Semua sampel memakai forced route dan target `https://api.ipify.org?format=json`; kegagalan teramati sebagai `SSL_EOF`/request failure pada node tertentu. VMess latency sukses berkisar `1.3–13.4s` dan menunjukkan variasi tinggi.
- Node acceptance yang gagal tetap berstatus `healthy` dengan counter health sukses, karena health production menguji `http://cp.cloudflare.com/`, sedangkan acceptance menguji `api.ipify.org`; ini menunjukkan kegagalan destination-specific, bukan bukti health persistence rusak.
- Matrix target pada generation aktif menguji 10 node sampel ke `api.ipify.org`, `api64.ipify.org`, dan health target `cp.cloudflare.com`. SS sample `001a5d3dbe56` dan `005ad94eddcd` lulus dua target IP; VLESS `000696533d9e` dan `00109feb6fbd` lulus; VMess `252551c6c920` lulus dua target, sedangkan `49e62e6f9273` timeout pada keduanya; Trojan `00c57c72366d` gagal target IPv4 tetapi lulus target IPv6.
- Probe `cp.cloudflare.com` pada port generation aktif `18776` tidak identik dengan acceptance: sebagian node lulus health tetapi gagal target IP, dan sebagian target IP tetap lulus setelah health probe error. Health probe saat ini diperlakukan sebagai liveness, bukan bukti egress universal.
- Seluruh file yang dirujuk PRD dan README tersedia.
- Link ke indeks ADR dan ADR-001 tersedia.
- Placeholder diagram arsitektur di PRD diganti dengan diagram Mermaid yang memuat gateway, picker, sing-box, syncer, checker, scorer, dan SQLite.

- Historical deployment record: validasi host lain di bawah ini adalah bukti lama, bukan target operasional saat ini. Production test aktif tetap hanya pada systemd service PC lokal.

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
Fase 3 geo per-node: command `hopline geo --config <file> --node <id> --json` sekarang mengambil self-IP HTTPS melalui Gateway dengan route `node-<id>`, menjalankan fallback geolocation, menyimpan metadata ke SQLite, dan tidak mengubah health. Offline command smoke dengan fake dependencies lulus; production node belum dijalankan.
Fase 3 country routing: username `country-<cc>` dan `country-<cc>-sticky-<sessionId>` memfilter metadata geolocation fresh dengan default `country_max_age=3600`, tetap menerapkan health/cooldown, menghasilkan 503 saat pool kosong, dan sticky rebind tidak keluar dari country pool. Full suite 84 test lulus.
Production subscription rollout: empat URL subscription baru ditambahkan atomik ke `/etc/hopline/hopline.toml` (permission 0600), backup config/app dibuat di `/var/backups/hopline/20261014T164726Z`, dan service aktif setelah deployment. Sync menghasilkan 1,035 node; status terakhir 1 healthy, 3 degraded, sisanya unknown. Geo diagnostic dicoba pada node production, tetapi endpoint exit-IP/provider tunnel gagal; belum ada metadata geolocation. Country routes `country-id`, `country-cn`, `country-fi`, dan `country-kr` merespons 503 karena metadata country belum tersedia.
Root cause `unknown=1031`: production `[health]` tidak memiliki `targets`, sehingga daemon tidak membuat `ActiveProbeScheduler`; node baru tersimpan di registry tetapi tidak mendapat health row. Fix menambahkan bounded URL-probe queue dengan concurrency default 10. Target production sekarang `http://cp.cloudflare.com/`; response direct adalah 204. Generation port fix melewati gateway/control/metrics dan probe memakai generation aktif dinamis; listener production terverifikasi di `127.0.0.1:18775`. Sampel probe langsung menunjukkan sebagian VMess berhasil (`True`), sementara VLESS/SS/Trojan sample gagal; status setelah satu pass Cloudflare: 1,533 nodes, 0 healthy, 519 degraded, 708 dead, 306 unknown. Healthy tetap 0 karena state lama membutuhkan hysteresis recovery dan node gagal masuk cooldown/backoff.
- Audit per source/protocol production: node hasil subscription benar-benar diuji melalui generation aktif `18775` dengan target Cloudflare. Sumber subscription pertama memiliki sample VLESS/Trojan/SS dengan TCP reachability tetapi gagal atau timeout pada handshake protocol/HTTP probe; sumber kedua memiliki sample SS dan VLESS yang lulus; sumber regional memiliki sample VMess yang lulus. Generated config generation-4 memuat 506 SS, 502 Trojan, 519 VLESS, dan 6 VMess outbound. Tidak ada bukti cacat parser/generator global; belum melakukan perubahan protocol secara spekulatif.
Validasi sesi ini: full discovery suite menjalankan 87 test dengan `python3 -W error::ResourceWarning -m unittest discover -s tests -v` dan seluruhnya lulus. `PYTHONPATH=. python3 tools/smoke_ephemeral.py --fixture-dir . --timeout 20` menguji setiap protokol; Shadowsocks, Trojan, VLESS, dan VMess semuanya authenticated `200`, invalid/missing credential `407`, serta `production_service_touched: false`. `gateway_load.py` menghasilkan `admitted=4 rejected=12`; `https_proxy_acceptance.py` mengembalikan payload `pong`. Tidak ada root cause parser/generator yang terbukti, sehingga tidak ada regression test baru yang ditambahkan secara spekulatif.
- Root cause parity dengan 9router: 9router menganggap proxy live jika CONNECT dan response target selesai dengan status numerik apa pun, sedangkan Hopline sebelumnya hanya menerima `200..399`. False-negative ini mengeject node yang transport-live dan menghasilkan `503` sebelum Gateway mencoba node tersebut. Perbaikan mengubah active HTTP probe menjadi transport-completion check; regression menguji target `503` yang selesai sebagai sehat dan CONNECT `407` sebagai gagal. Perbaikan parser tambahan menerima password Trojan arbitrary seperti 9router; seluruh node Trojan production yang diaudit kebetulan memakai credential UUID.
- Validasi sesi ini: targeted parser/probe 13/13 dan full discovery suite 89/89 lulus tanpa `ResourceWarning`; `tools/smoke_config.py` lulus `sing-box check`; load smoke `admitted=4 rejected=12`; HTTPS proxy acceptance mengembalikan `pong`. Scope production aktif tetap PC lokal; service production tidak direstart pada validasi tersebut.
- Update sesi 2026-10-15: source retirement subscription diimplementasikan di `SQLiteRegistry.reconcile_subscription_sources()` dan dipanggil scheduler hanya setelah seluruh source/static node dalam satu siklus selesai. Source lama dihapus beserta node orphan; node shared dipertahankan. Guard parsial mencegah retirement saat shutdown menghentikan siklus sebelum semua source dicoba.
- Bukti offline: regression source retirement dan partial-cycle guard lulus; full discovery suite `92 tests — OK` dengan `python3 -W error::ResourceWarning -m unittest discover -s tests`.
- Bukti production PC lokal: commit `1ad52ff` dideploy hanya untuk `registry.py` dan `scheduler.py` ke `/opt/hopline/app`; backup dibuat di `/var/backups/hopline/source-retirement-20261015T042525Z`; service systemd direstart dan tetap `active`. Refresh berjalan dengan 4 source aktif, 0 source orphan, 0 source missing, 0 orphan node, dan 1.833 node owned. Snapshot terbaru tercatat `2026-10-15 04:26:07`.
- Boundary smoke production PC: listener `18770`, `18771`, `18772`, `18773` aktif; control status merespons; valid local proxy auth menghasilkan HTTP 200; tanpa auth menghasilkan HTTP 407; tidak ada error journal pascarestart. Config subscription tidak diubah dan URL/credential tidak dicetak.
- Status gate: implementasi, offline verification, dan refresh production PC lokal selesai. Host lain bukan scope validasi default dan tidak boleh disentuh tanpa permintaan eksplisit user.
- Acceptance harness production PC ditambahkan di `tools/production_acceptance.py`; output redacted dan hanya mengeluarkan protocol, node ID, status, exit IP, latency, dan verdict. Full suite setelah penambahan test harness: `94 tests — OK`.
- Acceptance production PC dengan tiga sampel per protokol sebelum source VMess tambahan: SS `3/3 HTTP 200`, Trojan `3/3 HTTP 200`, VLESS `3/3 HTTP 200`; VMess saat itu belum eligible dan tidak diklaim lulus.
- Gate Fase 1 setelah source tambahan: jalur subscription → health picker → forced Gateway → HTTPS target terbukti untuk SS, Trojan, VLESS, dan minimal satu VMess. Perluasan sampel VMess masih dibatasi latency tinggi dan health pool kecil.
- Source VMess tambahan diaktifkan pada production PC lokal melalui config private. Config dibackup ke `/var/backups/hopline/subscription-vmess-20261015T045906Z.toml`; URL tidak disimpan di repository dan fingerprint source adalah `c6fa3d173aee`.
- Setelah restart systemd, source snapshot valid dengan body `6401` bytes dan registry berisi `1.855` node: `603 SS`, `606 Trojan`, `621 VLESS`, `25 VMess`. Health VMess saat verifikasi: `1 healthy`, `1 degraded`, `6 dead`, `17 unknown`.
- Acceptance forced-route production PC dengan satu sampel per protokol lulus: SS, Trojan, VLESS, dan VMess semuanya HTTP 200. VMess sample menghasilkan exit IP dan latency `11079.5 ms`; latency tinggi dicatat sebagai risiko operasional, bukan failure.
- Verifikasi seluruh node source VMess `c6fa3d173aee`: ownership langsung source berisi `16` node. Forced-route end-to-end melalui Gateway production PC ke target HTTPS IP-echo menghasilkan `16/16 HTTP 200`, `0` gagal. Latency terukur `985.0–1944.1 ms`; hasil ini membuktikan semua 16 node hidup saat diuji, bukan jaminan permanen karena node subscription dapat berubah.
- `/status` production PC setelah deploy `control.py` mengembalikan breakdown protokol dan health yang konsisten: `1.850` node; SS `603`, Trojan `605`, VLESS `618`, VMess `24`. Agregat health: healthy `461`, degraded `184`, dead `13`, quarantine `0`, unknown `1.192`. Invariant terverifikasi: total protocol = total node dan jumlah state per protocol = total protocol.
- Full suite setelah perubahan status API: `95 tests — OK`. Backup deployed control module berada di `/var/backups/hopline/status-protocol-20261015T055432Z`; service lokal tetap active dan listener control `127.0.0.1:18772` merespons.
- `/status` kini memiliki breakdown `countries` berdasarkan metadata geolocation tersimpan. Smoke production setelah deploy menunjukkan `1.848` node dalam key `unknown` karena belum ada country metadata aktif pada snapshot tersebut; agregat country/state konsisten dengan global health.
- Full suite setelah penambahan country breakdown: `96 tests — OK`. Backup deployed control module berada di `/var/backups/hopline/status-country-20261015T055900Z`; service lokal active dan control `127.0.0.1:18772` merespons.
- Akar masalah country `unknown` dikonfirmasi: registry production memiliki `1.849` node tetapi `0` row geolocation. Diagnostic satu node melalui route aktual berhasil memperoleh exit IP dan country `RU`.
- Collector `hopline geo --all` ditambahkan untuk refresh metadata country secara eksplisit dan terbatas; tidak dijalankan pada setiap `/status`.
- Deploy collector CLI ke production menggunakan backup `/var/backups/hopline/geo-collector-20261015T074839Z`. Batch terbatas `--limit 3 --concurrency 1` memproses 3 node: 2 berhasil, 1 gagal karena `GeoLookupError`; metadata tersimpan menghasilkan country `JP: 1`, `RU: 1`, `US: 1`. `/status` live menampilkan ketiganya dan invariant country/global health lulus.
- Full suite setelah collector country: `97 tests — OK`.
- Geolocation fallback `reallyfreegeoip` ditambahkan dan diuji dengan fixture; smoke langsung endpoint publik `https://reallyfreegeoip.org/json/8.8.8.8` mengembalikan HTTP `403`, sehingga provider diperlakukan sebagai fallback dan bukan dijamin unlimited.
- Registry production setelah subscription refresh berisi `1.850` node tetapi `0` row geolocation. Metadata country terikat `node_id` dan dapat hilang ketika node diganti/retired; `/status` dengan benar menempatkan node tanpa metadata ke `unknown`.
- Auto-refresh country kini mengikuti scheduler health: semua node eligible langsung masuk bounded queue, memakai `[health].interval` dan `[health].concurrency`; metadata fresh, `dead`, dan `quarantine` tetap dilewati. Full suite queue update: `99 tests — OK`.
- Production config saat verifikasi memakai health interval `60s` dan concurrency `4`; queue geo tidak lagi dibatasi 10 node per 15 menit.
- Deploy queue geo mengikuti health menggunakan backup `/var/backups/hopline/country-health-queue-20261015T094038Z`; service active. Setelah 15 detik, geolocation rows bertambah menjadi `16` dan `/status` menampilkan country nyata `CH`, `DE`, `FI`, `GB`, `IN`, `JP`, `KR`, `NL`, `RU`, `US`. Invariant country/global health lulus.
- Deploy auto-refresh menggunakan backup `/var/backups/hopline/country-auto-refresh-20261015T092329Z`; service active.
## Blocker / Risiko Aktif

| Risiko | Status | Bukti/kondisi | Next action |
|---|---|---|---|
| Protocol egress belum stabil lintas node | open | Matrix target menunjukkan VLESS sample lulus dua target; VMess memiliki satu node timeout dua target; Trojan memiliki kegagalan IPv4-specific; tiga putaran sebelumnya menghasilkan VLESS `9/9`, VMess `8/9`, Trojan `6/9`, Shadowsocks `4/9` | Ulangi acceptance protocol-specific pada `api.ipify.org` dan `api64.ipify.org`, pisahkan IPv4/IPv6, lalu evaluasi node secara individual |
| Country production belum terisi penuh | in progress | Auto-refresh mengikuti scheduler health dan langsung mengantrekan semua node eligible; mayoritas masih `unknown` karena route/provider dapat gagal | Biarkan queue berjalan dan pantau provider failure serta metadata stale |
| Provider geolocation gratis memiliki rate limit dan perubahan response | open | Queue memakai concurrency health (`4` pada production saat verifikasi) dan fallback chain; provider `reallyfreegeoip` mengembalikan HTTP 403 saat direct smoke | Pantau error provider; turunkan concurrency bila provider mulai rate-limit |
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
