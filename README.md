# Hopline

Hopline adalah gateway proxy lokal yang memilih node sehat dari subscription VMess, VLESS, Trojan, atau Shadowsocks, lalu meneruskan koneksi HTTP/HTTPS melalui sing-box.

Hopline ditujukan untuk developer atau tim kecil yang menjalankan script/bot di VPS dan membutuhkan satu endpoint proxy lokal tanpa mengubah routing jaringan VPS.

> **Status:** Fase 1 ditutup (2026-10-18). Vertical slice, scheduler berkala, CLI, health scoring, failover pre-forward (lihat [routing limits](docs/routing-limits.md)), sticky/country/capability routing, control API, web panel, dan metrics Prometheus tersedia. Gate Fase 1 lulus; stabilitas egress per-node tetap dilacak sebagai risiko operasional. Status acceptance terukur ada di [docs/acceptance-status.md](docs/acceptance-status.md). Lihat [PROGRESS.md](PROGRESS.md).

## Dokumen Utama

- [PRD](PRD_Hopline.md) — tujuan, scope, requirement, dan acceptance criteria.
- [Architecture](ARCHITECTURE.md) — boundary modul, alur runtime, dan invariant.
- [Roadmap](ROADMAP.md) — fase, gate, dan urutan pengerjaan.
- [Progress](PROGRESS.md) — status faktual, bukti, risiko, dan next action.
- [Changelog](CHANGELOG.md) — perubahan yang sudah terjadi.
- [Contributing](CONTRIBUTING.md) — aturan kontribusi dan verifikasi.
- [Security](SECURITY.md) — aturan secret, privasi, dan pelaporan masalah.
- [Documentation index](docs/README.md) — configuration, control API, web panel, subscriptions, routing, acceptance status, limits, recovery, and benchmarks.
- [ADR index](docs/adr/README.md) — keputusan arsitektur yang memiliki konsekuensi jangka panjang.

## Interface Target

```bash
export HTTPS_PROXY=http://hopline:password-lokal@127.0.0.1:18770
curl https://api.ipify.org
```

Interface utama adalah HTTP proxy dengan dukungan `CONNECT`. Username `hopline` dan password pada `[auth]` adalah credential lokal Hopline; credential node/provider tidak boleh dipakai oleh client. `rotate` tetap dipilih secara internal, per koneksi proxy, bukan otomatis per HTTP request jika client memakai connection pooling.

## Arsitektur Singkat

```text
Client → Hopline Gateway :18770 → sing-box generation → selected node → target
                                  ├── generation lama: drain koneksi aktif
                                  └── generation baru: koneksi baru
```

Hopline mengelola pemilihan, health, failover sebelum byte client diteruskan, sinkronisasi subscription, dan lifecycle sing-box. Config update memakai generation baru; stream aktif tidak diputus oleh lifecycle Hopline. Hopline tidak melakukan MITM dan tidak mengulang traffic setelah forwarding dimulai.

## Status Saat Ini

Package runtime tersedia di `hopline/`. Parser share-link VLESS, Trojan, VMess, dan Shadowsocks, structured parser Clash YAML/sing-box JSON, bounded subscription fetch, SQLite registry dengan removed hysteresis tiga sync, conditional validators, last-valid fallback, config generation, generation-aware sing-box engine, HTTP CONNECT gateway, rotate, sticky routing process-local, node routing, drain, scheduler berkala, CLI, control API, web panel, dan metrics sudah diuji. Sticky memakai username `sticky-<sessionId>`, TTL idle default 10 menit, dan rebind ke node sehat sebelum CONNECT 200 jika binding lama dead atau tidak eligible. Lihat [PROGRESS.md](PROGRESS.md) untuk bukti dan pekerjaan berikutnya.

Parser share-link dan generator sing-box mempertahankan transport WebSocket/TLS; Shadowsocks `v2ray-plugin` menyimpan `plugin` dan `plugin_opts`, sedangkan VMess mempertahankan `security`, `global_padding`, dan `authenticated_length`.

## CLI

```bash
python3 -m hopline doctor --json
python3 -m hopline test --url "$HOPLINE_SUBSCRIPTION_URL" --json
python3 -m hopline sync --url "$HOPLINE_SUBSCRIPTION_URL" --db hopline.db --json
```

`sync` menyimpan node dan metadata subscription ke SQLite. `test` mengambil dan mem-parse subscription tanpa menjalankan sing-box. `doctor` memeriksa schema registry, jumlah node, dan binary sing-box. Output `--json` hanya berisi metadata; credential node dan isi subscription tidak ditampilkan.

