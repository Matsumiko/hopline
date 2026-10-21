# Acceptance Status

Acceptance membuktikan jalur egress end-to-end, bukan jaminan uptime per node. Angka di bawah adalah bukti terakhir yang tercatat, bukan target permanen.

## Ringkasan terakhir (2026-10-18, production PC lokal)

| Family | SS | Trojan | VLESS | VMess | Total |
|---|---|---|---|---|---|
| IPv4 `api4.ipify.org` | 3/5 | 4/5 | 3/5 | 4/5 | **14/20** |
| IPv6 `api6.ipify.org` | 5/5 | 5/5 | 4/5 | 1/5 | **15/20** |

Kedua address family berfungsi lintas protokol. Kegagalan bersifat per-node (variability provider), bukan cacat routing, parser, atau generator.

## Interpretasi status

| Kondisi | Arti |
|---|---|
| `passed: true` | Semua sampel per protokol terpenuhi dan seluruh forced route sukses. |
| `missing_protocol_samples` | Pool healthy untuk protokol tersebut kurang dari `--per-protocol`. Bukan bukti kerusakan. |
| `request_failed` | Node gagal saat diuji (timeout, TLS, handshake). Node bisa saja hidup saat probe tapi mati saat acceptance. |
| `exit_ip_family_mismatch` | Target family tidak cocok; dihitung gagal untuk target tersebut. |

## Menjalankan ulang

```bash
sudo -u hopline env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  python3 tools/production_acceptance.py \
  --config /etc/hopline/hopline.toml --per-protocol 5 \
  --target 'https://api4.ipify.org?format=json'
```

Ulangi dengan `api6.ipify.org` untuk family IPv6. Output hanya memuat protokol, node ID, status, exit IP, latency, dan verdict — tidak ada credential.

## Hal yang tidak dibuktikan acceptance

- Kestabilan jangka panjang (angka ini snapshot, bukan uptime).
- Throughput atau kualitas bandwidth.
- Destination selain target probe (sebagian node gagal ke `api.ipify.org` tetapi lolos ke health target).
- Jaminan IPv6 untuk VMess: coverage tipis dan bergantung komposisi subscription.

## Risiko yang masih terbuka

| Risiko | Status |
|---|---|
| Egress per-node tidak 100% stabil | open — dilacak di [PROGRESS.md](../PROGRESS.md) |
| VMess IPv6 terbatas (1/5 pada sampel) | open — best-effort sampai sumber VMess IPv6 bertambah |
| Country metadata belum terisi penuh | in progress — rate limit provider geolocation |
