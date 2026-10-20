# 🎬 Movie Recap Studio — Streamlit Edition

ONC_1 (React) code style ကို **GitHub + Streamlit Cloud** မှာ run လို့ရအောင်
Python/Streamlit နဲ့ ပြန်ဆောက်ထားတာ။ Spidy Dub App လိုပဲ sidebar မှာ
**Gemini API key** နဲ့ **Groq API key** ထည့်ရတယ် — တစ်ခါထည့်ရင် browser
localStorage မှာ မှတ်ထားတယ် (Streamlit Secrets / env နဲ့လည်း ရတယ်)။
**Edge TTS 7.3.1** ပါတယ်။ Create by Bo Bo Myint Mo.

## လုပ်ဆောင်ချက်

1. **Video တင်** → ffmpeg နဲ့ audio ထုတ် (mp3 16k mono 32k)
2. **Groq Whisper** (`whisper-large-v3`) → စကားပြော + timestamps
   (ဖိုင်ကြီးရင် အပိုင်းခွဲပြီး အလိုအလျောက် ဆက်ပေးတယ်)
3. **Gemini** (`gemini-2.5-flash`, sidebar မှာ model ပြောင်းလို့ရ) → Mode အလိုက် Script:
   - 🎬 **Recap** — frames (vision) + transcript → scenes script
     (Script Style: Movie Recap / Documentary / Storytelling / Viral Short)
   - 💬 **Subtitle** — dialogue တွေ မြန်မာ ဘာသာပြန် (အချိန်ကိုက်၊ SRT ရတယ်)
   - 🎙️ **Dubbing** — ဘာသာပြန် dialogue တွေကို အချိန်ကွက်ထဲ အသံထပ်သွင်း
   - 🎬+🎙️ **Recap + Dub** — Narrator + dialogue ပေါင်းစပ်
   - 📱 **Social Kit** — 🔥 3s Hook + Viral Caption + Hashtags 5 ခု
   - Script ကို ဇယားထဲမှာ တိုက်ရိုက်ပြင်လို့ရတယ်
4. **TTS (၂ မျိုး ရွေး)**:
   - 🌐 **Edge TTS 7.3.1** — Thiha/Nilar မြန်မာအသံ + Multilingual 12 မျိုး,
     အမြန် 🐌0.85 / ▶️1.0 / ⚡1.25
   - 🤖 **Gemini TTS** — ONC voice 20 မျိုး (မြန်မာအမည်တွေနဲ့) + Voice Style 11 +
     Emotion 11
5. **ffmpeg Render → တကယ့် MP4** (browser WebM မဟုတ်):
   🪞 Mirror (Copyright Bypass), 🎨 Color Tone 5 မျိုး, 🌫️ Blur box
   (X/Y/W/H/Strength), 💬 Subtitle burn-in (Padauk, ကာလာ/Size/BG/နေရာ ချိန်လို့ရ),
   🖼️ Logo (4 corners, size, opacity), 🎵 BGM + Volume mix (TTS/Original/BGM),
   ⚡ Hyper-Sync (Recap မှာ video ကို narration နဲ့ကိုက် အမြန်/အနှေး ချိန်),
   📐 16:9 / 9:16 / 1:1

## Streamlit Cloud ပေါ်တင်နည်း (အခမဲ့)

1. ဒီ folder ကို GitHub repo အသစ်တစ်ခုထဲ push လုပ်
2. <https://share.streamlit.io> → **GitHub** နဲ့ login → **Create app**
   → repo ရွေး, Branch: `main`, Main file path: `app.py` → **Deploy**
   (~2–3 မိနစ် build — `packages.txt` က ffmpeg + Padauk font သွင်းပေးမယ်)
3. App ပွင့်ရင် sidebar မှာ **Gemini** + **Groq** key ထည့်ရုံပဲ
   (ဒါမှမဟုတ် App **Settings → Secrets** မှာ ထည့်):
   ```toml
   GEMINI_API_KEY = "<redacted>"
   GROQ_API_KEY = "gsk_..."
   ```

Key တွေယူနည်း (အခမဲ့):
- **Gemini** — <https://aistudio.google.com/apikey>
- **Groq** — <https://console.groq.com/keys>

## ကိုယ့် computer ပေါ် run နည်း

```bash
pip install -r requirements.txt   # + ffmpeg system package လိုတယ်
streamlit run app.py
```

## မှတ်ချက်များ

- **Poster/Thumbnail Maker မပါဘူး** — Gemini image generation က free tier မှာ
  quota `limit: 0` (billing လိုတယ်)။ အရင် ဆုံးဖြတ်ချက်အတိုင်း ဖယ်ထားတယ် —
  ပြန်ထည့်ချင်ရင် ပြောပါ။
- Browser version ရဲ့ Canvas preview / Timeline drag editor က Streamlit မှာ
  မရှိဘူး — အစား Render Settings slider တွေနဲ့ ချိန်ပြီး တကယ့် MP4 render ထုတ်တယ်။
- Edge TTS က Microsoft server ကို တိုက်ရိုက်ခေါ်တာမို့ Streamlit Cloud ပေါ်မှာ
  အလုပ်လုပ်တယ် (7.3.1 က Sec-MS-GEC v2 token အသစ်နဲ့ 403 ပြဿနာ ပြင်ပြီးသား)။
- Video ရှည်ရင် Render ကြာနိုင်တယ် (Cloud CPU အပေါ် မူတည်)။
- အလုပ်ဖိုင်တွေ `work/` အောက်မှာ သိမ်းတယ် (git မှာ မပါ)။ TTS cache ရှိလို့
  စာသားတူရင် ပြန်ထုတ်စရာမလိုဘူး။
