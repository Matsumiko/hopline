# PRD Hopline

Oct 13, 2026 · @matsumiko

## Ringkasan

Hopline adalah gateway proxy lokal yang mengubah kumpulan node langganan (VMess, VLESS, Trojan, Shadowsocks) menjadi satu endpoint HTTP. Aplikasi cukup menunjuk satu alamat proxy, dan Hopline memilih node yang sehat untuk setiap koneksi.

Jaringan VPS tidak berubah. Hanya request yang dikirim lewat Hopline yang keluar dengan IP node, sehingga geolokasi yang terbaca provider tujuan mengikuti node tersebut.

Hopline memakai sing-box sebagai mesin terowongan. Logika pemilihan node, pemantauan kesehatan, dan failover dikerjakan Hopline sendiri. Node mati atau lambat dihindari otomatis, dan kegagalan mendadak disembunyikan dari klien selama itu aman dilakukan.

| Item | Isi |
| --- | --- |
| Produk | Hopline, egress proxy gateway |
| Pengguna | Satu pengembang atau tim kecil yang menjalankan script atau bot di VPS |
| Endpoint utama | 127.0.0.1:18770 (HTTP proxy, mendukung CONNECT) |
| Mesin terowongan | sing-box di 127.0.0.1:18771 |
| Bahasa | Python 3.11+ (asyncio) |
| Pengembangan | 4 fase, dari MVP sampai operasional |

## Latar belakang dan masalah

Pengguna ingin request ke API provider AI keluar lewat IP negara tertentu tanpa membeli proxy residential dan tanpa mengubah jaringan VPS. Node langganan sudah dimiliki, tetapi cara memakainya belum nyaman.

Masalah yang diselesaikan:

- Klien seperti NekoRay mengaktifkan satu node pada satu waktu. Semua request ikut node itu, padahal tiap request mungkin perlu node berbeda.
- Daftar node berubah mengikuti URL subscription, dan sebagian node mati atau lambat tanpa pemberitahuan.
- Node bisa hidup tetapi diblokir provider tertentu, jadi cek hidup atau mati saja tidak cukup.
- Node yang mati mendadak membuat request gagal. Mengulang POST ke API AI secara sembarangan bisa menimbulkan biaya ganda.
- Tidak ada satu tempat untuk melihat kondisi seluruh node.

Hopline menjawabnya dengan satu lapisan gateway: mengambil node otomatis, menilai kesehatannya, memilih per koneksi, dan pindah node saat gagal.

## Tujuan, non-tujuan, dan metrik

Hopline berhasil kalau aplikasi cukup menunjuk satu proxy URL dan selalu keluar lewat node yang sehat tanpa kerja manual.

**Tujuan**

- Satu endpoint lokal yang memilih node per koneksi (rotate, sticky, per negara, atau node tertentu).
- Sinkronisasi node otomatis dari satu atau lebih URL subscription.
- Pemantauan kesehatan per node dan per grup tujuan, dengan eject instan saat gagal.
- Failover transparan untuk kegagalan sebelum request terkirim.
- Jaringan VPS tidak berubah.

**Non-tujuan**

- Bukan proxy residential: IP tetap IP datacenter milik node, dan jumlahnya terbatas.
- Bukan alat anti-deteksi atau pemalsuan fingerprint.
- Bukan VPN level jaringan, hanya proxy per koneksi.
- Tidak memeriksa atau memodifikasi isi traffic (tanpa MITM).
- Tidak mencatat isi request, header, atau API key.

**Metrik keberhasilan**

| Metrik | Target |
| --- | --- |
| Koneksi gagal saat satu node dimatikan mendadak | Paling banyak 1-3 koneksi total, tanpa error terlihat untuk koneksi baru |
| Respons saat semua node mati | 503 yang jelas dalam beberapa detik (usulan: 5 detik atau kurang), bukan menggantung |
| Kerja manual setelah subscription diatur | Nol |
| Menambah klien baru | Satu baris proxy URL |
| POST yang sudah terkirim | Tidak pernah di-retry otomatis |
| Secret di log | Nol, diverifikasi tes otomatis |
| Resource saat idle | Cukup ringan untuk VPS kecil (angka batas ditetapkan setelah Fase 1) |

