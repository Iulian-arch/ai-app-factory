# Agent lecții RAW University (Windows)

Salvează lecțiile cursului, le transcrie cu Buzz și le pune în `G:\Salvari video si transcrieri curs RAW`
sub numele `Modul 1_lectia 1.mp4` + `Modul 1_lectia 1.txt`, etc. Titlurile reale sunt în `index.csv`.

## 1. Pregătire (o singură dată)
1. Instalează **Python 3.11+** de pe python.org (bifează „Add Python to PATH").
2. Copiază folderul `lecture-agent` pe PC (de ex. `C:\lecture-agent`). Deschide **PowerShell** în el și rulează:
   ```
   pip install -r requirements.txt
   playwright install chromium
   ```
3. **OBS**: Tools → *WebSocket Server Settings* → bifează *Enable WebSocket server*, setează o parolă.
   Adaugă surse: *Display Capture* (ecranul pe care rulează Chrome) și *Audio Output Capture* (sunetul).
   În Settings → Output, alege formatul de înregistrare (mp4 sau mkv).
4. Copiază `.env.example` ca `.env` și completează user, parolă site, parola OBS.
   Dacă `buzz` nu e recunoscut în PowerShell, pune în `.env` calea la Buzz.exe (`BUZZ_CMD=...`).

## 2. Rulare în 3 etape
1. `python recon.py`: doar se uită pe site. Verifică `recon_report.json` (fără parole) și trimite-l mai departe pentru ajustări.
2. Test pe o lecție: `python agent.py --only 1 1`. Verifică videoul (imagine + sunet) și `.txt`.
3. Un modul: `python agent.py --module 1`, apoi tot cursul: `python agent.py`.

Dacă se oprește, rulează din nou aceeași comandă: lecțiile gata se sar.
În timpul înregistrării cu OBS nu folosi calculatorul și nu lăsa PC-ul să intre în sleep.

## Atenție
- Dacă primul login automat nu merge, agentul îți cere să te loghezi manual în fereastra de Chrome; sesiunea se reține.
- `lessons.json` se generează automat din pagina cursului; verifică împărțirea pe module înainte de rularea completă (`--refresh` îl reface).
- Folosește materialele doar personal.
