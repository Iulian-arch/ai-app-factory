"""Comandă OBS prin WebSocket (inclus în OBS 28+)."""
import shutil
import time
from pathlib import Path

import obsws_python as obs

from common import FatalError, OBS_HOST, OBS_PASSWORD, OBS_PORT


class Recorder:
    def __init__(self):
        try:
            self.cl = obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD, timeout=10)
        except Exception as e:
            raise FatalError(
                f"Nu mă pot conecta la OBS ({OBS_HOST}:{OBS_PORT}): {e}\n"
                "1) Pornește programul OBS.\n"
                "2) În OBS: Tools -> WebSocket Server Settings -> bifează 'Enable WebSocket server', "
                "port 4455, setează o parolă.\n"
                "3) Pune aceeași parolă în fișierul .env la OBS_PASSWORD=...") from e

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
