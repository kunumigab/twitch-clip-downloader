# Twitch Clip Downloader

Herramienta para descargar automáticamente los clips de uno o varios canales de Twitch,
organizarlos por fecha de creación y conservar el título como contexto (para subirlos
luego a YouTube u otra plataforma).

## Stack recomendado

**Python 3.12** + **Docker**

- `yt-dlp`: descarga los clips (soporta URLs de clips de Twitch de forma nativa).
- API Helix de Twitch (`requests`): lista los clips de un canal con título, fecha y URL.
- Sin base de datos: un archivo de estado JSON evita re-descargas.
- Docker: imagen única, portable a cualquier máquina/NAS/VPS.

Alternativas consideradas:
- Node.js: viable, pero el soporte de Twitch en yt-dlp (Python) es más robusto.
- TwitchDownloaderCLI: es lo que usas manualmente; se puede invocar desde Docker,
  pero añade un binario externo y es más frágil en automatización.

## Estructura

```
.
├── AGENTS.md            # este archivo (seguimiento del proyecto)
├── Dockerfile
├── docker-compose.yml
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
# Docker (recomendado)
docker compose run --rm downloader

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
- [ ] Programación periódica (cron / `docker compose` con restart + sleep, o Task Scheduler)
- [ ] Renombrado/plantillas de título para YouTube

## Notas y decisiones

- Los clips de Twitch caducan (~14-60 días según el canal); conviene ejecutar periódicamente.
- La API Helix requiere token de app (client credentials), no de usuario.
- Los nombres de archivo se sanean (sin caracteres ilegales en Windows).
- El estado se guarda en `output/.downloaded.json`; borrarlo fuerza re-descarga.

## Historial

- 2026-11-14: Creación inicial del proyecto (Python + yt-dlp + Helix API + Docker).
