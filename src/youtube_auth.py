#!/usr/bin/env python3
"""Autoriza canales de YouTube vía OAuth (Fase 1: solo autorización).

Cada canal (propio o de marca donde tu cuenta es admin/editor) se autoriza
una vez y su refresh_token se guarda en un archivo de tokens, indexado por
"perfil". Luego la subida (Fase 2) usará esos tokens.

Uso:
  python src/youtube_auth.py --config config.json --authorize mi_canal
  python src/youtube_auth.py --config config.json --list
"""

import argparse
import json
import os
import sys
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def load_youtube_config(cfg_path: str) -> dict:
    cfg = {}
    if Path(cfg_path).exists():
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
    yt = cfg.get("youtube", {})
    client_id = os.environ.get("YOUTUBE_CLIENT_ID") or yt.get("client_id")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET") or yt.get("client_secret")
    if not client_id or not client_secret:
        sys.exit(
            "ERROR: faltan credenciales de YouTube. Añade 'youtube.client_id' y "
            "'youtube.client_secret' en config.json o define YOUTUBE_CLIENT_ID / "
            "YOUTUBE_CLIENT_SECRET."
        )
    tokens_file = Path(
        os.environ.get("YOUTUBE_TOKENS_FILE") or yt.get("tokens_file", "youtube_tokens.json")
    )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "tokens_file": tokens_file,
    }


def load_tokens(tokens_file: Path) -> dict:
    if tokens_file.exists():
        return json.loads(tokens_file.read_text(encoding="utf-8"))
    return {}


def save_tokens(tokens_file: Path, tokens: dict) -> None:
    tokens_file.write_text(
        json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    try:
        tokens_file.chmod(0o600)
    except OSError:
        pass


def authorize(yt: dict, profile: str) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    client_config = {
        "installed": {
            "client_id": yt["client_id"],
            "client_secret": yt["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    # access_type=offline + prompt=consent garantizan refresh_token
    creds = flow.run_local_server(
        port=0, access_type="offline", prompt="consent"
    )

    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    channel_title = items[0]["snippet"]["title"] if items else "(desconocido)"
    channel_id = items[0]["id"] if items else None

    tokens = load_tokens(yt["tokens_file"])
    tokens[profile] = {
        "refresh_token": creds.refresh_token,
        "channel_id": channel_id,
        "channel_title": channel_title,
        "scopes": list(creds.scopes or SCOPES),
    }
    save_tokens(yt["tokens_file"], tokens)
    print(f"Perfil '{profile}' autorizado para el canal: {channel_title} ({channel_id})")
    print(f"Tokens guardados en {yt['tokens_file']}")


def list_profiles(yt: dict) -> None:
    tokens = load_tokens(yt["tokens_file"])
    if not tokens:
        print(f"No hay perfiles autorizados en {yt['tokens_file']}")
        return
    for profile, data in tokens.items():
        print(f"- {profile}: {data.get('channel_title')} ({data.get('channel_id')})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Autorización OAuth de canales de YouTube")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--authorize", metavar="PERFIL", help="Autoriza un canal y guarda su token")
    ap.add_argument("--list", action="store_true", help="Lista los perfiles autorizados")
    args = ap.parse_args()

    yt = load_youtube_config(args.config)
    if args.authorize:
        authorize(yt, args.authorize)
    elif args.list:
        list_profiles(yt)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
