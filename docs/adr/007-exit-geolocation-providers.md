# ADR-007: Exit-IP Geolocation Provider Fallback

- **Status:** accepted untuk diagnostic country Fase 3
- **Scope:** lookup lokasi IP exit dan metadata observability; bukan active health
- **Evidence:** response contract provider yang diuji melalui `checkip.com`, `ip.cc`, dan `cekipsaya.com` lookup

## Context

Country node tidak boleh disimpulkan dari negara server speed-test, hostname relay, atau Cloudflare Ray ID. Country routing membutuhkan lokasi IP exit yang benar-benar diamati melalui outbound node. Provider geolocation gratis dapat rate-limit, gagal, atau mengubah response.

## Decision

Hopline menyediakan adapter geolocation dengan fallback berurutan:

1. `https://checkip.com/api/v1/ip?ip={ip}`
2. `https://ip.cc/webapi/product/api-ip-address?language=en&ip={ip}`
3. `https://cekipsaya.com/api/?action=lookup&target={ip}` dengan `Referer` yang sesuai

Response harus mengembalikan IP yang sama dengan IP input dan country code ISO-3166 alpha-2. `cekipsaya` memakai field `country` seperti `Poland (PL)`; `resolved=false` tidak menggagalkan hasil jika IP dan country tersedia.

Hasil disimpan di tabel `geolocation`, terpisah dari health, dengan IP, country, ASN, organisasi, provider, dan timestamp. Credential node, URL subscription, dan secret tidak disimpan di hasil diagnostic atau error fallback. Command `hopline geo --config <file> --node <id> --json` memperoleh IP melalui HTTPS self-IP request yang melewati Gateway dengan username `node-<id>` dan password lokal Hopline.

## Consequences

- Provider dapat diganti tanpa mengubah domain model.
- Fallback meningkatkan peluang diagnostic berhasil tetapi tetap memerlukan rate-limit/freshness policy sebelum dipakai sebagai filter country.
- Lookup harus dijalankan melalui tunnel node yang diuji; lookup IP dari VPS hanya diagnostic terhadap VPS.
- Hasil country tidak mengubah state health.
- `country-*` routing belum dianggap selesai sampai lookup melalui outbound node, cache freshness, dan empty-pool behavior memiliki acceptance test.

## Alternatives rejected

- Cloudflare Ray ID sebagai lokasi: identifier request, bukan country result.
- Country dari speed-test server: lokasi server test bukan lokasi IP exit.
- Satu provider tanpa fallback: terlalu rapuh terhadap rate limit dan provider outage.

## Confirmation

- Unit tests memvalidasi normalisasi CheckIP, fallback ke ip.cc dan cekipsaya, IP mismatch rejection, Referer lookup, self-IP request melalui route node, secret safety, dan SQLite persistence.
- Runtime country routing tetap gated sampai country picker, cache freshness, dan empty-pool behavior memiliki acceptance test.