Daemon memakai file TOML private (`0600`). Sumber node dapat berupa subscription HTTP(S) dan/atau `static_nodes` share link langsung. `static_nodes` menjalankan node satuan tanpa mencocokkannya ke subscription:

```toml
static_nodes = [
  "vless://...",
  "vmess://...",
  "ss://...",
  "trojan://...",
]

[hopline]
database = "/var/lib/hopline/hopline.db"
interval = 2700
jitter = 30
gateway_host = "127.0.0.1"
control_port = 18772
country_max_age = 3600
sing_box_binary = "/usr/local/bin/sing-box"
engine_workdir = "/var/lib/hopline/engine"
max_active_connections = 64

[auth]
username = "hopline"
password = "password-lokal-yang-kuat"

[[subscriptions]]
url = "https://example.invalid/subscription"
```

`[auth]` wajib berisi username dan password lokal. Simpan file TOML dengan permission `0600`. Credential node/provider tetap berada internal Hopline dan tidak pernah menjadi credential client. `control_port` default `18772` untuk service production dan dapat diatur ke `0` pada test agar OS memilih port ephemeral. CLI `status` dan `nodes` tetap memakai `18772` secara default; gunakan `--port` jika daemon memakai port lain.

## React Control Panel

Panel operasional React tersedia di `webui/`. Panel ini read-only pada tahap awal dan memakai endpoint `/status` serta `/nodes`; credential node, share link, subscription URL, dan password tidak pernah dikirim ke browser.

Build dan jalankan development server:

```bash
cd webui
npm ci
npm run dev -- --host 127.0.0.1
```

Vite meneruskan `/status` dan `/nodes` ke control API `127.0.0.1:18772`. Untuk daemon production, build panel lalu set directory hasil build pada file TOML private:

```toml
[hopline]
webui_dir = "/opt/hopline/app/webui/dist"
```

Control API tetap localhost-only. Static panel dilayani dari control port yang sama, sehingga akses remote harus melalui SSH tunnel atau mekanisme akses lokal yang sudah disetujui; jangan bind control API ke internet.

Panel menampilkan ringkasan health, protocol/country counts, filter node berdasarkan ID/server/country, serta metadata egress non-secret. Tombol "Sync now" memicu subscription refresh melalui `POST /sync` yang dijalankan daemon.
Refresh subscription berjalan mengikuti `interval` dan `jitter`. Setiap source menyimpan snapshot valid terakhir, memakai ETag/Last-Modified bila tersedia, dan mempertahankan node lama saat fetch atau parse gagal. Node mendapat ID stabil dari parameter koneksi; node baru ditambahkan, node identik lintas source dideduplikasi, dan node yang hilang dari satu snapshot baru dilepas setelah tiga sync valid berturut-turut. Jika URL dihapus dari konfigurasi, source tersebut direkonsiliasi setelah satu siklus sync lengkap: snapshot dan node yang hanya dimiliki source itu dihapus, sedangkan node yang masih dimiliki source aktif tetap dipertahankan. Siklus yang terhenti sebelum semua source dicoba tidak melakukan retirement.
Untuk affinity per sesi, gunakan username proxy `sticky-<sessionId>`, misalnya `sticky-job-42`. Binding hanya hidup di proses Gateway dan hilang saat restart; TTL diperpanjang ketika koneksi berhasil dipakai. `node-<id>` tetap forced tanpa fallback, sedangkan `rotate` tetap memilih ulang per koneksi.

Routing capability IP memakai username:

```text
ipv4
ipv6
ipv4-sticky-<sessionId>
ipv6-sticky-<sessionId>
```

Capability IPv4/IPv6 disimpan terpisah dari health. Hanya hasil probe family yang memiliki IP valid dan masih fresh yang eligible. Capability route tidak mengubah `rotate`, `node-<id>`, atau country route; pool kosong mengembalikan `503`. Capability failure tidak mengubah health node.

Aktifkan collector capability secara eksplisit:

```toml
[capability]
enabled = true
max_age = 3600
interval = 900
timeout = 20
concurrency = 1
ipv4_url = "https://api4.ipify.org?format=json"
ipv6_url = "https://api6.ipify.org?format=json"
```

`/nodes` menampilkan capability per node sebagai `ipv4` dan `ipv6`, termasuk `capable`, observed `ip`, `checked_at`, dan `last_error`. Capability adalah bukti egress ke target probe, bukan jaminan semua destination dapat dicapai.

