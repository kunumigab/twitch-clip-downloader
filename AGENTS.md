# Twitch Clip Downloader

Herramienta para descargar automáticamente los clips de uno o varios canales de Twitch,
organizarlos por fecha de creación y conservar el título como contexto (para subirlos
luego a YouTube u otra plataforma).

## Stack recomendado

**Python 3.12** + **Podman** (con Quadlet para systemd)

- `yt-dlp`: descarga los clips (soporta URLs de clips de Twitch de forma nativa).
- API Helix de Twitch (`requests`): lista los clips de un canal con título, fecha y URL.
- Sin base de datos: un archivo de estado JSON evita re-descargas.
- Podman + Quadlet: imagen única, portable, rootless y gestionada por systemd (timer incluido).

Alternativas consideradas:
- Node.js: viable, pero el soporte de Twitch en yt-dlp (Python) es más robusto.
- TwitchDownloaderCLI: es lo que usas manualmente; se puede invocar desde Docker,
  pero añade un binario externo y es más frágil en automatización.

## Estructura

```
.
├── AGENTS.md            # este archivo (seguimiento del proyecto)
├── README.md            # documentación de uso
├── Dockerfile                     # usado por podman build y por CI
├── .github/workflows/build.yml    # CI: build + push a ghcr.io
├── twitch-clip-downloader.container  # unit Quadlet (systemd)
├── twitch-clip-downloader.timer      # timer systemd (ejecución periódica)
├── requirements.txt
├── config.example.json  # copia a config.json y edita
├── src/
│   ├── downloader.py    # lógica principal
│   ├── youtube_auth.py  # autorización OAuth de canales de YouTube
│   └── youtube_upload.py # subida de vídeos a YouTube
└── output/              # clips descargados (montado como volumen)
    └── YYYY-MM-DD/
        ├── <fecha>_<titulo>_<id>.mp4
        └── <fecha>_<titulo>_<id>.json   # metadatos (título, url, fecha, canal)
```

## Configuración

1. Crea una app en https://dev.twitch.tv/console/apps (tipo "Confidential").
   Obtén `Client ID` y `Client Secret`.
2. Copia `config.example.json` a `config.json` y rellena credenciales y canales.
3. O usa variables de entorno: `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`,
   `TWITCH_CHANNELS=canal1,canal2`.

## Uso

```bash
# Podman con imagen de GHCR (recomendado; la publica GitHub Actions)
podman pull ghcr.io/OWNER/REPO:latest
podman run --rm -v ./output:/app/output:Z -v ./config.json:/app/config.json:ro,Z ghcr.io/OWNER/REPO:latest

# O build local
podman build -t twitch-clip-downloader:latest .
podman run --rm -v ./output:/app/output:Z -v ./config.json:/app/config.json:ro,Z twitch-clip-downloader:latest

# Quadlet (systemd, rootless): ver cabecera de twitch-clip-downloader.container
#   cp twitch-clip-downloader.container twitch-clip-downloader.timer ~/.config/containers/systemd/
#   systemctl --user daemon-reload && systemctl --user enable --now twitch-clip-downloader.timer

# Local
pip install -r requirements.txt
python src/downloader.py --config config.json
```

Opciones:
- `--since YYYY-MM-DD` / `--until YYYY-MM-DD`: rango de fechas de creación.
- `--days N`: clips de los últimos N días.
- `--month YYYY-MM`: clips de un mes concreto.
- `--year YYYY`: clips de un año concreto.
- `--all`: descarga todos los clips, sin filtro de fecha.
- `--max N`: máximo de clips por canal por ejecución.
- `--dry-run`: lista lo que descargaría sin descargar.

## Estado del proyecto

- [x] Estructura inicial, Dockerfile, config de ejemplo
- [x] Listado de clips vía API Helix con paginación
- [x] Descarga con yt-dlp organizada por fecha + metadatos JSON
- [x] Estado persistente (`output/.downloaded.json` o en S3) para no re-descargar
- [x] Almacenamiento configurable: local (`output_dir`) o S3 compatible (AWS, MinIO, R2, B2...)
- [x] Subida automática a YouTube (OAuth por canal, `auto_upload`, `--no-upload`)
- [x] Programación periódica vía timer de systemd + Quadlet (`twitch-clip-downloader.timer`)
- [x] Renombrado/plantillas de título para YouTube (`youtube.title_template`)

## Notas y decisiones

- Los clips de Twitch caducan (~14-60 días según el canal); conviene ejecutar periódicamente.
- La API Helix requiere token de app (client credentials), no de usuario.
- Los nombres de archivo se sanean (sin caracteres ilegales en Windows).
- El estado se guarda en `output/.downloaded.json` (local) o en `s3://<bucket>/<prefix>/.downloaded.json` (modo S3); borrarlo fuerza re-descarga.
- En modo S3, `output_dir` actúa como staging temporal; con `keep_local: false` las copias locales se borran tras subir.

## Historial

- 2026-11-14: Creación inicial del proyecto (Python + yt-dlp + Helix API + Docker).
- 2026-11-14: Docker reemplazado por Podman + Quadlet (unit `.container` + `.timer`).
- 2026-11-14: CI con GitHub Actions: build y push de la imagen a ghcr.io.
- 2026-11-14: Imagen multi-arquitectura (linux/amd64 + linux/arm64) vía QEMU en CI.
- 2026-11-14: Almacenamiento configurable: local o S3 compatible (boto3), con estado también en S3.
- 2026-11-18: Filtros de fecha CLI (`--days`, `--month`, `--year`, `--since`/`--until`, `--all`).
- 2026-11-18: Timer de systemd documentado como modo automático/manual configurable (`OnCalendar=`).
- 2026-11-18: Fase 1 YouTube: `src/youtube_auth.py` autoriza canales (propios o de marca con rol admin/editor) vía OAuth y guarda refresh_tokens por perfil en `youtube_tokens.json`.
- 2026-11-18: Fase 2 YouTube: `src/youtube_upload.py` sube vídeos (`videos.insert`, resumable), con `--pending` (usa `channel_map` y `.uploaded.json`) o subida directa con `--profile`.
- 2026-11-18: Fase 3 YouTube: subida automática tras descarga en `downloader.py` (`youtube.auto_upload`, `--no-upload`); en modo S3 sube antes de borrar los locales.
- 2026-11-18: Fase 4 YouTube: `youtube.title_template` (`{title}`, `{channel}`, `{date}`, `{id}`) y documentación en README.
