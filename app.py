#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎬 Movie Recap Studio — Streamlit Edition
==========================================
ONC_1 (React) code style ကို GitHub + Streamlit Cloud မှာ run လို့ရအောင်
Python/Streamlit နဲ့ ပြန်ဆောက်ထားတာ — Spidy Dub App (audio-dub-studio) လို
sidebar မှာ Gemini + Groq API key ထည့်၊ browser localStorage မှာ မှတ်ထားတယ်။

Pipeline:
  1. Video တင် → ffmpeg နဲ့ audio ထုတ် (mp3 16k mono 32k)
  2. Groq Whisper (whisper-large-v3) → စကားပြော segments + timestamps
  3. Gemini → Mode အလိုက် Script ထုတ်
       🎬 Recap      : frames (vision) + transcript → scenes script
       💬 Subtitle   : dialogues ကို မြန်မာ ဘာသာပြန် (အချိန်ကိုက်)
       🎙️ Dubbing    : dialogues ဘာသာပြန် → အသံထပ်သွင်း
       🎬+🎙️ Recap+Dub: Narrator + dialogue ပေါင်းစပ် script
     + 📱 Social Kit (🔥 3s Hook + Caption + Hashtags)
  4. TTS — 🌐 Edge TTS (edge-tts 7.3.1, Thiha/Nilar + Multilingual)
           🤖 Gemini TTS (ONC voice 20 မျိုး, Voice Style + Emotion)
  5. ffmpeg Render (တကယ့် MP4) — 🪞 Mirror, 🎨 Color Tone, 🌫️ Blur box,
     💬 Subtitle burn-in (Padauk), 🖼️ Logo, 🎵 BGM mix, ⚡ Hyper-Sync,
     📐 16:9 / 9:16 / 1:1

Create by Bo Bo Myint Mo
"""
import asyncio
import base64
import hashlib
import json
import os
import re
import subprocess
import time
import wave
from pathlib import Path

import requests
import streamlit as st

# ------------------------------------------------------------------ constants
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"
GEMINI_TEXT_MODEL_DEFAULT = "gemini-3.8-flash"        # 2.5-flash retired (404, 2026-10-21 live error)
GEMINI_TTS_MODEL = "gemini-3.8-flash-tts"              # 2.5-flash-preview-tts လည်း retired မို့ ကြိုပြောင်း
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3"  # turbo က hallucination များလို့ full model

WORK = Path("work")
TTS_CACHE = WORK / "tts_cache"

# ONC_1 VOICES (Gemini TTS) — id, မြန်မာအမည်, gender
GEMINI_VOICES = [
    ("Charon", "အောင်အောင်", "Male"), ("Fenrir", "ရဲရင့်", "Male"),
    ("Orus", "မင်းခန့်", "Male"), ("Enceladus", "ဇေယျာ", "Male"),
    ("Iapetus", "ထက်မြတ်", "Male"), ("Algenib", "မျိုးမင်း", "Male"),
    ("Rasalgethi", "စည်သူ", "Male"), ("Schedar", "ကောင်းကင်", "Male"),
    ("Alnilam", "သီဟ", "Male"), ("Sadachbia", "ဝေယံ", "Male"),
    ("Kore", "စုစု", "Female"), ("Aoede", "သန္တာ", "Female"),
    ("Leda", "လှိုင်", "Female"), ("Callirrhoe", "အေးအေး", "Female"),
    ("Autonoe", "မြမြ", "Female"), ("Despina", "နန်းဆု", "Female"),
    ("Erinome", "ရွှေရည်", "Female"), ("Laomedeia", "သီရိ", "Female"),
    ("Achernar", "မေမီ", "Female"), ("Gacrux", "နှင်းနှင်း", "Female"),
]
_GEMINI_VOICE_LABELS = {v: f"{n} ({g}) — {v}" for v, n, g in GEMINI_VOICES}

# Edge TTS voices (Spidy Dub App လို) — 7.3.1, Sec-MS-GEC v2 token ပါလို့ 403 မရှိ
EDGE_VOICES = [
    ("my-MM-ThihaNeural", "🗣️ ကျား (Thiha) — မြန်မာ"),
    ("my-MM-NilarNeural", "🗣️ မ (Nilar) — မြန်မာ"),
    ("en-US-AvaMultilingualNeural", "🌍 Ava (Multilingual)"),
    ("en-US-AndrewMultilingualNeural", "🌍 Andrew (Multilingual)"),
    ("en-US-EmmaMultilingualNeural", "🌍 Emma (Multilingual)"),
    ("en-US-BrianMultilingualNeural", "🌍 Brian (Multilingual)"),
    ("en-AU-WilliamMultilingualNeural", "🌍 William (Multilingual)"),
    ("de-DE-FlorianMultilingualNeural", "🌍 Florian (Multilingual)"),
    ("de-DE-SeraphinaMultilingualNeural", "🌍 Seraphina (Multilingual)"),
    ("fr-FR-RemyMultilingualNeural", "🌍 Remy (Multilingual)"),
    ("fr-FR-VivienneMultilingualNeural", "🌍 Vivienne (Multilingual)"),
    ("it-IT-GiuseppeMultilingualNeural", "🌍 Giuseppe (Multilingual)"),
    ("ko-KR-HyunsuMultilingualNeural", "🌍 Hyunsu (Multilingual)"),
    ("pt-BR-ThalitaMultilingualNeural", "🌍 Thalita (Multilingual)"),
]
_EDGE_VOICE_LABELS = dict(EDGE_VOICES)

SCRIPT_STYLES = [
    ("recap", "🎥 Movie Recap",
     "Summarize the entire storyline sequentially into an engaging, complete story from start to finish. MAKE SURE to write an in-depth and detailed script."),
    ("documentary", "🎞️ Cinematic Documentary",
     "Professional documentary style with dramatic tone, deep insights, and cinematic pacing. Write an in-depth script."),
    ("storytelling", "📖 Storytelling",
     "Natural, casual, and relatable storytelling tone, as if narrating a compelling story to a close friend. Write an in-depth script."),
    ("viral_short", "🔥 Viral Short",
     "Fast-paced short-form style. Start with an ultra-strong 3-second hook to maximize retention and keep the energy high."),
    ("none", "None (Default)", "Standard cinematic movie recap narration."),
]
_SCRIPT_STYLE_PROMPTS = {k: p for k, _l, p in SCRIPT_STYLES}

VOICE_STYLES = ["None (Default)", "Energetic Movie Recap", "News Anchor",
                "Storyteller", "Calm & Professional", "Horror & Suspense",
                "Romantic & Soft", "Comedy & Playful", "Action & Thriller",
                "Documentary Nature", "Emotional & Sad"]

SPEED_PRESETS = [("slow", "🐌 အနှေး Slow", 0.85),
                 ("normal", "▶️ ပုံမှန် Normal", 1.0),
                 ("fast", "⚡ အမြန် Fast", 1.25)]

EMOTIONS = [("Neutral", "😐 ပုံမှန် Neutral"),
            ("MovieRecap", "🎬 ရုပ်ရှင်အကျဉ်း Movie Recap"),
            ("Happy", "😊 ပျော်ရွှင်သော Happy"), ("Sad", "😢 ဝမ်းနည်းသော Sad"),
            ("Angry", "😠 ဒေါသထွက်သော Angry"), ("Calm", "😌 တည်ငြိမ်သော Calm"),
            ("Energetic", "⚡ တက်ကြွသော Energetic"),
            ("Whisper", "🤫 တိုးတိုးပြော Whisper"),
            ("Storytelling", "📖 ပုံပြင်ပြော Storytelling"),
            ("Professional", "👔 လုပ်ငန်းသုံး Professional"),
            ("Casual", "☕ ပေါ့ပေါ့ပါးပါး Casual")]
_EMOTION_LABELS = dict(EMOTIONS)

# ONC COLOR_TONES → ffmpeg eq filter
COLOR_TONES = {
    "Normal (Original)": "",
    "Cinematic": "eq=brightness=-0.06:contrast=1.2:saturation=1.1",
    "Vibrant": "eq=brightness=0.03:contrast=1.1:saturation=1.3",
    "Vintage": "eq=brightness=-0.04:contrast=1.1:saturation=0.7,colorbalance=rs=0.15:gs=0.05:bs=-0.10",
    "B&W": "hue=s=0,eq=contrast=1.2",
}

ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
LOGO_POSITIONS = ["top-left", "top-right", "bottom-left", "bottom-right"]

SRC_LANGS = [
    ("🤖 Auto (အလိုအလျောက်)", None), ("🇬🇧 English", "en"),
    ("🇰🇷 Korean", "ko"), ("🇯🇵 Japanese", "ja"), ("🇨🇳 Chinese", "zh"),
    ("🇹🇭 Thai", "th"), ("🇻🇳 Vietnamese", "vi"), ("🇮🇩 Indonesian", "id"),
    ("🇪🇸 Spanish", "es"), ("🇫🇷 French", "fr"), ("🇩🇪 German", "de"),
    ("🇷🇺 Russian", "ru"), ("🇮🇳 Hindi", "hi"),
]

MODES = ["recap", "subtitle", "dubbing", "recap_dub"]
MODE_LABELS = {"recap": "🎬 Recap", "subtitle": "💬 Subtitle",
               "dubbing": "🎙️ Dubbing", "recap_dub": "🎬+🎙️ Recap + Dub"}

# ------------------------------------------------------------------ page + CSS
st.set_page_config(page_title="Movie Recap Studio", page_icon="🎬",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
  .stApp { background:#050b14; }
  section[data-testid="stSidebar"] { background:#0a1220; border-right:1px solid rgba(30,58,138,.5); }
  h1,h2,h3 { color:#22d3ee !important; letter-spacing:.02em; }
  .stButton>button { background:linear-gradient(90deg,#2563eb,#06b6d4); color:#fff;
    font-weight:700; border:1px solid rgba(6,182,212,.35); border-radius:12px; }
  .stButton>button:hover { filter:brightness(1.15); }
  .stTextArea textarea, .stTextInput input { background:#000 !important; color:#f8fafc !important;
    border:1px solid rgba(30,58,138,.5) !important; border-radius:12px !important; }
  .hero { text-align:center; padding:10px 0 2px 0; }
  .hero .t { font-size:30px; font-weight:900; color:#22d3ee; letter-spacing:.08em; }
  .hero .s { color:rgba(191,219,254,.6); font-size:13px; margin-top:2px; }
  .credit { text-align:center; color:rgba(191,219,254,.45); font-size:12px; padding:14px 0 4px 0; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------ helpers
def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def video_dims(path):
    """ffprobe → (width, height) — rotation metadata ပါရင် ပြောင်းပြန်လှန်."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height",
                        "-show_entries", "stream_tags=rotate",
                        "-of", "default=noprint_wrappers=1", str(path)],
                       capture_output=True, text=True)
    w = h = 0
    rotate = 0
    for line in r.stdout.splitlines():
        if line.startswith("width="):
            w = int(line.split("=")[1] or 0)
        elif line.startswith("height="):
            h = int(line.split("=")[1] or 0)
        elif "rotate=" in line:
            try:
                rotate = abs(int(line.split("rotate=")[1]))
            except Exception:
                pass
    if not w or not h:
        return 1920, 1080
    if rotate in (90, 270):
        w, h = h, w
    return w, h