## Pengguna dan use case

Pengguna utama adalah satu pengembang yang menjalankan script, bot, atau SDK di VPS dan sekaligus mengoperasikan Hopline. Klien adalah aplikasi apa pun yang bisa diarahkan ke proxy HTTP. Klien memilih perilaku routing lewat username proxy.

| Use case | Username proxy | Perilaku |
| --- | --- | --- |
| Tiap request memakai node berbeda | rotate | Node baru per koneksi dari pool yang sehat |
| Satu pekerjaan butuh IP konsisten | sticky-job42 | Node sama selama TTL (default 10 menit), pindah otomatis jika node mati |
| Provider hanya menerima negara tertentu | country-sg | Hanya node bertag Singapura |
| Negara tertentu dan IP konsisten | country-sg-sticky-job42 | Gabungan dua mode di atas |
| Debug satu node | node-\<id> | Paksa node itu, tanpa fallback |

Contoh pemakaian:

```bash
export HTTPS_PROXY=http://rotate:x@127.0.0.1:18770
curl https://api.ipify.org
```

## Arsitektur dan alur request

Request klien melewati gateway, picker, dan tunnel engine. Empat tugas latar belakang menjaga registry, health, dan konfigurasi engine.

```mermaid
flowchart LR
    C[Client] --> G[Gateway :18770]
    G --> P[Picker]
    P --> T[sing-box :18771]
    T --> N[Selected egress node]
    S[Syncer] --> D[(SQLite registry)]
    D --> P
    D --> E[Config generator]
    E --> T
    K[Checker] --> H[Scorer]
    G --> H
    H --> D
```

Gateway meminta kandidat node dari Picker, lalu membuka tunnel ke inbound milik generation aktif sing-box dengan ID node sebagai username. Scorer menerima hasil koneksi nyata dari gateway dan hasil probe dari Checker. Syncer menjaga registry node. Perubahan config mem-publish generation baru pada listener lokal yang berbeda; generation lama tetap tersedia untuk koneksi yang sudah terikat sampai drain selesai.

### Keputusan: mesin tunnel, generation, dan port

Mesin tunnel default adalah sing-box. Routing per username lewat inbound mixed dan rule `auth_user` adalah fitur bawaannya, dan itu inti desain Hopline. Syncer sudah mem-parse format Clash sendiri, jadi kelebihan mihomo (membaca subscription Clash langsung) tidak dibutuhkan.

- Kode mesin dipisah di balik interface kecil: membuat config generation, start, healthcheck, publish, drain, dan stop. `reload` in-place tidak menjadi primitive stream-preserving.
- Setiap generation sing-box memakai listener localhost yang unik. Gateway menyimpan registry generation → port dan memilih generation aktif hanya untuk koneksi baru.
- Generation lama tidak dihentikan sampai active connection count-nya nol. Jika jumlah port atau resource tidak mencukupi, sync menunggu dan tidak memutus stream.
- Health state tidak membuat generation baru dan tidak me-reload sing-box. Generation baru hanya dibuat saat parameter koneksi atau himpunan node berubah.
- Prasyarat Fase 1: tes di VPS bahwa satu inbound mixed dengan beberapa user mengarahkan tiap user ke outbound yang berbeda pada versi sing-box yang dipakai, lalu tes generation swap dengan koneksi aktif.

Port default berada di rentang 18000-19000, di bawah range ephemeral Linux (32768-60999) dan menjauhi port umum tool proxy lain. Semua port bisa diubah lewat konfigurasi, terikat ke 127.0.0.1, dan diperiksa oleh hopline doctor.

| Fungsi | Port default |
| --- | --- |
| Gateway Hopline (dipakai klien) | 18770 |
| Mesin tunnel sing-box (internal) | 18771 |
| Control API Hopline | 18772 |
| API kontrol mesin (internal, untuk delay test) | 18773 |

## Persyaratan fungsional

Hopline terdiri dari tujuh modul. Angka default boleh diubah lewat konfigurasi.

### Syncer

