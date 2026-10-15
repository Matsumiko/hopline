# Changelog

Format mengikuti prinsip Keep a Changelog. Dokumen ini hanya mencatat perubahan yang sudah terjadi, bukan rencana.

## [Unreleased]

### Added
- Runtime isolated `28770-28773` dihapus. Production PC sekarang hanya memakai systemd `18770-18773`.
- Subscription production diganti secara clean cutover menjadi empat source privat dengan filter protocol/country. Registry lama dikosongkan sebelum restart; hasil awal 631 node. VMess belum memiliki node healthy pada smoke pertama dan tidak diklaim lulus.
- Mengoreksi scope bukti production: acceptance empat protokol sebelumnya berasal dari daemon isolated `28770-28773`, bukan systemd registry 901 node. Systemd PC kini disinkronkan dari `main`, memakai auth dan active HTTP probe, lalu divalidasi langsung di `18770-18773`. SS/Trojan/VLESS forced route lulus; sampel VMess production gagal TLS/relay; rotate lulus 6/8; country NL/DE dan country-sticky lulus; pool country kosong mengembalikan `503`.
- Production PC lokal kini tervalidasi untuk `rotate`, forced `node-<id>`, sticky session, dan country routing. Sticky mempertahankan exit IP yang sama lintas koneksi; country `DE` dan `AM` hanya memilih node dengan metadata negara yang sesuai; country tanpa pool mengembalikan `503` secara cepat. Metadata SS belum tersedia karena diagnostic exit-IP SS gagal.
- File-backed SQLite registry memakai WAL dan `busy_timeout=5000` agar health writes tidak gagal ketika active probe, control API, atau Gateway traffic membaca database bersamaan. Regression test mencakup concurrent read transaction.
- Production PC lokal tervalidasi dengan VLESS, VMess, Trojan, dan Shadowsocks: forced route masing-masing HTTPS `200`, 48/48 concurrent CONNECT `200`, auth salah/kosong `407`, dan status akhir 4 healthy.
- Menyamakan active HTTP probe dengan semantik 9router: CONNECT harus berhasil dan response target harus selesai dengan status HTTP numerik apa pun; target `4xx/5xx` tidak lagi menjadi false-negative health, sedangkan timeout, TLS, malformed response, dan CONNECT rejection tetap gagal. Menambahkan regression coverage.
- Parser Trojan sekarang mempertahankan password provider arbitrary dan tidak lagi memaksa format UUID; outbound generator meneruskan password tersebut ke sing-box.
- Full suite terbaru menjalankan 87 test tanpa `ResourceWarning`; smoke ephemeral menguji VLESS, VMess, Trojan, dan Shadowsocks dengan authenticated HTTP 200 serta invalid/missing credential HTTP 407 tanpa menyentuh service production. Load smoke menghasilkan 4 koneksi diterima dan 12 ditolak dari 16 concurrent; HTTPS proxy acceptance mengembalikan payload `pong`.
- Scheduler kini merekonsiliasi source subscription yang dihapus dari konfigurasi setelah siklus sync lengkap. Snapshot source lama dan node yang tidak lagi dimiliki source aktif dihapus; node shared dipertahankan. Retirement tidak berjalan pada siklus parsial saat shutdown.
- Registry menambahkan test untuk source retirement, orphan/shared node ownership, dan guard siklus parsial.
- Verifikasi implementasi: full suite `92/92` lulus dengan `ResourceWarning` diperlakukan sebagai error. Production PC lokal kemudian dideploy dan divalidasi setelah restart: 4 source aktif, 0 source orphan, 0 source missing, 0 orphan node, dan 1.833 node owned. Validasi sesi ini hanya mencakup production PC lokal.
- Menambahkan `tools/production_acceptance.py` untuk forced-route acceptance pada production PC lokal. Harness memilih node healthy per protokol, mengambil exit IP melalui HTTPS target, dan meredaksi credential/server/port/share-link dari output. Hasil pertama: Shadowsocks 3/3, Trojan 3/3, dan VLESS 3/3 HTTP 200; VMess belum memiliki node healthy (6 dead, 2 degraded dari 8 node).
- Gateway sekarang mewajibkan credential lokal `[auth]` sebelum memilih node. Username client (`hopline` secara default) dan password lokal tidak diteruskan ke sing-box; credential node tetap internal. Smoke ephemeral memverifikasi credential benar, salah, dan kosong.
- Memperbaiki collision port multi-generation: sing-box generation sekarang melewati gateway/control/metrics port, dan HTTP active probe memakai port generation aktif. Target production probe diganti ke `http://cp.cloudflare.com/`.
- Memperbaiki health lifecycle production: daemon sekarang mengaktifkan URL probe ketika `[health].targets` dikonfigurasi, dan scheduler memakai bounded concurrency default 10. Node baru tidak lagi tertahan sebagai `unknown`; production pass menurunkan unknown dari 1.031 menjadi 3 dari 1.535 node.
- Memperbaiki dispatch `hopline run` agar systemd daemon tidak masuk restart loop; menambahkan fallback geolocation `ipwho.is` setelah provider utama gagal.
- Production subscription rollout menambahkan empat source subscription privat (utama, CN, FI, KR) ke config lokal; sync menghasilkan 1,035 node. Geo/country routing masih blocked karena node production yang tersedia belum berhasil menyediakan exit-IP.
- `control_port` sekarang configurable dengan default production tetap `18772`; daemon tests memakai port ephemeral `0` sehingga tidak bentrok dengan service production yang sedang berjalan.
- Menambahkan `hopline geo --config <file> --node <id> --json`: self-IP HTTPS request melalui route `node-<id>`, fallback country lookup, persistence metadata non-secret, dan validasi error tanpa membocorkan credential.
- Menambahkan country routing `country-<cc>` dan `country-<cc>-sticky-<sessionId>` berbasis geolocation fresh (default 3600 detik), dengan 503 saat pool kosong dan sticky rebind tetap di country pool.
- Menambahkan diagnostic geolocation berbasis IP exit dengan fallback berurutan `checkip.com`, `ip.cc`, dan `cekipsaya.com?action=lookup&target=...`. Hasil country/IP/ASN disimpan terpisah dari health dan tidak mengandung credential.
- Production deployment verified for local Gateway auth on the authorized Debian 12 VPS: commit `70c6cb7` active, `[auth]` config private, valid credential returned CONNECT `200`, and wrong/missing credentials returned `407`. Control status reported four healthy nodes and the authenticated egress smoke returned HTTP `200`.
- Menambahkan riset dan ADR health probing berdasarkan source NekoBox. URL/HTTP test tetap menjadi active health yang ringan; full/download/upload/country/simple-download dipisahkan sebagai diagnostic on-demand. Forced-node regression memastikan `node-<id>` tidak fallback ke node lain.
- Dokumentasi health probe diperjelas: HTTP/URL probe adalah active health; lima mode NekoBox lainnya diposisikan sebagai diagnostic on-demand dan forced routing tidak melakukan fallback.
- Fase 2 health/failover: cooldown 30 detik setelah failure, eject setelah tiga failure berturut-turut, active-probe backoff, recovery hysteresis, picker filtering, dan fast 503 saat pool kosong. Regression coverage menegaskan pre-forward failover, no-retry setelah byte, active-stream preservation, serta relay incremental.
- Fase 3 slice pertama: username `sticky-<sessionId>` memakai binding process-local dengan idle TTL 10 menit, rebind sebelum CONNECT 200 saat node tidak eligible, serta regression untuk same-session reuse, empty pool, dan active relay lifecycle.