def auto_canvas(path):
    """video အချိုးအလိုက် canvas — 9:16 တင်ရင် 9:16 ပဲ ထွက်အောင် (settings မလို)."""
    w, h = video_dims(path)
    if h > w:
        return (1080, 1920)
    if w > h:
        return (1920, 1080)
    return (1080, 1080)


def has_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=index", "-of", "csv=p=0",
                        str(path)], capture_output=True, text=True)
    return bool(r.stdout.strip())


def fmt_ts(sec):
    """SRT timestamp (ONC formatSrtTime)."""
    total_ms = max(0, int(round(sec * 1000)))
    h, rem = divmod(total_ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_clock(sec):
    sec = max(0, int(sec or 0))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def fix_pronunciation(text):
    """ONC fixPronunciation."""
    if not text:
        return text
    for wrong, right in {"ဘီး": "ဘိမ်း", "အံ့သြ": "အံ့အော"}.items():
        text = text.replace(wrong, right)
    return text


def generate_subtitle_chunks(text, total_duration, start_time=0.0, max_len=24):
    """ONC generateSubtitleChunks port — sentence split, max_len wrap,
    comma/space aware wrap (Unicode မဖြတ်), 2-line pairing, proportional timing."""
    if not text or total_duration <= 0:
        return []
    raw = [s for s in re.sub(r"([။!?])", r"\1\n", text).split("\n") if s.strip()]
    chunks = []
    MAX_LEN = max_len
    for seg in raw:
        s = seg.strip()
        while len(s) > MAX_LEN:
            window = s[:MAX_LEN]
            comma = window.rfind("၊")
            space = window.rfind(" ")
            if comma > 8:
                cut = comma + 1
            elif space > 8:
                cut = space
            else:
                nxt = s.find(" ", 12)
                cut = nxt if (nxt != -1 and nxt < len(s) - 5) else len(s)
            if cut < len(s):
                chunks.append(s[:cut].strip())
                s = s[cut:].strip()
            else:
                break
        if s:
            chunks.append(s)
    if not chunks:
        chunks = [text]
    paired = []
    for i in range(0, len(chunks), 2):
        paired.append(chunks[i] + ("\n" + chunks[i + 1] if i + 1 < len(chunks) else ""))
    weights = []
    for c in paired:
        w = len(c.replace("\n", "")) + 15
        if "။" in c:
            w += 10
        if "၊" in c:
            w += 5
        if "?" in c:
            w += 5
        weights.append(w)
    total_w = sum(weights) or 1
    out, t = [], float(start_time)
    for c, w in zip(paired, weights):
        d = (w / total_w) * total_duration
        out.append({"text": c, "start": t, "end": t + d})
        t += d
    return out


def build_srt(items):
    """items: [{start,end,text}] → SRT string."""
    lines = []
    for i, it in enumerate(items, 1):
        txt = str(it.get("text", "")).strip()
        if not txt:
            continue
        lines.append(f"{i}\n{fmt_ts(it['start'])} --> {fmt_ts(it['end'])}\n{txt}\n")
    return "\n".join(lines)


def atempo_chain(rate):
    """atempo က 0.5–2.0 ပဲ ရလို့ chain ခွဲထုတ်."""
    parts = []
    r = float(rate)
    while r > 2.0:
        parts.append("atempo=2.0")
        r /= 2.0
    while r < 0.5:
        parts.append("atempo=0.5")
        r /= 0.5
    parts.append(f"atempo={r:.4f}")
    return ",".join(parts)


def run_progress(cmd, total_dur, progress_cb=None, base=0.0, span=1.0):
    """ffmpeg ကို -progress နဲ့ run → out_time ကနေ % တွက် (Render loading ပြဖို့)."""
    if not progress_cb or not total_dur or total_dur <= 0:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("ffmpeg: " + (r.stderr or "")[-600:])
        return
    full = [cmd[0]] + ["-progress", "pipe:1", "-nostats"] + list(cmd[1:])
    p = subprocess.Popen(full, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    last = -1.0
    for line in p.stdout:
        if line.startswith("out_time_ms="):
            try:
                t = int(line.strip().split("=", 1)[1]) / 1e6
            except Exception:
                continue
            val = base + span * max(0.0, min(1.0, t / total_dur))
            if val - last >= 0.01:
                last = val
                progress_cb(val)
    err = p.stderr.read() if p.stderr else ""
    p.wait()
    if p.returncode != 0:
        raise RuntimeError("ffmpeg: " + (err or "")[-600:])
    progress_cb(base + span)


def silence(path, seconds, sr=24000):
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         f"anullsrc=r={sr}:cl=mono", "-t", f"{max(0.05, seconds):.3f}",
         "-ar", str(sr), str(path)])


# ------------------------------------------------------- browser localStorage
_LS_GEMINI = "mrs_gemini_key"
_LS_GROQ = "mrs_groq_key"


def _local_storage():
    try:
        from streamlit_local_storage import LocalStorage
        return LocalStorage(key="mrs_ls")
    except Exception:
        return None


def _ls_get(ls, k):
    try:
        return (ls.getItem(k) or "").strip() if ls else ""
    except Exception:
        return ""


def _ls_set(ls, k, v, ckey):
    try:
        if ls and v:
            ls.setItem(k, v, key=ckey)
    except Exception:
        pass