- FR-S1: Mengambil banyak URL subscription secara berkala (default 45 menit, dengan jitter). Memakai ETag atau If-Modified-Since bila tersedia, timeout 20 detik, dan mempertahankan salinan valid terakhir jika fetch gagal.
- FR-S2: Mem-parse daftar link base64 (vmess, vless, trojan, ss), Clash YAML, dan sing-box JSON. Entri rusak diabaikan tanpa crash. Ada batas jumlah node (default 2000) dan ukuran body.
- FR-S3: ID node stabil berupa hash pendek dari protokol, server, port, uuid atau password, dan parameter transport utama. Tidak memakai nama atau urutan.
- FR-S4: Node identik antar subscription digabung (dedup).
- FR-S5: Node yang hilang ditandai removed setelah 3 sync berturut-turut tidak muncul, lalu dihapus.
- FR-S6: Tag otomatis per node: negara (dari nama node, dikonfirmasi lookup IP keluar), subscription asal, dan protokol.
- FR-S7: Config sing-box dibuat ulang dan di-reload hanya jika himpunan node atau parameter koneksinya berubah, tidak pernah karena perubahan status kesehatan.

### Checker

- FR-C1: Probe aktif lewat endpoint delay Clash API dan atau request HTTPS nyata lewat node, ke target probe (default: endpoint umum dan host provider AI dari konfigurasi). Konkurensi default 10, jadwal dengan jitter, interval berbeda per state.
- FR-C2: Menemukan IP keluar tiap node (IP, negara, ASN bila ada) dan menandai node yang IP keluarnya kembar.
- FR-C3: Menerima feedback pasif dari gateway: sukses, gagal, dan latensi tiap koneksi nyata.
- FR-C4: Kesehatan dilacak per pasangan (node, grup tujuan). Ada grup default "\*" dan grup tambahan dari konfigurasi, karena node yang sehat untuk satu tujuan bisa diblokir di tujuan lain.

### Scorer

Scorer menyimpan sliding window 20 hasil terakhir dan EWMA latensi per node (dan per grup tujuan), lalu menghasilkan skor numerik untuk pemilihan berbobot. State: healthy, degraded, quarantine, dead.

| Kondisi | Hasil |
| --- | --- |
| 3 kegagalan berturut-turut | dead seketika, dikeluarkan dari traffic nyata, probe segera dipicu |
| Success rate di bawah 70% pada window, atau EWMA latensi lebih dari 2x median pool | degraded |
| Node dead | quarantine, tes ulang dengan backoff 1, 2, 5, 15, 60 menit |
| 1 probe sukses dari quarantine | degraded |
| 3 sukses berturut-turut dari degraded | healthy (hysteresis agar tidak flapping) |
| Setelah satu kegagalan | cooldown 30 detik sebelum node bisa dipilih lagi |

### Picker

- FR-P1: Kandidat adalah node healthy untuk grup tujuan, disaring sesuai mode (country, node, sticky).
- FR-P2: Power of two choices: ambil 2 kandidat acak berbobot, pilih yang EWMA latensinya lebih rendah atau koneksi aktifnya lebih sedikit.
- FR-P3: Mengembalikan daftar kandidat berurutan (utama dan cadangan), bukan satu node.
- FR-P4: Ada batas koneksi aktif per node. Node yang jenuh dilewati.
- FR-P5: Panic mode: jika node healthy kurang dari 20% pool, node degraded ikut dipilih.
- FR-P6: Tanpa kandidat, kembalikan 503 dengan pesan jelas dalam hitungan detik.

### Gateway

