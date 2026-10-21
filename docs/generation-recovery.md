# Generation Failure Recovery

Prosedur saat start generation baru gagal, saat generasi lama tidak kunjung drain, atau saat service berhenti melayani.

## Perilaku otomatis yang sudah ada

| Kejadian | Yang dilakukan Hopline |
|---|---|
| `sing-box check` menolak config | Generation baru **tidak** dipublish; generation lama tetap aktif. |
| Proses sing-box mati sebelum listener terbuka | Proses dibersihkan, error dicatat, generation lama tetap aktif. |
| Node tidak kompatibel | Node di-drop dari generation; dicatat di log `node(s) dropped`. |
| Sync gagal seluruhnya | `run` keluar dengan status `2`; systemd me-restart service. |

Artinya kegagalan publish **tidak** memutus koneksi yang sedang berjalan. Yang bisa terjadi adalah egress baru ikut gagal bila generation lama juga bermasalah.

## Diagnosis cepat

```bash
systemctl status hopline.service
sudo journalctl -u hopline.service --since '-15 min' --no-pager | grep -E 'rejected|dropped|Traceback|exited'
ls -1 /var/lib/hopline/engine/          # generation aktif + yang drain
ss -ltn | grep -E ':1877[0-9]'
```

Tanda-tanda:

- `sing-box config rejected` → config tidak valid (biasanya field node/provider). Generation lama tetap jalan.
- `sing-box exited before listener opened` → binary/path/port bermasalah, atau config lolos check tapi gagal runtime.
- `node(s) dropped (sing-box-incompatible)` → node tertentu tidak bisa dipakai; bukan kegagalan global.
- Tidak ada listener `18771+` → generation tidak pernah naik.
- `NRestarts` naik terus → crash-loop; lihat langkah di bawah.

## Prosedur pemulihan

### 1. Generation baru gagal, generation lama masih melayani

Tidak perlu tindakan darurat. Perbaiki penyebab lalu picu sync ulang:

```bash
# Setelah memperbaiki config/node sumber
curl -s -X POST -u "hopline:$AUTH" http://127.0.0.1:18772/sync
```

Jika masalah berasal dari subscription, hapus sumber bermasalah lewat panel atau `POST /subscriptions/delete`.

### 2. Generation lama tidak kunjung drain

Generation lama hanya berhenti saat lease terakhir dilepas. Jika drain berjalan lama, itu berarti masih ada stream aktif — **bukan hang**. Periksa:

```bash
curl -s -u "hopline:$AUTH" http://127.0.0.1:18772/nodes | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["nodes"]))'
```

Jangan mematikan service untuk "menyelesaikan" drain; itu justru memutus stream yang sedang dilindungi.

### 3. Service crash-loop

```bash
sudo systemctl stop hopline.service
sudo journalctl -u hopline.service -n 100 --no-pager
```

Kemudian validasi config tanpa menyentuh service:

```bash
PYTHONPATH=/opt/hopline/app python3 -m hopline doctor --db /var/lib/hopline/hopline.db --json
```

Jika penyebabnya perubahan source terakhir, rollback app tree:

```bash
sudo systemctl stop hopline.service
sudo mv /opt/hopline/app /opt/hopline/app.broken
sudo cp -a /var/backups/hopline/app-<TIMESTAMP> /opt/hopline/app
sudo systemctl start hopline.service
```

### 4. Semua node tidak eligible

Health state tersimpan di SQLite. Untuk mengembalikan node yang terkarantina manual:

```bash
curl -s -X POST -u "hopline:$AUTH" http://127.0.0.1:18772/nodes/<node-id>/enable
```

Untuk memaksa probe ulang satu node:

```bash
curl -s -X POST -u "hopline:$AUTH" http://127.0.0.1:18772/nodes/<node-id>/probe
```

### 5. Registry rusak atau tidak konsisten

SQLite memakai WAL. Backup sebelum intervensi:

```bash
sudo systemctl stop hopline.service
sudo cp -a /var/lib/hopline/hopline.db /var/backups/hopline/hopline.db-$(date -u +%Y%m%dT%H%M%SZ)
sudo sqlite3 /var/lib/hopline/hopline.db 'PRAGMA integrity_check;'
sudo systemctl start hopline.service
```

Registry dapat dibangun ulang dari subscription; health dan geolocation akan terbentuk kembali.

## Yang tidak boleh dilakukan

- Jangan `SIGKILL` sing-box atau daemon untuk mempercepat drain.
- Jangan mengubah config sambil menunggu drain; selesaikan satu siklus.
- Jangan menonaktifkan lease untuk "menghindari hang" — itu mengembalikan bug P0.
- Jangan menyalin credential node ke log, tiket, atau commit saat melaporkan insiden.