Routing country memakai username:

```text
country-id
country-sg-sticky-job42
```

Hanya metadata country yang cocok dan lebih baru dari `country_max_age` yang dipakai. Node `dead`, `quarantine`, cooldown, metadata missing, dan metadata stale dilewati. Jika pool country kosong, Gateway mengembalikan `503`. Sticky country hanya melakukan rebind di negara yang sama.
Untuk memverifikasi lokasi IP exit satu node, daemon harus sedang berjalan dan node sudah tersimpan di registry:

```bash
python3 -m hopline geo --config hopline.toml --node <node-id> --json
```

Untuk mengisi country banyak node secara terkontrol, gunakan batch refresh. Metadata fresh dilewati, node `dead` dan `quarantine` dilewati, dan `--limit` membatasi jumlah node pada satu batch:

```bash
python3 -m hopline geo --config hopline.toml --all --limit 10 --concurrency 2 --json
```

Command batch membuka request HTTPS self-IP melalui route masing-masing `node-<node-id>`, menjalankan fallback geolocation, menyimpan metadata non-secret ke SQLite, lalu menampilkan ringkasan country. Jalankan ulang sampai `selected` dan `failed` sesuai kebutuhan. Jangan menjalankan lookup pada setiap request `/status`.

Command single membuka request HTTPS ke endpoint self-IP melalui Gateway memakai route `node-<node-id>`, lalu mengirim IP hasilnya ke fallback geolocation dan menyimpan metadata non-secret ke SQLite. `--exit-ip-url` dapat mengganti endpoint self-IP yang kompatibel mengembalikan `{"ip":"..."}`. Command gagal jika node tidak ada, Gateway tidak berjalan, atau response tidak berisi IP valid.
Daemon juga menjalankan refresh country otomatis di background setelah Gateway aktif, menggunakan interval dan concurrency yang sama seperti active health (`[health].interval` dan `[health].concurrency`). Semua node eligible langsung masuk bounded queue; metadata fresh, node `dead`, dan `quarantine` dilewati. `/status` hanya membaca metadata tersimpan dan tidak menjalankan network lookup.


Jalankan sekali atau sebagai daemon:

```bash
python3 -m hopline run --config hopline.toml --once
python3 -m hopline run --config hopline.toml
```

Template systemd tersedia di `packaging/hopline.service`. Service memakai user terpisah, `NoNewPrivileges`, `PrivateTmp`, filesystem protection, dan hanya `/var/lib/hopline` writable.

## Control API

Daemon `run` membuka API localhost di `127.0.0.1:18772`:

```bash
python3 -m hopline status --json
python3 -m hopline nodes --json
```

Endpoint HTTP read-only:

```text
GET /status
GET /nodes
```

`/status` mempertahankan field `nodes`, `health`, dan `schema_version`. Field tambahan `protocols` memuat setiap protokol (`ss`, `trojan`, `vless`, `vmess`) dengan `total`, `healthy`, `degraded`, `dead`, `quarantine`, dan `unknown`. Field `countries` memakai `country_code` dari metadata geolocation tersimpan sebagai key uppercase; node tanpa metadata country masuk key `unknown`. Setiap country juga memiliki `total` dan breakdown state yang sama. `health` adalah agregat global; jumlah state dalam setiap protocol/country harus sama dengan `total`, dan jumlah `total` protocol/country harus sama dengan `nodes`.

Contoh bentuk response:

```json
{
  "nodes": 1850,
  "health": {"healthy": 461, "degraded": 184, "dead": 13, "quarantine": 0, "unknown": 1192},
  "protocols": {
    "ss": {"total": 603, "healthy": 143, "degraded": 60, "dead": 5, "quarantine": 0, "unknown": 395},
    "trojan": {"total": 605, "healthy": 144, "degraded": 62, "dead": 1, "quarantine": 0, "unknown": 398},
    "vless": {"total": 618, "healthy": 156, "degraded": 60, "dead": 3, "quarantine": 0, "unknown": 399},
    "vmess": {"total": 24, "healthy": 18, "degraded": 2, "dead": 4, "quarantine": 0, "unknown": 0}
  },
  "countries": {
    "ID": {"total": 120, "healthy": 80, "degraded": 20, "dead": 10, "quarantine": 0, "unknown": 10},
    "unknown": {"total": 50, "healthy": 10, "degraded": 5, "dead": 2, "quarantine": 0, "unknown": 33}
  },
  "schema_version": 2
}
```