- FR-G1: HTTP proxy asinkron di 127.0.0.1:18770, mendukung CONNECT (HTTPS) dan forwarding HTTP biasa. SOCKS5 opsional di tahap lanjut.
- FR-G2: Username dibaca dengan grammar di bawah. Username tidak valid dijawab 407 atau 400 dengan pesan yang membantu.
- FR-G3: Rantai ke sing-box: gateway membuka koneksi ke 127.0.0.1:18771, mengirim CONNECT dengan Proxy-Authorization Basic (ID node dan secret), lalu menyalurkan byte dua arah.
- FR-G4: Klien menerima 200 Connection Established hanya setelah tunnel benar-benar siap.
- FR-G5: Backpressure dan half-close ditangani dengan benar, memori tidak tumbuh pada stream panjang (SSE), dan shutdown menunggu koneksi aktif selesai.
- FR-G5a: Setelah byte client diteruskan, Hopline **MUST NOT** memutus stream aktif karena sync, perubahan health, rotasi, config update, atau generation swap. POST yang sudah terkirim dan SSE yang sedang berjalan tidak boleh dibuat gagal oleh lifecycle Hopline.
- FR-G5b: Config node baru memakai generation baru. Koneksi baru diarahkan ke generation aktif; generation lama tetap melayani koneksi yang sudah terikat sampai koneksi selesai, lalu baru dihentikan.
- FR-G5c: Jika engine tidak mendukung swap tanpa gangguan pada listener, Hopline **MUST NOT** melakukan reload/restart otomatis saat ada stream aktif. Update ditunda atau service masuk maintenance tanpa memutus koneksi aktif.
- FR-G6: Bind ke 127.0.0.1 secara default. Jika dibuka ke luar, autentikasi wajib dan sistem memberi peringatan.

| Username | Arti |
| --- | --- |
| rotate | Pilih ulang node tiap koneksi |
| sticky-\<sessionId> | Node sama selama sesi, TTL idle default 10 menit, diperpanjang setelah CONNECT sukses; state process-local |
| country-<cc> | Hanya node dengan country code geolocation yang fresh dan cocok |
| country-<cc>-sticky-<sessionId> | Country filter lalu sticky/rebind hanya dalam country pool |
| node-\<nodeId> | Paksa satu node, tanpa fallback |

### Control API dan CLI

Control API berjalan di port terpisah (usulan 127.0.0.1:18772) dan dilindungi token.

- GET /status, GET /nodes, GET /nodes/{id}, GET /metrics (format Prometheus).
- POST /sync, POST /nodes/{id}/disable, POST /nodes/{id}/enable, POST /nodes/{id}/probe.
- CLI: hopline run, sync, status, nodes, test (request lewat gateway dan tampilkan IP keluar), dan doctor (cek binary sing-box, port, validitas config, konektivitas).

Kegagalan sebelum byte klien diteruskan dapat disembunyikan melalui failover. Setelah byte klien diteruskan, koneksi telah menjadi tanggung jawab relay dan lifecycle Hopline tidak boleh memutuskannya.

Invariant tegas:

> Hopline tidak pernah memutus stream aktif karena sync, reload, rotasi, perubahan health, atau generation swap. POST yang sudah terkirim tidak boleh gagal karena Hopline sendiri.

Generation swap adalah mekanisme perubahan config: generation baru menerima koneksi baru, generation lama tetap hidup sampai semua koneksi yang telah terikat selesai. Jika swap tanpa gangguan tidak tersedia, perubahan config ditunda; jangan mengorbankan stream aktif.

| Situasi | Tindakan |
|---|---|
| Connect atau handshake gagal sebelum byte klien diteruskan | Laporkan kegagalan ke Scorer, coba kandidat berikutnya (maksimal 3 percobaan) |
| Node pertama belum menjawab dalam sekitar 1,5 detik | Hedged connect: jalankan kandidat kedua paralel, pakai yang selesai lebih dulu, batalkan yang lain |
| Node mati setelah byte klien diteruskan | Tidak ada retry otomatis; error diteruskan ke klien |
| Sync/config berubah saat stream aktif | Generation baru untuk koneksi baru; generation lama di-drain tanpa memutus stream |
| Engine hanya mendukung reload yang memutus stream | Tunda update atau maintenance eksplisit; **jangan reload otomatis** |
| POST ke API AI sudah terkirim | Tidak pernah di-retry otomatis, mencegah biaya atau aksi ganda |
| Stream (SSE) putus di tengah karena upstream | Tidak dilanjutkan, error diteruskan; Hopline tidak boleh menjadi penyebab putus |
| Banyak node gagal bersamaan | Retry budget global (sekitar 10% dari koneksi terakhir) mencegah retry storm |
| Semua node tidak tersedia | 503 cepat dengan pesan jelas, tanpa menggantung |

Aturan pendukung:

