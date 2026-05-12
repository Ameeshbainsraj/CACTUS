"""
CACTUS Personal AI Assistant v5.0 — Bulletproof Edition
- JARVIS personality via Groq
- Always listening, no wake word
- Local fast-path for all core commands (no Groq needed)
- Groq only used for ambiguous/chat commands
- TTS via PowerShell SAPI
- Spotify desktop app only
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
WEATHER_CITY  = os.getenv("WEATHER_CITY", "Chennai")

# ── State ────────────────────────────────────────────────────────────────────
quiet_mode   = False
voice_active = False

# ── TTS — PowerShell SAPI ────────────────────────────────────────────────────
_tts_queue = queue.Queue()
_tts_ready = threading.Event()

def _speak_powershell_blocking(text: str):
    safe = text.replace("'", "").replace('"', "")
    subprocess.run(
        ["powershell", "-Command",
         f"Add-Type -AssemblyName System.Speech; "
         f"$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
         f"$s.Rate=2; $s.Volume=100; $s.Speak('{safe}')"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
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

# ── Groq — Central Brain ──────────────────────────────────────────────────────
def groq_request(messages: list, max_tokens: int = 500) -> str:
    if not GROQ_API_KEY:
        return "No Groq API key set."
    try:
        payload = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "max_tokens": max_tokens,
            "messages": messages
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
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Neural link down. {e}"

def parse_intent(cmd: str) -> dict:
    system_prompt = f"""
You are the intent parser for CACTUS, a JARVIS-like AI assistant for {MASTER_NAME}.

Given a user's voice command, return a JSON object with:
- "intent": one of [spotify, volume_up, volume_down, volume_set, mute, unmute,
  brightness_set, brightness_up, brightness_down,
  whatsapp, email, news_tamil, news_global, news_topic,
  weather, stock, search, screenshot, time, lock, sleep_pc,
  shutdown, restart, media_next, media_prev, media_pause, media_resume,
  quiet_mode, resume_mode, chat]
- "query": the main subject/search term extracted (song name, city, topic, number etc.)
- "response": a short JARVIS-style spoken confirmation (1 sentence, witty, direct)

Rules:
- If user says anything about music/songs/artists → spotify
- If user says open/launch/start spotify with no song → intent=spotify, query=""
- For volume: extract number if given, else just up/down
- For brightness: extract number if given
- For news: detect if tamil, global, or specific topic
- For weather: extract city name or use default
- For stocks: extract ticker symbol
- For search/google/find/look up: extract search query
- For casual chat, questions, jokes, general conversation → chat
- ONLY return valid JSON, nothing else.

