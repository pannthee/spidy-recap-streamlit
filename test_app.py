"""Unit tests for Movie Recap Studio (Streamlit) core helpers + render smoke test.
Run: .venv/bin/python -m pytest test_app.py -q   (or plain python test_app.py)
Note: importing app.py executes the Streamlit UI script once (headless-safe);
helpers are then exercised directly. ffmpeg needed for the render smoke test.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def _load():
    spec = importlib.util.spec_from_file_location("mrs_app", HERE / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


app = _load()


def test_subtitle_chunks_burmese():
    text = "ဒီအပိုင်းမှာတော့ ဇာတ်ကောင်က အိမ်ပြန်လာတယ်။ သူမေးတယ်၊ မင်းဘာလုပ်နေတာလဲ။"
    chunks = app.generate_subtitle_chunks(text, 10.0, 5.0)
    assert chunks, "no chunks"
    assert abs(chunks[0]["start"] - 5.0) < 0.01
    assert abs(chunks[-1]["end"] - 15.0) < 0.05
    # timing is contiguous
    for a, b in zip(chunks, chunks[1:]):
        assert abs(a["end"] - b["start"]) < 0.05
    # no chunk line longer than ~30 chars (24 limit + pairing tolerance)
    for c in chunks:
        for line in c["text"].split("\n"):
            assert len(line) <= 30, line


def test_srt_build():
    srt = app.build_srt([{"start": 0, "end": 1.5, "text": "မင်္ဂလာပါ"},
                         {"start": 61.0, "end": 62.25, "text": "နောက်တစ်ခု"}])
    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert "00:01:01,000 --> 00:01:02,250" in srt


def test_parse_gemini_json():
    obj = app.parse_gemini_json('```json\n{"scenes": [{"start": 0, "end": 5, "text": "x"}]}\n```')
    assert obj["scenes"][0]["text"] == "x"


def test_edge_rate_and_atempo():
    assert app._edge_rate(1.0) == "+0%"
    assert app._edge_rate(1.25) == "+25%"
    assert app._edge_rate(0.85) == "-15%"
    assert app.atempo_chain(1.0) == "atempo=1.0000"
    assert app.atempo_chain(3.0).count("atempo") == 2  # 2.0 * 1.5


def test_ass_write(tmp_path=None):
    out = HERE / "work" / "test_subs.ass"
    out.parent.mkdir(parents=True, exist_ok=True)
    app.write_ass([{"start": 0, "end": 4, "text": "မင်္ဂလာပါ။ ဒါက စမ်းသပ်စာတန်းပါ။"}],
                  out, 1920, 1080)
    txt = out.read_text(encoding="utf-8")
    assert "Padauk" in txt and "\\pos(" in txt and "Dialogue:" in txt


def test_fix_pronunciation():
    assert app.fix_pronunciation("ဘီး") == "ဘိမ်း"


def test_render_smoke():
    """End-to-end ffmpeg render on a synthetic 6s video (subtitle mode path)."""
    wd = HERE / "work" / "smoke"
    wd.mkdir(parents=True, exist_ok=True)
    vid = wd / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=640x360:rate=30:duration=6",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(vid)], check=True)
    S = {"run_dir": str(wd), "mode": "subtitle", "video_path": str(vid),
         "sync": None, "audio_path": None,
         "sub_items": [{"start": 0.5, "end": 5.5,
                        "text": "ဒါက စမ်းသပ် စာတန်းထိုးပါ။ နောက်တစ်ကြောင်း ဆက်ပြောပါမယ်။"}]}
    cfg = dict(aspect="16:9", mirror=True, color_tone="Cinematic",
               hypersync=False, subs_on=True, sub_color="#FFFFFF",
               sub_bg="#000000", sub_size=45, sub_bg_op=60, sub_x=10, sub_y=75,
               blur_on=True, blur_x=10, blur_y=70, blur_w=80, blur_h=25,
               blur_strength=25, logo_path=None, logo_pos="top-right",
               logo_size=15, logo_opacity=100, bgm_path=None,
               tts_vol=100, orig_vol=100, bgm_vol=20)
    out = app.render_final(S, cfg)
    assert Path(out).exists() and Path(out).stat().st_size > 10000
    d = app.dur(out)
    assert 5.5 < d < 6.6, d


def test_auto_canvas_and_portrait_render():
    """9:16 video → canvas 1080x1920 + final render လည်း portrait ပဲ ထွက်."""
    wd = HERE / "work" / "portrait"
    wd.mkdir(parents=True, exist_ok=True)
    vid = wd / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=360x640:rate=30:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(vid)], check=True)
    assert app.auto_canvas(str(vid)) == (1080, 1920)
    S = {"run_dir": str(wd), "mode": "subtitle", "video_path": str(vid),
         "sync": None, "audio_path": None,
         "sub_items": [{"start": 0.5, "end": 3.5,
                        "text": "ဒါက portrait စမ်းသပ်စာတန်း ဖြစ်ပါတယ်။ ဖတ်ရလွယ်ရမယ်။"}]}
    cfg = dict(aspect="16:9", mirror=False, color_tone="Normal (Original)",
               hypersync=False, subs_on=True, sub_color="#FFFFFF",
               sub_bg="#000000", sub_size=None, sub_bg_op=60, sub_x=None,
               sub_y=None, blur_on=False, blur_x=10, blur_y=70, blur_w=80,
               blur_h=25, blur_strength=25, logo_path=None,
               logo_pos="top-right", logo_size=15, logo_opacity=100,
               bgm_path=None, tts_vol=100, orig_vol=100, bgm_vol=20)
    out = app.render_final(S, cfg)
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", out], capture_output=True, text=True)
    assert r.stdout.strip() == "1080,1920", r.stdout
    # ASS font size auto for portrait must be big (>= 90)
    ass = (wd / "subs.ass").read_text(encoding="utf-8")
    import re as _re
    m = _re.search(r"Style: MRS,Padauk,(\d+)", ass)
    assert m and int(m.group(1)) >= 90, ass[:400]
    # subtitles centered: \an8 + \pos at canvas center x=540 (1080 wide)
    assert "\\an8\\pos(540," in ass, ass[:600]


def test_no_original_audio_outside_subtitle():
    """Recap mode: cfg orig_vol=100 ပေးတောင် မူရင်းအသံ (noise) မပါရ."""
    wd = HERE / "work" / "noorig"
    wd.mkdir(parents=True, exist_ok=True)
    vid = wd / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=320x180:rate=30:duration=4",
                    "-f", "lavfi", "-i", "anoisesrc=color=white:duration=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(vid)], check=True)
    tts = wd / "tts.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "sine=frequency=660:duration=4",
                    "-c:a", "libmp3lame", str(tts)], check=True)
    S = {"run_dir": str(wd), "mode": "recap", "video_path": str(vid),
         "sync": None, "audio_path": str(tts),
         "items": [{"start": 0.0, "end": 4.0, "duration": 4.0, "text": "x"}],
         "sub_items": []}
    cfg = dict(aspect="16:9", mirror=False, color_tone="Normal (Original)",
               hypersync=False, subs_on=False, sub_color="#FFFFFF",
               sub_bg="#000000", sub_size=None, sub_bg_op=60, sub_x=None,
               sub_y=None, blur_on=False, blur_x=None, blur_y=None,
               blur_w=None, blur_h=None, blur_strength=30, logo_path=None,
               logo_pos="top-right", logo_size=15, logo_opacity=100,
               bgm_path=None, tts_vol=100, orig_vol=100, bgm_vol=20)
    out = app.render_final(S, cfg)
    # TTS = 660Hz sine ပဲ ရှိရမယ် — 3kHz အထက် highpass ဖြတ်ရင် noise (မူရင်းအသံ)
    # ပါလာရင် အသံကျန်မယ်; မပါရင် တိတ်ဆိတ်နီးပါး ဖြစ်ရမယ်
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", out,
                        "-af", "highpass=f=3000,volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    import re as _re
    m = _re.search(r"mean_volume: (-?[\d.]+)", r.stderr)
    assert m, r.stderr[-500:]
    assert float(m.group(1)) < -50, f"original audio leaked: {m.group(1)} dB"


if __name__ == "__main__":
    test_subtitle_chunks_burmese()
    test_srt_build()
    test_parse_gemini_json()
    test_edge_rate_and_atempo()
    test_ass_write()
    test_fix_pronunciation()
    test_render_smoke()
    test_auto_canvas_and_portrait_render()
    test_no_original_audio_outside_subtitle()
    print("ALL TESTS PASS")