- Timeout fase connect pendek (default 3 detik). Timeout fase baca respons panjang dan bisa diatur, karena respons AI bisa lama. Streaming tidak di-buffer.
- Eject instan: setiap kegagalan koneksi nyata langsung memperbarui Scorer, tanpa menunggu jadwal probe.
- Klien menerima 200 Connection Established hanya setelah tunnel siap, jadi failover terlihat klien sebagai koneksi yang sedikit lebih lambat, bukan error.
- Setiap hasil koneksi dilaporkan ke Scorer, sehingga pemilihan berikutnya langsung memakai data terbaru.

### Kontrak health test dan diagnostic

Hopline membedakan tes liveness ringan dari diagnostic berbiaya tinggi. Active health scheduler hanya memakai HTTP/URL probe melalui outbound node yang sedang diuji: CONNECT ke target, request HTTP bounded, timeout, dan status response yang diharapkan. Node healthy berarti tunnel dan request probe berhasil sesuai policy; hasil latency dicatat terpisah dari status health.

Mode diagnostic seperti full download/upload, country lookup, dan simple download tidak dijalankan periodik oleh health scheduler. Mode tersebut membutuhkan traffic nyata, dependency endpoint eksternal, atau interpretasi metadata tambahan. Jika ditambahkan ke CLI, hasilnya harus dipisahkan sebagai diagnostic dan tidak boleh mengubah health node tanpa policy eksplisit.

Country dari server pengujian bukan bukti negara IP keluar. Verifikasi negara harus memakai endpoint geolocation yang memang mengembalikan IP/negara dan dicatat sebagai hasil diagnostic terpisah. Adapter baseline memakai fallback `checkip.com` → `ip.cc` → `cekipsaya.com?action=lookup&target={ip}`. Response `cekipsaya` dengan `resolved=false` tetap dapat diterima jika IP dan country valid. Hasil wajib memiliki freshness policy; provider failure atau hasil stale tidak mengubah health node. Command `hopline geo --config <file> --node <id> --json` memperoleh self-IP melalui route `node-<id>` pada Gateway, lalu menyimpan metadata geolocation non-secret.

## Persyaratan non-fungsional

Angka berlabel usulan adalah titik awal dan divalidasi lewat load test di Fase 4.

| Aspek | Persyaratan |
| --- | --- |
| Performa | Overhead gateway per koneksi kecil dibanding latensi node. Load test 200 koneksi bersamaan (usulan) melaporkan tingkat gagal dan perilaku failover |
| Keandalan | Restart otomatis sebagai service. Status node dipulihkan setelah restart. Crash sing-box terdeteksi dan di-restart |
| Resource | Ringan saat idle dan cocok untuk VPS kecil. Tidak ada pertumbuhan memori pada stream panjang |
| Skala | Sampai 2000 node (batas default) dan beberapa ratus koneksi bersamaan (usulan) |
| Kompatibilitas | Klien apa pun yang mendukung HTTP proxy dengan CONNECT, termasuk lewat env var HTTPS\_PROXY. Target Linux x86\_64 dan arm64 (usulan) |
| Portabilitas | Docker tidak wajib. Dockerfile dan unit systemd disediakan |
| Pemeliharaan | Type hints di semua kode, fungsi kecil yang bisa diuji, dependensi minimal dan umum dipakai |
| Pengujian | Seluruh tes berjalan tanpa akses jaringan (sing-box dan server subscription di-mock) |

## Model data, konfigurasi, dan persistensi

Data disimpan di SQLite supaya Hopline tidak lupa node mana yang mati setelah restart. Skema memakai tabel versi atau migrasi sederhana.

| Entitas | Isi utama |
| --- | --- |
| Subscription | Nama, URL (disimpan sebagai secret), ETag, waktu sync terakhir, hasil sync |
| Node | ID stabil, protokol, server, port, kredensial (secret), tag (negara, sumber, protokol), status removed, IP keluar, negara, ASN |
Generation swap dan invariant stream aktif diatur oleh FR-G5a–FR-G5c dan bagian Resilience. Entitas data tidak memiliki kewenangan untuk memutus koneksi aktif.
- Timeout dan ambang state machine: semua angka di bagian Scorer.
- Batas: retry budget dan koneksi maksimum per node.
- Logging: level, format, dan direktori data.

