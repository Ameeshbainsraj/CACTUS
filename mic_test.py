"""
CACTUS Mic Diagnostic
Run this to see exactly what's wrong with your microphone.
"""
import sys

print("\n[1] Checking PyAudio...")
try:
    import pyaudio
    p = pyaudio.PyAudio()
    count = p.get_device_count()
    print(f"    PyAudio OK — {count} audio devices found\n")
    for i in range(count):
        info = p.get_device_info_by_index(i)
        if info.get('maxInputChannels', 0) > 0:
            print(f"    MIC [{i}] {info['name']} — inputs: {info['maxInputChannels']}")
    p.terminate()
except Exception as e:
    print(f"    FAIL: {e}")

print("\n[2] Checking SpeechRecognition...")
try:
    import speech_recognition as sr
    print(f"    SpeechRecognition version: {sr.__version__}")
    mics = sr.Microphone.list_microphone_names()
    print(f"    Microphones found: {len(mics)}")
    for i, m in enumerate(mics):
        print(f"      [{i}] {m}")
except Exception as e:
    print(f"    FAIL: {e}")

print("\n[3] Trying to listen for 3 seconds...")
try:
    import speech_recognition as sr
    r   = sr.Recognizer()
    mic = sr.Microphone()
    with mic as source:
        r.adjust_for_ambient_noise(source, duration=1)
        print("    Listening... say something!")
        audio = r.listen(source, timeout=3, phrase_time_limit=3)
    text = r.recognize_google(audio)
    print(f"    HEARD: '{text}'")
    print("    MIC IS WORKING PERFECTLY.")
except sr.WaitTimeoutError:
    print("    Timeout — no speech detected (mic may be working but silent)")
except sr.UnknownValueError:
    print("    Could not understand audio (mic IS working, just unclear)")
except Exception as e:
    print(f"    FAIL: {e}")
    print("\n    LIKELY FIX: Go to Windows Settings > Privacy > Microphone")
    print("    and make sure 'Allow apps to access your microphone' is ON.")

print("\n[4] Checking pyttsx3 (text to speech)...")
try:
    import pyttsx3
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    print(f"    pyttsx3 OK — {len(voices)} voices available")
    for v in voices:
        print(f"      {v.name} — {v.id}")
    engine.say("CACTUS voice test successful.")
    engine.runAndWait()
    print("    If you heard that, TTS is working.")
except Exception as e:
    print(f"    FAIL: {e}")

print("\nDone. Paste this output so we can fix any issues.")