Health state dasar: `healthy`, `degraded`, `dead`, dan `quarantine`. Response `/nodes` hanya memuat node ID, protocol, host, port, nama, state, counters, dan latency; credential tidak pernah dikembalikan.
Jika CONNECT valid tetapi tidak ada kandidat yang tersedia, gateway mengembalikan `503 Service Unavailable` dengan cepat. Jika CONNECT ke kandidat gagal sebelum respons `200`, gateway mencoba kandidat berikutnya. Hopline baru mengirim `200 Connection Established` setelah upstream berhasil, sehingga retry tidak terjadi setelah byte client diteruskan.
Active probe opsional dikonfigurasi tanpa credential. Target wajib diisi agar node baru tidak tetap `unknown`; scheduler menjalankan probe melalui bounded queue dengan concurrency default 10:

```toml
[health]
mode = "http"
targets = ["http://cp.cloudflare.com/"]
interval = 300
timeout = 5
concurrency = 10
proxy_host = "127.0.0.1"
proxy_port = 18771
```

Mode `http` membuka CONNECT ke mixed inbound sing-box dengan auth user node, lalu meminta target melalui tunnel. CONNECT harus berhasil dan response target harus selesai dengan status HTTP numerik apa pun; status target tidak dinilai sebagai kesehatan provider. Timeout, gagal CONNECT, TLS, atau relay tetap gagal. Mode `tcp` tetap tersedia sebagai default. Service systemd hanya perlu akses jaringan keluar dan membaca config private; port control tetap localhost.

Untuk Shadowsocks dengan `v2ray-plugin`, Hopline meneruskan opsi plugin ke sing-box. Ini diperlukan untuk node WS/TLS seperti export Nekobox; tanpa field tersebut, node terlihat sehat pada TCP tetapi gagal saat handshake protocol.

### Strategi DNS

Hopline mendefinisikan resolver `dns-direct` untuk hostname relay/node dan satu `dns-remote-<node-id>` per node untuk query target. Setiap resolver remote memakai `8.8.8.8` dengan `detour` langsung ke outbound node yang sama. Rule DNS mencocokkan `auth_user`, sehingga query dari credential node A mengikuti outbound node A; tidak ada selector global untuk DNS target. `auth_user` dan password inbound tetap dipakai untuk routing CONNECT ke outbound node.

### Health probe dan diagnostic

Active health Hopline memakai HTTP/URL probe ringan melalui node yang diuji. Full download, download-only, upload-only, country, dan simple-download bukan polling health; mode tersebut memerlukan diagnostic command terpisah karena biaya traffic dan interpretasinya berbeda.

### Diagnostic geolocation

```text
checkip.com → ip.cc → cekipsaya.com?action=lookup&target={ip}
```

`cekipsaya` dikirim dengan `Referer: https://cekipsaya.com/cek-ip-saya/`. Hasil disimpan terpisah dari health pada registry: IP, country code/name, ASN, organisasi, provider, dan timestamp. `resolved=false` tetap dapat diterima bila response memiliki IP dan country yang valid. Lookup wajib dijalankan melalui tunnel node yang diuji; lookup dari mesin pemanggil hanya membuktikan IP mesin pemanggil. Provider failure atau hasil stale tidak mengubah health node dan belum mengaktifkan `country-*` routing otomatis.

`node-<id>` adalah forced routing: hanya node tersebut yang dicoba dan tidak ada fallback ke kandidat lain.

## Load dan acceptance smoke
### Smoke egress ephemeral

Jalankan smoke tanpa menyentuh service production. Runner membaca fixture lokal yang tidak boleh di-commit, membuat config dan listener ephemeral, memeriksa DNS bootstrap, menguji CONNECT dengan credential benar, lalu memastikan CONNECT tanpa `Proxy-Authorization` menghasilkan `407`:

```bash
PYTHONPATH=. python3 tools/smoke_ephemeral.py --fixture-dir . --timeout 20
```

Fixture yang diperlukan: `vless-node.txt`, `vmess-node.txt`, `trojan-node.txt`, dan `shadowsocks-node.txt`. Output runner tidak mencetak share link, UUID, password, atau credential.

Harness lokal tersedia tanpa node subscription nyata:

```bash
PYTHONPATH=. python3 experiments/f1/gateway_load.py
PYTHONPATH=. python3 experiments/f1/https_proxy_acceptance.py
```

