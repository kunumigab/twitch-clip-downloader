#!/usr/bin/env python3
"""Descarga clips de canales de Twitch organizados por fecha de creación."""

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

HELIX = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"


def load_config(path: str) -> dict:
    cfg = {}
    if Path(path).exists():
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    tw = cfg.get("twitch", {})
    client_id = os.environ.get("TWITCH_CLIENT_ID") or tw.get("client_id")
    client_secret = os.environ.get("TWITCH_CLIENT_SECRET") or tw.get("client_secret")
    channels_env = os.environ.get("TWITCH_CHANNELS")
    channels = (
        [c.strip() for c in channels_env.split(",") if c.strip()]
        if channels_env
        else tw.get("channels", [])
    )
    if not client_id or not client_secret:
        sys.exit("ERROR: faltan TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET (config.json o entorno)")
    if not channels:
        sys.exit("ERROR: no hay canales configurados (twitch.channels o TWITCH_CHANNELS)")

    storage = os.environ.get("STORAGE") or cfg.get("storage", "local")
    if storage not in ("local", "s3"):
        sys.exit(f"ERROR: storage debe ser 'local' o 's3', no {storage!r}")

    s3_cfg = cfg.get("s3", {})
    s3 = {
        "endpoint_url": os.environ.get("S3_ENDPOINT_URL") or s3_cfg.get("endpoint_url"),
        "bucket": os.environ.get("S3_BUCKET") or s3_cfg.get("bucket"),
        "prefix": (os.environ.get("S3_PREFIX") or s3_cfg.get("prefix", "")).strip("/"),
        "region": os.environ.get("S3_REGION") or s3_cfg.get("region", "us-east-1"),
        "access_key_id": os.environ.get("S3_ACCESS_KEY_ID") or s3_cfg.get("access_key_id"),
        "secret_access_key": os.environ.get("S3_SECRET_ACCESS_KEY") or s3_cfg.get("secret_access_key"),
        "keep_local": bool(s3_cfg.get("keep_local", False)),
    }
    if storage == "s3":
        missing = [k for k in ("endpoint_url", "bucket", "access_key_id", "secret_access_key") if not s3[k]]
        if missing:
            sys.exit(f"ERROR: faltan claves s3 en config.json o entorno: {', '.join(missing)}")

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "channels": channels,
        "default_since_days": cfg.get("default_since_days", 30),
        "max_per_channel": cfg.get("max_per_channel", 0),
        "output_dir": Path(os.environ.get("OUTPUT_DIR") or cfg.get("output_dir", "output")),
        "storage": storage,
        "s3": s3,
    }


