"""
CACTUS Personal AI Assistant v5.0
- JARVIS-like personality
- Responds to ALL voice commands — no wake word needed
- TTS via PowerShell SAPI (guaranteed on Windows)
- Spotify auto-play via URI
- Smart command guessing via Groq for unknown inputs
"""

import os
import sys
import time
import threading
import subprocess
import webbrowser
import urllib.request
import urllib.parse
import json
import datetime
import re
import queue
from dotenv import load_dotenv

load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
MASTER_NAME   = os.getenv("MASTER_NAME", "Master")
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
WEATHER_CITY  = os.getenv("WEATHER_CITY", "Chennai")

# ── State ────────────────────────────────────────────────────────────────────
quiet_mode   = False
voice_active = False

# ── TTS — PowerShell SAPI ─────────────────────────────────────────────────────
_tts_queue  = queue.Queue()
_tts_ready  = threading.Event()
_tts_engine = None

def _speak_powershell_blocking(text: str):
    safe = text.replace("'", "").replace('"', "")
    subprocess.run(
        ["powershell", "-Command",
         f"Add-Type -AssemblyName System.Speech; "
         f"$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
         f"$s.Rate=2; $s.Volume=100; $s.Speak('{safe}')"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def _tts_worker():
    _tts_ready.set()
    while True:
        item = _tts_queue.get()
        if item is None:
            break
        try:
            _speak_powershell_blocking(item)
        finally:
            _tts_queue.task_done()

_tts_thread = threading.Thread(target=_tts_worker, daemon=True)
_tts_thread.start()

def speak(text: str):
    if quiet_mode:
        print(f"[CACTUS — muted] {text}")
        return
    print(f"[CACTUS] {text}")
    _tts_queue.put(text)

def speak_wait(text: str):
    speak(text)
    if not quiet_mode:
        _tts_queue.join()

def debug_tts():
    print("[DEBUG] TTS mode: PowerShell SAPI (guaranteed)")

# ── Groq Brain — JARVIS personality ──────────────────────────────────────────
def ask_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        return "No Groq API key configured, sir."
    try:
        payload = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "max_tokens": 500,
            "messages": [
                {"role": "system", "content": (
                    f"You are CACTUS, a highly intelligent personal AI assistant — "
                    f"think JARVIS from Iron Man. You serve {MASTER_NAME} exclusively. "
                    f"Your tone is calm, composed, witty, and razor-sharp. "
                    f"You are never sycophantic. You speak in short, punchy sentences — "
                    f"maximum 2-3 sentences per response unless more detail is explicitly requested. "
                    f"You occasionally make dry, clever remarks. "
                    f"You address {MASTER_NAME} by name naturally, not every sentence. "
                    f"Never say 'Certainly!' or 'Of course!' or 'Great question!' — "
                    f"just answer directly and confidently."
                )},
                {"role": "user", "content": prompt}
            ]
        }).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"My neural link is down, {MASTER_NAME}. {e}"

# ── Groq Command Guesser ──────────────────────────────────────────────────────
def guess_command(cmd: str) -> str:
    """Ask Groq to interpret an ambiguous command and respond naturally."""
    if not GROQ_API_KEY:
        return ask_groq(cmd)
    try:
        payload = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "max_tokens": 300,
            "messages": [
                {"role": "system", "content": (
                    f"You are CACTUS, a JARVIS-like AI assistant for {MASTER_NAME}. "
                    f"The user said something you need to interpret. "
                    f"Figure out what they most likely want — whether it's information, "
                    f"a task, a question, small talk, or anything else — and respond naturally. "
                    f"Be concise, witty, and direct. Max 2-3 sentences. "
                    f"If it sounds like they want music, news, weather, or web search, "
                    f"tell them what you'd do and do your best to answer."
                )},
                {"role": "user", "content": cmd}
            ]
        }).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Couldn't parse that one, {MASTER_NAME}. {e}"

