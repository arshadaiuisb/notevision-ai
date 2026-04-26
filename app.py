import streamlit as st
import tempfile, os, re
import google.generativeai as genai

# ── PDF support ──────────────────────────────────────────────
try:
    import fitz
    PDF_OK = True
except ImportError:
    PDF_OK = False

# ── TTS ──────────────────────────────────────────────────────
try:
    from gtts import gTTS
    TTS_OK = True
except ImportError:
    TTS_OK = False

# ── Video ────────────────────────────────────────────────────
try:
    from moviepy.editor import (ImageClip, AudioFileClip,
                                concatenate_videoclips,
                                concatenate_audioclips)
    from PIL import Image, ImageDraw, ImageFont
    import numpy as np
    VIDEO_OK = True
except ImportError:
    VIDEO_OK = False

# ── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="NoteVision AI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.stApp{background:#0f1117}
.main-title{
  font-size:2.2rem;font-weight:700;
  background:linear-gradient(135deg,#667eea,#764ba2);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
}
.subtitle{color:#8b8fa8;font-size:.95rem;margin-bottom:1.5rem}
.sec{color:#a78bfa;font-size:.78rem;font-weight:600;text-transform:uppercase;
     letter-spacing:.6px;border-bottom:1px solid #2a2d3e;padding-bottom:5px;margin-bottom:10px}
.success-box{background:#1e2a1e;border:1px solid #2a4a2a;border-radius:8px;
             padding:12px;color:#7dc47d;font-size:.9rem}
.info-box{background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;
          padding:12px;color:#b0b3cc;font-size:.88rem}
div[data-testid="stButton"]>button{
  background:linear-gradient(135deg,#667eea,#764ba2)!important;
  color:#fff!important;border:none!important;border-radius:10px!important;
  font-weight:600!important;width:100%!important}
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────

def get_api_key():
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return st.session_state.get("gemini_key", "")


def extract_pdf(f) -> str:
    if not PDF_OK:
        return ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(f.read()); path = tmp.name
    doc = fitz.open(path)
    txt = "\n".join(p.get_text() for p in doc)
    doc.close(); os.unlink(path)
    return txt[:8000]


def generate_script(content: str, minutes: int, api_key: str) -> str:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    words = minutes * 140
    prompt = f"""You are an expert narrator creating a {minutes}-minute audio/video overview script.
Write approximately {words} words.
Start each major section with "## Section Title" on its own line.
Write in flowing conversational paragraphs. Be engaging, informative, and comprehensive.

Create a {minutes}-minute detailed overview about:

{content[:6000]}"""
    resp = model.generate_content(prompt)
    return resp.text


def build_slides(script: str):
    parts = re.split(r'^## ', script, flags=re.MULTILINE)
    slides = []
    for p in parts:
        if not p.strip():
            continue
        lines = p.strip().split('\n')
        title = lines[0].strip()
        body  = ' '.join(lines[1:]).strip()[:350]
        slides.append({"title": title, "body": body})
    if not slides:
        chunks = [script[i:i+400] for i in range(0, len(script), 400)]
        slides = [{"title": f"Part {i+1}", "body": c} for i, c in enumerate(chunks)]
    return slides


def generate_mp3(script: str) -> bytes:
    clean = re.sub(r'^##[^\n]*', '', script, flags=re.MULTILINE).strip()
    tts = gTTS(text=clean, lang='en', slow=False)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tts.save(f.name); path = f.name
    data = open(path, "rb").read()
    os.unlink(path)
    return data


def make_slide_image(slide, idx, total, W=1280, H=720):
    img  = Image.new("RGB", (W, H), "#0f1117")
    draw = ImageDraw.Draw(img)
    try:
        ft = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
        fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except Exception:
        ft = fb = fs = ImageFont.load_default()

    # Accent blob
    for r in range(160, 0, -3):
        a = int(255*(1-r/160)*0.18)
        draw.ellipse([W-110-r, 90-r, W-110+r, 90+r], fill=(102,126,234))

    # Header
    draw.text((48, 18), "NoteVision AI", fill="#a78bfa", font=fs)
    draw.text((W-90, 18), f"{idx+1} / {total}", fill="#4a4e6a", font=fs)

    # Progress bar
    draw.rectangle([48, 52, W-48, 56], fill="#2a2d3e")
    pw = int((W-96)*(idx+1)/total)
    draw.rectangle([48, 52, 48+pw, 56], fill="#667eea")

    # Title
    title = slide["title"][:55]+("..." if len(slide["title"])>55 else "")
    draw.text((80, 175), title, fill="#ffffff", font=ft)
    tw = draw.textlength(title, font=ft)
    draw.rectangle([80, 228, 80+min(tw,480), 231], fill="#667eea")

    # Body
    words = slide["body"].split()
    line, y = "", 268
    for w in words:
        test = (line+" "+w).strip()
        if draw.textlength(test, font=fb) > W-180 and line:
            draw.text((80, y), line, fill="#b0b3cc", font=fb)
            line, y = w, y+34
            if y > H-65: break
        else:
            line = test
    if line and y <= H-65:
        draw.text((80, y), line, fill="#b0b3cc", font=fb)

    # Footer
    draw.rectangle([0, H-38, W, H-37], fill="#2a2d3e")
    draw.text((80, H-24),
              "Generated by NoteVision AI — Powered by Google Gemini",
              fill="#4a4e6a", font=fs)
    return img


def generate_mp4(slides, audio_bytes: bytes, secs: int = 8) -> bytes:
    tmp = tempfile.mkdtemp()
    clips = []
    for i, slide in enumerate(slides):
        img = make_slide_image(slide, i, len(slides))
        p   = os.path.join(tmp, f"s{i}.png")
        img.save(p)
        clips.append(ImageClip(p).set_duration(secs))

    video = concatenate_videoclips(clips, method="compose")

    ap = os.path.join(tmp, "audio.mp3")
    with open(ap, "wb") as f: f.write(audio_bytes)
    ac = AudioFileClip(ap)
    vd = video.duration
    if ac.duration < vd:
        loops = int(vd/ac.duration)+1
        ac = concatenate_audioclips([ac]*loops).subclip(0, vd)
    else:
        ac = ac.subclip(0, vd)

    out = os.path.join(tmp, "out.mp4")
    video.set_audio(ac).write_videofile(
        out, fps=24, codec="libx264",
        audio_codec="aac", verbose=False, logger=None)

    data = open(out,"rb").read()
    for fn in os.listdir(tmp):
        try: os.unlink(os.path.join(tmp,fn))
        except: pass
    try: os.rmdir(tmp)
    except: pass
    return data


# ── UI ───────────────────────────────────────────────────────

st.markdown('<h1 class="main-title">📚 NoteVision AI</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">AI-powered audio & video overview generator — Powered by Google Gemini (Free)</p>',
            unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="sec">🔑 Google Gemini API Key</div>', unsafe_allow_html=True)
    api_key = get_api_key()
    if not api_key:
        api_key = st.text_input("Paste your Gemini API key",
                                type="password",
                                placeholder="AIza...")
        if api_key:
            st.session_state["gemini_key"] = api_key
        st.markdown("""<div class="info-box">
        Get a <b>free</b> key at:<br>
        <a href="https://aistudio.google.com/app/apikey" target="_blank">
        aistudio.google.com → Get API Key</a>
        </div>""", unsafe_allow_html=True)
    else:
        st.success("✅ API Key loaded")

    st.markdown('<div class="sec">📋 Source Content</div>', unsafe_allow_html=True)
    src_type = st.radio("Input", ["Text / Topic", "Upload PDF"],
                        label_visibility="collapsed")
    text_in = pdf_txt = ""
    if src_type == "Text / Topic":
        text_in = st.text_area("Content or topic", height=180,
                               placeholder="e.g. 'History of the Mughal Empire'\nor paste a full article...")
    else:
        up = st.file_uploader("Upload PDF", type=["pdf"])
        if up:
            with st.spinner("Reading PDF..."):
                pdf_txt = extract_pdf(up)
            if pdf_txt:
                st.success(f"✅ {len(pdf_txt)} characters extracted")
            else:
                st.error("Could not read PDF.")

    st.markdown('<div class="sec">⏱ Settings</div>', unsafe_allow_html=True)
    minutes      = st.select_slider("Length", [5,8,10,12], value=5,
                                    format_func=lambda x: f"{x} minutes")
    secs_slide   = st.slider("Seconds per slide", 6, 20, 8)
    gen_btn      = st.button("✨ Generate Overview")

# ── Generation ───────────────────────────────────────────────
source = pdf_txt or text_in

if gen_btn:
    if not api_key:
        st.error("❌ Please enter your Google Gemini API key in the sidebar.")
    elif not source.strip():
        st.error("❌ Please paste content or upload a PDF first.")
    else:
        prog = st.progress(0, text="Starting…")
        c1, c2 = st.columns(2)
        try:
            # Script
            prog.progress(10, text="🤖 Gemini is writing your script…")
            script = generate_script(source, minutes, api_key)
            slides = build_slides(script)
            prog.progress(35, text=f"✅ Script ready — {len(script.split())} words, {len(slides)} slides")

            with st.expander("📝 View Generated Script", expanded=False):
                st.markdown(script)

            # Audio
            prog.progress(40, text="🎙 Generating MP3 audio…")
            if TTS_OK:
                mp3 = generate_mp3(script)
                prog.progress(62, text="✅ MP3 ready!")
                with c1:
                    st.markdown("### 🎙 Audio Overview")
                    st.audio(mp3, format="audio/mp3")
                    st.download_button("⬇ Download MP3", mp3,
                                       "NoteVision-overview.mp3",
                                       "audio/mpeg",
                                       use_container_width=True)
            else:
                mp3 = b""
                st.warning("gTTS not installed — audio skipped.")

            # Video
            prog.progress(65, text="🎬 Building MP4 video… (please wait)")
            if VIDEO_OK and mp3:
                mp4 = generate_mp4(slides, mp3, secs_slide)
                prog.progress(95, text="✅ MP4 ready!")
                with c2:
                    st.markdown("### 🎬 Video Overview")
                    st.video(mp4)
                    st.download_button("⬇ Download MP4", mp4,
                                       "NoteVision-overview.mp4",
                                       "video/mp4",
                                       use_container_width=True)
            else:
                st.warning("moviepy/Pillow not installed — video skipped.")

            prog.progress(100, text="🎉 Done!")
            st.markdown("""<div class="success-box">
            ✅ <b>Generation complete!</b><br>
            Your real <b>MP3</b> and <b>MP4</b> files are ready to play and download!
            </div>""", unsafe_allow_html=True)

        except Exception as e:
            err = str(e)
            if "API_KEY" in err.upper() or "invalid" in err.lower():
                st.error("❌ Invalid Gemini API key. Copy it again from aistudio.google.com")
            else:
                st.error(f"❌ Error: {err}")