def _ls_del(ls, k, ckey):
    try:
        if ls:
            ls.eraseItem(k, key=ckey)
            try:
                ls.storedItems.pop(k, None)
            except Exception:
                pass
    except Exception:
        pass


# ------------------------------------------------------------------ Gemini
def _gemini_post(api_key, model, payload, timeout=300):
    url = f"{GEMINI_BASE}{model}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    delays = [2, 4, 8]
    last = None
    for i in range(3):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as e:
            last = RuntimeError(f"Gemini request failed: {e}")
            time.sleep(delays[i])
            continue
        if r.status_code in (429, 500, 502, 503) and i < 2:
            last = RuntimeError(f"Gemini error {r.status_code}: {r.text[:300]}")
            time.sleep(delays[i])
            continue
        if not r.ok:
            raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:300]}")
        return r.json()
    raise last or RuntimeError("Gemini request failed")


def _gemini_text(api_key, model, parts, json_mode=True, timeout=300):
    payload = {"contents": [{"parts": parts}]}
    if json_mode:
        payload["generationConfig"] = {"responseMimeType": "application/json"}
    data = _gemini_post(api_key, model, payload, timeout=timeout)
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise RuntimeError("Gemini က မျှော်လင့်မထားတဲ့ response ပြန်တယ်")


def parse_gemini_json(text):
    """ONC parseGeminiJSON port."""
    clean = re.sub(r"```json|```", "", text, flags=re.I).strip()
    s, e = clean.find("{"), clean.rfind("}")
    if s != -1 and e != -1:
        clean = clean[s:e + 1]
    try:
        return json.loads(clean)
    except Exception as ex:
        raise RuntimeError(f"AI မှ မှားယွင်းသော format ပြန်ပို့ပါသည်။ (JSON Parse Error) {ex}")


# ------------------------------------------------------------------ Groq
def _groq_single(audio_path, api_key, language=None):
    form = {"model": GROQ_MODEL, "response_format": "verbose_json"}
    if language:
        form["language"] = language
    headers = {"Authorization": f"Bearer {api_key}"}
    with open(audio_path, "rb") as f:
        files = {"file": (Path(audio_path).name, f, "audio/mpeg")}
        try:
            r = requests.post(GROQ_URL, headers=headers, files=files,
                              data=form, timeout=600)
        except requests.Timeout:
            raise RuntimeError("Groq transcription timed out — network စစ်ပြီး ပြန်ကြိုးစားပါ")
    if not r.ok:
        try:
            msg = r.json().get("error", {}).get("message") or f"Groq Error ({r.status_code})"
        except Exception:
            msg = f"Groq Error ({r.status_code})"
        raise RuntimeError(f"စာသားထုတ်တာ ပျက်သွားတယ် (Groq HTTP {r.status_code}): {msg}")
    data = r.json()
    segs = [{"start": float(s["start"]), "end": float(s["end"]),
             "text": s["text"].strip()}
            for s in data.get("segments", []) if s.get("text", "").strip()]
    return {"language": data.get("language"), "segments": segs}


def transcribe_audio(audio_path, api_key, language=None, work_dir=None,
                     progress_cb=None):
    """Groq Whisper — ဖိုင်ကြီးရင် အချိန်အပိုင်းခွဲပြီး ဆက် (Spidy Dub ပုံစံ)."""
    size_mb = os.path.getsize(audio_path) / 1e6
    total = dur(audio_path)
    if size_mb <= 20 or total <= 0:
        return _groq_single(audio_path, api_key, language)
    CHUNK = 1200.0  # 32kbps mp3 → ~4.8MB/ခု (Groq 25MB အောက် safe)
    out, t = [], 0.0
    idx = 0
    while t < total:
        idx += 1
        chunk = Path(work_dir) / f"groq_chunk_{idx}.mp3"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t}", "-t", f"{CHUNK}",
             "-i", str(audio_path), "-ac", "1", "-ar", "16000",
             "-b:a", "32k", str(chunk)])
        data = _groq_single(chunk, api_key, language)
        for s in data["segments"]:
            out.append({"start": s["start"] + t, "end": s["end"] + t,
                        "text": s["text"]})
        t += CHUNK
        if progress_cb:
            progress_cb(min(1.0, t / total))
    return {"language": None, "segments": out}


# ------------------------------------------------------------- frames (vision)
def extract_frames(video_path, start, end, work_dir, max_frames=12):
    """ONC extractFramesForVision port — ffmpeg နဲ့ frame ထုတ် → inlineData parts."""
    span = max(0.1, end - start)
    parts = []
    for i in range(max_frames):
        t = start + span * (i + 0.5) / max_frames
        fp = Path(work_dir) / f"frame_{int(start)}_{i}.jpg"
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}",
                            "-i", str(video_path), "-frames:v", "1",
                            "-vf", "scale=320:-2", "-q:v", "5", str(fp)],
                           capture_output=True, text=True)
        if r.returncode == 0 and fp.exists() and fp.stat().st_size > 500:
            parts.append({"inlineData": {
                "mimeType": "image/jpeg",
                "data": base64.b64encode(fp.read_bytes()).decode()}})
    return parts


def _transcript_slice(segments, start, end):
    lines = []
    for s in segments:
        if s["end"] >= start and s["start"] <= end:
            lines.append(f"[{s['start']:.1f}s-{s['end']:.1f}s] {s['text']}")
    return "\n".join(lines) or "(ဒီအပိုင်းမှာ စကားပြောသံ မရှိပါ)"


