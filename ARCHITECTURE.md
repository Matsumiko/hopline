# Hopline Architecture

## Tujuan Arsitektur

Menyediakan satu HTTP proxy lokal yang memilih egress node per koneksi, memantau health, dan melakukan failover hanya sebelum byte client diteruskan. Deployment target adalah satu service Python asyncio yang mengelola sing-box sebagai subprocess.

## Boundary

```text
┌────────────────────────────────────────────────────────┐
│ Hopline process                                        │
│                                                        │
│  Gateway ── Picker ── Scorer ── Health state          │
│     │         │          │                            │
│     └──── TunnelEngine ──┴── Storage                  │
│                    │                                   │
│                  Syncer                                │
└────────────────────┼───────────────────────────────────┘
                     ▼
              sing-box subprocess
                     ▼
                 egress node
```

### Modul

- **Gateway:** menerima HTTP proxy dan `CONNECT`, membaca username, melakukan relay dua arah, dan menjaga backpressure.
- **Picker:** menyaring kandidat berdasarkan mode, health, kapasitas, dan tujuan; mengembalikan kandidat berurutan.
- **Scorer:** menyimpan state health, sliding window, EWMA, cooldown, hysteresis, dan feedback koneksi.
- **Checker:** menjalankan active probe dan menerima hasil pasif dari gateway.
- **Syncer:** fetch subscription, parse, validasi, dedup, tagging, dan sinkronisasi registry.
- **TunnelEngine:** adapter lifecycle sing-box, generator config, generation management, healthcheck, dan crash detection. Reload tidak boleh mengganggu stream aktif.
- **Storage:** SQLite untuk subscription, node, health, history terbatas, dan sticky session.
- **Control:** API token-protected dan CLI operator.

Semua modul berada dalam satu process sampai bukti skala atau ownership mengharuskan pemisahan. Tidak ada network hop internal antar modul Hopline.

## Alur CONNECT

1. Gateway menerima koneksi client.
2. Gateway parse `Proxy-Authorization` dan username routing.
3. Picker mengembalikan kandidat node yang sesuai.
4. Gateway membuka koneksi ke inbound sing-box dengan credential node.
5. Gateway menyelesaikan handshake tunnel.
6. Jika gagal sebelum byte client diteruskan, gateway melaporkan failure dan mencoba kandidat berikutnya sesuai budget.
7. Gateway baru mengirim `200 Connection Established` setelah tunnel siap.
8. Gateway merelay byte dua arah dengan backpressure dan half-close.
9. Setelah forwarding dimulai, kegagalan diteruskan; tidak ada retry otomatis.
10. Hasil koneksi dilaporkan ke Scorer.

## Alur Sinkronisasi

```text
subscription URL
  → bounded fetch + ETag/Last-Modified
  → parser protocol/format
  → validate + stable ID + dedup
  → compare node set
  → publish new engine generation for new connections
  → drain old generation without closing active streams
```

Status health tidak menyebabkan reload atau restart engine. Jika engine yang dipakai tidak mendukung generation swap tanpa memutus stream, perubahan config ditunda sampai aman atau membutuhkan maintenance eksplisit; Hopline tidak memutus stream aktif untuk mengejar update.

## Generation dan Stream Ownership

- Gateway menandai koneksi sebagai `pre_forward` sampai tunnel siap dan byte client pertama diteruskan.
- Setelah forwarding dimulai, koneksi memiliki owner generation dan tidak boleh dipindahkan.
- Generation baru hanya menerima koneksi baru.
- Generation lama dihentikan hanya setelah jumlah koneksi aktifnya nol.
- Shutdown normal menunggu generation aktif dan generation lama selesai; timeout shutdown menghasilkan status operasional yang jelas, bukan retry traffic.
## Invariant

1. Default bind hanya `127.0.0.1`.
2. `200 Connection Established` berarti tunnel telah siap.
3. Tidak ada retry setelah byte client diteruskan.
4. **Hopline tidak memutus stream aktif karena lifecycle atau config update.**
5. Config node baru memakai generation baru; generation lama di-drain sampai koneksinya selesai.
6. Jika engine tidak mendukung generation swap, update config ditunda ketika ada stream aktif.
7. Health state tidak memicu reload/restart engine aktif.
8. Secret tidak keluar dari boundary secret handling.
9. Pool kosong menghasilkan 503 bounded, bukan hang.
10. Stream tidak dibuffer seluruhnya di memory.
11. Sticky session dapat direbind ketika node terikat tidak tersedia.

## Data Ownership

| Data | Pemilik |
|---|---|
| Canonical node dan subscription | Syncer/Storage |
| Health per node dan target group | Scorer/Storage |
| Kandidat koneksi | Picker, dari state Scorer |
| Sticky binding | Picker/Storage |
| sing-box runtime config | TunnelEngine |
| Client byte stream | Gateway, tidak dipersistenkan |

## Dependency Utama

- Python 3.11+ dan `asyncio`.
- SQLite.
- YAML dan Pydantic untuk konfigurasi.
- sing-box sebagai tunnel engine.

Versi dan feasibility fitur sing-box harus dibuktikan di Fase 0 sebelum interface runtime dianggap stabil.

## Trade-off

Modular monolith dipilih karena target deployment kecil, kebutuhan koordinasi state tinggi, dan biaya operasional microservices tidak memberi manfaat pada fase awal. sing-box tetap subprocess karena menyediakan implementasi protokol tunnel dan dapat diganti di belakang `TunnelEngine` jika kebutuhan terbukti.
