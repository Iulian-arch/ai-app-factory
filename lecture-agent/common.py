"""Cod comun: configurare, browser, login, lista de lecții, denumiri."""
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
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
USE_YTDLP = os.environ.get("USE_YTDLP", "0") == "1"  # VdoCipher are DRM -> OBS
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
DISABLE_GPU = os.environ.get("DISABLE_GPU", "0") == "1"  # pune 1 dacă OBS înregistrează ecran negru
BASE_URL = re.match(r"https?://[^/]+", COURSE_URL).group(0)

PROFILE_DIR = HERE / "browser_profile"  # aici rămâne sesiunea de login
LESSONS_JSON = HERE / "lessons.json"


class FatalError(Exception):
    """Eroare după care nu are sens să continuăm (ex. OBS nu rulează)."""


def settle(page, ms=8000):
    """Așteaptă să se încarce pagina, dar nu blochează dacă site-ul face cereri la nesfârșit."""
    try:
        page.wait_for_load_state("networkidle", timeout=ms)
    except Exception:
        pass
    page.wait_for_timeout(1500)


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


_CHROME_PROC = None


def _find_chrome():
    local = os.environ.get("LOCALAPPDATA", "")
    for p in (os.environ.get("CHROME_PATH", ""),
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              os.path.join(local, r"Google\Chrome\Application\chrome.exe")):
        if p and Path(p).exists():
            return p
    return None


def _cdp_up():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2)
        return True
    except Exception:
        return False


def launch_browser(p):
    """Pornește Chrome-ul NORMAL (cu DRM/Widevine funcțional) și se conectează la el cu Playwright."""
    global _CHROME_PROC
    chrome = _find_chrome()
    if chrome:
        if not _cdp_up():
            cmd = [chrome, f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={PROFILE_DIR}",
                   "--autoplay-policy=no-user-gesture-required", "--no-first-run",
                   "--no-default-browser-check", "--start-maximized"]
            if DISABLE_GPU:
                cmd.append("--disable-gpu")
            _CHROME_PROC = subprocess.Popen(cmd)
            for _ in range(60):
                if _cdp_up():
                    break
                time.sleep(0.5)
            else:
                sys.exit("EROARE: Chrome nu a pornit în modul de control. Închide toate ferestrele Chrome "
                         "deschise de agent (și din Task Manager) și rulează din nou.")
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        ctx = browser.contexts[0]
    else:
        log("Chrome nu a fost găsit (pune CHROME_PATH în .env). Folosesc Chromium Playwright (DRM poate să nu meargă).")
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), headless=False, no_viewport=True,
            args=["--autoplay-policy=no-user-gesture-required"],
            ignore_default_args=["--enable-automation", "--disable-component-update"])
    ctx.set_default_navigation_timeout(120_000)  # site-ul poate fi lent (2 minute)
    ctx.set_default_timeout(60_000)
    return ctx


def close_browser(ctx):
    try:
        if ctx.browser is not None and _CHROME_PROC is not None:
            ctx.browser.close()  # doar deconectare
        else:
            ctx.close()
    except Exception:
        pass
    if _CHROME_PROC is not None:
        _CHROME_PROC.terminate()


def _has_password_field(page):
    return page.locator("input[type=password]:visible").count() > 0


def is_logged_in(page):
    """Logat = pe /my-account/ există linkul de deconectare."""
    return page.locator("a[href*='customer-logout'], a[href*='action=logout']").count() > 0


def _check_login(page):
    page.goto(BASE_URL + "/my-account/", wait_until="domcontentloaded")
    settle(page)
    return is_logged_in(page)


def login(page):
    """Login automat pe /my-account/ (WooCommerce); dacă nu merge, te lasă să te loghezi manual."""
    if _check_login(page):
        log("Login: sesiune existentă, sunt logat.")
        return
    if _has_password_field(page) and SITE_USER and SITE_PASS:
        user = page.locator("input[name=username]:visible, input[type=email]:visible, "
                            "input[type=text]:visible").first
        pwd = page.locator("input[name=password]:visible, input[type=password]:visible").first
        user.fill(SITE_USER)
        pwd.fill(SITE_PASS)
        pwd.press("Enter")
        settle(page)
        if _check_login(page):
            log("Login automat reușit.")
            return
    log("Nu am putut face login automat.")
    input("Loghează-te MANUAL în fereastra deschisă (pe /my-account/), apoi apasă Enter aici... ")
    if not _check_login(page):
        sys.exit("EROARE: tot nu sunt logat. Verifică user/parola și rulează din nou.")


