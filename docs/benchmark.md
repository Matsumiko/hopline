# Benchmark

Benchmark ini in-process: tidak memakai subscription, node, atau credential, sehingga angka dapat dibandingkan antar mesin dan aman di-commit.

## Menjalankan

```bash
PYTHONPATH=. python3 tools/benchmark.py --rounds 3 --json
```

Setiap skenario membuat upstream proxy palsu dan gateway `127.0.0.1` dengan port ephemeral.

## Skenario

| Skenario | Yang diukur |
|---|---|
| `admission` | 64 CONNECT bersamaan dengan limit 8 per node: berapa diterima, ditolak `503`, dan berapa lama. |
| `relay_throughput` | 64 chunk × 16 KiB dialirkan dua arah; throughput efektif (MiB/s). |
| `generation_swap` | 16 stream aktif lalu generation baru dipublish: berapa stream tetap hidup, waktu publish, waktu drain setelah stream ditutup. |

## Hasil acuan (2026-10-21, local Linux)

```text
python=3.12.3 rounds=2
admission           accepted=8  elapsed_ms p50=42.0
relay_throughput    p50=144.6 MiB/s
generation_swap     streams_alive=16/16  swap_publish_ms p50=0.0
```

## Cara membaca

- `admission.accepted` **harus** sama dengan `limit_per_node`; kalau tidak, ada bug admission, bukan masalah performa.
- `streams_alive` **harus** sama dengan `connections`; nilai lebih rendah berarti regresi lifecycle.
- `swap_publish_ms` kecil karena publish hanya menukar referensi; drain sebenarnya menunggu lease, bukan blocking pada swap.
- Throughput bergantung CPU dan jumlah copy; jangan bandingkan antar mesin dengan spesifikasi berbeda.

## Batas

- Angka ini mengukur gateway Python, bukan egress node nyata.
- Tidak mengukur latency jaringan, TLS handshake node, atau throughput provider.
- Untuk uji node nyata, gunakan `tools/production_acceptance.py` (lihat [acceptance-status.md](acceptance-status.md)).
- Hasil bisa berbeda bila `max_active_connections` atau ukuran chunk diubah; catat parameter saat membandingkan.
