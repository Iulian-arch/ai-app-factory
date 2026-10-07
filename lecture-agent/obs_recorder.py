"""Comandă OBS prin WebSocket (inclus în OBS 28+)."""
import os
import shutil
import subprocess
import time
from pathlib import Path

import obsws_python as obs

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


class Recorder:
    def __init__(self):
        try:
            self.cl = _connect()
            return
        except Exception as first_error:
            err = first_error
        exe = _find_obs()
        if exe:  # OBS nu rulează (sau nu e gata): îl pornim noi
            print("OBS nu răspunde; îl pornesc...", flush=True)
            subprocess.Popen([exe, "--disable-shutdown-check"], cwd=str(Path(exe).parent))
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
            + "Verifică în OBS: Tools -> WebSocket Server Settings -> 'Enable WebSocket server' (port 4455) "
            "și că parola din OBS este aceeași cu OBS_PASSWORD din fișierul .env.") from err

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