## Keamanan dan privasi

URL subscription, UUID atau password node, token Control API, dan secret Clash API tidak boleh muncul di log, metrik, pesan error, maupun repositori. Hopline hanya mencatat apa yang dibutuhkan untuk operasi.

- Penyimpanan secret: file konfigurasi berizin 0600 dan direktori data tidak dapat dibaca pengguna lain. Setiap output yang menampilkan secret dimasking.
- Log: hanya timestamp, ID node, host tujuan (tanpa path dan query), hasil, dan latensi. Tidak ada URL lengkap, header, atau isi request.
- Input tidak tepercaya: isi subscription divalidasi (ukuran, port, format field) dan tidak pernah dieksekusi atau di-eval.
- Jaringan: gateway, inbound sing-box, dan Clash API terikat ke 127.0.0.1. Clash API dan Control API memakai secret atau token.
- Binary sing-box: skrip instal memverifikasi checksum unduhan.
- Pembukaan ke luar: bila gateway diatur tidak di 127.0.0.1, autentikasi wajib dan sistem memberi peringatan keras.
- Verifikasi: ada tes otomatis yang memeriksa bahwa output log tidak mengandung secret.

Pemakaian node langganan untuk traffic otomatis dalam jumlah besar bisa melanggar ketentuan penyedia node. Pengguna perlu memeriksa aturan penyedianya sebelum dipakai.

## Observability dan operasional

Kondisi pool harus terlihat dalam hitungan detik tanpa membaca log.

- Metrik Prometheus di GET /metrics: success rate, latensi, koneksi aktif, dan state per node, serta jumlah retry, jumlah 503, dan hasil sync secara global.
- Log kejadian penting: node dead, node pulih, sync, dan retry, dalam format teks atau JSON.
- hopline status dan hopline nodes untuk ringkasan pool dari terminal. hopline doctor memeriksa binary sing-box, port, validitas config, dan konektivitas.
- Dashboard web kecil bersifat opsional dan masuk daftar pengembangan lanjut.

Operasional:

- Berjalan sebagai service (unit systemd) atau container (Dockerfile), dengan restart otomatis.
- Hopline mengelola sing-box sebagai subprocess: start, reload mulus, dan restart bila crash.
- Config sing-box dibuat otomatis dan di-reload hanya ketika himpunan node berubah.
- Skrip instal dan README dengan quickstart disediakan di Fase 4.

## Pengujian dan kriteria penerimaan

Seluruh tes harus lulus tanpa akses jaringan, sehingga siap dipakai di CI.

- Tes unit: parser share-link (valid, rusak, kasus tepi), pembuatan ID stabil, transisi state machine, backoff, hysteresis, grammar username, dan Picker (power of two choices, panic mode, kesehatan per grup).
- Tes integrasi dengan node palsu yang bisa dimatikan, diperlambat, atau menolak koneksi: failover transparan, hedged connect, eject instan, tidak ada retry setelah byte terkirim, retry budget, 503 cepat, dan rebind sticky saat node mati.
- Tes streaming (respons panjang mirip SSE) untuk memastikan tidak ada buffering dan tidak ada timeout prematur.
- Skrip load test (contoh 200 koneksi bersamaan) yang melaporkan tingkat gagal dan perilaku failover.

**Kriteria penerimaan**

| Kriteria | Cara verifikasi |
| --- | --- |
| Dengan HTTPS\_PROXY=http://rotate:x@127.0.0.1:18770, memanggil URL IP-echo menghasilkan IP keluar yang berbeda dari IP VPS | hopline test dan pengecekan manual |
| Mematikan satu node di tengah tes menghasilkan paling banyak 1-3 koneksi gagal total, tanpa error terlihat untuk koneksi baru | Tes integrasi dengan node palsu |
| POST yang sudah terkirim tidak pernah di-retry otomatis | Tes integrasi |
| Semua node mati menghasilkan 503 yang cepat dan jelas, bukan hang | Tes integrasi |
| Node ditambah atau dihapus di subscription terdeteksi pada sync berikutnya, tanpa reload sing-box yang tidak perlu | Tes syncer dan generator config |
| Tidak ada secret di log | Tes yang memeriksa output log |
| Gateway idle memakai CPU dan RAM rendah | Pengukuran di VPS kecil |

