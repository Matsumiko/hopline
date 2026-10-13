# Architecture Decision Records

ADR menyimpan alasan keputusan yang memengaruhi boundary, dependency, lifecycle, data ownership, atau kontrak Hopline.

## Status

- `proposed` — usulan belum menjadi baseline.
- `accepted` — keputusan menjadi baseline untuk scope yang disebutkan.
- `deprecated` — tidak lagi direkomendasikan.
- `superseded` — digantikan ADR lain.

## Index

| ID | Keputusan | Status |
|---|---|---|
| [ADR-001](001-modular-monolith-sing-box.md) | Modular monolith Python dengan sing-box sebagai tunnel subprocess | accepted untuk baseline Fase 0–1 |

## Aturan

- Jangan mengubah keputusan accepted secara diam-diam; buat ADR baru jika keputusan berubah.
- ADR tidak membuktikan implementasi. Bukti runtime dan gate dicatat di `PROGRESS.md`.
- Setiap ADR harus menyebut scope, konsekuensi, alternatif, dan cara konfirmasi.
