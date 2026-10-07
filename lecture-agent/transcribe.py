"""Transcriere cu Buzz (linia de comandă). Rezervă: faster-whisper."""
import subprocess
from pathlib import Path

from common import BUZZ_CMD, BUZZ_MODEL, LANGUAGE, log


def _with_buzz(video: Path, txt: Path):
    before = {p: p.stat().st_mtime for p in video.parent.glob("*.txt")}
    cmd = [BUZZ_CMD, "add", "--task", "transcribe", "--model-type", "whisper",
           "--model-size", BUZZ_MODEL, "--language", LANGUAGE, "--txt", "--hide-gui", str(video)]
    log("Buzz: " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    # Buzz adaugă data în numele fișierului; îl găsim și îl redenumim
    new = [p for p in video.parent.glob("*.txt")
           if p.stem.startswith(video.stem) and (p not in before or p.stat().st_mtime > before[p])]
    if not new:
        raise RuntimeError("Buzz nu a produs niciun fișier .txt.")
    newest = max(new, key=lambda p: p.stat().st_mtime)
    if newest != txt:
        txt.unlink(missing_ok=True)
        newest.rename(txt)


def _with_faster_whisper(video: Path, txt: Path):
    from faster_whisper import WhisperModel  # pip install faster-whisper
    model = WhisperModel(BUZZ_MODEL, compute_type="int8")
    segments, _ = model.transcribe(str(video), language=LANGUAGE)
    txt.write_text("\n".join(s.text.strip() for s in segments), encoding="utf-8")


def transcribe(video: Path) -> Path:
    txt = video.with_suffix(".txt")
    try:
        _with_buzz(video, txt)
    except Exception as e:
        log(f"Buzz a eșuat ({e}). Încerc faster-whisper...")
        _with_faster_whisper(video, txt)
    if not txt.exists() or txt.stat().st_size == 0:
        raise RuntimeError("Transcrierea este goală.")
    return txt
