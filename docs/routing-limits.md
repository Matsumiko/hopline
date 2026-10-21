# Routing and Failover Limits

Batasan ini sengaja dipilih; perilaku di luar batas bukan bug yang belum diperbaiki.

## Batas failover

| Situasi | Perilaku |
|---|---|
| CONNECT ke node gagal sebelum `200` dikirim ke client | Gateway mencoba kandidat berikutnya (bounded). |
| Upstream sudah mengirim `200` | **Tidak ada retry.** Kegagalan diteruskan ke client. |
| Byte client sudah diteruskan | **Tidak ada retry**, tidak ada rebind, tidak ada pindah generasi. |
| Pool kosong / semua cooldown | `503` cepat, tanpa menunggu. |
| `node-<id>` forced | Tanpa fallback; gagal = gagal. |
| Sticky | Rebind hanya sebelum forwarding dan hanya ke node eligible. |

## Batas rotasi

`rotate` memilih node **per koneksi proxy**, bukan per request HTTP. Client yang memakai connection pooling (keep-alive) dapat mengirim banyak request pada satu koneksi dan tetap memakai node yang sama. Untuk rotasi per request, client harus membuka koneksi proxy baru atau mematikan pooling.

## Batas routing

| Route | Batas |
|---|---|
| `country-<cc>` | Hanya memakai metadata geolocation yang **fresh** (`country_max_age`) dan cocok. Node tanpa metadata tidak eligible. |
| `ipv4` / `ipv6` | Hanya node dengan capability probe **fresh** dan IP valid. Capability bukan jaminan semua destination. |
| `sticky-<session>` | Binding in-memory; hilang saat proses restart. TTL idle, bukan TTL absolut. |
| `node-<id>` | Node harus ada di generasi aktif; node yang di-drop karena tidak kompatibel tidak dapat dipilih. |

## Batas health vs performa

Probe health (`healthy`/`degraded`/`dead`) hanya berasal dari active/passive probe. Kegagalan relay dicatat di `performance.conn_failures` dan **tidak** mengubah state. Konsekuensi: node bisa `healthy` tetapi sering gagal relay; gunakan `performance.success_rate` dan `latency_ewma_ms` untuk kualitas.

Health probe juga destination-specific: lolos `cp.cloudflare.com` bukan berarti lolos semua target.

## Batas lifecycle

- Generation baru hanya melayani koneksi baru.
- Generation lama dihentikan setelah **semua lease** dilepas.
- Jika generation baru gagal start, generation lama tetap aktif dan signature tidak diperbarui sehingga sync berikutnya mencoba lagi.
- Shutdown normal menunggu drain; tidak ada pemutusan paksa stream aktif.
