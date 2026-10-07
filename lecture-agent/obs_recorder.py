"""Comandă OBS prin WebSocket (inclus în OBS 28+)."""
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

import obsws_python as obs

logging.getLogger("obsws_python").setLevel(logging.CRITICAL)  # fără stack trace la fiecare încercare

from common import FatalError, OBS_HOST, OBS_PASSWORD, OBS_PORT


def _find_obs():
    pf, pf86 = os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for p in (os.environ.get("OBS_PATH", ""),
              os.path.join(pf, r"obs-studio\bin\64bit\obs64.exe"),
              os.path.join(pf86, r"obs-studio\bin\64bit\obs64.exe")):
        if p and Path(p).exists():
            return p
    return None


def _connect():
    return obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD, timeout=10)


def _obs_running():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe"], capture_output=True, text=True).stdout
        return "obs64.exe" in out
    except Exception:
        return False


def _ensure_websocket_config():
    """Activează serverul WebSocket în setările OBS (doar când OBS e oprit). Face copie de siguranță."""
    cfg_dir = Path(os.environ.get("APPDATA", "")) / "obs-studio" / "plugin_config" / "obs-websocket"
    cfg = cfg_dir / "config.json"
    data = {}
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        shutil.copy(cfg, cfg.with_name("config.json.bak-agent"))
    data.update({"server_enabled": True, "server_port": OBS_PORT, "alerts_enabled": False,
                 "first_load": False, "auth_required": bool(OBS_PASSWORD),
                 "server_password": OBS_PASSWORD})
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps(data, indent=4), encoding="utf-8")
    print(f"Am activat WebSocket în setările OBS ({cfg}), port {OBS_PORT}.", flush=True)


def _start_obs(exe):
    """Pornește OBS ca la dublu-click (ShellExecute), ca să meargă și cu permisiuni speciale."""
    folder = str(Path(exe).parent)
    try:
        if hasattr(os, "startfile"):
            os.startfile(exe, arguments="--disable-shutdown-check", cwd=folder)
        else:
            subprocess.Popen([exe, "--disable-shutdown-check"], cwd=folder)
    except Exception as e:
        raise FatalError(
            f"Nu pot porni OBS automat ({e}).\n"
            "Pornește OBS TU (dublu-click pe iconița lui), așteaptă să se deschidă complet și rulează din nou comanda. "
            "Setările WebSocket au fost deja scrise, deci OBS le va încărca la pornire.") from e


class Recorder:
    def __init__(self):
        try:
            self.cl = _connect()
            return
        except Exception as first_error:
            err = first_error
        exe = _find_obs()
        if _obs_running():
            raise FatalError(
                "OBS rulează, dar serverul WebSocket nu răspunde (port %s).\n"
                "ÎNCHIDE OBS complet (File -> Exit; verifică și iconița de lângă ceas) și rulează din nou: "
                "agentul îl pornește și îl configurează singur." % OBS_PORT) from err
        if exe:  # OBS nu rulează: îl configurăm și îl pornim noi
            try:
                _ensure_websocket_config()
            except Exception as e:
                print(f"Nu am putut scrie setările OBS: {e}", flush=True)
            print("Pornesc OBS...", flush=True)
            _start_obs(exe)
            for _ in range(30):
                time.sleep(3)
                try:
                    self.cl = _connect()
                    time.sleep(2)
                    return
                except Exception as e:
                    err = e
        raise FatalError(
            f"Nu mă pot conecta la OBS ({OBS_HOST}:{OBS_PORT}): {err}\n"
            + ("" if exe else "Nu am găsit OBS pe calculator: pune calea la obs64.exe în .env (OBS_PATH=...).\n")
            + "Verifică că OBS_PASSWORD din .env este completat și rulează din nou.") from err

    def start(self):
        if self.cl.get_record_status().output_active:
            self.cl.stop_record()
            time.sleep(2)
        self.cl.start_record()
        for _ in range(20):
            if self.cl.get_record_status().output_active:
                return
            time.sleep(0.5)
        raise RuntimeError("OBS nu a pornit înregistrarea.")

    def stop(self, dest_base: Path) -> Path:
        """Oprește înregistrarea și mută fișierul la dest_base + extensia originală."""
        out = self.cl.stop_record().output_path
        for _ in range(60):  # OBS scrie fișierul final după stop
            p = Path(out)
            if p.exists() and p.stat().st_size > 0:
                break
            time.sleep(0.5)
        final = dest_base.with_suffix(Path(out).suffix)
        shutil.move(out, final)
        return final
