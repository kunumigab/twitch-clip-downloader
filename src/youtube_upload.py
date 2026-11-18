#!/usr/bin/env python3
"""Sube vídeos a YouTube usando los perfiles autorizados en la Fase 1.

Uso:
  # Subir un vídeo concreto (perfil explícito)
  python src/youtube_upload.py --config config.json --profile mi_canal video.mp4

  # Subir todos los clips descargados pendientes (usa channel_map de config.json)
  python src/youtube_upload.py --config config.json --pending

  # Simular sin subir
  python src/youtube_upload.py --config config.json --pending --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

TOKEN_URI = "https://oauth2.googleapis.com/token"


def load_config(cfg_path: str) -> dict:
    cfg = {}
    if Path(cfg_path).exists():
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
    yt = cfg.get("youtube", {})
    client_id = yt.get("client_id")
    client_secret = yt.get("client_secret")
    if not client_id or not client_secret:
        sys.exit("ERROR: faltan youtube.client_id / youtube.client_secret en config.json")
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "tokens_file": Path(yt.get("tokens_file", "youtube_tokens.json")),
        "privacy_status": yt.get("privacy_status", "private"),
        "channel_map": yt.get("channel_map", {}),
        "title_template": yt.get("title_template", "{title}"),
        "output_dir": Path(cfg.get("output_dir", "output")),
    }


def load_tokens(tokens_file: Path) -> dict:
    if not tokens_file.exists():
        sys.exit(f"ERROR: no existe {tokens_file}. Ejecuta primero src/youtube_auth.py --authorize")
    return json.loads(tokens_file.read_text(encoding="utf-8"))


def get_credentials(yt: dict, profile: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    tokens = load_tokens(yt["tokens_file"])
    if profile not in tokens:
        sys.exit(f"ERROR: perfil '{profile}' no autorizado. Perfiles: {', '.join(tokens) or '(ninguno)'}")
    creds = Credentials(
        token=None,
        refresh_token=tokens[profile]["refresh_token"],
        token_uri=TOKEN_URI,
        client_id=yt["client_id"],
        client_secret=yt["client_secret"],
        scopes=tokens[profile].get("scopes"),
    )
    creds.refresh(Request())
    return creds


def load_uploaded(output_dir: Path) -> set:
    f = output_dir / ".uploaded.json"
    if f.exists():
        return set(json.loads(f.read_text(encoding="utf-8")))
    return set()


def save_uploaded(output_dir: Path, uploaded: set) -> None:
    (output_dir / ".uploaded.json").write_text(
        json.dumps(sorted(uploaded), indent=2), encoding="utf-8"
    )


def render_title(template: str, meta: dict, video_path: Path) -> str:
    created = (meta.get("created_at") or "")[:10]
    values = {
        "title": meta.get("title") or video_path.stem,
        "channel": meta.get("channel") or "",
        "date": created,
        "id": meta.get("id") or video_path.stem,
    }
    try:
        title = template.format(**values)
    except (KeyError, IndexError, ValueError):
        title = values["title"]
    return title[:100]


def build_metadata(video_path: Path, meta_path: Path | None, title_template: str = "{title}") -> dict:
    meta = {}
    if meta_path and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    title = render_title(title_template, meta, video_path)
    description_lines = []
    if meta.get("url"):
        description_lines.append(f"Clip original: {meta['url']}")
    if meta.get("channel"):
        description_lines.append(f"Canal de Twitch: {meta['channel']}")
    if meta.get("created_at"):
        description_lines.append(f"Fecha: {meta['created_at']}")
    return {
        "snippet": {
            "title": title,
            "description": "\n".join(description_lines),
            "categoryId": "20",  # Gaming
        },
        "status": {"privacyStatus": None},  # se rellena en upload_video
    }


def upload_video(yt: dict, profile: str, video_path: Path, meta_path: Path | None,
                 privacy: str | None = None) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = get_credentials(yt, profile)
    youtube = build("youtube", "v3", credentials=creds)
    body = build_metadata(video_path, meta_path, yt.get("title_template", "{title}"))
    body["status"]["privacyStatus"] = privacy or yt["privacy_status"]
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Subiendo... {int(status.progress() * 100)}%")
    video_id = response["id"]
    print(f"  Subido: https://www.youtube.com/watch?v={video_id}")
    return video_id


def find_pending(yt: dict) -> list[tuple[Path, Path, str]]:
    """Devuelve (video, meta_json, perfil) para clips locales no subidos."""
    uploaded = load_uploaded(yt["output_dir"])
    pending = []
    for meta_path in sorted(yt["output_dir"].glob("*/*.json")):
        if meta_path.name.startswith("."):
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        clip_id = meta.get("id") or meta_path.stem
        if clip_id in uploaded:
            continue
        channel = meta.get("channel")
        profile = yt["channel_map"].get(channel)
        if not profile:
            print(f"  Sin perfil YouTube para canal '{channel}' (channel_map), omitiendo {meta_path.name}")
            continue
        videos = [p for p in meta_path.parent.glob(meta_path.stem + ".*")
                  if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
        if not videos:
            print(f"  Sin vídeo para {meta_path.name}, omitiendo")
            continue
        pending.append((videos[0], meta_path, profile))
    return pending


def main() -> None:
    ap = argparse.ArgumentParser(description="Sube vídeos a YouTube")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--profile", help="Perfil de YouTube (para subida directa)")
    ap.add_argument("--privacy", choices=["private", "unlisted", "public"], help="Sobrescribe privacy_status")
    ap.add_argument("--pending", action="store_true", help="Sube todos los clips locales pendientes")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("video", nargs="?", help="Vídeo a subir (requiere --profile)")
    args = ap.parse_args()

    yt = load_config(args.config)

    if args.pending:
        pending = find_pending(yt)
        print(f"{len(pending)} vídeos pendientes")
        uploaded = load_uploaded(yt["output_dir"])
        for video, meta_path, profile in pending:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            clip_id = meta.get("id") or meta_path.stem
            print(f"  [{profile}] {video.name}")
            if args.dry_run:
                continue
            try:
                upload_video(yt, profile, video, meta_path, args.privacy)
                uploaded.add(clip_id)
                save_uploaded(yt["output_dir"], uploaded)
            except Exception as e:
                print(f"  ERROR subiendo {video.name}: {e}")
        return

    if args.video:
        if not args.profile:
            sys.exit("ERROR: --video requiere --profile")
        video = Path(args.video)
        if not video.exists():
            sys.exit(f"ERROR: no existe {video}")
        meta_path = video.with_suffix(".json")
        if args.dry_run:
            print(f"[dry-run] Subiría {video} al perfil '{args.profile}'")
            return
        upload_video(yt, args.profile, video, meta_path if meta_path.exists() else None, args.privacy)
        return

    ap.print_help()


if __name__ == "__main__":
    main()