- Baseline dokumentasi proyek: `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `PROGRESS.md`, `CONTRIBUTING.md`, `SECURITY.md`, dan `AGENTS.md`.
- Indeks keputusan arsitektur di `docs/adr/`.

### Changed

- `PRD_Hopline.md` diperbarui dengan urutan vertical slice Fase 0–4, gate verifikasi, keputusan awal, dan protokol pencatatan pembangunan.

### Added

- Eksperimen feasibility lokal Fase 0 di `experiments/f0/run.py` untuk routing `auth_user` tanpa node atau subscription nyata.
- ADR-002 dan kontrak generation ownership untuk menjaga active stream.
- Harness `experiments/f0/generation_swap.py` untuk membuktikan stream lama tetap hidup saat generation baru menerima koneksi baru.

### Verified

- sing-box 1.14.3 memvalidasi config mixed inbound, menerima HTTP CONNECT, dan merutekan dua user ke dua outbound HTTP berbeda.
- SIGHUP menerapkan config route baru setelah downtime singkat dan proses tetap hidup.
- Credential fixture tidak muncul pada output sing-box.
- Generation swap harness lulus tiga kali.
- Smoke node VLESS live lulus secara ephemeral; IP egress berbeda dari IP VPS dan credential tidak masuk repository atau runtime log.

### Known Limitation

- SIGHUP menutup stream aktif saat reload. Graceful reload belum tersedia dan tidak boleh diasumsikan oleh TunnelEngine.
- Config live yang diberikan memiliki field `outbounds[0].encryption` yang ditolak sing-box 1.14.3; validasi sementara menghapus field legacy itu pada temporary config saja.

### Added

- Package runtime `hopline/` dengan model Node, parser VLESS, config generator sing-box, GenerationManager, SingBoxEngine, dan HTTP CONNECT Gateway.
- Mode `rotate`, node-specific routing, upstream Basic Auth, generation publish, drain, dan listener stop tanpa memutus relay aktif.
- Test suite offline dan integration smoke Gateway → sing-box → target lokal.
- `tools/smoke_config.py` untuk memvalidasi generated config melalui `sing-box check`.

### Verified

- Delapan test F1 lulus tanpa `ResourceWarning`.
- Generated config fixture lulus `sing-box check`.

### Added

- `SQLiteRegistry` untuk metadata schema, subscription source, deduplicated nodes, dan node-source ownership.
- `Syncer` untuk bounded VLESS snapshot text/base64, invalid-entry isolation, stable snapshot detection, dan fallback ke node registry valid terakhir.
- `SingBoxEngine.apply_nodes()` dan `Syncer.sync_text_and_apply()` untuk generation publish hanya saat parameter node berubah.

### Verified

- Empat belas test F1 lulus tanpa `ResourceWarning`, termasuk sync snapshot → SQLite → sing-box generation dan no-op sync tanpa generation reload.

### Added

- `SubscriptionFetcher` dengan timeout, batas body, User-Agent, ETag, dan `If-Modified-Since`.
- Registry menyimpan body valid terakhir dan metadata validator.
- Parser snapshot untuk VLESS, Trojan, VMess, dan Shadowsocks.
- Fallback ke registry valid terakhir saat fetch gagal; HTTP 304 menjadi no-op.
- Generator sing-box memetakan outbound Shadowsocks ke tipe `shadowsocks`.

### Verified

- URL subscription pengguna diambil secara ephemeral: 100 node, 0 invalid, empat protokol.
- Generated config 100 node lulus `sing-box check`.
- Sembilan belas test lulus tanpa `ResourceWarning`; credential tidak dicetak, disimpan di fixture publik, atau masuk commit.

### Added

- `SubscriptionScheduler` dengan interval, jitter, cancellation, dan optional generation apply.
- CLI `python3 -m hopline sync`, `test`, dan `doctor` dengan output `--json`, exit code, dan error pada stderr.

### Verified

- Dua puluh tiga test lulus tanpa `ResourceWarning`.
- CLI help, JSON doctor, missing URL error, live sync 100 node, dan live doctor sudah dijalankan.

### Not Implemented Yet

- Health checker, scorer, picker, dan Control API.
- Scheduler production lifecycle dan systemd packaging.

### Added

- Private TOML config loader dengan validasi permission `0600`.
- CLI `run` untuk one-shot sync atau scheduler daemon dengan SIGTERM/SIGINT shutdown.
- Hardened `packaging/hopline.service` dengan user terpisah dan filesystem/network restrictions.

### Verified

- Dua puluh sembilan test lulus tanpa `ResourceWarning`.
- `run --once` live sync menghasilkan 100 node; `systemd-analyze verify` menerima unit service.

### Added

- Structured subscription parser untuk Clash YAML dan sing-box JSON.
- Removed hysteresis per subscription source: node baru dihapus setelah tiga snapshot berturut-turut tidak memuat node tersebut.

### Verified

- Dua puluh enam test lulus tanpa `ResourceWarning`.
- Fixture Clash YAML dan sing-box JSON berhasil diparse; node invalid diabaikan.
- Hysteresis mempertahankan node pada sync pertama/kedua dan menghapusnya setelah sync ketiga.

### Added

- Health registry dengan state `healthy`, `degraded`, `dead`, dan `quarantine`.
- Passive success/failure feedback dan injected active probe seam.
- Localhost-only control API `GET /status` dan `GET /nodes`.
- CLI read-only `status` dan `nodes`.

### Verified

- Tiga puluh dua test lulus tanpa `ResourceWarning`.
- Control API smoke menghasilkan status JSON tanpa credential node.

### Changed

- Gateway sekarang melewati node `dead`/`quarantine`, mencatat feedback passive, dan mencoba kandidat berikutnya sebelum mengirim `200 Connection Established`.
- Retry tetap dibatasi pada fase pre-byte; relay aktif tidak diulang otomatis.

### Verified

- 34 test lulus tanpa `ResourceWarning`.

### Added

- Konfigurasi `[health]` untuk target, interval, dan timeout active probe.
- `ActiveProbeScheduler` dengan timeout per node, cancellation, dan persistence ke SQLite health registry.
- Daemon `run` menjalankan probe berkala atau sekali pada mode `--once` jika target dikonfigurasi.

### Verified

- 37 test lulus tanpa `ResourceWarning`.
- Probe success, failure, timeout seam, dan graceful cancellation teruji.

### Added

- Active connection accounting per node dengan `503 Service Unavailable` saat admission limit tercapai.
- Harness `experiments/f1/gateway_load.py` untuk concurrent CONNECT.
- Harness `experiments/f1/https_proxy_acceptance.py` untuk relay gateway → upstream → origin lokal.

### Verified

- 16 concurrent CONNECT dengan limit 4 menghasilkan 4 accepted dan 12 rejected.
- HTTPS proxy acceptance merelay payload `pong` end-to-end.

### Changed

- Active probe mendukung mode `http`: CONNECT ke mixed inbound sing-box, GET ke target, dan validasi status `2xx`–`3xx`.
- Config mendukung `proxy_host` dan `proxy_port` untuk probe tunnel.

### Verified

- 41 test lulus tanpa `ResourceWarning`.
- HTTP probe berhasil dengan auth node, menolak CONNECT non-200, dan memvalidasi response target.

### Added

- Host Linux installation and rollback runbook di README.
- Systemd unit memakai `PYTHONPATH=/opt/hopline/app` dan read-only source/config paths.
- Deployment smoke tests untuk hardening unit dan `systemd-analyze verify`.

### Added

- Optional localhost Prometheus endpoint `/metrics`, disabled by default.
- Bounded metrics: node count, health-state count, and active-probe enabled state.
- Metrics configuration for bind host and port with localhost validation.

### Verified

- Staging host install completed with systemd user/group, private config, writable SQLite state, control API, and localhost metrics endpoint.
- Proxy egress smoke initially blocked because sing-box was absent from the systemd-visible path; resolved by installing `/usr/local/bin/sing-box` and wiring the service sandbox for netlink access.
- Earlier staging blocker is superseded by the verified system-wide sing-box installation; the remaining open item is real egress IP verification.

### Verified

- Daemon runtime now wires subscription sync, persistent sing-box generation, localhost gateway, health feedback, control API, and optional metrics.
- Staging with system-wide sing-box passed `doctor`, service startup, listeners on ports 18770–18773, and a live CONNECT handshake.
- Systemd allows `AF_NETLINK`, required by sing-box 1.14.3 under the service sandbox; the service remains localhost-only.
- Regression smoke membuktikan node pertama ditolak, node kedua berhasil, dan client hanya menerima satu respons `200`.

### Verified

- User-provided subscription fetched successfully and parsed into 301 fresh nodes: 75 Shadowsocks, 75 Trojan, 76 VLESS, and 75 VMess.
- Staging daemon ran with 601 registry nodes, systemd active, all localhost listeners available, and CONNECT handshake returning `200 Connection Established`.
- Public HTTPS egress was not proven: 20 rotate attempts and 19 explicitly healthy-node attempts returned HTTP 000 / `SSL_ERROR_SYSCALL` after CONNECT; no egress IP was recorded.

### Verified

- Real subscription runtime held 601 registry nodes; TCP reachability was 600/601.
- Protocol sample: one Trojan node returned egress IP `131.186.63.89`; sampled SS, VLESS, and VMess nodes failed HTTPS relay, and repeated Trojan attempts timed out. Production egress stability remains open.

### Fixed

- Preserve Shadowsocks `v2ray-plugin` and its WebSocket/TLS options from share links through SQLite registry and generated sing-box outbound config.
- Preserve VMess `security`, `global_padding`, and `authenticated_length` metadata.
- Verified the user-provided Nekobox Shadowsocks export through Hopline; it returned egress IPv6 `2a01:4f8:c010:6c95::1`.

- Preserve VLESS `packet_encoding` and `flow`, VMess `alter_id`, and corresponding metadata through parser, SQLite registry, generation signature, and sing-box config generation.
- Align VMess TLS detection with the link's `security` parameter instead of assuming every VMess link uses TLS.
- Verified 49 tests and `sing-box check` for generated VLESS/VMess configs; live VLESS/VMess egress remains open because current samples still fail during relay.

- Preserve Reality public key/short ID, uTLS fingerprint, ALPN, gRPC `service_name`, and transport metadata through structured parsing, SQLite persistence, generation signatures, and sing-box config generation.
- Normalize VLESS flow suffix `-udp443`, map VMess `h2` to sing-box `http`, and omit legacy VLESS `encryption=none` from generated outbounds because sing-box 1.14.3 rejects that field.
- Added regression coverage for Reality/gRPC/ALPN/flow and VMess h2 mappings. The full suite now passes 51 tests; a real subscription fetch parsed 300 nodes with zero invalid entries.
- Generated VLESS and VMess samples both pass `sing-box check`. Live samples still do not prove egress: VLESS timed out and VMess returned `SSL_ERROR_SYSCALL` during relay.

- Added `static_nodes` configuration for running direct VLESS, VMess, Shadowsocks, and Trojan share links without subscription synchronization.
- Deployed Hopline to the authorized Debian 12 VPS with private static-node config, systemd supervision, localhost gateway/control/metrics listeners, and system-wide sing-box 1.14.3.
- Remote smoke: four configured static nodes loaded; Shadowsocks returned egress IP `139.162.133.162`. VLESS, VMess, and Trojan remained unsuccessful on this VPS sample and were not marked healthy.

- Generated sing-box configurations now declare `dns-local`, set it as the default domain resolver, and attach it explicitly to relay/node outbounds. A single global `8.8.8.8` resolver detoured through `proxy` was intentionally not added because it is unsafe for a multi-node pool and can create DNS loops.
- Generated sing-box configurations now create one `dns-remote-<node-id>` server per node and match DNS rules by `auth_user`, so target DNS follows the same outbound selected for the authenticated CONNECT. Hopline inbound users, passwords, and `auth_user` outbound rules remain unchanged.
- Regression, multi-node `sing-box check`, and ephemeral egress smoke passed for VLESS, VMess, Trojan, and Shadowsocks with per-node DNS detours.
- Added `tools/smoke_ephemeral.py` for credential-safe VLESS WS/TLS, VMess WS/TLS, Trojan WS/TLS, and Shadowsocks egress checks. The runner validates direct node DNS bootstrap, authenticated CONNECT success, and `407` for missing credentials without touching the production service.
- Gateway now returns `407 Proxy Authentication Required` when CONNECT has no `Proxy-Authorization`; `rotate` remains explicit and is not inferred from a missing header.
- Production deployment verified on the authorized Debian 12 VPS: generated four-node config passed `sing-box check`, service restart stayed active, and gateway smoke returned HTTP 200 for VLESS, VMess, Trojan, and Shadowsocks plus HTTP 407 without proxy credentials.