Default load gate menjalankan 16 concurrent CONNECT dengan limit 4 per node: tepat 4 koneksi diterima dan sisanya mendapat `503 Service Unavailable`. Acceptance harness membuktikan CONNECT gateway → upstream proxy → origin lokal dan relay payload dua arah.

### Acceptance production PC

Untuk menguji node subscription yang sedang `healthy` melalui systemd production PC, gunakan harness redacted berikut. Harness hanya memakai Gateway lokal `127.0.0.1:18770`, memilih maksimal tiga node per protokol, memakai target HTTPS IP-echo, dan tidak mencetak server, port, UUID, password, URL subscription, atau share-link:

```bash
sudo -u hopline env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  python3 tools/production_acceptance.py \
  --config /etc/hopline/hopline.toml --per-protocol 3
```

Exit code `0` berarti semua protokol memiliki jumlah sampel yang diminta dan seluruh forced route berhasil. Exit code `1` berarti acceptance berjalan tetapi ada protokol yang kekurangan node healthy atau request gagal. `vmess` dapat berstatus belum teruji jika pool health-nya belum memiliki node eligible; hasil itu bukan bukti parser atau generator rusak.

## Installation host Linux

Run as root on the local Linux production host when installing the systemd service. Keep source, config, and runtime state separate:

```bash
groupadd --system hopline
useradd --system --gid hopline --home-dir /var/lib/hopline --shell /usr/sbin/nologin hopline
install -d -o root -g root -m 0755 /opt/hopline/app
install -d -o hopline -g hopline -m 0700 /var/lib/hopline
install -d -o root -g hopline -m 0750 /etc/hopline
install -o hopline -g hopline -m 0600 hopline.toml /etc/hopline/hopline.toml
install -o root -g root -m 0644 packaging/hopline.service /etc/systemd/system/hopline.service
systemctl daemon-reload
systemctl enable --now hopline.service
```

Install `sing-box` pada path system-wide yang dapat dibaca user `hopline`, misalnya `/usr/local/bin/sing-box`, lalu pastikan `sing_box_binary` menunjuk ke path tersebut. Binary di `/home/ubuntu/.local/bin` tidak dapat dipakai service karena `ProtectHome=true`.
Set `PYTHONPATH=/opt/hopline/app` in the service environment or install the package into the service Python environment. The service reads private config from `/etc/hopline`, writes SQLite state only to `/var/lib/hopline`, and keeps control API, gateway, and sing-box listeners bound to localhost. Never put subscription URLs or node credentials in unit files, shell history, logs, or repository files.
Production validation scope is local-only: use the systemd service on `127.0.0.1:18770-18773`. Do not use SSH or another host for tests, smoke runs, deployment, restart, or validation unless the user explicitly requests that remote operation in the same message.

Operational checks:

```bash
systemctl status hopline.service
journalctl -u hopline.service --since=-10m --no-pager
PYTHONPATH=/opt/hopline/app python3 -m hopline doctor --db /var/lib/hopline/hopline.db --json
PYTHONPATH=/opt/hopline/app python3 -m hopline status --json
curl http://127.0.0.1:18773/metrics
curl --proxy http://127.0.0.1:18770 --proxytunnel https://target.example

Rollback: stop the service, restore the previous `/opt/hopline/app` tree and `/etc/hopline/hopline.toml`, then run `systemctl restart hopline.service`. Existing SQLite state is retained.

## Metrics opsional

Metrics Prometheus disabled-by-default. Aktifkan pada `[health]`:

```toml
metrics_enabled = true
metrics_host = "127.0.0.1"
metrics_port = 18773
```

Endpoint `GET http://127.0.0.1:18773/metrics` hanya bind localhost dan menyediakan node count, health-state count, per-protocol node count, serta status active probe. Label dibatasi pada enum health state dan protocol; server tidak mengekspos host, port, node ID, URL, atau credential.

Scrape dan retention dimiliki Prometheus eksternal; Hopline hanya mengekspos gauge current-state dan tidak menyimpan time-series sendiri. Contoh job untuk satu VPS:

```yaml
scrape_configs:
  - job_name: hopline
    scrape_interval: 15s
    static_configs:
      - targets: ["127.0.0.1:18773"]
```

```bash
prometheus --storage.tsdb.retention.time=15d
```

Lihat ADR-012 untuk batas cardinality dan kebijakan retention.

## Batasan

- Bukan VPN level jaringan.
- Bukan residential proxy atau alat anti-deteksi.
- Tidak memodifikasi isi traffic.
- Pengguna bertanggung jawab memastikan penggunaan node subscription mematuhi ketentuan penyedia.
