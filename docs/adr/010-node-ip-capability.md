# ADR-010: Per-Node IP Family Capability

- **Status:** accepted untuk routing capability Fase 3
- **Scope:** capability egress IPv4/IPv6 per node; bukan pengganti health dan bukan jaminan destination universal
- **Evidence:** strict `api4.ipify.org`/`api6.ipify.org` acceptance menemukan node dual-family, IPv6-only, dan fail-both dalam pool production

## Context

Health menjawab apakah node dapat melewati target active probe. Acceptance production menunjukkan hasil dapat berbeda menurut node dan address family: beberapa node hanya berhasil pada IPv6, beberapa gagal pada kedua family, dan beberapa berhasil pada keduanya. Satu health target tidak cukup untuk menyimpulkan capability egress.

Hopline membutuhkan model dual-stack tanpa membuang node yang masih berguna. Capability disimpan terpisah dari health dan country metadata. Hanya IP yang terobservasi dan cocok dengan family probe yang menjadi capability positif. Kegagalan probe tidak menjadi capability negatif permanen; status kembali `unknown` setelah cache capability kedaluwarsa.

## Decision

Simpan capability IPv4 dan IPv6 secara terpisah per node, masing-masing dengan observed IP, checked timestamp, dan error terakhir. Capability fresh hanya berarti hasil probe family tersebut masih berlaku sampai `capability_max_age`; tidak berarti semua destination akan berhasil.

Tambahkan route eksplisit:

```text
ipv4
ipv6
ipv4-sticky-<sessionId>
ipv6-sticky-<sessionId>
```

`rotate`, `node-<id>`, country route, dan existing sticky route tetap mempertahankan perilaku. Route capability menyaring kandidat berdasarkan health, cooldown, dan capability fresh; pool kosong menghasilkan `503`. Forced `node-<id>` tetap tidak melakukan fallback dan tidak otomatis mengubah capability.

Capability collector memakai target IPv4/IPv6 yang dikonfigurasi, bounded concurrency, serta interval dan concurrency active health. Collector menyimpan hasil non-secret dan tidak mengubah health saat probe capability gagal.

## Consequences

- Node dual-stack, IPv4-only, IPv6-only, dan unknown dapat dibedakan tanpa menghapus node.
- Client yang memerlukan family tertentu harus memakai route capability eksplisit.
- Capability stale atau unknown tidak eligible pada route capability.
- Default `rotate` tetap backward-compatible dan dapat memilih node tanpa capability fresh.
- Probe target tetap merupakan evidence terbatas; capability bukan jaminan setiap destination atau protocol application-layer.
- Database schema bertambah satu table capability yang ikut lifecycle node.

## Alternatives rejected

- Menginfer family dari hostname, country, atau protocol: tidak membuktikan observed egress.
- Menjadikan health state sebagai capability: mencampur liveness target dengan address-family behavior.
- Mengeluarkan node IPv6-only dari registry: membuang egress yang masih valid.
- Memaksa semua request default ke IPv4 atau IPv6: merusak kompatibilitas client dan tujuan yang hanya mendukung satu family.

## Confirmation

- Unit tests memverifikasi persistence, freshness, family mismatch, picker filter, gateway routes, dan 503 saat capability pool kosong.
- Collector smoke memverifikasi successful IPv4/IPv6 observations dan failure isolation dari health.
- Production deployment hanya dilakukan setelah full suite dan local control/API smoke lulus.