_COLLECT_JS = r"""
({rx, start}) => {
  const re = new RegExp(rx);
  const out = []; let module = start; const seen = new Set();
  const isMod = t => t.length <= 80 && /^\s*modul\s*\d+/i.test(t);
  const txt = n => (n.textContent || '').trim().replace(/\s+/g,' ');
  const all = document.querySelectorAll('a[href], h1,h2,h3,h4,h5,h6,div,span,p,strong,b,li');
  // paginile au întâi descrieri de module (fără lecții), apoi lista "Course Content"
  const hasList = [...all].some(n => n.children.length === 0 && /^course content$/i.test(txt(n)));
  let inList = !hasList;
  for (const n of all) {
    if (n.tagName === 'A') {
      if (inList && re.test(n.href) && !seen.has(n.href)) {
        seen.add(n.href);
        out.push({module_title: module, title: txt(n), url: n.href});
      }
    } else if (n.children.length === 0 || n.matches('.ld-lesson-section-heading,.ld-item-list-section-heading')) {
      const t = txt(n);
      if (!inList && /^course content$/i.test(t)) inList = true;
      else if (inList && isMod(t) && !n.closest('a')) module = t;
    }
  }
  return {items: out, last_module: module};
}
"""


def _course_page_url(n):
    return COURSE_URL if n == 1 else f"{COURSE_URL}?ld-courseinfo-lesson-page={n}"


def _expand(page):
    for sel in (".ld-expand-button",):
        for el in page.locator(sel).all()[:5]:
            try:
                el.click(timeout=800)
            except Exception:
                pass


def _eval_page(page, module):
    return page.evaluate(_COLLECT_JS, {"rx": LESSON_URL_REGEX, "start": module})


def collect_lessons(page):
    """Citește TOATE paginile cursului (LearnDash are paginare) și grupează lecțiile pe module."""
    raw, seen_urls, module = [], set(), None
    for n in range(1, 30):
        page.goto(_course_page_url(n), wait_until="domcontentloaded")
        settle(page)
        _expand(page)
        res = _eval_page(page, module)
        new = [i for i in res["items"] if i["url"] not in seen_urls]
        log(f"Pagina {n} ({page.url}): {len(res['items'])} linkuri de lecții, {len(new)} noi")
        if not new and n > 1:  # încercăm butonul de paginare din pagina 1
            page.goto(COURSE_URL, wait_until="domcontentloaded")
            settle(page)
            link = page.locator(f"a[href*='ld-courseinfo-lesson-page={n}']").first
            if link.count() > 0:
                try:
                    link.click(timeout=5000)
                    settle(page, 12000)
                    _expand(page)
                    res = _eval_page(page, module)
                    new = [i for i in res["items"] if i["url"] not in seen_urls]
                    log(f"Pagina {n} (prin click pe paginare): {len(new)} lecții noi")
                except Exception as e:
                    log(f"Click pe paginare eșuat: {e}")
        if not new:
            (HERE / f"debug_course_page{n}.html").write_text(page.content(), encoding="utf-8")
            break
        module = res["last_module"]
        seen_urls.update(i["url"] for i in new)
        raw.extend(new)
    modules, order = {}, []
    for item in raw:
        key = item["module_title"] or "Fără modul"
        if key not in modules:
            modules[key] = []
            order.append(key)
        modules[key].append(item)
    lessons = []
    for mi, key in enumerate(order, 1):
        m = re.search(r"modul\s*(\d+)", key, re.I)
        num = int(m.group(1)) if m else mi
        for li, item in enumerate(modules[key], 1):
            lessons.append({"module": num, "lesson": li, "module_title": key,
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
