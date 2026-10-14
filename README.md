# Hopline

Hopline adalah gateway proxy lokal yang memilih node sehat dari subscription VMess, VLESS, Trojan, atau Shadowsocks, lalu meneruskan koneksi HTTP/HTTPS melalui sing-box.

Hopline ditujukan untuk developer atau tim kecil yang menjalankan script/bot di VPS dan membutuhkan satu endpoint proxy lokal tanpa mengubah routing jaringan VPS.

> **Status:** Fase 1 sedang berjalan. Runtime vertical slice, HTTP subscription fetch, dan multi-protocol snapshot Syncer tersedia; scheduler berkala, CLI, health scoring, dan failover belum selesai.

## Dokumen Utama

- [PRD](PRD_Hopline.md) — tujuan, scope, requirement, dan acceptance criteria.
- [Architecture](ARCHITECTURE.md) — boundary modul, alur runtime, dan invariant.
- [Roadmap](ROADMAP.md) — fase, gate, dan urutan pengerjaan.
- [Progress](PROGRESS.md) — status faktual, bukti, risiko, dan next action.
- [Changelog](CHANGELOG.md) — perubahan yang sudah terjadi.
- [Contributing](CONTRIBUTING.md) — aturan kontribusi dan verifikasi.
- [Security](SECURITY.md) — aturan secret, privasi, dan pelaporan masalah.
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

Package runtime tersedia di `hopline/`. Parser share-link VLESS, Trojan, VMess, dan Shadowsocks, structured parser Clash YAML/sing-box JSON, bounded subscription fetch, SQLite registry dengan removed hysteresis tiga sync, conditional validators, last-valid fallback, config generation, generation-aware sing-box engine, HTTP CONNECT gateway, rotate, sticky routing process-local, node routing, drain, scheduler dasar, dan CLI sudah diuji. Sticky memakai username `sticky-<sessionId>`, TTL idle default 10 menit, dan rebind ke node sehat sebelum CONNECT 200 jika binding lama dead atau tidak eligible. Lihat [PROGRESS.md](PROGRESS.md) untuk bukti dan pekerjaan berikutnya.

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
gateway_port = 18770
tunnel_port = 18771
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
Untuk affinity per sesi, gunakan username proxy `sticky-<sessionId>`, misalnya `sticky-job-42`. Binding hanya hidup di proses Gateway dan hilang saat restart; TTL diperpanjang ketika koneksi berhasil dipakai. `node-<id>` tetap forced tanpa fallback, sedangkan `rotate` tetap memilih ulang per koneksi.
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

Command ini membuka request HTTPS ke endpoint self-IP melalui Gateway memakai route `node-<node-id>`, lalu mengirim IP hasilnya ke fallback geolocation dan menyimpan metadata non-secret ke SQLite. `--exit-ip-url` dapat mengganti endpoint self-IP yang kompatibel mengembalikan `{"ip":"..."}`. Command gagal jika node tidak ada, Gateway tidak berjalan, atau response tidak berisi IP valid.


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

Health state dasar: `healthy`, `degraded`, `dead`, dan `quarantine`. Response hanya memuat node ID, protocol, host, port, nama, state, counters, dan latency; credential tidak pernah dikembalikan.
Gateway memilih node `healthy` atau `degraded` yang tidak sedang cooldown; node `dead` dan `quarantine` dilewati. Kegagalan pertama memberi cooldown 30 detik. Tiga kegagalan berturut-turut memindahkan node ke `dead`; active probe mencoba ulang dengan backoff 1, 2, 5, 15, lalu 60 menit. Satu sukses memulihkan node ke `degraded`, dan tiga sukses berturut-turut memulihkannya ke `healthy`.
Jika CONNECT valid tetapi tidak ada kandidat yang tersedia, gateway mengembalikan `503 Service Unavailable` dengan cepat. Jika CONNECT ke kandidat gagal sebelum respons `200`, gateway mencoba kandidat berikutnya. Hopline baru mengirim `200 Connection Established` setelah upstream berhasil, sehingga retry tidak terjadi setelah byte client diteruskan.
Active probe opsional dikonfigurasi tanpa credential. Target wajib diisi agar node baru tidak tetap `unknown`; scheduler menjalankan probe melalui bounded queue dengan concurrency default 10:

```toml
[health]
mode = "http"
targets = ["https://provider.example/health"]
interval = 300
timeout = 5
concurrency = 10
proxy_host = "127.0.0.1"
proxy_port = 18771
```

Mode `http` membuka CONNECT ke mixed inbound sing-box dengan auth user node, lalu meminta target melalui tunnel dan menerima status HTTP `2xx`–`3xx` sebagai sehat. Mode `tcp` tetap tersedia sebagai default. Service systemd hanya perlu akses jaringan keluar dan membaca config private; port control tetap localhost.

Untuk Shadowsocks dengan `v2ray-plugin`, Hopline meneruskan opsi plugin ke sing-box. Ini diperlukan untuk node WS/TLS seperti export Nekobox; tanpa field tersebut, node terlihat sehat pada TCP tetapi gagal saat handshake protocol.

### Strategi DNS

Hopline mendefinisikan resolver `dns-direct` untuk hostname relay/node dan satu `dns-remote-<node-id>` per node untuk query target. Setiap resolver remote memakai `8.8.8.8` dengan `detour` langsung ke outbound node yang sama. Rule DNS mencocokkan `auth_user`, sehingga query dari credential node A mengikuti outbound node A; tidak ada selector global untuk DNS target. `auth_user` dan password inbound tetap dipakai untuk routing CONNECT ke outbound node.

### Health probe dan diagnostic

Active health Hopline memakai HTTP/URL probe ringan melalui node yang diuji. Full download, download-only, upload-only, country, dan simple-download bukan polling health; mode tersebut memerlukan diagnostic command terpisah karena biaya traffic dan interpretasinya berbeda.

### Diagnostic geolocation

```text
checkip.com → ip.cc → cekipsaya.com?action=lookup&target={ip}
```

`cekipsaya` dikirim dengan `Referer: https://cekipsaya.com/cek-ip-saya/`. Hasil disimpan terpisah dari health pada registry: IP, country code/name, ASN, organisasi, provider, dan timestamp. `resolved=false` tetap dapat diterima bila response memiliki IP dan country yang valid. Lookup wajib dijalankan melalui tunnel node yang diuji; lookup dari VPS hanya membuktikan IP VPS. Provider failure atau hasil stale tidak mengubah health node dan belum mengaktifkan `country-*` routing otomatis.

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

## Installation host Linux

Run as root on a dedicated VPS. Keep source, config, and runtime state separate:

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

Endpoint `GET http://127.0.0.1:18773/metrics` hanya bind localhost dan menyediakan node count, health-state count, serta status active probe. Label dibatasi pada enum health state; server tidak mengekspos host, port, node ID, URL, atau credential.

## Batasan

- Bukan VPN level jaringan.
- Bukan residential proxy atau alat anti-deteksi.
- Tidak memodifikasi isi traffic.
- Pengguna bertanggung jawab memastikan penggunaan node subscription mematuhi ketentuan penyedia.
