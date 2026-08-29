#!/usr/bin/env python3
"""Auto-generate the adegard portfolio page from the GitHub API.

Fetches all public repos (non-forks), auto-detects screenshot thumbnails by
scanning each repo's git tree, merges curated descriptions/categories/features,
and renders index.html. Meant to run inside a scheduled GitHub Actions workflow
(env: GITHUB_TOKEN), but also runs locally (unauthenticated).

Usage: python3 scripts/gen_site.py [-o index.html]
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

USER = "adegard"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = "index.html"

# ---------------------------------------------------------------------------
# Language badge colors
# ---------------------------------------------------------------------------
LANG_COLORS = {
    "Kotlin": "#7F52FF",
    "Python": "#3572A5",
    "JavaScript": "#F1E05A",
    "HTML": "#E34C26",
    "Shell": "#89E051",
    "PHP": "#4F5D95",
    "R": "#198CE7",
    "PowerShell": "#012456",
    "VBScript": "#3A6EA5",
    "VBA": "#867DB1",
    "AutoHotkey": "#6594B9",
    "MQL4": "#E24F22",
    "C++": "#F34B7D",
}
FALLBACK = "#8B949E"
FALLBACK_LABEL = "Docs"

AVATAR_URL = f"https://avatars.githubusercontent.com/u/23522577?v=4"

# ---------------------------------------------------------------------------
# Curated data (editable). Categories below are also the display order.
# ---------------------------------------------------------------------------
C_ANDROID = "android"
C_TERMINAL = "terminal"
C_WEB = "web"
C_GAS = "gas"
C_BROWSER = "browser"
C_WINDOWS = "windows"
C_AI = "ai"
C_LINUX = "linux"
C_META = "meta"

CAT_LABELS = {
    C_ANDROID: "Android Apps",
    C_TERMINAL: "Terminal & Termux Tools",
    C_WEB: "Web Apps & Self-Hosted",
    C_GAS: "Google Apps Script & Sheet Tools",
    C_BROWSER: "Browser Extensions & Bookmarklets",
    C_WINDOWS: "Windows & Automation Scripts",
    C_AI: "AI & Data Experiments",
    C_LINUX: "Linux & DIY Hardware",
    C_META: "Experiments & Misc",
}

# name -> (category, language, description)
CURATED = {
    # Android
    "PixelCam": (C_ANDROID, "Kotlin", "Privacy-friendly camera that brings Pixel photographic styles — HDR, night, portrait — to plain Android and an iOS feel to the viewfinder."),
    "HealthX": (C_ANDROID, "Kotlin", "Step tracker that runs entirely on the phone: no watch, no account, no cloud. Optional self-hosted Home Assistant sync."),
    "meteo-cesate": (C_ANDROID, "Kotlin", "Ad-free, tracking-free weather app: 24-hour + 7-day forecast, worldwide cities, and thunderstorm alerts."),
    "epubreader": (C_ANDROID, "Kotlin", "EPUB reader with text-to-speech, page-fitting layout, bookmarks, themes and a built-in library."),
    "blockblast": (C_ANDROID, "Kotlin", "Block Blast-style puzzle game with a custom Canvas renderer, combo scoring and zero external dependencies."),
    "GMaps-WV-Nav": (C_ANDROID, "Kotlin", "Navigation-first Google Maps wrapper focused on a clean, distraction-free driving experience."),
    "autotrader-android": (C_ANDROID, "Kotlin", "Automatic trading bot for Android: momentum + trend stock selection with virtual money, or real trading via Saxo."),
    "WhatsAppWrapper": (C_ANDROID, "Kotlin", "Lightweight WebView wrapper around WhatsApp."),
    "RadioStreamer": (C_ANDROID, "Kotlin", "Ad-free internet radio: stream any station, background playback, and your own reinstall-proof station list."),
    "amazon-tracker": (C_ANDROID, "Kotlin", "Browse Amazon with built-in tracker/ad-blocking and get price-drop alerts across 10 Amazon regions."),
    "ImageCompressor": (C_ANDROID, "Kotlin", "Gallery viewer with built-in image compression — keep control of your data."),
    "TextBrowserApp": (C_ANDROID, "Kotlin", "Text-focused browser app for Android with read-aloud (TTS)."),
    "oled-keyboard": (C_ANDROID, "Kotlin", "OLED-themed Android keyboard: Italian QWERTY, accented letters, no suggestions, light-on-black themes."),
    "ha": (C_ANDROID, "Kotlin", "Home Assistant client made for Fire TV Stick."),
    "mots-crois-s-android": (C_ANDROID, "JavaScript", "French crossword (mots croisés) app."),
    "ytmusic-apk": (C_ANDROID, "JavaScript", "Search and stream YouTube music on-device — no server, no account, background playback, plus an iOS companion."),
    "RcloneRemotes": (C_ANDROID, "Kotlin", "Manage cloud storage from Android via rclone: file browser, built-in text editor, upload/download and folder sync between remotes."),
    # Terminal
    "shell-agent": (C_TERMINAL, "Shell", "Local coding assistant for Termux: an opencode-style agent loop powered by Ollama, fully on-device. Windows setup included."),
    "terminal_text_browser": (C_TERMINAL, "Python", "Web browser that lives in your terminal — also runs in Termux."),
    "terminal_epub_reader": (C_TERMINAL, "Python", "Simple EPUB reader for the terminal and Termux."),
    "terminal_radio": (C_TERMINAL, "Python", "Radio player for the terminal."),
    "Python_radio_player": (C_TERMINAL, "Python", "Simple terminal radio player."),
    "Python_Music": (C_TERMINAL, "Python", "YouTube music player for the terminal."),
    "Terminal-Bricks-Breaker": (C_TERMINAL, "Python", "Bricks-breaker game played in pure terminal."),
    "Termux-Package-Manager-TUI": (C_TERMINAL, "Shell", "Text-user interface for Termux package management."),
    "Termux_backup": (C_TERMINAL, "Shell", "Backup and restore scripts for Termux."),
    # Web
    "GPS-Nav-HTML": (C_WEB, "HTML", "Single-file, offline-first GPS navigator: live tracking, POI search and turn-by-turn car/walking routing."),
    "No-Cookie-Browser": (C_WEB, "Python", "Retro 90s-style GTK browser that runs ephemeral — no cookies, cache or history by default."),
    "HTML-photo-gallery": (C_WEB, "HTML", "Self-contained photo gallery in a single HTML file."),
    "Strmhm": (C_WEB, "HTML", "Self-hosted streaming start page (Streaming home)."),
    "webreader": (C_WEB, "Python", "Ebook-style reader for the web."),
    "PHP_drive_sync": (C_WEB, "PHP", "PHP + Bash web UI to compare and sync local folders with Google Drive via rclone."),
    "PHP_files_manager": (C_WEB, "PHP", "Lightweight PHP file manager for a home server."),
    "PHP_server_ebooks_reader": (C_WEB, "PHP", "Simple self-hosted EPUB reader server."),
    "PHP_Photo_Gallery-": (C_WEB, "PHP", "Ultra-light photo gallery server (< 50 kB), no database, auto thumbnails."),
    # Apps Script
    "Formula_Updater": (C_GAS, "JavaScript", "Google Sheets add-on that reformats complex formulas into readable, commented multi-line blocks."),
    "Engineering_Gsheet_PFD": (C_GAS, "JavaScript", "Engineering project workbook tooling for Google Sheets."),
    "CoolPropAPI": (C_GAS, "Python", "CoolProp thermodynamic property data exposed to Google Apps Script / Sheets."),
    "Geocode.gs": (C_GAS, "JavaScript", "WMO climate API helpers as a Google Apps Script."),
    "gsheet_formula_beautifier-in-GAS-": (C_GAS, "JavaScript", "Formula beautifier implemented in Google Apps Script."),
    "gsheet_notepad-plus-plus": (C_GAS, "Config", "Google Sheets formula syntax highlighting for Notepad++."),
    "GAS_scripts": (C_GAS, "JavaScript", "Collection of Google Apps Script utilities for Sheets."),
    "P5-js-Pop-up-gsheet-GAS-": (C_GAS, "HTML", "P5.js pop-up UI driven from a Google Sheet."),
    "P5.JS-in-Google-Apps": (C_GAS, "HTML", "Running P5.js inside Google Apps."),
    # Browser
    "Remove_Ads_Chrome_extension": (C_BROWSER, "JavaScript", "Chrome extension that removes ads from web pages."),
    "Chrome_extension_Linkedin_cleaning": (C_BROWSER, "JavaScript", "Chrome extension to declutter the LinkedIn feed."),
    "Chrome_extension_Weather_gmail": (C_BROWSER, "JavaScript", "Demo extension that fetches weather and live-edits Gmail's DOM."),
    "usefull_bookmarklets": (C_BROWSER, "JavaScript", "Handy collection of bookmarklets."),
    "Bookmarklet-to-clip-webpages-to-google-docs": (C_BROWSER, "JavaScript", "Bookmarklet to clip whole web pages into Google Docs."),
    # Windows
    "WinScripts": (C_WINDOWS, "PowerShell", "Collection of PowerShell utilities."),
    "MyChocolateyApps": (C_WINDOWS, "PowerShell", "Recommended Chocolatey app lineup for fresh Windows installs."),
    "AutomaticDesktopBackground": (C_WINDOWS, "PowerShell", "Automatic desktop wallpaper rotation in PowerShell."),
    "xls_macro_save_value": (C_WINDOWS, "VBA", "Excel VBA macro to snapshot cell values and re-import them into another workbook."),
    "vbs_scripts": (C_WINDOWS, "VBScript", "VBScript utilities."),
    "AHK_SCRIPTS": (C_WINDOWS, "AutoHotkey", "AutoHotkey macro recorder scripts."),
    "AHK-Tasks-scheduler": (C_WINDOWS, "AutoHotkey", "Task scheduler written in AutoHotkey."),
    "AutoRisponderTool": (C_WINDOWS, "AutoHotkey", "Autoresponder tooling for growth hacking, in AHK."),
    "Chrome-Steps-Recorder": (C_WINDOWS, "AutoHotkey", "Step recorder for Chrome driven by AutoHotkey."),
    "imacros": (C_WINDOWS, "AutoHotkey", "iMacros installation and quick scripts."),
    "TagIE.ahk": (C_WINDOWS, "AutoHotkey", "TagIE — Internet Explorer web-process automation in AutoHotkey."),
    "TagIE_Scripts": (C_WINDOWS, "AutoHotkey", "TagIE browser automation examples and strategies."),
    "tagui_scripts": (C_WINDOWS, "AutoHotkey", "TagUI editor and browser automation scripts for Chrome/Firefox."),
    "PRT_AUTOHOTKEY": (C_WINDOWS, "AutoHotkey", "Backtesting automation for ProRealTime."),
    "YouTubeBox": (C_WINDOWS, "AutoHotkey", "YouTube box player for Windows."),
    "PRT_CODE": (C_WINDOWS, "Config", "Notepad++ syntax highlighter for ProRealTime code."),
    "scrcpy_parameters": (C_WINDOWS, "Config", "Recommended scrcpy mirroring parameters on Windows."),
    # AI & data
    "AI-book-generator": (C_AI, "Python", "Generates complete books using AI, driven from Python."),
    "cover_generator": (C_AI, "Python", "Stable Diffusion (SDXL) ebook cover generator — Kaggle notebook."),
    "Python_Chiller_cycle": (C_AI, "Python", "Chiller refrigeration-cycle analysis in Python."),
    "R_STAT": (C_AI, "R", "Statistical studies with R."),
    "PRT": (C_AI, "R", "Machine-learning experiments on ProRealTime data."),
    "MQL4_CODE": (C_AI, "MQL4", "MetaTrader 4 MQL4 indicators and strategies."),
    "Curl_Dom_Parser": (C_AI, "PHP", "Web scraping with cURL + DOM parser."),
    "SMS-Marketing": (C_AI, "PHP", "PHP REST API to send SMS messages."),
    "php": (C_AI, "PHP", "Web scraping with cURL-PHP and mailer experiments."),
    # Linux
    "linux-config-backup": (C_LINUX, "Shell", "Back up and restore your whole Linux config in one shot."),
    "bash_scripts": (C_LINUX, "Shell", "Assorted bash recipes (Puppy Linux era)."),
    "python_scripts": (C_LINUX, "Python", "Assorted Python scripts."),
    "autobrightness_linux": (C_LINUX, "Python", "Auto-adjusts screen brightness from your webcam feed."),
    "Hotspot_ad_blocker": (C_LINUX, "Shell", "DNS-filtering Wi-Fi hotspot that blocks ads for every client."),
    "Hourly-Gmail-Pinger": (C_LINUX, "JavaScript", "Checks Gmail on a schedule, so email comes to you instead of you hunting it."),
    "Arduino_AND_ESP32_projects": (C_LINUX, "C++", "Arduino and ESP32 hardware experiments."),
    "Ghost5_Pen_drawing": (C_LINUX, "Config", "Pen-plotter drawings made with a Ghost 5 3D printer."),
    "Debloat_Android_ADB": (C_LINUX, "Shell", "ADB commands to debloat stock Android."),
    # Meta & misc
    "blog": (C_META, "Docs", "This very site — the source of my GitHub Pages blog."),
    "adegard.github.io": (C_META, "HTML", "My GitHub Pages root site."),
    "adegard": (C_META, "Docs", "My GitHub profile intro README — auto-shown at the top of github.com/adegard."),
    "pc-dream": (C_META, "Docs", "Idea board: Intelligent Strategies for a Smarter World."),
    "JS_code": (C_META, "JavaScript", "Collection of small JavaScript snippets."),
    "ReactTest": (C_META, "JavaScript", "React playground / testing repo."),
    "Tutorial": (C_META, "Docs", "Assorted tutorial notes."),
    "test": (C_META, "Misc", "Public sandbox repo."),
}

# name -> (blurb, [tags])
FEATURED = [
    ("PixelCam", "A camera app that puts Pixel-grade photographic styles (HDR, night, portrait) on plain Android, with no tracking.", ["Kotlin", "CameraX", "Mobile"]),
    ("HealthX", "A step tracker that runs entirely on your phone — hardware step counting, targets & achievements, no watch, no cloud.", ["Kotlin", "Privacy", "Mobile"]),
    ("meteo-cesate", "Weather with worldwide city search, 24h + 7-day forecasts, and thunderstorm alerts pushed straight to your phone.", ["Kotlin", "Open-Meteo", "Mobile"]),
    ("autotrader-android", "An automatic trading bot: momentum + trend + sentiment stock selection with virtual money, or real trading via Saxo.", ["Kotlin", "Finance", "Mobile"]),
    ("epubreader", "A full EPUB reader — text-to-speech, bookmarks, themes and a library — in a clean swipe-driven Android app.", ["Kotlin", "TTS", "Mobile"]),
    ("blockblast", "A polished Block Blast puzzle game built with a custom Canvas renderer and zero external dependencies.", ["Kotlin", "Game", "Mobile"]),
    ("ytmusic-apk", "Search and stream YouTube songs on-device — no server, no account, no login. Background playback included.", ["JavaScript", "Audio", "Mobile"]),
    ("shell-agent", "An opencode-style coding agent for Termux powered entirely by Ollama. Reads, writes and runs code on your phone.", ["Shell", "AI", "Termux"]),
    ("GPS-Nav-HTML", "A single-file, offline GPS navigator: live tracking, POI search and turn-by-turn routing — no app store needed.", ["HTML", "Offline", "Web"]),
    ("No-Cookie-Browser", "A retro 90s-era GTK browser that runs ephemeral — no cookies, cache or history, perfect for the old internet feel.", ["Python", "GTK", "Privacy"]),
    ("amazon-tracker", "Browse Amazon with tracker & ad blocking and get price-drop alerts across ten Amazon regions.", ["Kotlin", "Shopping", "Mobile"]),
    ("RadioStreamer", "An ad-free internet radio app: stream any station, keep listening with the screen off, manage your own station list.", ["Kotlin", "Audio", "Mobile"]),
    ("RcloneRemotes", "A Kotlin/Compose Android app that manages all your cloud storage through rclone — file browser, text editor, uploads and multi-provider folder sync.", ["Kotlin", "Cloud", "Mobile"]),
]

# Repos that should never get an auto-detected screenshot thumbnail.
SHOT_BLACKLIST = {
    "Ghost5_Pen_drawing",
    "MyChocolateyApps",
    "AutomaticDesktopBackground",
    "WinScripts",
    "adegard.github.io",
    "TagIE.ahk",
    "tagui_scripts",
    "ReactTest",
    "AHK-Tasks-scheduler",
}

# Optional: pin the exact screenshot path for a repo; otherwise auto-detected.
SHOT_OVERRIDES = {
    "PixelCam": "docs/screenshot.png",
    "meteo-cesate": "docs/screenshot.png",
    "ytmusic-apk": "docs/screenshot.png",
    "GPS-Nav-HTML": "screenshots/Screenshot_20260807-101315.png",
    "No-Cookie-Browser": "screen.jpg",
    "GMaps-WV-Nav": "screenshots/navigation.png",
    "ImageCompressor": "Screenshot_20260829-104021.png",
    "TextBrowserApp": "screenshot.png",
    "mots-crois-s-android": "Screenshot_20260726-142401.png",
    "webreader": "Immagine 2025-06-12 120020.jpg",
    "terminal_text_browser": "screen.jpg",
    "PHP_Photo_Gallery-": "screen.jpg",
    "blockblast": "docs/gameplay.png",
    "HealthX": "screenshots/dashboard.png",
    "RcloneRemotes": "docs/screenshot.png",
    "AutoRisponderTool": "screenshot.png",
    "Chrome_extension_Weather_gmail": "Screenshot.png",
    "Formula_Updater": "Immagine 2025-06-09 141420.jpg",
    "PHP_drive_sync": "screen.jpg",
    "PHP_files_manager": "screenshot.jpg",
    "PHP_server_ebooks_reader": "screen_reader.jpg",
    "gsheet_notepad-plus-plus": "Cattura2.JPG",
    "Engineering_Gsheet_PFD": "Immagine 2025-06-10 103639.jpg",
    "xls_macro_save_value": "Immagine 2025-06-19 141138.jpg",
    "oled-keyboard": "screenshot.png",
    "epubreader": "screenshots/app.png",
    "amazon-tracker": "docs/screen1.png",
}

CAT_ORDER = [
    (C_ANDROID, None),
    (C_TERMINAL, None),
    (C_WEB, None),
    (C_GAS, None),
    (C_BROWSER, None),
    (C_WINDOWS, None),
    (C_AI, None),
    (C_LINUX, None),
    (C_META, "Small experiments, scaffolds and notes — included for completeness, not necessarily 'done' projects."),
]

BAD_ASSETS = re.compile(
    r"(node_modules|/gradle/|\.idea|\.git/|favicon|launcher|logo|/icon|icon |banner|badge|marker|\.svg$)",
    re.I,
)


def fallback_category(name, lang, desc):
    n = name.lower()
    d = (desc or "").lower() + " " + n
    if lang == "Kotlin" or "android" in d:
        return C_ANDROID
    if lang == "Shell" or "termux" in n or "terminal" in n or "tui" in n:
        return C_TERMINAL
    if lang in ("PHP", "HTML") or "web" in d or "server" in d or "browser" in d:
        return C_WEB
    if "sheet" in d or "apps script" in d or lang == "R":
        return C_GAS
    if "chrome" in n or "extension" in d or "bookmarklet" in n:
        return C_BROWSER
    if lang in ("PowerShell", "VBA", "VBScript", "AutoHotkey", "MQL4"):
        return C_WINDOWS
    if lang == "C++" or "arduino" in d or "esp" in d or "printer" in d:
        return C_LINUX
    if lang == "Python" or "ai" in d or "ml" in d:
        return C_AI
    return C_META


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------
def http_get(url):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "portfolio-gen",
            "Authorization": f"Bearer {TOKEN}",
        } if TOKEN else {
            "Accept": "application/vnd.github+json",
            "User-Agent": "portfolio-gen",
        },
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def fetch_repos():
    repos, page = [], 1
    while True:
        batch = http_get(f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}")
        if not batch:
            break
        repos.extend(r for r in batch if not r.get("fork"))
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_tree_paths(name):
    try:
        data = http_get(f"https://api.github.com/repos/{USER}/{name}/git/trees/HEAD?recursive=1")
        return [t.get("path", "") for t in data.get("tree", [])]
    except Exception:
        return []


def pick_shot(paths):
    best, best_score = None, None
    for p in paths:
        if not re.search(r"\.(png|jpe?g|gif|webp)$", p, re.I):
            continue
        if BAD_ASSETS.search(p):
            continue
        score = 4
        pl = p.lower()
        if "screenshot" in pl:
            score = 0
        elif "screen." in pl or "screen_" in pl:
            score = 1
        elif "screenshots/" in pl:
            score = 1
        elif pl.startswith("docs/") or pl.startswith("immagine "):
            score = 2
        elif "/" not in p:
            score = 3
        if best_score is None or score < best_score:
            best, best_score = p, score
    return best


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------
def lang_color(lang):
    return LANG_COLORS.get(lang, FALLBACK)


def label(lang):
    return lang if lang else FALLBACK_LABEL


def thumb(name, shot):
    if not shot:
        return ""
    q = urllib.parse.quote(shot, safe="/")
    return (
        f'<img class="thumb" loading="lazy" '
        f'src="https://raw.githubusercontent.com/{USER}/{name}/HEAD/{q}" '
        f'alt="{name} screenshot">'
    )


def lang_badge(lang):
    c = lang_color(lang)
    return f'<span class="badge"><span class="dot" style="background:{c}"></span>{label(lang)}</span>'


def card(item):
    name, cat, lang, desc, shot = item
    return f"""
      <a class="card" href="https://github.com/{USER}/{name}" target="_blank" rel="noopener">
        {thumb(name, shot)}
        <div class="card-head"><h3>{name}</h3>{lang_badge(lang)}</div>
        <p>{desc}</p>
        <span class="card-go">View repo →</span>
      </a>"""


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=OUT)
    args = ap.parse_args()
    OUT = args.out

    repos = fetch_repos()
    if not repos:
        print("error: no repos fetched", file=sys.stderr)
        sys.exit(1)

    live = {}
    for r in repos:
        live[r["name"]] = {
            "desc": (r.get("description") or "").strip() or r["name"],
            "lang": r.get("language") or "",
            "pushed": (r.get("pushed_at") or "")[:10],
        }

    # Merge curated order with live data, append brand-new repos.
    items = []  # (name, cat, lang, desc, shot)
    seen = set()
    for name in list(CURATED.keys()) + sorted(live.keys()):
        if name in seen or name not in live:
            continue
        seen.add(name)
        data = live[name]
        cur = CURATED.get(name)
        cat = cur[0] if cur else fallback_category(name, data["lang"], data["desc"])
        lang = data["lang"] or (cur[1] if cur else "")
        desc = cur[2] if cur else data["desc"]
        if name in CURATED and len(cur) == 3:
            pass
        items.append([name, cat, lang, desc, None])

    # Screenshot scan (idempotent: overrides win, otherwise auto-detect).
    print(f"scanning {len(items)} repos for screenshots…")
    for it in items:
        name = it[0]
        if name in SHOT_OVERRIDES:
            it[4] = SHOT_OVERRIDES[name]
            continue
        if name in SHOT_BLACKLIST:
            it[4] = None
            continue
        it[4] = pick_shot(fetch_tree_paths(name))

    n_shots = sum(1 for it in items if it[4])
    print(f"repos: {len(items)} | with screenshots: {n_shots}")

    # Assemble HTML using the same template as the static generator.
    featured_names = {f[0] for f in FEATURED if any(it[0] == f[0] for it in items)}
    fcards = []
    for name, blurb, tags in FEATURED:
        if name not in featured_names:
            continue
        it = next(x for x in items if x[0] == name)
        tag_html = "".join(f'<span class="tag">{t}</span>' for t in tags)
        fcards.append(f"""
      <a class="fcard" href="https://github.com/{USER}/{name}" target="_blank" rel="noopener">
        {thumb(name, it[4])}
        <div class="fcard-top">
          <span class="fcard-star">★</span>
          <h3>{name}</h3>
        </div>
        <p>{blurb}</p>
        <div class="tags">{tag_html}</div>
        <span class="fcard-go">Open in GitHub →</span>
      </a>""")

    cat_buttons = ['<button class="fbtn active" data-filter="all">All</button>'] + [
        f'<button class="fbtn" data-filter="{cid}">{CAT_LABELS[cid]}</button>' for cid, _ in CAT_ORDER
    ]

    sections = []
    for cid, note in CAT_ORDER:
        rows = [c for c in items if c[1] == cid]
        cards_html = "\n".join(card(r) for r in rows)
        note_html = f'<p class="section-note">{note}</p>' if note else ""
        sections.append(f"""
    <section class="cat" id="cat-{cid}">
      <h2 class="cat-title">{CAT_LABELS[cid]} <span class="count">{len(rows)}</span></h2>
      {note_html}
      <div class="grid">{cards_html}
      </div>
    </section>""")

    langs = {}
    for it in items:
        l = it[2]
        if l:
            langs[l] = langs.get(l, 0) + 1
    top_lang = max(langs, key=langs.get) if langs else "-"
    android_n = sum(1 for it in items if it[1] == C_ANDROID)
    term_n = sum(1 for it in items if it[1] == C_TERMINAL)
    year = "2026"
    stats = [
        (str(len(items)), "public repos"),
        (str(android_n), "Android apps"),
        (str(term_n), "terminal tools"),
        (top_lang, "most used language"),
        (f"2016–{year}", "years tinkering"),
    ]
    stats_html = "\n          ".join(
        f'<div class="stat"><div class="stat-n">{b}</div><div class="stat-l">{s}</div></div>'
        for b, s in stats
    )
    fcards_html = "".join(fcards)
    cat_buttons_html = "\n      ".join(cat_buttons)
    sections_html = "".join(sections)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>adegard — projects & portfolio</title>
<meta name="description" content="adegard — open-source projects: Android apps, terminal tools, web experiments and more.">
<link rel="icon" type="image/png" href="{AVATAR_URL}">
<style>
  :root {{
    --bg: #0e1116;
    --bg2: #131820;
    --card: #171d27;
    --border: #232b38;
    --text: #e6eaf0;
    --muted: #9aa7b8;
    --accent: #4cc2ff;
    --accent2: #7c6cff;
    --radius: 14px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.55;
  }}
  a {{ color: inherit; text-decoration: none; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 0 20px; }}

  nav {{
    position: sticky; top: 0; z-index: 50;
    background: rgba(14,17,22,.85);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
  }}
  nav .wrap {{ display: flex; align-items: center; justify-content: space-between; height: 58px; }}
  .brand {{ font-weight: 700; font-size: 1.05rem; letter-spacing: .3px; display: flex; align-items: center; }}
  .brand img {{ width: 26px; height: 26px; border-radius: 50%; margin-right: 9px; border: 1px solid var(--border); }}
  .brand span {{ color: var(--accent); }}
  .navlinks {{ display: flex; gap: 18px; font-size: .9rem; color: var(--muted); }}
  .navlinks a:hover {{ color: var(--text); }}

  header.hero {{ padding: 72px 0 30px; text-align: center; }}
  .hero h1 {{ font-size: 2.6rem; letter-spacing: .5px; }}
  .hero .role {{ color: var(--accent); font-weight: 600; margin-top: 6px; }}
  .hero p.tagline {{ color: var(--muted); max-width: 640px; margin: 14px auto 0; }}
  .hero .socials {{ margin-top: 20px; display: flex; gap: 14px; justify-content: center; }}
  .hero .socials a {{
    border: 1px solid var(--border); background: var(--card);
    padding: 8px 16px; border-radius: 999px; font-size: .85rem; color: var(--muted);
    transition: .15s;
  }}
  .hero .socials a:hover {{ color: var(--text); border-color: var(--accent); }}

  .stats {{
    display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px;
    margin: 40px 0 10px;
  }}
  .stat {{ background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px 10px; text-align: center; }}
  .stat-n {{ font-size: 1.6rem; font-weight: 800; color: var(--accent); }}
  .stat-l {{ font-size: .8rem; color: var(--muted); margin-top: 2px; }}

  section.block {{ padding: 46px 0; }}
  h2.section-title {{ font-size: 1.5rem; margin-bottom: 22px; }}
  h2.section-title::after {{ content: ""; display: block; width: 46px; height: 3px; margin-top: 8px; border-radius: 2px; background: linear-gradient(90deg, var(--accent), var(--accent2)); }}

  .fgrid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }}
  .fcard {{
    background: linear-gradient(160deg, var(--card), var(--bg2));
    border: 1px solid var(--border); border-radius: var(--radius);
    padding: 22px; display: flex; flex-direction: column; gap: 10px;
    transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
  }}
  .fcard:hover {{ transform: translateY(-3px); border-color: var(--accent); box-shadow: 0 10px 30px rgba(76,194,255,.08); }}
  .fcard-top {{ display: flex; align-items: center; gap: 8px; }}
  .fcard-star {{ color: var(--accent); font-size: .8rem; }}
  .fcard h3 {{ font-size: 1.08rem; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  .fcard p {{ color: var(--muted); font-size: .92rem; flex: 1; }}
  .tags {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .tag {{
    font-size: .72rem; padding: 3px 9px; border-radius: 999px;
    background: rgba(124,108,255,.12); color: #b6aaff; border: 1px solid rgba(124,108,255,.3);
  }}
  .fcard-go {{ color: var(--accent); font-size: .85rem; font-weight: 600; }}

  .filters {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 26px; }}
  .fbtn {{
    background: var(--card); color: var(--muted); border: 1px solid var(--border);
    padding: 7px 14px; border-radius: 999px; font-size: .82rem; cursor: pointer; transition: .15s;
  }}
  .fbtn:hover {{ color: var(--text); border-color: var(--accent); }}
  .fbtn.active {{ background: var(--accent); border-color: var(--accent); color: #04121c; font-weight: 700; }}

  .cat {{ margin-bottom: 52px; }}
  .cat-title {{ font-size: 1.3rem; margin-bottom: 16px; }}
  .cat-title .count {{
    font-size: .85rem; vertical-align: middle; margin-left: 8px; color: var(--muted);
    background: var(--bg2); border: 1px solid var(--border); border-radius: 999px; padding: 2px 10px;
  }}
  .section-note {{ color: var(--muted); font-size: .85rem; margin: -10px 0 16px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }}

  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px; display: flex; flex-direction: column; gap: 8px; transition: .15s ease; }}
  .card:hover {{ border-color: var(--accent); transform: translateY(-2px); }}
  .thumb {{ width: 100%; height: 130px; object-fit: cover; border-radius: 8px; border: 1px solid var(--border); background: var(--bg2); }}
  .fcard .thumb {{ height: 170px; margin: -22px -22px 14px; width: calc(100% + 44px); border: none; border-bottom: 1px solid var(--border); border-radius: var(--radius) var(--radius) 0 0; }}
  .card-head {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
  .card h3 {{ font-size: .98rem; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
  .badge {{
    font-size: .7rem; color: var(--muted); background: var(--bg2);
    border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px;
    display: inline-flex; align-items: center; gap: 5px; white-space: nowrap;
  }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
  .card p {{ color: var(--muted); font-size: .87rem; flex: 1; }}
  .card-go {{ color: var(--accent); font-size: .8rem; font-weight: 600; opacity: .8; }}
  .card:hover .card-go {{ opacity: 1; }}

  footer {{ border-top: 1px solid var(--border); padding: 34px 0 50px; color: var(--muted); font-size: .85rem; }}
  footer .wrap {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; align-items: center; }}

  @media (max-width: 720px) {{
    .stats {{ grid-template-columns: repeat(2, 1fr); }}
    nav .navlinks {{ display: none; }}
  }}
</style>
</head>
<body>

<nav>
  <div class="wrap">
    <a class="brand" href="#top"><img src="{AVATAR_URL}" alt="adegard logo"><span>adegard</span> · projects</a>
    <div class="navlinks">
      <a href="#featured">Featured</a>
      <a href="#projects">All projects</a>
      <a href="https://github.com/{USER}" target="_blank" rel="noopener">GitHub</a>
    </div>
  </div>
</nav>

<header class="hero" id="top">
  <div class="wrap">
    <h1>adegard</h1>
    <div class="role">Android · Python · Web · Automation · AI experiments</div>
    <p class="tagline">Everything here is open source. Most of it is built to solve a real, everyday problem — on a phone, in a terminal, or on my own hardware. No tracking, no cloud, no accounts.</p>
    <div class="socials">
      <a href="https://github.com/{USER}" target="_blank" rel="noopener">GitHub · @{USER}</a>
    </div>
    <div class="stats">
      {stats_html}
    </div>
  </div>
</header>

<section class="block" id="featured">
  <div class="wrap">
    <h2 class="section-title">Featured projects</h2>
    <div class="fgrid">{fcards_html}
    </div>
  </div>
</section>

<section class="block" id="projects">
  <div class="wrap">
    <h2 class="section-title">All projects</h2>
    <div class="filters">
      {cat_buttons_html}
    </div>
    {sections_html}
  </div>
</section>

<footer>
  <div class="wrap">
    <span>© adegard · built with plain HTML/CSS · auto-generated from GitHub's API</span>
    <span><a href="https://github.com/{USER}" target="_blank" rel="noopener" style="color:var(--accent)">github.com/{USER}</a></span>
  </div>
</footer>

<script>
  const btns = document.querySelectorAll(".fbtn");
  const cats = document.querySelectorAll(".cat");
  btns.forEach(btn => {{
    btn.addEventListener("click", () => {{
      btns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const f = btn.dataset.filter;
      cats.forEach(c => {{
        c.style.display = (f === "all" || c.id === "cat-" + f) ? "" : "none";
      }});
    }});
  }});
</script>
</body>
</html>
"""
    with open(OUT, "w") as f:
        f.write(html)
    print(f"wrote {OUT} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()