Example:
{{"intent": "spotify", "query": "Blinding Lights The Weeknd", "response": "Playing Blinding Lights on Spotify."}}
"""
    result = groq_request([
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": cmd}
    ], max_tokens=200)

    try:
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {"intent": "chat", "query": cmd, "response": ""}

def ask_groq_chat(prompt: str) -> str:
    return groq_request([
        {"role": "system", "content": (
            f"You are CACTUS, a highly intelligent personal AI — think JARVIS from Iron Man. "
            f"You serve {MASTER_NAME} exclusively. "
            f"Tone: calm, composed, witty, razor-sharp. Never sycophantic. "
            f"Max 2-3 sentences. Dry humour occasionally. "
            f"Address {MASTER_NAME} by name naturally, not every sentence. "
            f"Never say Certainly, Of course, or Great question."
        )},
        {"role": "user", "content": prompt}
    ])

# ── Weather ───────────────────────────────────────────────────────────────────
def get_weather(city: str = None) -> str:
    city = city or WEATHER_CITY
    try:
        encoded = urllib.parse.quote(city)
        req = urllib.request.Request(
            f"https://wttr.in/{encoded}?format=3",
            headers={"User-Agent": "curl/7.68.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8").strip()
            return re.sub(r'[^\x00-\x7F+\-\d\w\s:,.]', '', raw).strip()
    except Exception as e:
        return f"Could not fetch weather: {e}"

# ── News RSS ──────────────────────────────────────────────────────────────────
def fetch_rss(url: str, count: int = 3):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        results = []
        for item in re.findall(r"<item>(.*?)</item>", content, re.DOTALL)[:count]:
            t = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item) or \
                re.search(r"<title>(.*?)</title>", item)
            l = re.search(r"<link>(.*?)</link>", item) or \
                re.search(r"<guid[^>]*>(https?://[^<]+)</guid>", item)
            title = t.group(1).strip() if t else ""
            link  = l.group(1).strip() if l else ""
            if title:
                results.append((title, link))
        return results
    except Exception:
        return []

def get_tamilnadu_news(count=3):
    for feed in [
        "https://www.thehindu.com/news/national/tamil-nadu/feeder/default.rss",
        "https://timesofindia.indiatimes.com/rssfeeds/-2128938702.cms",
    ]:
        items = fetch_rss(feed, count)
        if items:
            return items
    return [("Could not fetch Tamil Nadu news.", "")]

def get_global_news(count=3):
    for feed in [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    ]:
        items = fetch_rss(feed, count)
        if items:
            return items
    return [("Could not fetch global news.", "")]

def get_topic_news(topic: str, count=3):
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(topic)}&hl=en&gl=US&ceid=US:en"
    items = fetch_rss(url, count)
    return items if items else [(f"No news found for {topic}.", "")]

def read_news(items):
    for i, (title, link) in enumerate(items, 1):
        speak_wait(f"Headline {i}: {title}")
        if link:
            webbrowser.open(link)
        time.sleep(0.3)

# ── Spotify — desktop app only ────────────────────────────────────────────────
def open_spotify(query: str = ""):
    query = query.strip()
    if query:
        encoded = urllib.parse.quote(query)
        uri = f"spotify:search:{encoded}"
        speak(f"Playing {query} on Spotify.")
    else:
        uri = "spotify:"
        speak("Opening Spotify.")

    subprocess.Popen(
        ["powershell", "-Command", f'Start-Process "{uri}"'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    if query:
        time.sleep(2.5)
        subprocess.Popen(
            ["powershell", "-Command",
             "$w=New-Object -ComObject WScript.Shell; "
             "$w.AppActivate('Spotify'); "
             "Start-Sleep -Milliseconds 600; "
             "$w.SendKeys('{ENTER}')"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

# ── Volume ────────────────────────────────────────────────────────────────────
def set_volume(query: str, direction: str = ""):
    m = re.search(r"(\d+)", query)
    if m:
        level = max(0, min(100, int(m.group(1))))
        os.system(f"nircmd.exe setsysvolume {int(65535 * level / 100)}")
        speak(f"Volume at {level} percent.")
    elif direction == "up":
        os.system("nircmd.exe changesysvolume 6554")
        speak("Volume up.")
    elif direction == "down":
        os.system("nircmd.exe changesysvolume -6554")
        speak("Volume down.")

# ── Brightness ────────────────────────────────────────────────────────────────
def set_brightness(query: str, direction: str = ""):
    m = re.search(r"(\d+)", query)
    level = int(m.group(1)) if m else (30 if direction == "down" else 100)
    level = max(0, min(100, level))
    subprocess.run(
        ["powershell", "-Command",
         f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
         f".WmiSetBrightness(1,{level})"],
        capture_output=True
    )
    speak(f"Brightness at {level} percent.")

# ── Screenshot ────────────────────────────────────────────────────────────────
def take_screenshot():
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(os.path.expanduser("~"), "Pictures", f"cactus_{ts}.png")
    subprocess.run([
        "powershell", "-Command",
        f"Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
        f"$b=New-Object System.Drawing.Bitmap("
        f"[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width,"
        f"[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); "
        f"$g=[System.Drawing.Graphics]::FromImage($b); "
        f"$g.CopyFromScreen(0,0,0,0,$b.Size); $b.Save('{path}')"
    ], capture_output=True)
    speak("Screenshot saved to Pictures.")

# ── Media keys ────────────────────────────────────────────────────────────────
def send_media_key(key: str):
    subprocess.run(
        ["powershell", "-Command",
         f"$w=New-Object -ComObject WScript.Shell; $w.SendKeys('{key}')"],
        capture_output=True
    )

# ── System ────────────────────────────────────────────────────────────────────
def handle_system(action: str):
    actions = {
        "lock":     ("Locking up.",                          "rundll32.exe user32.dll,LockWorkStation"),
        "sleep_pc": (f"Goodnight, {MASTER_NAME}.",           "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"),
        "shutdown": ("Shutting down. See you on the other side.", "shutdown /s /t 5"),
        "restart":  ("Restarting. Back in a moment.",        "shutdown /r /t 5"),
    }
    msg, cmd = actions.get(action, ("Unknown system command.", ""))
    speak_wait(msg)
    if cmd:
        os.system(cmd)

# ── Quiet / Resume ────────────────────────────────────────────────────────────
def enter_quiet_mode():
    global quiet_mode
    _tts_queue.put("Going silent. I'll be here.")
    _tts_queue.join()
    quiet_mode = True
    print("[CACTUS] Quiet mode ON.")

def exit_quiet_mode():
    global quiet_mode
    quiet_mode = False
    speak(f"Back online, {MASTER_NAME}.")

# ── Boot Greeting ─────────────────────────────────────────────────────────────
def boot_greeting():
    _tts_ready.wait(timeout=10)
    time.sleep(0.5)

    hour = datetime.datetime.now().hour
    tod  = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")

    speak_wait(f"{tod}, {MASTER_NAME}. All systems online. CACTUS is ready.")
    time.sleep(0.2)

    speak_wait("Pulling your weather.")
    speak_wait(get_weather())
    time.sleep(0.2)

    speak_wait("Tamil Nadu briefing.")
    read_news(get_tamilnadu_news(3))

    speak_wait("Global headlines.")
    read_news(get_global_news(3))

    speak_wait(f"Briefing complete. I'm listening, {MASTER_NAME}.")

# ── Command Router ────────────────────────────────────────────────────────────
def route_command(cmd: str):
    if not cmd.strip():
        return

    c = cmd.lower().strip()

    # ── Quiet / Resume — always first ────────────────────────────────────────
    if any(x in c for x in ["be quiet", "shut up", "go quiet", "stop talking", "silence"]):
        enter_quiet_mode(); return
    if any(x in c for x in ["talk to me", "come back", "wake up", "stop being quiet"]):
        exit_quiet_mode(); return
    if quiet_mode:
        return

    # ── LOCAL FAST-PATH — core commands work even if Groq is down ────────────

    # Spotify
    if "spotify" in c or re.search(r"\bplay\b", c):
        query = re.sub(
            r"\b(play|open|launch|spotify|on|please|up|some|me|and|put|start|cactus)\b",
            "", c
        ).strip(" ,.")
        open_spotify(query); return

    # Weather
    if "weather" in c or "temperature" in c or "temp" in c or "how hot" in c or "how cold" in c:
        m = re.search(r"(?:in|for|at)\s+([a-zA-Z\s]+)", c)
        city = m.group(1).strip() if m else None
        speak(get_weather(city)); return

    # News
    if any(x in c for x in ["news", "headlines", "what's happening"]):
        if "tamil" in c:
            speak("Tamil Nadu headlines.")
            read_news(get_tamilnadu_news(4)); return
        topic = re.sub(r"\b(news|headlines|about|on|latest|whats happening)\b", "", c).strip()
        if topic and len(topic) > 2:
            speak(f"News on {topic}.")
            read_news(get_topic_news(topic, 4)); return
        speak("Global headlines.")
        read_news(get_global_news(4)); return

    # Volume
    if any(x in c for x in ["volume", "louder", "quieter", "turn up", "turn down"]):
        if any(x in c for x in ["up", "louder", "turn up", "raise", "increase"]):
            set_volume("", "up"); return
        if any(x in c for x in ["down", "quieter", "turn down", "lower", "decrease"]):
            set_volume("", "down"); return
        set_volume(c); return

    # Mute
    if "unmute" in c:
        os.system("nircmd.exe mutesysvolume 0"); speak("Unmuted."); return
    if "mute" in c:
        os.system("nircmd.exe mutesysvolume 1"); speak("Muted."); return

    # Brightness
    if any(x in c for x in ["brightness", "dim", "brighten", "screen brighter", "screen darker"]):
        if any(x in c for x in ["up", "brighten", "increase", "brighter"]):
            set_brightness("", "up"); return
        if any(x in c for x in ["down", "dim", "decrease", "darker"]):
            set_brightness("", "down"); return
        set_brightness(c); return

    # Media
    if any(x in c for x in ["next track", "next song", "skip"]):
        send_media_key("{NEXTTRACK}"); speak("Next track."); return
    if any(x in c for x in ["previous", "prev track", "go back"]):
        send_media_key("{PREVTRACK}"); speak("Previous track."); return
    if any(x in c for x in ["pause", "stop music", "pause music"]):
        send_media_key("{MEDIA_PLAY_PAUSE}"); speak("Paused."); return
    if any(x in c for x in ["resume music", "resume", "unpause"]):
        send_media_key("{MEDIA_PLAY_PAUSE}"); speak("Resuming."); return

    # Screenshot
    if "screenshot" in c or "screen capture" in c:
        take_screenshot(); return

    # Time / Date
    if any(x in c for x in ["time", "what day", "what's the date", "date"]):
        speak(datetime.datetime.now().strftime("It's %I:%M %p on %A, %B %d.")); return

    # Search
    if any(x in c for x in ["search", "google", "look up", "find", "look for"]):
        query = re.sub(r"\b(search|google|look up|find|look for|cactus)\b", "", c).strip()
        webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
        speak(f"Searching for {query}."); return

    # Stocks
    if any(x in c for x in ["stock", "share price", "shares"]):
        ticker = re.sub(r"\b(stock|price|shares?|of|for|check|what is|whats)\b", "", c).strip().upper()
        webbrowser.open(f"https://finance.yahoo.com/quote/{ticker}")
        speak(f"Pulling up {ticker}."); return

    # WhatsApp
    if "whatsapp" in c:
        m = re.search(r"(\d+)\s+(.*)", c)
        if m:
            webbrowser.open(f"https://wa.me/{m.group(1)}?text={urllib.parse.quote(m.group(2))}")
            speak("WhatsApp message ready.")
        else:
            webbrowser.open("https://web.whatsapp.com")
            speak("Opening WhatsApp.")
        return

    # Email
    if any(x in c for x in ["email", "gmail", "compose"]):
        webbrowser.open("https://mail.google.com/mail/?view=cm&fs=1")
        speak("Opening Gmail compose."); return

    # System
    if "lock" in c:
        handle_system("lock"); return
    if "sleep" in c and "pc" in c:
        handle_system("sleep_pc"); return
    if "shutdown" in c or "shut down" in c:
        handle_system("shutdown"); return
    if "restart" in c or "reboot" in c:
        handle_system("restart"); return

    # Help
    if "help" in c or "what can you do" in c:
        speak(
            f"You can ask me anything, {MASTER_NAME}. "
            "Spotify, volume, brightness, WhatsApp, Gmail, "
            "news, weather, stocks, Google, screenshots, system controls, "
            "or just talk to me."
        ); return

    # ── Groq fallback — ambiguous or chat commands ────────────────────────────
    print(f"[ROUTING → GROQ] {cmd}")
    parsed  = parse_intent(cmd)
    intent  = parsed.get("intent", "chat")
    query   = parsed.get("query", cmd)
    print(f"[INTENT] {intent} | query: {query}")

    if intent == "spotify":
        open_spotify(query)
    elif intent == "weather":
        speak(get_weather(query if query else None))
    elif intent == "news_tamil":
        speak("Tamil Nadu headlines."); read_news(get_tamilnadu_news(4))
    elif intent == "news_global":
        speak("Global headlines."); read_news(get_global_news(4))
    elif intent == "news_topic":
        speak(f"News on {query}."); read_news(get_topic_news(query, 4))
    elif intent == "search":
        webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
        speak(f"Searching for {query}.")
    elif intent == "stock":
        webbrowser.open(f"https://finance.yahoo.com/quote/{query.upper()}")
        speak(f"Pulling up {query.upper()}.")
    elif intent == "screenshot":
        take_screenshot()
    elif intent == "time":
        speak(datetime.datetime.now().strftime("It's %I:%M %p on %A, %B %d."))
    elif intent == "volume_up":
        set_volume("", "up")
    elif intent == "volume_down":
        set_volume("", "down")
    elif intent == "volume_set":
        set_volume(query)
    elif intent == "mute":
        os.system("nircmd.exe mutesysvolume 1"); speak("Muted.")
    elif intent == "unmute":
        os.system("nircmd.exe mutesysvolume 0"); speak("Unmuted.")
    elif intent == "brightness_up":
        set_brightness("", "up")
    elif intent == "brightness_down":
        set_brightness("", "down")
    elif intent == "brightness_set":
        set_brightness(query)
    elif intent == "media_next":
        send_media_key("{NEXTTRACK}"); speak("Next track.")
    elif intent == "media_prev":
        send_media_key("{PREVTRACK}"); speak("Previous track.")
    elif intent == "media_pause":
        send_media_key("{MEDIA_PLAY_PAUSE}"); speak("Paused.")
    elif intent == "media_resume":
        send_media_key("{MEDIA_PLAY_PAUSE}"); speak("Resuming.")
    elif intent == "whatsapp":
        webbrowser.open("https://web.whatsapp.com"); speak("Opening WhatsApp.")
    elif intent == "email":
        webbrowser.open("https://mail.google.com/mail/?view=cm&fs=1"); speak("Opening Gmail.")
    elif intent in ("lock", "sleep_pc", "shutdown", "restart"):
        handle_system(intent)
    elif intent == "quiet_mode":
        enter_quiet_mode()
    elif intent == "resume_mode":
        exit_quiet_mode()
    else:
        speak(ask_groq_chat(cmd))

# ── Voice Loop ────────────────────────────────────────────────────────────────
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
            print("[VOICE] Calibrating...")
            recognizer.adjust_for_ambient_noise(source, duration=1.5)

        voice_active = True
        print("[CACTUS] Always listening.")

        while True:
            if quiet_mode:
                time.sleep(0.3)
                continue
            try:
                with mic as source:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
                text = recognizer.recognize_google(audio).lower().strip()
                if text:
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
        print("[VOICE] SpeechRecognition unavailable. Text mode only.")
        voice_active = False

# ── Terminal boot art ─────────────────────────────────────────────────────────
def terminal_boot():
    os.system("cls" if os.name == "nt" else "clear")
    for line in [
        "  ██████╗ █████╗  ██████╗████████╗██╗   ██╗███████╗",
        "  ██╔════╝██╔══██╗██╔════╝╚══██╔══╝██║   ██║██╔════╝",
        "  ██║     ███████║██║        ██║   ██║   ██║███████╗",
        "  ██║     ██╔══██║██║        ██║   ██║   ██║╚════██║",
        "  ╚██████╗██║  ██║╚██████╗   ██║   ╚██████╔╝███████║",
        "   ╚═════╝╚═╝  ╚═╝ ╚═════╝   ╚═╝    ╚═════╝ ╚══════╝",
        "", "        Personal AI Assistant v5.0",
        "  ─────────────────────────────────────────",
    ]:
        print(f"\033[32m{line}\033[0m")
        time.sleep(0.06)
    print()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    terminal_boot()
    _tts_ready.wait(timeout=8)

    voice_thread = threading.Thread(target=voice_loop, daemon=True)
    voice_thread.start()

    boot_greeting()
    time.sleep(2)

    if not voice_active:
        print("\n[CACTUS] Text mode active.\n")
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
        print("\n[CACTUS] Always listening. Just talk.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            speak_wait(f"Goodbye, {MASTER_NAME}. Stay sharp.")
            sys.exit(0)

if __name__ == "__main__":
    main()