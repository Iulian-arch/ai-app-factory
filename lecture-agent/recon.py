"""Pasul 0: află cum e construit site-ul (nu descarcă și nu înregistrează nimic).

Rulare:  python recon.py
Rezultat: recon_report.json + recon_*.png / recon_*.html (capturi ale paginilor)
"""
import json
import re

from playwright.sync_api import sync_playwright

import common as c

LINKS_JS = """() => {
  const seen = new Set(); const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const t = (a.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
    const k = a.href + '|' + t;
    if (!seen.has(k)) { seen.add(k); out.push({text: t, url: a.href}); }
  }
  return out;
}"""


def snapshot(page, name, url):
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(2000)
    page.screenshot(path=str(c.HERE / f"recon_{name}.png"), full_page=True)
    (c.HERE / f"recon_{name}.html").write_text(page.content(), encoding="utf-8")
    return {
        "url_final": page.url,
        "title": page.title(),
        "logged_in": c.is_logged_in(page),
        "password_field_visible": page.locator("input[type=password]:visible").count() > 0,
        "text_start": page.inner_text("body")[:1200],
        "links": [l for l in page.evaluate(LINKS_JS) if "raw-university.ro" in l["url"]][:150],
        "iframes": [f.url for f in page.frames if f != page.main_frame],
        "video_tags": page.locator("video").count(),
    }


def main():
    base = re.match(r"https?://[^/]+", c.COURSE_URL).group(0)
    report = {}
    with sync_playwright() as p:
        ctx = c.launch_browser(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        c.login(page)
        report["course_page"] = snapshot(page, "course", c.COURSE_URL)
        report["my_account"] = snapshot(page, "myaccount", base + "/my-account/")
        report["first_lesson"] = snapshot(page, "lesson1", base + "/lessons/introducere/")
        report["first_lesson"]["video_frames"] = [f.url for f in page.frames if f.locator("video").count() > 0]
        ctx.close()
    (c.HERE / "recon_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Gata. Trimite-mi recon_report.json (și, dacă poți, recon_course.png și recon_myaccount.png).")


if __name__ == "__main__":
    main()