## Fase pengembangan dan roadmap

Pengembangan berjalan sebagai vertical slice berurutan. Setiap fase memiliki output yang dapat dijalankan, kriteria penerimaan, dan catatan bukti di [PROGRESS.md](PROGRESS.md). Fase berikutnya tidak dimulai sebelum gate fase sebelumnya lulus atau risiko yang tersisa disetujui secara eksplisit.

### Fase 0 — Feasibility sing-box

Output: eksperimen lokal yang membuktikan satu inbound mixed dengan beberapa user dapat merutekan koneksi ke outbound berbeda berdasarkan `auth_user` pada versi sing-box yang dipilih.

Gate F0:

- Dua user menghasilkan dua jalur outbound yang benar.
- HTTP `CONNECT` berhasil melalui inbound sing-box.
- Harness generation membuktikan stream lama tetap hidup dan koneksi baru memakai generation baru.
- In-place `SIGHUP` yang memutus stream tercatat sebagai perilaku yang tidak boleh dipakai untuk preserve stream.
- Secret tidak muncul pada output proses atau error.
- Hasil dan versi binary dicatat di [PROGRESS.md](PROGRESS.md).

### Fase 1 — Vertical slice MVP

Output: satu subscription → parser → registry SQLite → config sing-box → gateway HTTP CONNECT → request keluar melalui node.

Scope wajib: satu subscription, parser empat protokol, stable node ID, dedup, `rotate`, `node-<id>`, `hopline test`, `hopline doctor`, dan redaction secret.

Gate F1:

- Dengan credential lokal `[auth]`, `HTTPS_PROXY=http://hopline:PASSWORD@127.0.0.1:18770` menghasilkan IP node, bukan IP VPS.
- Node dapat dipaksa dengan `node-<id>`.
- Semua node mati menghasilkan 503 cepat dan jelas.
- Config node baru dipublish sebagai generation baru; generation lama tidak diputus sampai koneksi aktifnya nol.
- Sync tanpa perubahan tidak membuat generation baru atau reload.
- Tes berjalan tanpa akses jaringan menggunakan fixture dan mock.
- Active-stream preservation dan secret redaction terverifikasi.

### Fase 2 — Health dan failover

Output: active/passive health, state machine, cooldown, pre-forward failover, dan 503 saat pool kosong. Active health memakai HTTP/URL probe ringan per node. Full/download/upload/country/simple-download adalah diagnostic on-demand dan bukan polling health default.

Gate F2: kegagalan sebelum byte client diteruskan dapat berpindah kandidat; tidak ada retry setelah byte diteruskan; node mati dieject instan; stream panjang tidak dibuffer.

### Fase 3 — Routing dan control plane

Output: sticky TTL, country routing, health per grup tujuan, control API, CLI status/nodes, dan metrik Prometheus.

Gate F3: grammar username, sticky rebind, country filter, endpoint control yang terlindungi token, serta observabilitas pool dapat diverifikasi offline.

### Fase 4 — Operasional

Output: systemd, Dockerfile, restart/reload sing-box, SQLite migration, load test, instalasi, dan quickstart.

Gate F4: service dapat dipulihkan setelah crash, load test target dilaporkan, secret scan lulus, dan dokumentasi deployment lengkap.

Fase 0 dan Fase 1 adalah prioritas awal. Fitur intelligence, routing tambahan, dashboard, dan SOCKS5 tidak boleh menggeser pembuktian jalur proxy dasar.

## Risiko, asumsi, dan pertanyaan terbuka

**Risiko**

