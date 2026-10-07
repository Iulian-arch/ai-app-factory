# HANDOFF: agent pentru lecțiile RAW University

Document de predare: conține tot ce trebuie pentru a prelua proiectul (de către utilizator sau de către un alt asistent), fără alt context.

- Repo: `Iulian-arch/ai-app-factory`, folder `lecture-agent/`
- Branch: `claude/lecture-download-transcribe-agent-4j6cht`, [PR #1](https://github.com/Iulian-arch/ai-app-factory/pull/1)
- Versiune cod (la momentul scrierii): `2026-10-07-obs-failfast` (se vede la rulare: `Versiune agent: ...`)
- Utilizatorul preferă limba română și explicații pentru începători. Rulează pe **Windows**, în PowerShell, în `C:\lecture-agent`.

## 1. Scopul
Pentru cursul de pe https://raw-university.ro/courses/raw-university/ (cont propriu al utilizatorului, cu user și parolă):
1. Se loghează automat pe site.
2. Parcurge pe rând fiecare modul și fiecare lecție.
3. Pentru fiecare lecție: pornește **OBS** (instalat, înregistrare ecran), deschide lecția pe tot ecranul, așteaptă să se termine, oprește OBS, închide lecția.
4. Rulează **Buzz** (instalat, transcriere) pe înregistrare și salvează transcrierea.
5. Trece la lecția următoare, apoi la modulul următor.

Rezultatele se salvează în `G:\Salvari video si transcrieri curs RAW`, cu denumiri de forma:
```
Modul 1_lectia 1.mp4
Modul 1_lectia 1.txt
index.csv   (corespondența fișier -> titlu real lecție -> URL)
```
Reluare sigură: lecțiile care au deja video și `.txt` se sar.

## 2. Ce am aflat despre site (din recon)
- Site WordPress cu **WooCommerce** (`/my-account/`) și **LearnDash** (cursuri).
- Login: pe `/my-account/` (formular WooCommerce). Dovada că ești logat: există linkul `customer-logout` / `action=logout` (pe pagina cursului apare „Log in" chiar și când ești logat).
- Lecțiile: linkuri `/lessons/<slug>/`. Pagina cursului are mai întâi descrieri „Modul 1…10" (fără lecții), apoi lista „Course Content" cu titluri „Modul 1 - Basics" etc.
- Lista este **paginată**: `?ld-courseinfo-lesson-page=2`. Prima pagină are 20 de lecții în 3 module; cursul are „peste 50" de lecții (91 de „steps" în sidebar). Paginile 2+ nu au fost confirmate că se citesc corect.
- Videoul este **VdoCipher** (`player.vdocipher.com`, în iframe), cu **DRM**. `yt-dlp` nu poate descărca. Singura variantă: înregistrare de ecran cu OBS.
- Site-ul are protecție anti-boți (`imunify-bot-check`) și cereri de fundal care nu se opresc, deci `networkidle` nu se atinge niciodată. Se folosește `settle()` (așteptare scurtă).
- Chrome-ul pornit direct de Playwright a dat în player eroarea „Protected Content" (probabil din cauza steagurilor de automatizare). De aceea codul pornește acum Chrome-ul normal și se conectează la el prin CDP.

## 3. Arhitectura codului (`lecture-agent/`)
| Fișier | Rol |
|---|---|
| `agent.py` | flux principal: login, lista lecțiilor, înregistrare OBS, transcriere. Argumente: `--only M L`, `--module M`, `--refresh`, `--force-obs`, `--skip-obs-check` |
| `common.py` | config din `.env`, pornire Chrome real (CDP, port 9222, profil `browser_profile/`), `login()`, `collect_lessons()` (paginare + grupare pe module), denumiri, `FatalError` |
| `obs_recorder.py` | `Recorder`: conectare OBS WebSocket (obsws-python, port 4455), scrie singur config WebSocket când OBS e oprit, încearcă să pornească OBS, `start()`/`stop()` (mută fișierul la numele final) |
| `transcribe.py` | Buzz CLI (`buzz add --task transcribe --model-type whisper --model-size <small> --language ro --txt --hide-gui`), redenumește rezultatul în `<nume>.txt`; rezervă `faster-whisper` |
| `recon.py` | doar explorare site: `recon_report.json`, capturi `recon_*.png` / `.html` |
| `.env` (din `.env.example`) | `SITE_USER`, `SITE_PASS`, `OBS_PASSWORD`, opțional `OUTPUT_DIR`, `BUZZ_CMD`, `BUZZ_MODEL`, `LANGUAGE`, `OBS_PATH`, `CHROME_PATH`, `DISABLE_GPU=1`, `USE_YTDLP` (implicit 0) |

Fluxul de înregistrare (`record_with_obs`): deschide lecția, găsește iframe-ul cu `<video>`, pornește OBS, apasă o tastă (gest de utilizator), fullscreen pe iframe, `play()`, așteaptă `ended` (sau `currentTime ≥ duration-0.5`; timp maxim `MAX_LESSON_HOURS=4`), închide pagina, oprește OBS.
Parolele nu se pun niciodată în chat sau în Git (`.env` este în `.gitignore`).

## 4. Starea curentă

### Confirmat de utilizator că merge
- Instalare Python și Playwright, rulare scripturi.
- Login automat și sesiune reținută.
- Citirea listei de lecții de pe pagina 1: **20 de lecții în 3 module**.
- Deschiderea cursului în Chrome.

### Neverificat încă
1. **Pornirea OBS din script**: `obs64.exe` nu apare în procese după lansare (lansarea cu `Popen` dăduse „Access is denied"; cu `os.startfile` nu apare eroare, dar OBS nu pornește). Cauză necunoscută (antivirus / Controlled folder access / crash la pornire). **Soluție de moment: utilizatorul pornește OBS manual**, scriptul se conectează la el.
2. **Conectarea la OBS WebSocket** când OBS rulează (parolă din `.env`; scriptul scrie config în `%APPDATA%\obs-studio\plugin_config\obs-websocket\config.json`, cu copie `config.json.bak-agent`).
3. **Redarea videoului VdoCipher** în Chrome-ul comandat (eroarea „Protected Content" văzută la primul recon, înainte de trecerea pe Chrome normal).
4. **Înregistrarea**: imagine + sunet corecte (risc de ecran negru: `DISABLE_GPU=1`).
5. **Fullscreen pe iframe** și detectarea sfârșitului lecției.
6. **Transcrierea cu Buzz**: comanda CLI scrisă din memorie, trebuie verificată pe versiunea instalată.
7. **Paginile 2+ ale listei de lecții** (în ultima rulare s-au găsit doar 20; codul are fallback prin click pe paginare și salvează `debug_course_page2.html` dacă nu găsește nimic).

### Problemă recurentă la utilizator
Actualizarea fișierelor se face manual (descărcare ZIP de pe branch și copiere peste `C:\lecture-agent`). De mai multe ori au rămas fișiere vechi (ex. `obs_recorder.py`). Verifică mereu prima linie `Versiune agent: ...` la rulare.

## 5. Cum se reia (pași)
1. Actualizează toate fișierele `.py` din `C:\lecture-agent` din ZIP-ul branch-ului (nu atinge `.env` și `browser_profile/`).
2. Verifică `.env` (user, parolă site, `OBS_PASSWORD`).
3. Pornește OBS manual; în *Tools → WebSocket Server Settings*: server activat, port 4455, aceeași parolă ca în `.env`. Surse: *Display Capture* (ecranul principal) + *Audio Output Capture*. Lasă OBS deschis.
4. Test pe o lecție scurtă:
   ```
   cd C:\lecture-agent
   python agent.py --refresh --only 1 1
   ```
5. Verifică în `G:\...` fișierele `Modul 1_lectia 1.mp4` (imagine + sunet) și `.txt`, plus `index.csv`.
6. Apoi un modul (`--module 1`), apoi tot cursul (`python agent.py`). Durata este cât durează lecțiile (înregistrare în timp real); PC-ul nu trebuie să intre în sleep, iar ecranul principal nu se folosește la altceva.

## 6. Probleme probabile și soluții
| Problemă | Soluție |
|---|---|
| Ecran negru în OBS | `DISABLE_GPU=1` în `.env`; Chrome fără accelerare hardware |
| „Protected Content" | Chrome: Setări → Setări site → Conținut protejat → permite; test manual într-un Chrome normal |
| OBS nu pornește singur | pornit manual; de investigat separat (antivirus, `OBS_PATH`, rulare ca administrator) |
| `buzz` nu e recunoscut | `BUZZ_CMD=<cale completă>` sau `pip install faster-whisper` |
| Lecții lipsă (pagina 2+) | log-ul „Pagina N ..." + `debug_course_page2.html` |
| „Chrome nu a pornit în modul de control" | închide toate ferestrele Chrome ale agentului (și din Task Manager); profil separat `browser_profile/`, port `CDP_PORT=9222` |

## 7. Idei pentru mai târziu (nefăcute)
- Pornire automată OBS după ce se află de ce nu apare procesul.
- Verificare automată a înregistrării (durată vs. durata videoului, nivel de sunet) înainte de transcriere.
- Script de actualizare a fișierelor pe PC (evită copierea manuală).
- Respectarea termenilor site-ului: materialele sunt doar pentru uz personal.