# ------------------------------------------------------------- script (step 3)
def gen_recap_scenes(api_key, model, video_path, segments, total_dur,
                     style_prompt, work_dir, progress_cb=None):
    """🎬 Recap — ONC recap prompt (audio အစား Groq transcript + frames)."""
    chunk_len = 300.0 if total_dur > 300 else total_dur
    scenes, t = [], 0.0
    n_chunks = max(1, int((total_dur + chunk_len - 1) // chunk_len))
    ci = 0
    while t < total_dur:
        ci += 1
        end = min(total_dur, t + chunk_len)
        frames = extract_frames(video_path, t, end, work_dir, max_frames=12)
        prompt = f"""You are a professional movie recap narrator. You are provided with VISUAL FRAMES from a video segment and the segment's spoken transcript (with timestamps).

CRITICAL INSTRUCTIONS:
1. Act as a natural, third-person narrator explaining the story engagingly (like a popular Burmese YouTube Movie Recap channel).
2. Watch the frames and read the transcript. DO NOT translate word-for-word. Summarize the visual events and audio context into a cohesive story.
3. Style: {style_prompt}
4. This segment is exactly from timestamp {t:.1f}s to {end:.1f}s (Duration: {end - t:.1f}s). You MUST write a detailed script covering this specific segment. Distribute your scenes from {t:.1f}s to {end:.1f}s. Ensure the script length matches the segment length perfectly.
5. Divide the story into chronological SCENES based on visual changes and story progression.
6. For each scene, provide the exact video START and END timestamps based on when that scene occurs.
7. Write all narration text in natural, spoken Myanmar (Burmese).

TRANSCRIPT:
{_transcript_slice(segments, t, end)}

FORMAT REQUIREMENT:
Respond ONLY with a valid JSON object exactly like this (timestamps must be between {t:.1f} and {end:.1f}):
{{
  "scenes": [
    {{"start": {t:.1f}, "end": {t + 5.5:.1f}, "text": "ဒီအပိုင်းမှာတော့ အဓိက ဇာတ်ကောင်က..."}},
    {{"start": {t + 5.5:.1f}, "end": {end:.1f}, "text": "အဲ့ဒီနောက်မှာတော့ သူတို့တွေဟာ..."}}
  ]
}}"""
        parts = [{"text": prompt}] + frames
        obj = parse_gemini_json(_gemini_text(api_key, model, parts))
        for sc in obj.get("scenes", []):
            try:
                scenes.append({"start": float(sc["start"]), "end": float(sc["end"]),
                               "text": str(sc["text"]).strip()})
            except Exception:
                continue
        t = end
        if progress_cb:
            progress_cb(ci / n_chunks)
    scenes = [s for s in scenes if s["text"] and s["end"] > s["start"]]
    scenes.sort(key=lambda s: s["start"])
    return scenes


def gen_recap_dub_dialogues(api_key, model, video_path, segments, total_dur,
                            work_dir, progress_cb=None):
    """🎬+🎙️ Recap+Dub — ONC hybrid prompt (Narrator + dialogue)."""
    chunk_len = 300.0 if total_dur > 300 else total_dur
    out, t = [], 0.0
    n_chunks = max(1, int((total_dur + chunk_len - 1) // chunk_len))
    ci = 0
    while t < total_dur:
        ci += 1
        end = min(total_dur, t + chunk_len)
        frames = extract_frames(video_path, t, end, work_dir, max_frames=12)
        prompt = f"""You are a hybrid "Recap + Dubbing" AI. You are provided with VISUAL FRAMES of this segment and its spoken transcript (with timestamps).
This segment is exactly from timestamp {t:.1f}s to {end:.1f}s.

CRITICAL INSTRUCTIONS:
1. You MUST create a complete script spanning this specific segment (from {t:.1f}s to {end:.1f}s).
2. When characters are speaking in the transcript, translate their EXACT dialogue into natural Burmese (keep their timestamps).
3. During silent parts, action scenes, or visual transitions where no one is speaking, insert a "Narrator" speaker to explain the story engagingly based on the visual frames.
4. The result should be a seamless, continuous story featuring both character dialogues and narrator explanations filling the segment length.
5. Write everything in natural, spoken Myanmar (Burmese). DO NOT insert manual line breaks inside a text string.

TRANSCRIPT:
{_transcript_slice(segments, t, end)}

FORMAT REQUIREMENT:
Respond ONLY with a valid JSON object exactly like this (timestamps must be between {t:.1f} and {end:.1f}):
{{
  "speakers": [{{"id": "Narrator", "gender": "Male"}}],
  "dialogues": [
    {{"speaker": "Narrator", "start": {t:.1f}, "end": {t + 2.0:.1f}, "text": "ရုပ်ရှင်အစမှာတော့..."}},
    {{"speaker": "Speaker 1", "start": {t + 2.5:.1f}, "end": {t + 4.0:.1f}, "text": "မင်းဘာလုပ်နေတာလဲ။"}}
  ]
}}"""
        parts = [{"text": prompt}] + frames
        obj = parse_gemini_json(_gemini_text(api_key, model, parts))
        for d in obj.get("dialogues", []):
            try:
                out.append({"speaker": str(d.get("speaker", "Speaker 1")),
                            "start": float(d["start"]), "end": float(d["end"]),
                            "text": str(d["text"]).strip()})
            except Exception:
                continue
        t = end
        if progress_cb:
            progress_cb(ci / n_chunks)
    out = [d for d in out if d["text"] and d["end"] > d["start"]]
    out.sort(key=lambda d: d["start"])
    return out


def gen_translated_dialogues(api_key, model, segments, mode, progress_cb=None):
    """💬 Subtitle / 🎙️ Dubbing — segments ကို batch 40 နဲ့ ဘာသာပြန် (အချိန်ကိုက်)."""
    if mode == "subtitle":
        rules = """You are a professional subtitle translator.
- Translate the speech into natural, modern, conversational Myanmar Burmese. Avoid robotic word-for-word or textbook translations.
- Preserve original emotions, context and tone. Retain proper nouns / brand names / common English expressions when translating them sounds unnatural.
- Do not alter or shorten the core meaning, and do not add explanations.
- Keep each line short enough for mobile subtitles (aim 4–8 Burmese words per segment where natural)."""
    else:  # dubbing
        rules = """This is for a VOICE DUBBING project.
- Translate the EXACT spoken dialogues into natural, spoken Burmese. DO NOT summarize the story.
- Only translate what the characters are actively saying, sequentially, one line per input segment.
- Output the translated text purely as a single continuous string per dialogue block (no manual line breaks)."""
    out = {}
    BATCH = 40
    n = max(1, (len(segments) + BATCH - 1) // BATCH)
    for bi in range(n):
        batch = segments[bi * BATCH:(bi + 1) * BATCH]
        payload_lines = "\n".join(
            f"{bi * BATCH + i}. [{s['start']:.2f}-{s['end']:.2f}] {s['text']}"
            for i, s in enumerate(batch))
        prompt = f"""{rules}

Translate EVERY line below. Respond ONLY with a valid JSON object:
{{"translations": [{{"i": 0, "text": "မြန်မာဘာသာပြန် စာသား"}}]}}
where "i" is the line number shown before each line.

LINES:
{payload_lines}"""
        obj = parse_gemini_json(_gemini_text(api_key, model, [{"text": prompt}]))
        for tr in obj.get("translations", []):
            try:
                out[int(tr["i"])] = str(tr["text"]).strip()
            except Exception:
                continue
        if progress_cb:
            progress_cb((bi + 1) / n)
    dialogues = []
    for i, s in enumerate(segments):
        txt = out.get(i, "")
        if txt:
            dialogues.append({"speaker": "Speaker 1", "start": s["start"],
                              "end": s["end"], "text": txt, "src": s["text"]})
    return dialogues


def gen_social_kit(api_key, model, script_text):
    """📱 Social Kit — ONC generateSocialKitFn prompt (script text အခြေခံ)."""
    prompt = f"""Based on this movie recap script, generate a structured JSON for a MOVIE RECAP video social media post.
Return EXACTLY this JSON structure:
{{
  "hook3s": "A high-retention 3-second hook (in Burmese) designed to stop viewers scrolling.",
  "viralCaption": "A punchy, cinematic viral social media caption (in Burmese).",
  "hashtags": ["#MovieRecap", "#CinemaRecap", "#Trending", "#FilmReview", "#MustWatch"]
}}

SCRIPT:
{script_text[:6000]}"""
    return parse_gemini_json(_gemini_text(api_key, model, [{"text": prompt}]))


# ------------------------------------------------------------------ TTS
def _edge_rate(speed):
    pct = int(round((float(speed) - 1.0) * 100))
    return f"{max(-50, min(50, pct)):+d}%"


async def _edge_save_async(text, voice, rate, path):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(path)


def edge_tts_save(text, voice, speed, path):
    """🌐 Edge TTS 7.3.1 → mp3 (cache + retry)."""
    TTS_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"edge:{voice}:{_edge_rate(speed)}:{text}".encode()).hexdigest()
    cache = TTS_CACHE / f"{key}.mp3"
    if cache.exists() and cache.stat().st_size > 500:
        Path(path).write_bytes(cache.read_bytes())
        return str(path)
    tmp = str(path) + ".part"
    last = None
    for _ in range(3):
        try:
            asyncio.run(_edge_save_async(text, voice, _edge_rate(speed), tmp))
            if os.path.getsize(tmp) > 500:
                os.replace(tmp, path)
                cache.write_bytes(Path(path).read_bytes())
                return str(path)
            last = RuntimeError("Edge TTS က အသံအလွတ် ပြန်တယ်")
        except Exception as e:
            last = e
            time.sleep(1.5)
    raise RuntimeError(f"Edge TTS မရဘူး: {last}")


def gemini_tts_save(api_key, text, voice, voice_style, emotion, speed, path):
    """🤖 Gemini TTS → PCM 24k → wav → mp3 (speed ကို atempo နဲ့, tail fade)."""
    TTS_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(
        f"gemini:{voice}:{voice_style}:{emotion}:{speed}:{text}".encode()).hexdigest()
    cache = TTS_CACHE / f"{key}.mp3"
    if cache.exists() and cache.stat().st_size > 500:
        Path(path).write_bytes(cache.read_bytes())
        return str(path)
    style_bits = []
    if voice_style and voice_style != "None (Default)":
        style_bits.append(f"a {voice_style} style")
    emo_label = _EMOTION_LABELS.get(emotion, emotion).split(" ", 1)[-1]
    if emotion and emotion != "Neutral":
        style_bits.append(f"{emo_label} emotion")
    direction = ("Speak in " + " with ".join(style_bits) +
                 ". Maintain this exact style for the whole reading."
                 if style_bits else "Speak naturally and clearly.")
    spoken = (f"[DO NOT SPEAK THIS INSTRUCTION] CRITICAL VOICE DIRECTION: "
              f"{direction} Do not add any extra words, sounds, or commentary. "
              f"Start at the first word of the text and stop at the last word.\n"
              f"--- TEXT TO SPEAK ---\n{fix_pronunciation(text)}")
    payload = {
        "contents": [{"parts": [{"text": spoken}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": voice}}}},
    }
    data = _gemini_post(api_key, GEMINI_TTS_MODEL, payload, timeout=180)
    try:
        part = next(p for p in data["candidates"][0]["content"]["parts"]
                    if "inlineData" in p)
        pcm = base64.b64decode(part["inlineData"]["data"])
        mime = part["inlineData"].get("mimeType", "")
        m = re.search(r"rate=(\d+)", mime)
        sr = int(m.group(1)) if m else 24000
    except Exception:
        raise RuntimeError("Gemini TTS က အသံ မပြန်ဘူး")
    wav_path = str(path) + ".wav"
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    total = dur(wav_path)
    af = []
    if abs(float(speed) - 1.0) > 0.01:
        af.append(atempo_chain(speed))
    fade_at = max(0.0, total / max(float(speed), 0.01) - 0.3)
    af.append(f"afade=t=out:st={fade_at:.2f}:d=0.3")
    run(["ffmpeg", "-y", "-v", "error", "-i", wav_path, "-af", ",".join(af),
         "-ar", "24000", "-b:a", "64k", str(path)])
    os.remove(wav_path)
    cache.write_bytes(Path(path).read_bytes())
    return str(path)


def tts_one(engine, text, path, *, gemini_key="", gemini_voice="Alnilam",
            edge_voice="my-MM-ThihaNeural", voice_style="None (Default)",
            emotion="MovieRecap", speed=1.0):
    if engine == "gemini":
        return gemini_tts_save(gemini_key, text, gemini_voice, voice_style,
                               emotion, speed, path)
    return edge_tts_save(text, edge_voice, speed, path)


# ------------------------------------------------- audio assembly (step 4)
def build_recap_audio(items, tts_kwargs, work_dir, progress_cb=None):
    """Recap: scenes အစဉ်လိုက် ဆက် → narration.mp3 + sync data
    (sync: {vidStart, vidEnd, audStart, audDur, text})."""
    parts, sync = [], []
    aud_t = 0.0
    for i, sc in enumerate(items):
        p = Path(work_dir) / f"tts_{i:04d}.mp3"
        tts_one(path=str(p), text=sc["text"], **tts_kwargs)
        d = dur(p)
        if d <= 0:
            continue
        parts.append(p)
        sync.append({"vidStart": sc["start"], "vidEnd": sc["end"],
                     "audStart": aud_t, "audDur": d, "text": sc["text"]})
        aud_t += d
        if progress_cb:
            progress_cb((i + 1) / len(items))
    if not parts:
        raise RuntimeError("အသံ တစ်ခုမှ မထွက်ဘူး")
    listfile = Path(work_dir) / "concat.txt"
    listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    out = Path(work_dir) / "narration.mp3"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listfile), "-c", "copy", str(out)])
    return str(out), sync, aud_t


def _fit_segment(src, slot, work_dir, tag):
    """slot ထက် ရှည်ရင် atempo နဲ့ fit (cap 1.8x) → (path, fitted_dur)."""
    d = dur(src)
    if slot and d > slot * 1.02:
        rate = min(d / slot, 1.8)
        out = Path(work_dir) / f"fit_{tag}.mp3"
        run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af",
             atempo_chain(rate), "-ar", "24000", str(out)])
        return str(out), dur(out)
    return str(src), d


def build_timeline_audio(items, total_dur, tts_kwargs, work_dir,
                         progress_cb=None):
    """Dubbing/Recap+Dub: dialogue တစ်ခုချင်းကို သူ့အချိန်ကွက်ထဲ ထည့်
    (silence gap + segment ဆက်) → timeline.mp3 (video အရှည်အတိုင်း)."""
    ordered = sorted(items, key=lambda d: d["start"])
    parts, cursor = [], 0.0
    for i, d in enumerate(ordered):
        p = Path(work_dir) / f"tts_{i:04d}.mp3"
        tts_one(path=str(p), text=d["text"], **tts_kwargs)
        slot = max(0.1, d["end"] - d["start"])
        p, fd = _fit_segment(p, slot, work_dir, f"{i:04d}")
        start = max(float(d["start"]), cursor)
        if start > cursor + 0.05:
            sp = Path(work_dir) / f"gap_{i:04d}.mp3"
            silence(sp, start - cursor)
            parts.append(sp)
            cursor = start
        parts.append(Path(p))
        cursor += fd
        if progress_cb:
            progress_cb((i + 1) / len(ordered))
    if cursor < total_dur - 0.05:
        sp = Path(work_dir) / "gap_end.mp3"
        silence(sp, total_dur - cursor)
        parts.append(sp)
    listfile = Path(work_dir) / "concat.txt"
    listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    out = Path(work_dir) / "narration.mp3"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listfile), "-ar", "24000", "-b:a", "96k", str(out)])
    return str(out)