| Risiko | Dampak | Mitigasi |
| --- | --- | --- |
| IP node adalah IP datacenter dan bisa dideteksi atau diblokir provider | Request ditolak atau dibatasi | Status kesehatan per grup tujuan, pilih negara yang didukung, batasan ini dinyatakan jelas sebagai non-tujuan |
| Banyak node dalam satu langganan berbagi IP keluar yang sama | Rotasi tidak benar-benar mengganti IP | Deteksi IP keluar kembar dan tandai di data node |
| Penyedia node membatasi atau melarang traffic otomatis | Akun langganan diblokir | Pengguna memeriksa ketentuan penyedia, batasi koneksi per node |
| Format subscription berubah atau berisi data berbahaya | Sync gagal atau parser disalahgunakan | Validasi ketat, batas ukuran, simpan salinan valid terakhir |
| Library HTTP memakai ulang koneksi (keep-alive) | Rotasi per koneksi tidak terasa per request | Dokumentasikan: matikan pooling atau buat sesi baru per request |
| Retry berlebihan memperparah gangguan | Beban menumpuk di sedikit node | Retry budget global dan panic mode |

**Asumsi**

- Pengguna menjalankan Hopline di VPS Linux dan memiliki URL subscription yang sah.
- Binary sing-box stabil tersedia dan mendukung fitur routing berdasarkan auth\_user serta Clash API.
- Tujuan utama adalah API provider AI melalui HTTPS (tunnel CONNECT).

### Keputusan awal

- HTTP proxy dengan `CONNECT` adalah interface utama sampai ada kebutuhan terukur untuk SOCKS5.
- Rotate berlaku per koneksi proxy, bukan otomatis per HTTP request; connection pooling client harus didokumentasikan.
- Retry hanya boleh terjadi sebelum byte client diteruskan ke tunnel.
- POST, SSE, dan traffic setelah forwarding tidak pernah di-retry otomatis.
- Hopline memakai modular monolith Python asyncio; sing-box dikelola sebagai subprocess melalui adapter kecil.
- Health state tidak memicu reload sing-box; reload hanya dipicu perubahan node atau parameter koneksi.

### Pertanyaan terbuka

- Berapa batas koneksi aktif per node yang aman untuk subscription yang dipakai? Tetapkan lewat load test F4.
- Provider AI mana saja yang masuk target probe awal? Tetapkan sebelum F2 active probe.
- Apakah dashboard web diperlukan? Default: tidak; CLI dan Prometheus cukup sampai ada kebutuhan operasional nyata.

Pertanyaan terbuka dicatat di [PROGRESS.md](PROGRESS.md) dan tidak boleh diselesaikan hanya melalui asumsi implementasi.

## Protokol pembangunan dan pencatatan

Dokumen pembangunan adalah bagian dari deliverable, bukan catatan opsional:

- [README.md](README.md): orientasi dan quickstart yang ditujukan untuk pengguna.
- [ARCHITECTURE.md](ARCHITECTURE.md): batas modul, alur runtime, dan invariant sistem.
- [ROADMAP.md](ROADMAP.md): urutan milestone dan gate yang dapat diverifikasi.
- [PROGRESS.md](PROGRESS.md): status faktual, bukti, keputusan terbuka, dan pekerjaan berikutnya.
- [CHANGELOG.md](CHANGELOG.md): perubahan yang sudah terjadi, bukan rencana.
- [CONTRIBUTING.md](CONTRIBUTING.md): alur kerja, aturan perubahan, dan verifikasi.
- [SECURITY.md](SECURITY.md): batas keamanan, secret handling, dan pelaporan masalah.
- [AGENTS.md](AGENTS.md): instruksi untuk sesi pembangunan berbantuan agen.
- [docs/adr/README.md](docs/adr/README.md): indeks keputusan arsitektur.

Aturan sesi:

1. Baca `AGENTS.md`, `PROGRESS.md`, dan dokumen yang relevan sebelum mengubah kode.
2. Klaim implementasi harus memiliki bukti berupa test, smoke run, atau output eksperimen; rencana diberi label planned.
3. Setelah perubahan selesai, update `PROGRESS.md` dan `CHANGELOG.md` bila perilaku atau artefak publik berubah.
4. Keputusan yang mengubah boundary, dependency, lifecycle, atau kontrak dicatat sebagai ADR sebelum atau bersamaan dengan implementasi.
5. Pekerjaan yang belum selesai tidak boleh ditulis sebagai selesai; gunakan status `planned`, `in progress`, `blocked`, atau `done`.

Status PRD: baseline produk dan arsitektur awal. Status implementasi aktual selalu mengikuti [PROGRESS.md](PROGRESS.md).
