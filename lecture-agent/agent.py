"""Agentul principal: login -> lecții -> video (yt-dlp sau OBS) -> transcriere.

Rulare:  python agent.py              (tot cursul)
         python agent.py --only 1 1   (doar Modul 1, lecția 1 – pentru test)
         python agent.py --module 1   (doar Modul 1)
         python agent.py --force-obs  (nu încerca descărcarea directă)
"""
import argparse
import json
import subprocess
import sys
import time
import traceback

from playwright.sync_api import sync_playwright

import common as c
from transcribe import transcribe

VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov")


def existing_video(base):
    for ext in VIDEO_EXT:
        p = c.OUTPUT_DIR / (base + ext)
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def export_cookies(ctx, path):
    """Salvează cookie-urile în format Netscape, pentru yt-dlp."""
    lines = ["# Netscape HTTP Cookie File"]
    for k in ctx.cookies():
        dom = k["domain"]
        lines.append("\t".join([dom, "TRUE" if dom.startswith(".") else "FALSE", k["path"],
                                "TRUE" if k["secure"] else "FALSE",
                                str(int(k.get("expires", 0) or 0)), k["name"], k["value"]]))
    path.write_text("\n".join(lines), encoding="utf-8")


def try_download(ctx, lesson, base):
    """Varianta A: yt-dlp direct de pe pagina lecției."""
    cookies = c.HERE / "cookies.txt"
    export_cookies(ctx, cookies)
    target = c.OUTPUT_DIR / (base + ".%(ext)s")
    cmd = [sys.executable, "-m", "yt_dlp", "--no-playlist", "--cookies", str(cookies),
           "--referer", lesson["url"], "-f", "bv*+ba/b", "--merge-output-format", "mp4",
           "-o", str(target), lesson["url"]]
    c.log("yt-dlp: încerc descărcarea directă...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    cookies.unlink(missing_ok=True)
    if r.returncode == 0 and existing_video(base):
        return existing_video(base)
    c.log("yt-dlp nu a putut descărca (" + (r.stderr.strip().splitlines() or ["?"])[-1] + "). Trec la OBS.")
    return None


def record_with_obs(ctx, lesson, base):
    """Varianta B: OBS pornește, lecția rulează fullscreen, OBS se oprește la final."""
    from obs_recorder import Recorder
    rec = Recorder()
    page = ctx.new_page()
    try:
        page.goto(lesson["url"], wait_until="domcontentloaded")
        frame = c.find_video_frame(page)
        if frame is None:
            raise RuntimeError("Nu am găsit niciun player video pe pagină.")
        rec.start()  # 1) pornește OBS
        time.sleep(1.5)
        page.bring_to_front()
        page.keyboard.press("Space")  # gest de utilizator, necesar pentru fullscreen
        if frame != page.main_frame:  # VdoCipher: playerul e într-un iframe -> fullscreen pe iframe
            try:
                frame.frame_element().evaluate("el => el.requestFullscreen()")
            except Exception as e:
                c.log(f"Fullscreen iframe a eșuat: {e}")
        frame.evaluate("""async () => {
            const v = document.querySelector('video');
            if (!document.fullscreenElement) { try { await v.requestFullscreen(); } catch (e) {} }
            v.currentTime = 0; v.muted = false; await v.play();
        }""")  # 2) fullscreen + play
        if not page.evaluate("() => !!document.fullscreenElement"):
            c.log("ATENȚIE: nu am reușit fullscreen; înregistrarea va include pagina.")
        # 3) așteaptă să se termine
        _wait_end(frame)
        time.sleep(2)
        page.close()  # 4) închide lecția
        return rec.stop(c.OUTPUT_DIR / base)  # 5) oprește OBS
    except Exception:
        try:
            rec.cl.stop_record()
        except Exception:
            pass
        raise
    finally:
        if not page.is_closed():
            page.close()


def _wait_end(frame):
    js = """() => { const v = document.querySelector('video');
        return !v || v.ended || (v.duration > 0 && v.currentTime >= v.duration - 0.5); }"""
    deadline = time.time() + c.MAX_LESSON_HOURS * 3600
    while time.time() < deadline:
        try:
            if frame.evaluate(js):
                return
        except Exception:  # frame reîncărcat; încercăm din nou
            pass
        time.sleep(3)
    raise TimeoutError("Lecția nu s-a terminat în timpul maxim.")


def process(ctx, lesson, force_obs):
    base = c.lesson_basename(lesson["module"], lesson["lesson"])
    txt = c.OUTPUT_DIR / (base + ".txt")
    video = existing_video(base)
    if video and txt.exists() and txt.stat().st_size > 0:
        c.log(f"[sar] {base} există deja.")
        return
    c.log(f"=== {base}: {lesson['title']} ===")
    if not video:
        if c.USE_YTDLP and not force_obs:
            video = try_download(ctx, lesson, base)
        if not video:
            video = record_with_obs(ctx, lesson, base)
    c.log(f"Video salvat: {video}")
    c.log(f"Transcriere salvată: {transcribe(video)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs=2, type=int, metavar=("MODUL", "LECTIA"))
    ap.add_argument("--module", type=int)
    ap.add_argument("--force-obs", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="reface lista de lecții")
    a = ap.parse_args()

    c.check_output_dir()
    with sync_playwright() as p:
        ctx = c.launch_browser(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        c.login(page)
        if c.LESSONS_JSON.exists() and not a.refresh:
            lessons = json.loads(c.LESSONS_JSON.read_text(encoding="utf-8"))
            c.log(f"Folosesc lista existentă ({len(lessons)} lecții) din lessons.json")
        else:
            lessons = c.collect_lessons(page)
            c.save_lessons(lessons)
            c.log(f"Am găsit {len(lessons)} lecții în {len({l['module'] for l in lessons})} module. "
                  "Verifică lessons.json și index.csv.")
        if a.only:
            lessons = [l for l in lessons if (l["module"], l["lesson"]) == tuple(a.only)]
        elif a.module:
            lessons = [l for l in lessons if l["module"] == a.module]
        failed = []
        for l in lessons:
            for attempt in (1, 2):
                try:
                    process(ctx, l, a.force_obs)
                    break
                except Exception:
                    c.log(f"Eroare (încercarea {attempt}) la Modul {l['module']} lecția {l['lesson']}:\n"
                          + traceback.format_exc())
            else:
                failed.append(c.lesson_basename(l["module"], l["lesson"]))
        c.log("GATA." + (f" Eșuate: {', '.join(failed)}" if failed else " Toate lecțiile au fost procesate."))
        c.close_browser(ctx)


if __name__ == "__main__":
    main()