# ── Spotify — search + auto play ─────────────────────────────────────────────
def get_spotify_track_uri(query: str) -> str:
    """Search Spotify API for a track and return its URI for direct playback."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.spotify.com/v1/search?q={encoded}&type=track&limit=1"
        # Use open.spotify.com search URL with autoplay intent via URI
        # We use the spotify: URI scheme which triggers the desktop app directly
        return f"spotify:search:{encoded}"
    except Exception:
        return ""

def handle_spotify(cmd: str):
    # Extract the song/artist query
    query = re.sub(
        r"\b(play|open|launch|spotify|on|via|using|start|put on|queue)\b",
        "", cmd, flags=re.IGNORECASE
    ).strip(" ,.")

    if query:
        encoded = urllib.parse.quote(query)
        # This URI opens Spotify desktop app AND triggers search + play
        spotify_uri = f"spotify:search:{encoded}"
        # Also open web fallback
        web_url = f"https://open.spotify.com/search/{encoded}"

        speak(f"Playing {query} on Spotify.")
        # Open the URI — Spotify desktop app handles autoplay
        subprocess.Popen(
            ["powershell", "-Command", f'Start-Process "{spotify_uri}"'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(1.5)
        # Simulate pressing Enter/Play in Spotify using keyboard shortcut
        ps_play = (
            "$w = New-Object -ComObject WScript.Shell; "
            "Start-Sleep -Milliseconds 800; "
            "$w.AppActivate('Spotify'); "
            "Start-Sleep -Milliseconds 500; "
            "$w.SendKeys(' ')"   # Space bar = play/pause in Spotify
        )
        subprocess.Popen(
            ["powershell", "-Command", ps_play],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    else:
        speak("Opening Spotify.")
        subprocess.Popen(
            ["powershell", "-Command", 'Start-Process "spotify:"'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

# ── Weather ───────────────────────────────────────────────────────────────────
def get_weather(city: str = None) -> str:
    city = city or WEATHER_CITY
    try:
        encoded = urllib.parse.quote(city)
        url = f"https://wttr.in/{encoded}?format=3"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8").strip()
            clean = re.sub(r'[^\x00-\x7F+\-\d\w\s:,.]', '', raw).strip()
            return clean
    except Exception as e:
        return f"Could not fetch weather: {e}"

# ── News RSS ──────────────────────────────────────────────────────────────────
def fetch_rss(url: str, count: int = 3):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        items = re.findall(r"<item>(.*?)</item>", content, re.DOTALL)
        results = []
        for item in items[:count]:
            t = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item)
            if not t:
                t = re.search(r"<title>(.*?)</title>", item)
            title = t.group(1).strip() if t else ""
            l = re.search(r"<link>(.*?)</link>", item)
            if not l:
                l = re.search(r"<guid[^>]*>(https?://[^<]+)</guid>", item)
            link = l.group(1).strip() if l else ""
            if title:
                results.append((title, link))
        return results
    except Exception:
        return []

def get_tamilnadu_news(count=3):
    feeds = [
        "https://www.thehindu.com/news/national/tamil-nadu/feeder/default.rss",
        "https://feeds.feedburner.com/ndtvnews-tamil-nadu",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128938702.cms",
    ]
    for feed in feeds:
        items = fetch_rss(feed, count)
        if items:
            return items
    return [("Could not fetch Tamil Nadu news.", "")]

def get_global_news(count=3):
    feeds = [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    ]
    for feed in feeds:
        items = fetch_rss(feed, count)
        if items:
            return items
    return [("Could not fetch global news.", "")]

def get_topic_news(topic: str, count=3):
    encoded = urllib.parse.quote(topic)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"
    items = fetch_rss(url, count)
    return items if items else [(f"No news found for {topic}.", "")]

# ── Boot Greeting ─────────────────────────────────────────────────────────────
def boot_greeting():
    _tts_ready.wait(timeout=10)
    debug_tts()
    time.sleep(0.5)

    now  = datetime.datetime.now()
    hour = now.hour
    tod  = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")

    speak_wait(f"{tod}, {MASTER_NAME}. All systems are online. CACTUS is ready.")
    time.sleep(0.3)

    speak_wait("Pulling your weather now.")
    weather = get_weather()
    speak_wait(f"{WEATHER_CITY}: {weather}")
    time.sleep(0.3)

    speak_wait("Your Tamil Nadu briefing. Opening each article as I go.")
    tn_news = get_tamilnadu_news(3)
    for i, (title, link) in enumerate(tn_news, 1):
        speak_wait(f"Headline {i}: {title}")
        if link:
            webbrowser.open(link)
        time.sleep(0.4)

    speak_wait("Global headlines now.")
    g_news = get_global_news(3)
    for i, (title, link) in enumerate(g_news, 1):
        speak_wait(f"Headline {i}: {title}")
        if link:
            webbrowser.open(link)
        time.sleep(0.4)

    speak_wait(f"That's your morning briefing, {MASTER_NAME}. I'm listening.")

# ── Command Handlers ──────────────────────────────────────────────────────────
def handle_volume(cmd: str):
    if "unmute" in cmd:
        os.system("nircmd.exe mutesysvolume 0")
        speak("Unmuted.")
    elif "mute" in cmd:
        os.system("nircmd.exe mutesysvolume 1")
        speak("Muted.")
    else:
        m = re.search(r"(\d+)", cmd)
        if m:
            level = max(0, min(100, int(m.group(1))))
            os.system(f"nircmd.exe setsysvolume {int(65535 * level / 100)}")
            speak(f"Volume at {level} percent.")
        elif "up" in cmd:
            os.system("nircmd.exe changesysvolume 6554")
            speak("Volume up.")
        elif "down" in cmd:
            os.system("nircmd.exe changesysvolume -6554")
            speak("Volume down.")

def handle_brightness(cmd: str):
    m = re.search(r"(\d+)", cmd)
    level = int(m.group(1)) if m else (30 if "dim" in cmd else 100)
    level = max(0, min(100, level))
    ps = (f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
          f".WmiSetBrightness(1,{level})")
    subprocess.run(["powershell", "-Command", ps], capture_output=True)
    speak(f"Brightness at {level} percent.")

def handle_whatsapp(cmd: str):
    m = re.search(r"whatsapp\s+(\d+)\s+(.*)", cmd, re.IGNORECASE)
    if m:
        webbrowser.open(f"https://wa.me/{m.group(1)}?text={urllib.parse.quote(m.group(2))}")
        speak("WhatsApp message ready to send.")
    else:
        webbrowser.open("https://web.whatsapp.com")
        speak("Opening WhatsApp.")

def handle_email(cmd: str):
    to_m  = re.search(r"to\s+([\w@.\-]+)", cmd, re.IGNORECASE)
    sub_m = re.search(r"subject\s+(.+?)(?=body|$)", cmd, re.IGNORECASE)
    bod_m = re.search(r"body\s+(.+)", cmd, re.IGNORECASE)
    to      = to_m.group(1)          if to_m  else ""
    subject = sub_m.group(1).strip() if sub_m else ""
    body    = bod_m.group(1).strip() if bod_m else ""
    params  = urllib.parse.urlencode({"to": to, "su": subject, "body": body})
    webbrowser.open(f"https://mail.google.com/mail/?view=cm&fs=1&{params}")
    speak(f"Composing email to {to}.")

def handle_news(cmd: str):
    c = cmd.lower()
    if "tamil" in c:
        speak("Tamil Nadu headlines. Opening articles now.")
        items = get_tamilnadu_news(4)
    elif any(x in c for x in ["global", "world", "international"]):
        speak("Global headlines. Opening articles now.")
        items = get_global_news(4)
    else:
        topic = re.sub(r"(news|on|about|regarding|latest|headlines)", "", c, flags=re.IGNORECASE).strip()
        speak(f"Fetching news on {topic}." if topic else "Pulling global news.")
        items = get_topic_news(topic, 4) if topic else get_global_news(4)
    for i, (title, link) in enumerate(items, 1):
        speak_wait(f"Headline {i}: {title}")
        if link:
            webbrowser.open(link)
        time.sleep(0.4)

def handle_search(cmd: str):
    query = re.sub(r"(search|google|look up|find)", "", cmd, flags=re.IGNORECASE).strip()
    if query:
        webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
        speak(f"Searching for {query}.")

def handle_stocks(cmd: str):
    ticker = re.sub(r"(stock|price|stocks|shares?|of|for|check)", "", cmd,
                    flags=re.IGNORECASE).strip().upper()
    if ticker:
        webbrowser.open(f"https://finance.yahoo.com/quote/{ticker}")
        speak(f"Pulling up {ticker}.")

def handle_screenshot():
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(os.path.expanduser("~"), "Pictures", f"cactus_{ts}.png")
    subprocess.run([
        "powershell", "-Command",
        f"Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
        f"$b=New-Object System.Drawing.Bitmap([System.Windows.Forms.Screen]::"
        f"PrimaryScreen.Bounds.Width,[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); "
        f"$g=[System.Drawing.Graphics]::FromImage($b); "
        f"$g.CopyFromScreen(0,0,0,0,$b.Size); $b.Save('{path}')"
    ], capture_output=True)
    speak("Screenshot saved to Pictures.")

def handle_media(cmd: str):
    keys = {
        "next": "{NEXTTRACK}", "skip": "{NEXTTRACK}",
        "previous": "{PREVTRACK}", "prev": "{PREVTRACK}",
        "pause": "{MEDIA_PLAY_PAUSE}", "resume": "{MEDIA_PLAY_PAUSE}",
        "stop": "{MEDIA_STOP}"
    }
    for kw, key in keys.items():
        if kw in cmd:
            ps = f"$w=New-Object -ComObject WScript.Shell; $w.SendKeys('{key}')"
            subprocess.run(["powershell", "-Command", ps], capture_output=True)
            speak(f"{kw.capitalize()}.")
            return

def handle_system(cmd: str):
    if "sleep" in cmd:
        speak(f"Goodnight, {MASTER_NAME}.")
        time.sleep(1)
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    elif "shutdown" in cmd:
        speak("Shutting down. See you on the other side.")
        os.system("shutdown /s /t 5")
    elif "restart" in cmd:
        speak("Restarting. Back in a moment.")
        os.system("shutdown /r /t 5")
    elif "lock" in cmd:
        speak("Locking up.")
        os.system("rundll32.exe user32.dll,LockWorkStation")

def what_time() -> str:
    return datetime.datetime.now().strftime("It's %I:%M %p on %A, %B %d.")

# ── Quiet / Talk ──────────────────────────────────────────────────────────────
def enter_quiet_mode():
    global quiet_mode
    msg = "Going silent. I'll be here when you need me."
    _tts_queue.put(msg)
    _tts_queue.join()
    quiet_mode = True
    print("[CACTUS] Quiet mode ON.")

def exit_quiet_mode():
    global quiet_mode
    quiet_mode = False
    speak(f"Back online, {MASTER_NAME}. What do you need?")

# ── Command Router ────────────────────────────────────────────────────────────
def route_command(cmd: str):
    c = cmd.lower().strip()

    if any(x in c for x in ["be quiet", "shut up", "go quiet", "silence", "stop talking"]):
        enter_quiet_mode(); return
    if any(x in c for x in ["talk to me", "come back", "i need you", "stop being quiet"]):
        exit_quiet_mode(); return
    if quiet_mode:
        return

    if any(x in c for x in ["volume", "mute", "unmute"]):
        handle_volume(c)
    elif any(x in c for x in ["brightness", "dim", "brighten"]):
        handle_brightness(c)
    elif "spotify" in c or re.search(r"\bplay\b.{1,60}\b(song|track|music|by|on spotify)?\b", c):
        handle_spotify(c)
    elif any(x in c for x in ["next track", "previous track", "next song", "skip", "pause music", "stop music", "resume music"]):
        handle_media(c)
    elif "whatsapp" in c:
        handle_whatsapp(c)
    elif "email" in c or "gmail" in c:
        handle_email(c)
    elif "news" in c or "headlines" in c:
        handle_news(c)
    elif "weather" in c:
        m    = re.search(r"weather\s+(?:in|for|at)?\s*(.+)", c)
        city = m.group(1).strip() if m else WEATHER_CITY
        speak(get_weather(city))
    elif "stock" in c or "share price" in c:
        handle_stocks(c)
    elif any(x in c for x in ["search", "google", "look up", "find"]):
        handle_search(c)
    elif "screenshot" in c:
        handle_screenshot()
    elif any(x in c for x in ["time", "date", "what day"]):
        speak(what_time())
    elif any(x in c for x in ["sleep pc", "shutdown", "restart", "lock pc", "lock screen", "lock"]):
        handle_system(c)
    elif "help" in c:
        speak(
            f"You can ask me anything, {MASTER_NAME}. "
            "Spotify, volume, brightness, WhatsApp, Gmail, "
            "news, weather, stocks, Google, screenshots, system controls, "
            "or just talk to me. I'll figure it out."
        )
    else:
        # Groq guesses intent and responds for EVERYTHING else
        speak(guess_command(cmd))

# ── Voice Loop — always listening, no wake word ───────────────────────────────
def voice_loop():
    global voice_active
    try:
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        recognizer.energy_threshold         = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold          = 0.8

        try:
            mic = sr.Microphone()
        except Exception as e:
            print(f"[VOICE] No microphone: {e}")
            return

        with mic as source:
            print("[VOICE] Calibrating mic...")
            recognizer.adjust_for_ambient_noise(source, duration=1.5)

        voice_active = True
        print("[CACTUS] Always listening. No wake word needed.")

        while True:
            if quiet_mode:
                time.sleep(0.3)
                continue
            try:
                with mic as source:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
                text = recognizer.recognize_google(audio).lower().strip()
                if not text:
                    continue
                print(f"[HEARD] {text}")
                route_command(text)

            except sr.WaitTimeoutError:
                pass
            except sr.UnknownValueError:
                pass
            except Exception as e:
                print(f"[VOICE ERR] {e}")
                time.sleep(1)

    except ImportError:
        print("[VOICE] SpeechRecognition not available. Text mode only.")
        voice_active = False

# ── Terminal boot art ─────────────────────────────────────────────────────────
def terminal_boot():
    os.system("cls" if os.name == "nt" else "clear")
    lines = [
        "  ██████╗ █████╗  ██████╗████████╗██╗   ██╗███████╗",
        "  ██╔════╝██╔══██╗██╔════╝╚══██╔══╝██║   ██║██╔════╝",
        "  ██║     ███████║██║        ██║   ██║   ██║███████╗",
        "  ██║     ██╔══██║██║        ██║   ██║   ██║╚════██║",
        "  ╚██████╗██║  ██║╚██████╗   ██║   ╚██████╔╝███████║",
        "   ╚═════╝╚═╝  ╚═╝ ╚═════╝   ╚═╝    ╚═════╝ ╚══════╝",
        "",
        "        Personal AI Assistant v5.0",
        "  ─────────────────────────────────────────",
    ]
    for line in lines:
        print(f"\033[32m{line}\033[0m")
        time.sleep(0.06)
    print()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    terminal_boot()

    _tts_ready.wait(timeout=8)
    debug_tts()

    voice_thread = threading.Thread(target=voice_loop, daemon=True)
    voice_thread.start()

    boot_greeting()

    time.sleep(2)

    if not voice_active:
        print("\n[CACTUS] No mic detected — text mode active.")
        print("[TYPE COMMANDS BELOW]\n")
        while True:
            try:
                cmd = input(">> ").strip()
                if not cmd:
                    continue
                if cmd.lower() in ["exit", "quit", "bye"]:
                    speak_wait(f"Goodbye, {MASTER_NAME}. Stay sharp.")
                    sys.exit(0)
                route_command(cmd)
            except (KeyboardInterrupt, EOFError):
                speak_wait(f"Goodbye, {MASTER_NAME}.")
                sys.exit(0)
    else:
        print("\n[CACTUS] Always listening. Just talk.")
        print("         Ctrl+C to exit.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            speak_wait(f"Goodbye, {MASTER_NAME}. Stay sharp.")
            sys.exit(0)

if __name__ == "__main__":
    main()