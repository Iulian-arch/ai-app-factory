"""Cod comun: configurare, browser, login, lista de lecții, denumiri."""
import csv
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_env():
    """Citește fișierul .env (fără biblioteci externe)."""
    env_file = HERE / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()

COURSE_URL = os.environ.get("COURSE_URL", "https://raw-university.ro/courses/raw-university/")
SITE_USER = os.environ.get("SITE_USER", "")
SITE_PASS = os.environ.get("SITE_PASS", "")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", r"G:\Salvari video si transcrieri curs RAW"))
OBS_HOST = os.environ.get("OBS_HOST", "localhost")
OBS_PORT = int(os.environ.get("OBS_PORT", "4455"))
OBS_PASSWORD = os.environ.get("OBS_PASSWORD", "")
BUZZ_CMD = os.environ.get("BUZZ_CMD", "buzz")
BUZZ_MODEL = os.environ.get("BUZZ_MODEL", "small")
LANGUAGE = os.environ.get("LANGUAGE", "ro")
BROWSER_CHANNEL = os.environ.get("BROWSER_CHANNEL", "chrome")  # "chrome" = Chrome instalat; gol = Chromium Playwright
LESSON_URL_REGEX = os.environ.get("LESSON_URL_REGEX", r"/(lessons?|lectii|lectie|topic|topics)/")
MAX_LESSON_HOURS = float(os.environ.get("MAX_LESSON_HOURS", "4"))

PROFILE_DIR = HERE / "browser_profile"  # aici rămâne sesiunea de login
LESSONS_JSON = HERE / "lessons.json"


def log(msg):
    print(msg, flush=True)
    with open(HERE / "agent.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def lesson_basename(module, lesson):
    """Denumirea cerută: 'Modul 1_lectia 1'."""
    return f"Modul {module}_lectia {lesson}"


def check_output_dir():
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        sys.exit(f"EROARE: nu pot folosi folderul {OUTPUT_DIR} ({e}). Unitatea G: este conectată?")
    free_gb = shutil.disk_usage(OUTPUT_DIR).free / 1e9
    log(f"Folder ieșire: {OUTPUT_DIR} (liber: {free_gb:.0f} GB)")
    if free_gb < 20:
        log("ATENȚIE: spațiu liber sub 20 GB; videoclipurile pot ocupa mult.")


def launch_browser(p, fullscreen_args=True):
    args = ["--autoplay-policy=no-user-gesture-required"]
    kwargs = dict(user_data_dir=str(PROFILE_DIR), headless=False, args=args, no_viewport=True)
    if BROWSER_CHANNEL:
        try:
            return p.chromium.launch_persistent_context(channel=BROWSER_CHANNEL, **kwargs)
        except Exception as e:  # Chrome lipsă -> Chromium
            log(f"Nu pot deschide '{BROWSER_CHANNEL}' ({e}); folosesc Chromium Playwright.")
    return p.chromium.launch_persistent_context(**kwargs)


def _has_password_field(page):
    return page.locator("input[type=password]:visible").count() > 0


def login(page):
    """Încearcă login automat; dacă nu merge, te lasă să te loghezi manual."""
    page.goto(COURSE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    if not _has_password_field(page):
        base = re.match(r"https?://[^/]+", COURSE_URL).group(0)
        for path in ("/login/", "/wp-login.php", "/autentificare/", "/my-account/", "/cont/"):
            if _is_logged_in_page(page):
                break
            page.goto(base + path, wait_until="domcontentloaded")
            if _has_password_field(page):
                break
    if _has_password_field(page) and SITE_USER and SITE_PASS:
        pwd = page.locator("input[type=password]:visible").first
        user = page.locator(
            "input[type=email]:visible, input[name=log]:visible, input[name=username]:visible, "
            "input[type=text]:visible"
        ).first
        user.fill(SITE_USER)
        pwd.fill(SITE_PASS)
        pwd.press("Enter")
        page.wait_for_load_state("networkidle")
    page.goto(COURSE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    if _has_password_field(page) or not _is_logged_in_page(page):
        log("Nu am putut confirma login-ul automat.")
        input("Loghează-te MANUAL în fereastra deschisă, intră pe pagina cursului, apoi apasă Enter aici... ")
        page.goto(COURSE_URL, wait_until="domcontentloaded")


def is_logged_in(page):
    """Logat = există link de deconectare (WooCommerce: customer-logout / logout)."""
    return page.locator("a[href*='logout'], a[href*='deconect']").count() > 0


def _is_logged_in_page(page):
    return is_logged_in(page) and not _has_password_field(page)


_COLLECT_JS = r"""
(rx) => {
  const re = new RegExp(rx);
  const out = []; let module = null; const seen = new Set();
  const nodes = document.querySelectorAll('h1,h2,h3,h4,h5,a[href]');
  for (const n of nodes) {
    if (n.tagName === 'A') {
      const href = n.href;
      if (re.test(href) && !seen.has(href)) {
        seen.add(href);
        out.push({module_title: module, title: (n.textContent || '').trim().replace(/\s+/g,' '), url: href});
      }
    } else {
      const t = (n.textContent || '').trim().replace(/\s+/g,' ');
      if (t && !n.closest('a')) module = t;
    }
  }
  return out;
}
"""


def collect_lessons(page):
    """Citește pagina cursului și grupează lecțiile pe module (după titlurile de secțiune)."""
    page.goto(COURSE_URL, wait_until="networkidle")
    # deschide eventualele module pliate
    for sel in ("[aria-expanded=false]", ".ld-expand-button", ".expand-all"):
        for el in page.locator(sel).all()[:50]:
            try:
                el.click(timeout=500)
            except Exception:
                pass
    raw = page.evaluate(_COLLECT_JS, LESSON_URL_REGEX)
    modules, order = {}, []
    for item in raw:
        key = item["module_title"] or "Fără modul"
        if key not in modules:
            modules[key] = []
            order.append(key)
        modules[key].append(item)
    lessons = []
    for mi, key in enumerate(order, 1):
        for li, item in enumerate(modules[key], 1):
            lessons.append({"module": mi, "lesson": li, "module_title": key,
                            "title": item["title"], "url": item["url"]})
    return lessons


def save_lessons(lessons):
    LESSONS_JSON.write_text(json.dumps(lessons, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(OUTPUT_DIR / "index.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Fișier", "Modul", "Titlu modul", "Lecția", "Titlu lecție", "URL"])
        for l in lessons:
            w.writerow([lesson_basename(l["module"], l["lesson"]), l["module"], l["module_title"],
                        l["lesson"], l["title"], l["url"]])


def find_video_frame(page, timeout_s=30):
    """Returnează frame-ul (pagina sau iframe) care conține un element <video>."""
    for _ in range(timeout_s * 2):
        for fr in page.frames:
            try:
                if fr.locator("video").count() > 0:
                    return fr
            except Exception:
                pass
        page.wait_for_timeout(500)
    return None
