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
  "storage": "local",
  "output_dir": "output"
}
```

También puedes usar variables de entorno en lugar del archivo:
`TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TWITCH_CHANNELS=canal1,canal2`.

### Almacenamiento: local o S3 compatible

`storage` puede ser `local` (por defecto) o `s3` (cualquier almacenamiento
compatible con S3: AWS S3, MinIO, Cloudflare R2, Backblaze B2, Wasabi...).

**Local** — los clips se guardan en `output_dir` (o `OUTPUT_DIR`):

```json
{ "storage": "local", "output_dir": "/ruta/a/clips" }
```

**S3** — los clips se suben a `s3://<bucket>/<prefix>/YYYY-MM-DD/` y, salvo que
`keep_local` sea `true`, las copias locales se borran tras subir. El estado
(`.downloaded.json`) también se guarda en el bucket, así que el contenedor puede
ser efímero:

```json
{
  "storage": "s3",
  "output_dir": "output",
  "s3": {
    "endpoint_url": "https://s3.us-east-1.amazonaws.com",
    "bucket": "mi-bucket",
    "prefix": "twitch-clips",
    "region": "us-east-1",
    "access_key_id": "TU_ACCESS_KEY",
    "secret_access_key": "TU_SECRET_KEY",
    "keep_local": false
  }
}
```

Variables de entorno equivalentes: `STORAGE`, `OUTPUT_DIR`, `S3_ENDPOINT_URL`,
`S3_BUCKET`, `S3_PREFIX`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`.
En modo S3, `output_dir` se usa solo como staging temporal.

### Subida a YouTube

Requiere una aplicación OAuth en Google Cloud (tipo **Aplicación de escritorio**)
con la **YouTube Data API v3** habilitada. Tu cuenta debe tener rol **Administrador
o Editor** en el canal de destino (propio o de marca); no hace falta ser propietario.

1. Añade a `config.json`:

   ```json
   "youtube": {
     "client_id": "TU_YOUTUBE_CLIENT_ID",
     "client_secret": "TU_YOUTUBE_CLIENT_SECRET",
     "tokens_file": "youtube_tokens.json",
     "privacy_status": "private",
     "auto_upload": false,
     "title_template": "{title} | {channel}",
     "channel_map": { "canal_twitch": "perfil_youtube" }
   }
   ```

2. Autoriza cada canal una vez (se abre el navegador; elige el canal correcto):

   ```bash
   python src/youtube_auth.py --config config.json --authorize perfil_youtube
   python src/youtube_auth.py --config config.json --list
   ```

3. Sube vídeos:

   ```bash
   # Todos los clips locales pendientes (según channel_map)
   python src/youtube_upload.py --config config.json --pending

   # Un vídeo concreto
   python src/youtube_upload.py --config config.json --profile perfil_youtube video.mp4
   ```

   Con `"auto_upload": true`, el downloader sube cada clip a YouTube justo tras
   descargarlo (antes de borrar los locales en modo S3). Usa `--no-upload` para
   desactivarlo en una ejecución. Las subidas se registran en `output/.uploaded.json`.

`title_template` admite `{title}`, `{channel}`, `{date}` e `{id}` (máx. 100 caracteres).
`privacy_status`: `private` (por defecto), `unlisted` o `public`.

Notas:
- No existe *service account* para YouTube: siempre OAuth con un usuario real.
- Si la app OAuth está en modo "Testing", los refresh tokens caducan a los 7 días;
  publícala o re-autoriza periódicamente.
- Cuota de la API: `videos.insert` cuesta ~1600 unidades (10.000/día por defecto).
- `youtube_tokens.json` contiene refresh tokens: no lo subas a git (ya está en `.gitignore`).

## Uso

### Podman con imagen de GHCR (recomendado)

GitHub Actions construye y publica la imagen en `ghcr.io` en cada push a `main`
(y en tags `v*`), para **linux/amd64 y linux/arm64** (multi-arch vía QEMU), así que
funciona igual en VMs ARM baratas y en x86_64. No hace falta build local:

```bash
podman pull ghcr.io/OWNER/REPO:latest
podman run --rm \
  -v ./output:/app/output:Z \
  -v ./config.json:/app/config.json:ro,Z \
  ghcr.io/OWNER/REPO:latest
```

Si el paquete es privado, autentícate primero con un PAT con scope `read:packages`:
`podman login ghcr.io`. Para hacerlo público: repo → Packages → Package settings →
Change visibility.

#### Tags de la imagen y actualización automática

Cada push a `main` publica dos tags apuntando a la misma imagen: `latest`
(mutable, se sobrescribe en cada build) y `sha-<commit>` (inmutable). Los tags
semver (`1.2.3`, `1.2`) solo se generan al crear un tag git `v*`.

- Con `:latest`, `podman run` **no** actualiza la imagen local por sí solo;
  hay que hacer `podman pull` explícito.
- El unit Quadlet (`twitch-clip-downloader.container`) incluye
  `AutoUpdate=registry`, que hace que Podman compruebe el registro y actualice
  la imagen en cada arranque del servicio. Requiere el timer de auto-update:

  ```bash
  systemctl --user enable --now podman-auto-update.timer
  ```

- Si prefieres un tag inmutable (`sha-...` o semver) para máxima
  reproducibilidad, fija ese tag en el `.container` y elimina `AutoUpdate=registry`.

También puedes construir localmente: `podman build -t twitch-clip-downloader:latest .`

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

#### Modo automático vs. manual

- **Automático**: habilita el timer como se indica arriba. La frecuencia se
  configura editando `OnCalendar=` en `twitch-clip-downloader.timer`
  (`hourly`, `*:0/30`, `daily`, `weekly`...) y luego
  `systemctl --user daemon-reload && systemctl --user restart twitch-clip-downloader.timer`.
- **Manual**: no habilites el timer (o deshabilítalo con
  `systemctl --user disable --now twitch-clip-downloader.timer`) y ejecuta una
  pasada bajo demanda con `systemctl --user start twitch-clip-downloader.service`
  o con `podman run --rm ... ghcr.io/OWNER/REPO:latest`.

### Local

```bash
pip install -r requirements.txt
python src/downloader.py --config config.json
```

### Opciones

| Opción | Descripción |
|---|---|
| `--since YYYY-MM-DD` | Solo clips creados desde esa fecha (por defecto: últimos 30 días) |
| `--until YYYY-MM-DD` | Solo clips creados hasta esa fecha (inclusive) |
| `--days N` | Clips de los últimos N días |
| `--month YYYY-MM` | Clips de un mes concreto |
| `--year YYYY` | Clips de un año concreto |
| `--all` | Descargar todos los clips, sin filtro de fecha |
| `--max N` | Máximo de clips por canal por ejecución (0 = sin límite) |
| `--dry-run` | Lista lo que descargaría sin descargar nada |
| `--no-upload` | No subir a YouTube aunque `auto_upload` esté activo |

## Notas

- Los clips de Twitch caducan (~14–60 días según el canal): conviene ejecutar
  el bot periódicamente.
- Los nombres de archivo se sanean (sin caracteres ilegales en Windows).
- Borrar `output/.downloaded.json` (o `s3://<bucket>/<prefix>/.downloaded.json` en modo S3) fuerza la re-descarga de todo.
- La subida a YouTube es opcional y está desactivada por defecto (`auto_upload: false`).

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
├── src/youtube_auth.py             # autorización OAuth de canales de YouTube
├── src/youtube_upload.py           # subida de vídeos a YouTube
└── output/                         # clips descargados (por fecha)
```
