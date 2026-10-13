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
- **TunnelEngine:** adapter lifecycle sing-box, generator config, reload, healthcheck, dan crash detection.
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
  → SQLite registry
  → regenerate/reload sing-box only when connection config changes
```

Status health tidak menyebabkan reload config.

## Invariant

1. Default bind hanya `127.0.0.1`.
2. `200 Connection Established` berarti tunnel telah siap.
3. Tidak ada retry setelah byte client diteruskan.
4. Reload sing-box tidak dipicu perubahan health saja.
5. Secret tidak keluar dari boundary secret handling.
6. Pool kosong menghasilkan 503 bounded, bukan hang.
7. Stream tidak dibuffer seluruhnya di memory.
8. Sticky session dapat direbind ketika node terikat tidak tersedia.

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