def get_app_token(client_id: str, client_secret: str) -> str:
    r = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def helix_get(path: str, token: str, client_id: str, params: dict[str, str | int]) -> dict:
    r = requests.get(
        f"{HELIX}{path}",
        headers={"Authorization": f"Bearer {token}", "Client-Id": client_id},
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get_broadcaster_id(channel: str, token: str, client_id: str) -> str | None:
    data = helix_get("/users", token, client_id, {"login": channel}).get("data", [])
    return data[0]["id"] if data else None


def list_clips(broadcaster_id: str, token: str, client_id: str, since: datetime) -> list[dict]:
    clips, cursor = [], None
    while True:
        params = {
            "broadcaster_id": broadcaster_id,
            "first": 100,
            "started_at": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if cursor:
            params["after"] = cursor
        resp = helix_get("/clips", token, client_id, params)
        clips.extend(resp.get("data", []))
        cursor = resp.get("pagination", {}).get("cursor")
        if not cursor:
            break
    return clips


def sanitize(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:max_len].rstrip("._") or "clip"


def s3_client(s3: dict):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=s3["endpoint_url"],
        region_name=s3["region"],
        aws_access_key_id=s3["access_key_id"],
        aws_secret_access_key=s3["secret_access_key"],
    )


def s3_key(s3: dict, *parts: str) -> str:
    return "/".join(p for p in (s3["prefix"], *parts) if p)


def load_state(cfg: dict) -> set:
    if cfg["storage"] == "s3":
        from botocore.exceptions import ClientError

        try:
            obj = s3_client(cfg["s3"]).get_object(
                Bucket=cfg["s3"]["bucket"], Key=s3_key(cfg["s3"], ".downloaded.json")
            )
            return set(json.loads(obj["Body"].read()))
        except ClientError:
            return set()
    state_file = cfg["output_dir"] / ".downloaded.json"
    if state_file.exists():
        return set(json.loads(state_file.read_text(encoding="utf-8")))
    return set()


def save_state(cfg: dict, state: set) -> None:
    payload = json.dumps(sorted(state), indent=2)
    if cfg["storage"] == "s3":
        s3_client(cfg["s3"]).put_object(
            Bucket=cfg["s3"]["bucket"],
            Key=s3_key(cfg["s3"], ".downloaded.json"),
            Body=payload.encode("utf-8"),
            ContentType="application/json",
        )
        return
    (cfg["output_dir"] / ".downloaded.json").write_text(payload, encoding="utf-8")


def upload_to_s3(cfg: dict, local_path: Path, key: str) -> None:
    s3_client(cfg["s3"]).upload_file(str(local_path), cfg["s3"]["bucket"], key)


def download_clip(clip: dict, dest_dir: Path, base_name: str) -> list[Path]:
    import yt_dlp
    from yt_dlp.utils import DownloadError

    out_template = str(dest_dir / f"{base_name}.%(ext)s")
    opts = {"outtmpl": out_template, "quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([clip["url"]])
        return sorted(dest_dir.glob(f"{base_name}.*"))
    except DownloadError as e:
        print(f"  ERROR descargando {clip['url']}: {e}")
        return []


def main() -> None:
    ap = argparse.ArgumentParser(description="Descarga clips de Twitch por canal")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--since", help="Fecha mínima de creación (YYYY-MM-DD)")
    ap.add_argument("--max", type=int, default=None, help="Máx. clips por canal")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    output_dir: Path = cfg["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    since = (
        datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=UTC)
        if args.since
        else datetime.now(UTC) - timedelta(days=cfg["default_since_days"])
    )
    max_per_channel = args.max if args.max is not None else cfg["max_per_channel"]

    token = get_app_token(cfg["client_id"], cfg["client_secret"])
    state = load_state(cfg)

    for channel in cfg["channels"]:
        print(f"\n== Canal: {channel} ==")
        bid = get_broadcaster_id(channel, token, cfg["client_id"])
        if not bid:
            print(f"  Canal no encontrado: {channel}")
            continue
        clips = list_clips(bid, token, cfg["client_id"], since)
        clips.sort(key=lambda c: c["created_at"])
        if max_per_channel:
            clips = clips[-max_per_channel:]
        print(f"  {len(clips)} clips desde {since.date()}")

        for clip in clips:
            if clip["id"] in state:
                continue
            created = datetime.strptime(clip["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            day_dir = output_dir / created.strftime("%Y-%m-%d")
            base = f"{created.strftime('%Y-%m-%d')}_{sanitize(clip['title'])}_{clip['id']}"
            meta = {
                "id": clip["id"],
                "title": clip["title"],
                "url": clip["url"],
                "created_at": clip["created_at"],
                "channel": channel,
                "duration": clip.get("duration"),
                "view_count": clip.get("view_count"),
            }
            if args.dry_run:
                print(f"  [dry-run] {base}  <-  {clip['url']}")
                continue
            day_dir.mkdir(parents=True, exist_ok=True)
            print(f"  Descargando: {clip['title']}")
            files = download_clip(clip, day_dir, base)
            if not files:
                continue
            meta_path = day_dir / f"{base}.json"
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            files.append(meta_path)
            if cfg["storage"] == "s3":
                day = created.strftime("%Y-%m-%d")
                for f in files:
                    upload_to_s3(cfg, f, s3_key(cfg["s3"], day, f.name))
                print(f"  Subido a s3://{cfg['s3']['bucket']}/{s3_key(cfg['s3'], day)}/")
                if not cfg["s3"]["keep_local"]:
                    for f in files:
                        f.unlink()
                    try:
                        day_dir.rmdir()
                    except OSError:
                        pass
            state.add(clip["id"])
            save_state(cfg, state)

    print("\nListo.")


if __name__ == "__main__":
    main()
