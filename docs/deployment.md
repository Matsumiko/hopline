# Deployment

Tiga jalur pemasangan: installer systemd (disarankan), container, dan manual.

## Prasyarat

- Linux dengan systemd (installer) atau Docker/Podman (container)
- Python 3.11+ (installer) atau image `python:3.12-slim` (container)
- `sing-box` **1.14.3** pada PATH; versi lain belum divalidasi
- File config private mode `0600`

## Opsi 1 — Installer systemd (disarankan)

```bash
sudo HOPLINE_INSTALL_START=0 bash packaging/install.sh
sudoedit /etc/hopline/hopline.toml     # isi [auth] dan [[subscriptions]]
sudo HOPLINE_INSTALL_START=1 bash packaging/install.sh
```

Installer bersifat idempoten:

| Aksi | Perilaku |
|---|---|
| User/group `hopline` | dibuat jika belum ada |
| `/opt/hopline/app` | diganti dari source; tree lama dibackup ke `/var/backups/hopline/app-<UTC>` |
| `/etc/hopline/hopline.toml` | **tidak pernah ditimpa**; dibuat dari `hopline.toml.example` hanya jika belum ada |
| `/var/lib/hopline` | dibuat `0700`, tidak dibersihkan |
| Unit systemd | dipasang, `enable`; service hanya di-restart bila `HOPLINE_INSTALL_START=1` |

Override path bila perlu:

```bash
sudo APP_DIR=/opt/hopline/app CONFIG_DIR=/etc/hopline STATE_DIR=/var/lib/hopline \
     UNIT_DIR=/etc/systemd/system HOPLINE_INSTALL_START=1 bash packaging/install.sh
```

Installer menolak jalan bila `sing-box` tidak ada di PATH.

## Opsi 2 — Container

```bash
docker build --build-arg SING_BOX_VERSION=1.14.3 -t hopline:local .

docker run -d --name hopline \
  --network host \
  -v /etc/hopline/hopline.toml:/etc/hopline/hopline.toml:ro \
  -v /var/lib/hopline:/var/lib/hopline \
  hopline:local
```

Catatan:

- `--network host` diperlukan karena gateway, control, dan metrics sengaja bind `127.0.0.1`. Dengan bridge network, port hanya terlihat di dalam container.
- Image berjalan sebagai user `hopline` (non-root) dengan `PYTHONDONTWRITEBYTECODE=1`.
- `HEALTHCHECK` memeriksa control API di `127.0.0.1:18772`.
- `sing-box` diunduh saat build dan dipin lewat `SING_BOX_VERSION`; naikkan versi secara eksplisit.
- Jangan mount `.env` atau credential lain ke image.

## Opsi 3 — Manual

Ikuti [README.md](../README.md#installation-host-linux). Ringkasnya: buat user/group, salin `hopline/` ke `/opt/hopline/app`, pasang config `0600`, pasang unit dari `packaging/hopline.service`, lalu `systemctl enable --now hopline.service`.

## Setelah terpasang

```bash
systemctl status hopline.service
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18772/login   # 200
curl -s http://127.0.0.1:18773/metrics | head
```

Panel: `http://127.0.0.1:18772` (login memakai `[auth]`).

## Upgrade

```bash
sudo HOPLINE_INSTALL_START=1 bash packaging/install.sh
```

Skema SQLite dimigrasi otomatis saat start. Migrasi bersifat aditif dan idempoten; database dari versi lebih baru ditolak, bukan dipakai dengan kolom yang hilang. Untuk rollback, lihat [generation-recovery.md](generation-recovery.md).

## Verifikasi pasca-deploy

```bash
sudo -u hopline env PYTHONPATH=/opt/hopline/app python3 -m hopline doctor --db /var/lib/hopline/hopline.db --json
```

Pastikan `sing_box: true` dan `schema_version` sama dengan `SQLiteRegistry.SCHEMA_VERSION`.
