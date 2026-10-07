"""Pasul 0: află cum e construit site-ul (nu descarcă și nu înregistrează nimic).

Rulare:  python recon.py
Rezultat: recon_report.json  (trimite-mi conținutul, fără parole)
"""
import json

from playwright.sync_api import sync_playwright

import common as c


def main():
    report = {}
    with sync_playwright() as p:
        ctx = c.launch_browser(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        c.login(page)
        lessons = c.collect_lessons(page)
        report["lessons_found"] = len(lessons)
        report["modules_found"] = len({l["module"] for l in lessons})
        report["first_lessons"] = lessons[:8]
        report["sample_links_on_course_page"] = page.evaluate(
            "() => [...document.querySelectorAll('a[href]')].slice(0, 60).map(a => a.href)")
        if lessons:
            page.goto(lessons[0]["url"], wait_until="networkidle")
            report["lesson_page"] = {
                "url": lessons[0]["url"],
                "iframes": [f.url for f in page.frames if f != page.main_frame],
                "video_tags_main": page.locator("video").count(),
                "video_tags_in_frames": [f.url for f in page.frames if f.locator("video").count() > 0],
                "downloadable_links": page.evaluate(
                    "() => [...document.querySelectorAll('a[href]')].map(a => a.href)"
                    ".filter(h => /\\.(mp4|mov|m4v|mp3|pdf)(\\?|$)/i.test(h))"),
            }
        ctx.close()
    (c.HERE / "recon_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
