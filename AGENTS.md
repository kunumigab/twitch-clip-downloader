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
├── Dockerfile                     # usado por podman build
├── twitch-clip-downloader.container  # unit Quadlet (systemd)
├── twitch-clip-downloader.timer      # timer systemd (ejecución periódica)
├── requirements.txt
├── config.example.json  # copia a config.json y edita
├── src/
│   └── downloader.py    # lógica principal
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
# Podman (recomendado)
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
- `--since YYYY-MM-DD`: solo clips creados desde esa fecha (por defecto: últimos 30 días).
- `--max N`: máximo de clips por canal por ejecución.
- `--dry-run`: lista lo que descargaría sin descargar.

## Estado del proyecto

- [x] Estructura inicial, Dockerfile, config de ejemplo
- [x] Listado de clips vía API Helix con paginación
- [x] Descarga con yt-dlp organizada por fecha + metadatos JSON
- [x] Estado persistente (`output/.downloaded.json`) para no re-descargar
- [ ] Subida automática a YouTube (pendiente, requiere OAuth de YouTube)
- [x] Programación periódica vía timer de systemd + Quadlet (`twitch-clip-downloader.timer`)
- [ ] Renombrado/plantillas de título para YouTube

## Notas y decisiones

- Los clips de Twitch caducan (~14-60 días según el canal); conviene ejecutar periódicamente.
- La API Helix requiere token de app (client credentials), no de usuario.
- Los nombres de archivo se sanean (sin caracteres ilegales en Windows).
- El estado se guarda en `output/.downloaded.json`; borrarlo fuerza re-descarga.

## Historial

- 2026-11-14: Creación inicial del proyecto (Python + yt-dlp + Helix API + Docker).
- 2026-11-14: Docker reemplazado por Podman + Quadlet (unit `.container` + `.timer`).