# ------------------------------------------------------------- subtitles (ASS)
def _ass_color(hex_color, alpha=0):
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}"


def _ass_time(sec):
    total_cs = max(0, int(round(sec * 100)))
    h, rem = divmod(total_cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_ass(sub_items, path, canvas_w, canvas_h, *, font_size=45,
              color="#FFFFFF", bg_color="#000000", bg_opacity=60,
              sub_x=10, sub_y=75, max_len=24, center=True):
    """sub_items (timed text) → generate_subtitle_chunks ခွဲ → ASS with \\pos.
    BorderStyle=3 (opaque box) — ONC ရဲ့ bg box ပုံစံ."""
    bg_alpha = int(round((100 - bg_opacity) / 100 * 255))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {canvas_w}
PlayResY: {canvas_h}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: MRS,Padauk,{int(font_size)},{_ass_color(color)},&H000000FF,{_ass_color(bg_color, bg_alpha)},&H00000000,-1,0,0,0,100,100,0,0,3,6,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    px = int(sub_x / 100 * canvas_w)
    py = int(sub_y / 100 * canvas_h)
    events = []
    for it in sub_items:
        span = max(0.1, it["end"] - it["start"])
        for ch in generate_subtitle_chunks(it["text"], span, it["start"],
                                           max_len=max_len):
            txt = ch["text"].replace("{", "(").replace("}", ")").replace("\n", r"\N")
            if center:  # အလယ်တည့်တည့် — \an8 = top-center anchor
                tag = f"{{\\an8\\pos({canvas_w // 2},{py})}}"
            else:
                tag = f"{{\\pos({px},{py})}}"
            events.append(
                f"Dialogue: 0,{_ass_time(ch['start'])},{_ass_time(ch['end'])},MRS,,0,0,0,,"
                f"{tag}{txt}")
    Path(path).write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return str(path)


def collect_sub_items(mode, items, sync=None):
    """mode အလိုက် subtitle timing source ရွေး."""
    if mode == "recap" and sync:
        return [{"start": s["audStart"], "end": s["audStart"] + s["audDur"],
                 "text": s["text"]} for s in sync]
    return [{"start": d["start"], "end": d["end"], "text": d["text"]}
            for d in items]


# ------------------------------------------------------------- render (step 5)
def make_hypersync_video(video_path, sync, canvas, work_dir, progress_cb=None):
    """⚡ Hyper-Sync — scene တစ်ခုချင်းကို narration အရှည်နဲ့ setpts ချိန် ဆက်."""
    W, H = canvas
    seg_files = []
    for i, s in enumerate(sync):
        vid_d = max(0.1, s["vidEnd"] - s["vidStart"])
        ratio = max(0.2, min(5.0, s["audDur"] / vid_d))
        seg = Path(work_dir) / f"hs_{i:04d}.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{s['vidStart']:.3f}",
             "-to", f"{s['vidEnd']:.3f}", "-i", str(video_path),
             "-vf", (f"setpts={ratio:.4f}*(PTS-STARTPTS),"
                     f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                     f"crop={W}:{H},setsar=1,fps=30,format=yuv420p"),
             "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             str(seg)])
        seg_files.append(seg)
        if progress_cb:
            progress_cb((i + 1) / len(sync))
    listfile = Path(work_dir) / "hs_concat.txt"
    listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in seg_files))
    out = Path(work_dir) / "synced.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listfile), "-c", "copy", str(out)])
    return str(out)


