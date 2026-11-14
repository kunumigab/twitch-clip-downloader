# Twitch Clip Downloader

Herramienta automática para descargar los clips de uno o varios canales de Twitch,
organizarlos por fecha de creación y conservar el título como contexto — pensada para
subirlos después a YouTube u otra plataforma.

## ¿Qué hace?

1. Se autentica contra la API de Twitch (Helix) con un token de aplicación
   (*client credentials*, no requiere login de usuario).
2. Resuelve el `broadcaster_id` de cada canal configurado.
3. Lista los clips del canal creados desde una fecha (por defecto, últimos 30 días),
   con paginación completa.
4. Descarga cada clip con `yt-dlp` y lo guarda en una carpeta por fecha:

   ```
   output/
   └── 2026-11-14/
       ├── 2026-11-14_Titulo_del_clip_AbCdEf.mp4
       └── 2026-11-14_Titulo_del_clip_AbCdEf.json   # metadatos
   ```

5. Escribe un `.json` de metadatos junto a cada vídeo (título, URL, fecha, canal,
   duración, vistas) para dar contexto al subirlo a otra plataforma.
6. Registra los IDs ya descargados en `output/.downloaded.json` para no repetir
   descargas en ejecuciones posteriores.

## Requisitos

- **Podman** (recomendado) o Python 3.12+ local.
- Una aplicación registrada en https://dev.twitch.tv/console/apps
  (tipo **Confidential**) para obtener `Client ID` y `Client Secret`.
  La URL de redirección OAuth no se usa (el flujo *client credentials* no redirige);
  puedes poner `http://localhost`.

## Configuración

Copia `config.example.json` a `config.json` y rellena:

```json
{
  "twitch": {
    "client_id": "TU_CLIENT_ID",
    "client_secret": "TU_CLIENT_SECRET",
    "channels": ["canal1", "canal2"]
  },
  "default_since_days": 30,
  "max_per_channel": 0,
  "output_dir": "output"
}
```

También puedes usar variables de entorno en lugar del archivo:
`TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TWITCH_CHANNELS=canal1,canal2`.

## Uso

### Podman (recomendado)

```bash
podman build -t twitch-clip-downloader:latest .
podman run --rm \
  -v ./output:/app/output:Z \
  -v ./config.json:/app/config.json:ro,Z \
  twitch-clip-downloader:latest
```

### Ejecución periódica con systemd (Quadlet, rootless)

```bash
mkdir -p ~/.config/containers/systemd
cp twitch-clip-downloader.container twitch-clip-downloader.timer ~/.config/containers/systemd/
# edita las rutas Volume= del .container a tu máquina
systemctl --user daemon-reload
systemctl --user enable --now twitch-clip-downloader.timer
```

El timer ejecuta el servicio a diario (`OnCalendar=daily`). Quadlet/systemd solo
funciona en Linux; en Windows usa WSL2 o Task Scheduler.

### Local

```bash
pip install -r requirements.txt
python src/downloader.py --config config.json
```

### Opciones

| Opción | Descripción |
|---|---|
| `--since YYYY-MM-DD` | Solo clips creados desde esa fecha (por defecto: últimos 30 días) |
| `--max N` | Máximo de clips por canal por ejecución (0 = sin límite) |
| `--dry-run` | Lista lo que descargaría sin descargar nada |

## Notas

- Los clips de Twitch caducan (~14–60 días según el canal): conviene ejecutar
  el bot periódicamente.
- Los nombres de archivo se sanean (sin caracteres ilegales en Windows).
- Borrar `output/.downloaded.json` fuerza la re-descarga de todo.
- La subida automática a YouTube está pendiente (requiere OAuth de YouTube).

## Estructura del proyecto

```
.
├── AGENTS.md                       # seguimiento del proyecto
├── Dockerfile                      # imagen (usada por podman build)
├── twitch-clip-downloader.container  # unit Quadlet (systemd)
├── twitch-clip-downloader.timer      # timer systemd (ejecución diaria)
├── requirements.txt
├── config.example.json
├── src/downloader.py               # lógica principal
└── output/                         # clips descargados (por fecha)
```