def render_final(S, cfg, progress_cb=None):
    """ffmpeg render → final.mp4 (တကယ့် MP4, browser WebM မဟုတ်).
    progress_cb(0.0–1.0): Hyper-Sync အဆင့် 0–35%, main render 35–100%."""
    work_dir = Path(S["run_dir"])
    mode = S["mode"]
    if mode != "subtitle":
        cfg["orig_vol"] = 0  # Subtitle Mode မှလွဲ မူရင်းအသံ လုံးဝဖျောက်
    W, H = auto_canvas(S["video_path"])  # video အချိုးအတိုင်း အလိုအလျောက်
    portrait = H > W
    src_video = S["video_path"]
    main_base, main_span = 0.0, 1.0

    if cfg["hypersync"] and mode == "recap" and S.get("sync"):
        src_video = make_hypersync_video(
            src_video, S["sync"], (W, H), work_dir,
            progress_cb=(lambda f: progress_cb(0.35 * f)) if progress_cb else None)
        main_base, main_span = 0.35, 0.65

    inputs = ["-i", src_video]
    idx_nar = idx_bgm = idx_logo = None
    if mode != "subtitle" and S.get("audio_path"):
        idx_nar = 1
        inputs += ["-i", S["audio_path"]]
    if cfg.get("bgm_path"):
        idx_bgm = len([x for x in inputs if x == "-i"])
        inputs += ["-stream_loop", "-1", "-i", cfg["bgm_path"]]
    if cfg.get("logo_path"):
        idx_logo = len([x for x in inputs if x == "-i"])
        inputs += ["-i", cfg["logo_path"]]

    # ---- video filter chain
    vf = []
    if not (cfg["hypersync"] and mode == "recap" and S.get("sync")):
        vf.append(f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},setsar=1")
    if cfg["mirror"]:
        vf.append("hflip")
    tone = COLOR_TONES.get(cfg["color_tone"], "")
    base_label = "0:v"
    fc = []
    if tone:
        vf.append(tone)
    if cfg["blur_on"]:
        # မူရင်း hardcoded subtitle ကို ဖုံးအောင် — full-width band (အောက်ပိုင်း)
        _bx = cfg.get("blur_x")
        _bw = cfg.get("blur_w")
        _by = cfg.get("blur_y")
        _bh = cfg.get("blur_h")
        bx_pct = 0 if _bx is None else _bx
        bw_pct = 100 if _bw is None else _bw
        by_pct = (68 if portrait else 72) if _by is None else _by
        bh_pct = (32 if portrait else 28) if _bh is None else _bh
        bw = max(1, int(bw_pct / 100 * W))
        bh = max(1, int(bh_pct / 100 * H))
        bx = int(bx_pct / 100 * W)
        by = int(by_pct / 100 * H)
        fc.append(f"[{base_label}]{','.join(vf)},split[va][vb]" if vf
                  else f"[{base_label}]split[va][vb]")
        fc.append(f"[vb]crop={bw}:{bh}:{bx}:{by},"
                  f"gblur=sigma={max(2, cfg['blur_strength'])}[blurred]")
        fc.append(f"[va][blurred]overlay={bx}:{by}[v1]")
        cur = "v1"
    else:
        fc.append(f"[{base_label}]{','.join(vf)}[v1]" if vf
                  else f"[{base_label}]null[v1]")
        cur = "v1"
    if cfg["subs_on"] and S.get("sub_items"):
        # Reel/Short-safe subtitle: font အကြီး (frame အမြင့်၏ ~5.2%),
        # portrait ဆို စာကြောင်းတို (14 လုံး) + Reel UI မဖုံးအောင် အပေါ်နည်း,
        # အမြဲ အလယ် (center)
        font_size = cfg.get("sub_size") or max(52, int(H * 0.052))
        sub_y = cfg.get("sub_y")
        sub_y = (64 if portrait else 78) if sub_y is None else sub_y
        max_len = 14 if portrait else (18 if H == W else 24)
        ass_path = write_ass(S["sub_items"], work_dir / "subs.ass", W, H,
                             font_size=font_size, color=cfg["sub_color"],
                             bg_color=cfg["sub_bg"], bg_opacity=cfg["sub_bg_op"],
                             sub_y=sub_y, max_len=max_len, center=True)
        esc = ass_path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        fc.append(f"[{cur}]ass='{esc}'[v2]")
        cur = "v2"
    if idx_logo is not None:
        lw = max(16, int(cfg["logo_size"] / 100 * W))
        pos = {"top-left": "24:24", "top-right": "W-w-24:24",
               "bottom-left": "24:H-h-24",
               "bottom-right": "W-w-24:H-h-24"}[cfg["logo_pos"]]
        fc.append(f"[{idx_logo}:v]scale={lw}:-1,format=rgba,"
                  f"colorchannelmixer=aa={cfg['logo_opacity'] / 100:.2f}[logo]")
        fc.append(f"[{cur}][logo]overlay={pos}[vout]")
        cur = "vout"
    else:
        fc.append(f"[{cur}]format=yuv420p[vout]")

    # ---- audio filter chain
    af = []
    a_labels = []
    if has_audio(src_video):
        af.append(f"[0:a]volume={cfg['orig_vol'] / 100:.2f}[a_orig]")
    else:
        af.append("anullsrc=r=44100:cl=stereo[a_orig_src]")
        af.append("[a_orig_src]volume=0[a_orig]")
    a_labels.append("[a_orig]")
    if idx_nar is not None:
        af.append(f"[{idx_nar}:a]volume={cfg['tts_vol'] / 100:.2f},"
                  "aresample=44100[a_nar]")
        a_labels.append("[a_nar]")
    if idx_bgm is not None:
        af.append(f"[{idx_bgm}:a]volume={cfg['bgm_vol'] / 100:.2f},"
                  "aresample=44100[a_bgm]")
        a_labels.append("[a_bgm]")
    af.append("".join(a_labels) +
              f"amix=inputs={len(a_labels)}:duration=longest:dropout_transition=0,"
              "alimiter=limit=0.95[aout]")

    if mode == "recap" and S.get("audio_path"):
        target = dur(S["audio_path"])
    else:
        target = dur(S["video_path"])

    out = work_dir / "final.mp4"
    cmd = (["ffmpeg", "-y", "-v", "error"] + inputs +
           ["-filter_complex", ";".join(fc + af),
            "-map", "[vout]", "-map", "[aout]",
            "-t", f"{target:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            "-r", "30", str(out)])
    try:
        run_progress(cmd, target, progress_cb, main_base, main_span)
    except RuntimeError as e:
        raise RuntimeError("Render မရဘူး — " + str(e))
    return str(out)


# ------------------------------------------------------------------ UI
S = st.session_state
for _k, _v in [("mode", "recap"), ("items", []), ("segments", None),
               ("audio_path", None), ("sync", None), ("social", None),
               ("final_path", None), ("sub_items", []), ("video_path", None),
               ("video_dur", 0.0), ("run_dir", None), ("script_done", False)]:
    if _k not in S:
        S[_k] = _v

st.markdown("""
<div class="hero">
  <div class="t">🎬 MOVIE RECAP STUDIO</div>
  <div class="s">Video → Script → အသံ → Render — GitHub + Streamlit Edition</div>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("#### 🔑 API Keys")
    localS = _local_storage()
    if S.get("_clear_keys"):
        _ls_del(localS, _LS_GEMINI, "ls_del_gemini")
        _ls_del(localS, _LS_GROQ, "ls_del_groq")
        for _k in ("gemini_key", "groq_key"):
            if _k in S:
                del S[_k]
        del S["_clear_keys"]

    def _secret(name):
        try:
            return (st.secrets.get(name) or "").strip()
        except Exception:
            return os.environ.get(name, "").strip()

    env_gemini = _secret("GEMINI_API_KEY")
    if not env_gemini and "gemini_key" not in S:
        _sg = _ls_get(localS, _LS_GEMINI)
        if _sg:
            S["gemini_key"] = _sg
    g_in = st.text_input("Gemini API Key", type="password", key="gemini_key",
                         placeholder="AIzaSy...",
                         help="Script + (Gemini TTS သုံးရင်) အသံအတွက် — တစ်ခါထည့်ရင် browser မှာ မှတ်ထားမယ်")
    typed_g = g_in.strip()
    if typed_g and typed_g != _ls_get(localS, _LS_GEMINI):
        _ls_set(localS, _LS_GEMINI, typed_g, "ls_set_gemini")
    gemini_key = typed_g or env_gemini
    st.markdown("🔑 အလကားယူရန်: [aistudio.google.com/apikey](https://aistudio.google.com/apikey)")
    if gemini_key:
        st.success("✅ Gemini key ရှိတယ်")
    else:
        st.warning("⚠️ Gemini key မရှိသေးဘူး (အဆင့် ၂ အတွက်လိုတယ်)")

    env_groq = _secret("GROQ_API_KEY")
    if not env_groq and "groq_key" not in S:
        _sq = _ls_get(localS, _LS_GROQ)
        if _sq:
            S["groq_key"] = _sq
    q_in = st.text_input("Groq API Key", type="password", key="groq_key",
                         placeholder="gsk_...",
                         help="အသံမှ စာသားထုတ်ဖို့ (Whisper) — တစ်ခါထည့်ရင် browser မှာ မှတ်ထားမယ်")
    typed_q = q_in.strip()
    if typed_q and typed_q != _ls_get(localS, _LS_GROQ):
        _ls_set(localS, _LS_GROQ, typed_q, "ls_set_groq")
    groq_key = typed_q or env_groq
    st.markdown("🔑 အလကားယူရန်: [console.groq.com/keys](https://console.groq.com/keys)")
    if groq_key:
        st.success("✅ Groq key ရှိတယ်")
    else:
        st.warning("⚠️ Groq key မရှိသေးဘူး (အဆင့် ၂ အတွက်လိုတယ်)")

    if st.button("🔑 သိမ်းထားတဲ့ key တွေ ဖျက်", use_container_width=True):
        S["_clear_keys"] = True
        st.rerun()
    st.divider()

    model_id = st.text_input("Gemini model (Script)", value=GEMINI_TEXT_MODEL_DEFAULT)
    st.divider()
    st.markdown("#### 🎚️ အသံ ဆက်တင်")
    engine_label = st.radio("TTS Engine", ["🌐 Edge TTS (7.3.1)", "🤖 Gemini TTS"],
                            help="Edge = အခမဲ့, မြန် (Thiha/Nilar မြန်မာအသံ). "
                                 "Gemini = ONC voice 20 မျိုး + Style/Emotion (Gemini key လို)")
    engine = "gemini" if engine_label.startswith("🤖") else "edge"
    if engine == "edge":
        edge_voice = st.selectbox("အသံ (Edge)", [v for v, _l in EDGE_VOICES],
                                  format_func=lambda v: _EDGE_VOICE_LABELS.get(v, v))
        gemini_voice, voice_style, emotion = "Alnilam", "None (Default)", "MovieRecap"
    else:
        gemini_voice = st.selectbox("အသံ (Gemini)", [v for v, _n, _g in GEMINI_VOICES],
                                    index=8,
                                    format_func=lambda v: _GEMINI_VOICE_LABELS.get(v, v))
        voice_style = st.selectbox("Voice Style", VOICE_STYLES)
        emotion = st.selectbox("Emotion", [e for e, _l in EMOTIONS],
                               index=1, format_func=lambda e: _EMOTION_LABELS.get(e, e))
        edge_voice = "my-MM-ThihaNeural"
    preset = st.radio("အမြန်နှုန်း", [p[0] for p in SPEED_PRESETS],
                      index=1, horizontal=True,
                      format_func=lambda p: dict((k, l) for k, l, _r in SPEED_PRESETS)[p])
    speed = dict((k, r) for k, _l, r in SPEED_PRESETS)[preset]

    tts_kwargs = dict(engine=engine, gemini_key=gemini_key,
                      gemini_voice=gemini_voice, edge_voice=edge_voice,
                      voice_style=voice_style, emotion=emotion, speed=speed)

    if st.button("🔊 အသံ စမ်းနားထောင်", use_container_width=True):
        WORK.mkdir(parents=True, exist_ok=True)
        _tp = WORK / "voice_test.mp3"
        try:
            with st.spinner("အသံထုတ်နေတယ်..."):
                tts_one(path=str(_tp),
                        text="မင်္ဂလာပါ။ ကျွန်တော့်အသံကို အခုလို ကြားရတဲ့အတွက် ဝမ်းသာပါတယ်။",
                        **tts_kwargs)
            S["_voice_test"] = str(_tp)
        except Exception as e:
            st.error(f"အသံစမ်းမရဘူး — {e}")
    if S.get("_voice_test") and os.path.isfile(S["_voice_test"]):
        st.audio(S["_voice_test"])

# ------------------------------------------------------------- mode + step 1
st.markdown("### ၁။ Video တင် + Mode ရွေး")
mode = st.radio("Processing Mode", MODES, horizontal=True,
                index=MODES.index(S["mode"]),
                format_func=lambda m: MODE_LABELS[m])
if mode != S["mode"]:
    S["mode"] = mode
    S.update(items=[], audio_path=None, sync=None, final_path=None,
             sub_items=[], script_done=False)
st.caption({
    "recap": "AI Vision က Video တစ်ခုလုံးစာ (Full Duration) အကျဉ်းချုပ် Script ရေးပေးမည်။",
    "subtitle": "မူရင်းအသံကို မဖျောက်ဘဲ စကားပြောများကို မြန်မာလို အချိန်ကိုက် စာတန်းထိုးပေးမည်။",
    "dubbing": "မူရင်းအသံနေရာတွင် မြန်မာလို ဘာသာပြန်ပြီး AI အသံဖြင့် အချိန်ကိုက် အသံထပ်သွင်းပေးမည်။",
    "recap_dub": "Narrator ဇာတ်ကြောင်းပြန်ခြင်းနှင့် ဇာတ်ကောင်အသံထပ်သွင်းခြင်းကို ပေါင်းစပ်ပေးမည်။",
}[mode])

# Script Style မလို — Recap မှာ ပုံသေ Movie Recap style ပဲ သုံးမယ်
script_style = "recap"
src_lang = st.selectbox("မူရင်းဘာသာစကား (Whisper)", [l for _l, l in SRC_LANGS],
                        format_func=lambda l: dict((v, k) for k, v in SRC_LANGS)[l])

up = st.file_uploader("Video ဖိုင် (mp4/mov/mkv/webm)", type=["mp4", "mov", "mkv", "webm"])
if up is not None:
    digest = hashlib.md5(up.getvalue()).hexdigest()[:10]
    run_dir = WORK / f"run_{digest}"
    run_dir.mkdir(parents=True, exist_ok=True)
    vpath = run_dir / ("video" + Path(up.name).suffix.lower())
    if not vpath.exists():
        vpath.write_bytes(up.getvalue())
    if S["video_path"] != str(vpath):
        S.update(video_path=str(vpath), run_dir=str(run_dir),
                 video_dur=dur(vpath), items=[], segments=None,
                 audio_path=None, sync=None, final_path=None,
                 sub_items=[], script_done=False)
    st.caption(f"✅ Video ရပြီ — ⏱️ Duration: {fmt_clock(S['video_dur'])} ({S['video_dur']:.1f}s)")

# ------------------------------------------------------------- step 2: script
st.markdown("### ၂။ Director's Script")
if st.button("✨ Script ထုတ်မယ် (Groq transcribe → Gemini script)",
             use_container_width=True, disabled=not S["video_path"]):
    if not groq_key:
        st.error("⚠️ Groq API key အရင်ထည့်ပါ (ဘယ်ဘက် sidebar)")
    elif not gemini_key:
        st.error("⚠️ Gemini API key အရင်ထည့်ပါ (ဘယ်ဘက် sidebar)")
    else:
        try:
            run_dir = Path(S["run_dir"])
            bar = st.progress(0.0, "အသံထုတ်နေတယ်...")
            audio_mp3 = run_dir / "audio.mp3"
            if not audio_mp3.exists():
                run(["ffmpeg", "-y", "-v", "error", "-i", S["video_path"],
                     "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
                     str(audio_mp3)])
            bar.progress(0.15, "Groq Whisper နဲ့ စာသားထုတ်နေတယ်...")
            data = transcribe_audio(str(audio_mp3), groq_key, src_lang,
                                    work_dir=run_dir,
                                    progress_cb=lambda p: bar.progress(0.15 + 0.25 * p))
            S["segments"] = data["segments"]
            if not S["segments"]:
                raise RuntimeError("Whisper က စကားပြော မတွေ့ဘူး — video မှာ အသံပါတာ သေချာပါစေ")
            bar.progress(0.45, "Gemini နဲ့ Script ရေးနေတယ်...")
            if mode == "recap":
                items = gen_recap_scenes(
                    gemini_key, model_id.strip() or GEMINI_TEXT_MODEL_DEFAULT,
                    S["video_path"], S["segments"], S["video_dur"],
                    _SCRIPT_STYLE_PROMPTS[script_style], run_dir,
                    progress_cb=lambda p: bar.progress(0.45 + 0.5 * p))
            elif mode == "recap_dub":
                items = gen_recap_dub_dialogues(
                    gemini_key, model_id.strip() or GEMINI_TEXT_MODEL_DEFAULT,
                    S["video_path"], S["segments"], S["video_dur"], run_dir,
                    progress_cb=lambda p: bar.progress(0.45 + 0.5 * p))
            else:
                items = gen_translated_dialogues(
                    gemini_key, model_id.strip() or GEMINI_TEXT_MODEL_DEFAULT,
                    S["segments"], mode,
                    progress_cb=lambda p: bar.progress(0.45 + 0.5 * p))
            if not items:
                raise RuntimeError("Script တစ်ခုမှ မထွက်ဘူး — ပြန်ကြိုးစားကြည့်ပါ")
            S["items"] = items
            S["script_done"] = True
            S["audio_path"] = None
            S["sync"] = None
            S["final_path"] = None
            S["sub_items"] = [] if mode == "recap" else collect_sub_items(mode, items)
            bar.progress(1.0, "ပြီးပြီ ✅")
        except Exception as e:
            st.error(f"Script ထုတ်မရဘူး — {e}")

if S["items"]:
    st.caption(f"📄 {len(S['items'])} ပိုင်း — စာသား/အချိန် ပြင်လို့ရတယ် (ပြင်ပြီး 'ပြင်တာသိမ်း' နှိပ်)")
    import pandas as pd
    rows = [{"start": round(float(d["start"]), 2), "end": round(float(d["end"]), 2),
             **({"speaker": d.get("speaker", "")} if "speaker" in d else {}),
             "text": d["text"]} for d in S["items"]]
    edited = st.data_editor(pd.DataFrame(rows), use_container_width=True,
                            num_rows="dynamic", key="items_editor")
    if st.button("💾 ပြင်တာသိမ်း"):
        new_items = []
        for _, r in edited.iterrows():
            if str(r["text"]).strip():
                d = {"start": float(r["start"]), "end": float(r["end"]),
                     "text": str(r["text"]).strip()}
                if "speaker" in edited.columns:
                    d["speaker"] = str(r.get("speaker", "Speaker 1"))
                new_items.append(d)
        S["items"] = new_items
        S["audio_path"] = None
        S["final_path"] = None
        S["sub_items"] = [] if mode == "recap" else collect_sub_items(mode, new_items)
        st.success("သိမ်းပြီးပြီ ✅")

    # 📱 Social Kit
    if mode != "subtitle":
        if st.button("📱 Social Kit ထုတ်မယ် (🔥 Hook + Caption + Hashtags)"):
            if not gemini_key:
                st.error("⚠️ Gemini API key လိုတယ်")
            else:
                try:
                    with st.spinner("Social Kit ရေးနေတယ်..."):
                        S["social"] = gen_social_kit(
                            gemini_key, model_id.strip() or GEMINI_TEXT_MODEL_DEFAULT,
                            "\n".join(d["text"] for d in S["items"]))
                except Exception as e:
                    st.error(f"Social Kit မရဘူး — {e}")
    if S.get("social"):
        sk = S["social"]
        st.markdown("#### 📱 Social Kit")
        st.text_input("🔥 3-Second Hook", value=sk.get("hook3s", ""), key="sk_hook")
        st.text_area("📝 Viral Caption", value=sk.get("viralCaption", ""),
                     key="sk_cap", height=80)
        st.text_input("#️⃣ Hashtags", value=" ".join(sk.get("hashtags", [])),
                      key="sk_tags")

# ------------------------------------------------------------- step 3: audio
st.markdown("### ၃။ အသံထုတ် (TTS)")
if mode == "subtitle":
    st.info("💬 Subtitle mode — အသံအသစ် မထုတ်ဘူး (မူရင်းအသံ အတိုင်းထားမယ်)")
else:
    if st.button("🎙️ အသံထုတ်မယ်", use_container_width=True,
                 disabled=not S["items"]):
        try:
            run_dir = Path(S["run_dir"])
            bar = st.progress(0.0, "TTS ထုတ်နေတယ်...")
            if mode == "recap":
                audio, sync, _tot = build_recap_audio(
                    S["items"], tts_kwargs, run_dir,
                    progress_cb=lambda p: bar.progress(p))
                S["sync"] = sync
                S["sub_items"] = collect_sub_items("recap", S["items"], sync)
            else:
                audio = build_timeline_audio(
                    S["items"], S["video_dur"], tts_kwargs, run_dir,
                    progress_cb=lambda p: bar.progress(p))
            S["audio_path"] = audio
            S["final_path"] = None
            bar.progress(1.0, "အသံရပြီ ✅")
        except Exception as e:
            st.error(f"အသံထုတ်မရဘူး — {e}")
    if S.get("audio_path") and os.path.isfile(S["audio_path"]):
        st.audio(S["audio_path"])
        st.download_button("⬇️ Narration MP3 ဒေါင်းရန်",
                           Path(S["audio_path"]).read_bytes(),
                           file_name="narration.mp3", mime="audio/mpeg")

# ------------------------------------------------------------- step 4: render
st.markdown("### ၄။ Final Video Render")
hypersync = st.checkbox(
    "⚡ Hyper-Sync (Recap: video ကို narration အရှည်နဲ့ကိုက် အမြန်/အနှေး ချိန်)",
    value=True)
can_render = bool(S["video_path"] and S["items"] and
                  (mode == "subtitle" or S.get("audio_path")))
if st.button("🎬 Final Video Render လုပ်မယ်", use_container_width=True,
             disabled=not can_render):
    try:
        # Render settings section ဖယ်ပြီး — မူလ default တန်ဖိုးတွေနဲ့ render မယ်
        cfg = dict(aspect="16:9", mirror=True, color_tone="Normal (Original)",
                   hypersync=hypersync, subs_on=True, sub_color="#FFFFFF",
                   sub_bg="#000000", sub_size=None, sub_bg_op=60, sub_x=None,
                   sub_y=None, blur_on=True, blur_x=None, blur_y=None,
                   blur_w=None, blur_h=None, blur_strength=30, logo_path=None,
                   logo_pos="top-right", logo_size=15, logo_opacity=100,
                   bgm_path=None, tts_vol=100,
                   orig_vol=(100 if mode == "subtitle" else 0),
                   bgm_vol=20)
        bar = st.progress(0.0, "🎬 Render စတင်နေတယ်... 0%")

        def _rcb(p):
            p = min(1.0, max(0.0, p))
            bar.progress(p, f"🎬 Render လုပ်နေတယ်... {int(p * 100)}%")
        S["final_path"] = render_final(S, cfg, progress_cb=_rcb)
        bar.progress(1.0, "🎬 Render ပြီးပြီ ✅ 100%")
        st.success("Render ပြီးပြီ ✅")
    except Exception as e:
        st.error(str(e))

if S.get("final_path") and os.path.isfile(S["final_path"]):
    st.video(S["final_path"])
    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        st.download_button("⬇️ Final MP4 ဒေါင်းရန်",
                           Path(S["final_path"]).read_bytes(),
                           file_name="MovieRecap_Final.mp4", mime="video/mp4")
    with dc2:
        if S.get("sub_items"):
            st.download_button("⬇️ SRT ဒေါင်းရန်",
                               build_srt(S["sub_items"]).encode("utf-8"),
                               file_name="subtitles.srt", mime="text/plain")
    with dc3:
        if S.get("segments"):
            st.download_button("⬇️ မူရင်း Transcript SRT",
                               build_srt(S["segments"]).encode("utf-8"),
                               file_name="transcript.srt", mime="text/plain")

st.markdown('<div class="credit">Create by Bo Bo Myint Mo • Movie Recap Studio — Streamlit Edition</div>',
            unsafe_allow_html=True)
