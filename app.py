import streamlit as st
import tempfile, os, re, io
from groq import Groq

# ── PDF ──────────────────────────────────────────────────────
try:
    import fitz
    PDF_OK = True
except ImportError:
    PDF_OK = False

# ── TTS ──────────────────────────────────────────────────────
try:
    import edge_tts
    import asyncio
    TTS_OK = True
    TTS_ENGINE = "edge"
except ImportError:
    try:
        from gtts import gTTS
        TTS_OK = True
        TTS_ENGINE = "gtts"
    except ImportError:
        TTS_OK = False
        TTS_ENGINE = None

# ── Image / Video ─────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFont
    import textwrap
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import cv2
    import numpy as np
    CV2_OK = True
except ImportError:
    CV2_OK = False

try:
    from pydub import AudioSegment
    PYDUB_OK = True
except ImportError:
    PYDUB_OK = False

# ── Page config ───────────────────────────────────────────────
st.set_page_config(page_title="NoteVision AI", page_icon="📚",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.stApp{background:#0f1117}
.main-title{font-size:2.2rem;font-weight:700;
  background:linear-gradient(135deg,#667eea,#764ba2);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{color:#8b8fa8;font-size:.95rem;margin-bottom:1rem}
.sec{color:#a78bfa;font-size:.78rem;font-weight:600;text-transform:uppercase;
     letter-spacing:.6px;border-bottom:1px solid #2a2d3e;padding-bottom:5px;margin-bottom:10px}
.success-box{background:#1e2a1e;border:1px solid #2a4a2a;border-radius:8px;
             padding:12px;color:#7dc47d;font-size:.9rem}
.info-box{background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;
          padding:10px;color:#b0b3cc;font-size:.85rem;line-height:1.6}
.urdu-box{direction:rtl;text-align:right;font-size:1.1rem;
          line-height:2;color:#c4c7e0;padding:10px;
          background:#1a1d2e;border-radius:8px;border:1px solid #2a2d3e}
div[data-testid="stButton"]>button{
  background:linear-gradient(135deg,#667eea,#764ba2)!important;
  color:#fff!important;border:none!important;border-radius:10px!important;
  font-weight:600!important;width:100%!important}
</style>
""", unsafe_allow_html=True)

# ── Voice definitions ─────────────────────────────────────────

ENGLISH_FEMALE = {
    "Aria — American 🇺🇸":     "en-US-AriaNeural",
    "Jenny — American 🇺🇸":    "en-US-JennyNeural",
    "Sonia — British 🇬🇧":     "en-GB-SoniaNeural",
    "Natasha — Australian 🇦🇺":"en-AU-NatashaNeural",
}
ENGLISH_MALE = {
    "Guy — American 🇺🇸":      "en-US-GuyNeural",
    "Eric — American 🇺🇸":     "en-US-EricNeural",
    "Ryan — British 🇬🇧":      "en-GB-RyanNeural",
    "William — Australian 🇦🇺":"en-AU-WilliamNeural",
}
URDU_FEMALE = {
    "Uzma — اردو خاتون 🇵🇰":   "ur-PK-UzmaNeural",
}
URDU_MALE = {
    "Asad — اردو مرد 🇵🇰":     "ur-PK-AsadNeural",
}

# ── Helpers ───────────────────────────────────────────────────

def get_key():
    try:    return st.secrets["GROQ_API_KEY"]
    except: return st.session_state.get("groq_key", "")

def extract_pdf(f) -> str:
    if not PDF_OK: return ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as t:
        t.write(f.read()); path = t.name
    doc = fitz.open(path)
    txt = "\n".join(p.get_text() for p in doc)
    doc.close(); os.unlink(path)
    return txt[:10000]

def generate_script(content, minutes, key, language="English"):
    client = Groq(api_key=key)
    words  = minutes * 130

    if language == "اردو":
        system_prompt = (
            f"آپ ایک پیشہ ور دستاویزی راوی ہیں۔ "
            f"ایک {minutes} منٹ کا اردو بیانیہ اسکرپٹ لکھیں — کم از کم {words} الفاظ۔ "
            "اسکرپٹ کو 8 سے 12 حصوں میں تقسیم کریں۔ "
            "ہر حصے کا عنوان '## ' سے شروع کریں۔ "
            "قدرتی، روانی اردو میں لکھیں جیسے زبانی بول رہے ہوں۔ "
            "کوئی بلٹ پوائنٹ نہیں۔ صرف بہتا ہوا نثر۔ "
            "مکمل اردو رسم الخط استعمال کریں۔"
        )
        user_prompt = (
            f"اس موضوع پر {minutes} منٹ کا مکمل اردو بیانیہ اسکرپٹ لکھیں:\n\n{content[:7000]}"
        )
    else:
        system_prompt = (
            f"You are a professional documentary narrator. "
            f"Write a {minutes}-minute spoken narration script — exactly {words} words minimum. "
            "Divide into 8-12 sections. Start every section heading with '## ' on its own line. "
            "Each section must have at least 3-4 full paragraphs. "
            "Write naturally as if speaking aloud. No bullet points. Only flowing prose."
        )
        user_prompt = (
            f"Write a full {minutes}-minute narration script about:\n\n{content[:7000]}"
        )

    r = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=6000,
        messages=[
            {"role":"system","content": system_prompt},
            {"role":"user",  "content": user_prompt}
        ])
    return r.choices[0].message.content

def build_slides(script):
    parts  = re.split(r'^## ', script, flags=re.MULTILINE)
    slides = []
    for p in parts:
        if not p.strip(): continue
        lines = p.strip().split('\n')
        title = lines[0].strip()
        body  = ' '.join(lines[1:]).strip()
        slides.append({"title": title, "body": body})
    if not slides:
        chunks = [script[i:i+600] for i in range(0, len(script), 600)]
        slides = [{"title": f"Section {i+1}", "body": c} for i,c in enumerate(chunks)]
    return slides

# ── TTS ───────────────────────────────────────────────────────

async def _edge_save(text, voice, path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)

def generate_mp3_edge(script, voice_id) -> bytes:
    clean = re.sub(r'^##[^\n]*', '', script, flags=re.MULTILINE).strip()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        path = f.name
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_edge_save(clean, voice_id, path))
    loop.close()
    data = open(path, "rb").read()
    os.unlink(path)
    return data

def generate_mp3_gtts(script, lang="en") -> bytes:
    clean  = re.sub(r'^##[^\n]*', '', script, flags=re.MULTILINE).strip()
    chunks = [clean[i:i+4500] for i in range(0, len(clean), 4500)]
    tmp    = tempfile.mkdtemp()
    parts  = []
    for i, chunk in enumerate(chunks):
        tts = gTTS(text=chunk, lang=lang, slow=False)
        p   = os.path.join(tmp, f"p{i}.mp3"); tts.save(p); parts.append(p)
    merged = os.path.join(tmp, "merged.mp3")
    with open(merged, "wb") as out:
        for p in parts:
            with open(p,"rb") as f: out.write(f.read())
    data = open(merged,"rb").read()
    for p in parts:
        try: os.unlink(p)
        except: pass
    try: os.unlink(merged); os.rmdir(tmp)
    except: pass
    return data

def generate_mp3(script, voice_id="en-US-AriaNeural", lang="en") -> bytes:
    if TTS_ENGINE == "edge":
        return generate_mp3_edge(script, voice_id)
    else:
        return generate_mp3_gtts(script, lang)

def get_audio_duration(mp3_bytes) -> float:
    if PYDUB_OK:
        try:
            seg = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
            return len(seg)/1000.0
        except: pass
    return len(mp3_bytes)*8/(128*1000)

# ── Slide drawing ─────────────────────────────────────────────

def make_slide(slide, idx, total, language="English", W=1280, H=720):
    img  = Image.new("RGB",(W,H),"#0f1117")
    draw = ImageDraw.Draw(img)
    for i in range(H):
        r=int(15+10*(i/H)); g=int(17+8*(i/H)); b=int(23+20*(i/H))
        draw.line([(0,i),(W,i)],fill=(r,g,b))
    for r in range(160,0,-4):
        draw.ellipse([W-110-r,90-r,W-110+r,90+r],fill=(102,126,234))

    # Try fonts
    try:
        ft=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",44)
        fb=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",22)
        fs=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",15)
        fh=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",18)
    except:
        ft=fb=fs=fh=ImageFont.load_default()

    # Header
    draw.rectangle([0,0,W,70],fill=(26,29,46))
    draw.rectangle([0,68,W,70],fill=(102,126,234))
    header_txt = "📚 NoteVision AI — اردو" if language=="اردو" else "📚 NoteVision AI"
    draw.text((30,24), header_txt, fill=(167,139,250), font=fh)
    draw.text((W-120,24), f"{idx+1} / {total}", fill=(139,143,168), font=fs)

    # Progress bar
    draw.rectangle([0,H-12,W,H],fill=(26,29,46))
    pw=int(W*(idx+1)/total)
    draw.rectangle([0,H-12,pw,H],fill=(102,126,234))

    # Section badge
    sec_txt = f"حصہ {idx+1}" if language=="اردو" else f"SECTION {idx+1}"
    draw.rectangle([60,100,220,138],fill=(45,53,101))
    draw.text((70,108), sec_txt, fill=(167,139,250), font=fs)

    # Title
    title=slide["title"][:50]+("..." if len(slide["title"])>50 else "")
    draw.text((60,155), title, fill=(255,255,255), font=ft)
    try: tw=draw.textlength(title,font=ft)
    except: tw=min(len(title)*26,W-120)
    draw.rectangle([60,210,60+min(int(tw),W-120),213],fill=(102,126,234))

    # Body
    body=slide["body"][:500]+("..." if len(slide["body"])>500 else "")
    wrapped=textwrap.wrap(body, width=68)
    y=235
    for line in wrapped:
        if y>H-55: break
        draw.text((60,y), line, fill=(176,179,204), font=fb)
        y+=34

    # Footer
    draw.rectangle([0,H-44,W,H-13],fill=(15,17,23))
    footer = "NoteVision AI  •  Groq & Llama 3  •  اردو ایڈیشن" if language=="اردو" \
             else "Generated by NoteVision AI  •  Powered by Groq & Llama 3"
    draw.text((60,H-38), footer, fill=(74,78,106), font=fs)
    return img

# ── Video ─────────────────────────────────────────────────────

def generate_video(slides, mp3_bytes, target_mins, language, prog_cb=None) -> bytes:
    if not CV2_OK or not PIL_OK: return None
    W,H,FPS = 1280,720,24
    tmp      = tempfile.mkdtemp()
    dur      = max(get_audio_duration(mp3_bytes), target_mins*60)
    sps      = dur/len(slides)
    if prog_cb: prog_cb(f"🎬 Rendering {len(slides)} slides × {sps:.1f}s…")
    silent   = os.path.join(tmp,"silent.mp4")
    writer   = cv2.VideoWriter(silent, cv2.VideoWriter_fourcc(*"mp4v"), FPS,(W,H))
    for i,slide in enumerate(slides):
        if prog_cb: prog_cb(f"🎨 Slide {i+1}/{len(slides)}…")
        frame=cv2.cvtColor(np.array(make_slide(slide,i,len(slides),language,W,H)),cv2.COLOR_RGB2BGR)
        for _ in range(int(FPS*sps)): writer.write(frame)
    writer.release()
    ap=os.path.join(tmp,"audio.mp3")
    with open(ap,"wb") as f: f.write(mp3_bytes)
    final=os.path.join(tmp,"final.mp4")
    if prog_cb: prog_cb("🔊 Merging audio into video…")
    ret=os.system(f'ffmpeg -y -i "{silent}" -i "{ap}" -c:v copy -c:a aac -shortest "{final}" -loglevel error')
    if ret==0 and os.path.exists(final) and os.path.getsize(final)>10000:
        data=open(final,"rb").read()
    else:
        try:
            from moviepy.editor import VideoFileClip,AudioFileClip,concatenate_audioclips
            vc=VideoFileClip(silent); ac=AudioFileClip(ap)
            if ac.duration<vc.duration:
                loops=int(vc.duration/ac.duration)+1
                ac=concatenate_audioclips([ac]*loops).subclip(0,vc.duration)
            else: ac=ac.subclip(0,vc.duration)
            vc.set_audio(ac).write_videofile(final,codec="libx264",audio_codec="aac",verbose=False,logger=None)
            data=open(final,"rb").read()
        except: data=open(silent,"rb").read()
    for fn in os.listdir(tmp):
        try: os.unlink(os.path.join(tmp,fn))
        except: pass
    try: os.rmdir(tmp)
    except: pass
    return data

# ── UI ────────────────────────────────────────────────────────

st.markdown('<h1 class="main-title">📚 NoteVision AI</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">AI-powered audio & video overview — English & اردو | Groq + Llama 3 (Free)</p>',
            unsafe_allow_html=True)

with st.sidebar:

    # API Key
    st.markdown('<div class="sec">🔑 Groq API Key</div>', unsafe_allow_html=True)
    key = get_key()
    if not key:
        key = st.text_input("Paste Groq API key", type="password", placeholder="gsk_…")
        if key: st.session_state["groq_key"] = key
        st.markdown("""<div class="info-box">🆓 Free at <b>console.groq.com</b><br>
        Sign up → API Keys → Create Key</div>""", unsafe_allow_html=True)
    else:
        st.success("✅ Groq API Key loaded")

    # ── LANGUAGE SELECTION ───────────────────────────────────
    st.markdown('<div class="sec">🌐 Output Language</div>', unsafe_allow_html=True)
    language = st.radio(
        "Language",
        ["🇬🇧 English", "🇵🇰 اردو"],
        horizontal=True,
        key="language"
    )
    lang_code = "اردو" if "اردو" in language else "English"

    if lang_code == "اردو":
        st.success("🇵🇰 اردو زبان منتخب کی گئی")
    else:
        st.success("🇬🇧 English language selected")

    # Source
    st.markdown('<div class="sec">📋 Source Content</div>', unsafe_allow_html=True)
    src = st.radio("Input", ["Text / Topic", "Upload PDF"], label_visibility="collapsed")
    text_in = pdf_txt = ""
    if src == "Text / Topic":
        placeholder = "مثال: 'پاکستان کی تاریخ' یا کوئی مضمون یہاں پیسٹ کریں..." \
                      if lang_code=="اردو" else \
                      "e.g. 'History of Pakistan'\nor paste any article…"
        text_in = st.text_area("Topic or paste article", height=150,
                               placeholder=placeholder)
    else:
        up = st.file_uploader("PDF", type=["pdf"])
        if up:
            with st.spinner("Reading PDF…"):
                pdf_txt = extract_pdf(up)
            if pdf_txt:
                st.success(f"✅ {len(pdf_txt)} characters extracted")
            else:
                st.error("Could not read PDF.")

    # Duration
    st.markdown('<div class="sec">⏱ Duration</div>', unsafe_allow_html=True)
    minutes = st.select_slider("Length", [5,8,10,12], value=5,
                               format_func=lambda x: f"{x} minutes")

    # ── VOICE SELECTION ──────────────────────────────────────
    st.markdown('<div class="sec">🎙 Voice Selection</div>', unsafe_allow_html=True)

    if lang_code == "اردو":
        gender = st.radio("Voice Gender / صنف", ["👩 خاتون (Female)", "👨 مرد (Male)"],
                          horizontal=True, key="voice_gender")
        voice_options = URDU_FEMALE if "خاتون" in gender else URDU_MALE
        st.info("🎙 Microsoft اردو Neural Voice — پاکستانی لہجہ")
        gtts_lang = "ur"
    else:
        gender = st.radio("Voice Gender", ["👩 Female", "👨 Male"],
                          horizontal=True, key="voice_gender")
        voice_options = ENGLISH_FEMALE if "Female" in gender else ENGLISH_MALE
        gtts_lang = "en"

    voice_name     = st.selectbox("Choose Voice", list(voice_options.keys()), key="voice_name")
    selected_voice = voice_options[voice_name]
    st.caption(f"🎤 `{selected_voice}`")

    if TTS_ENGINE == "gtts":
        st.warning("⚠️ edge-tts not installed. Install it for Urdu/male voice support.")

    # Video settings
    st.markdown('<div class="sec">🎬 Video Settings</div>', unsafe_allow_html=True)
    secs_slide = st.slider("Seconds per slide", 6, 20, 8)
    gen_btn    = st.button("✨ Generate Overview" if lang_code=="English" else "✨ جائزہ تیار کریں")

# ── Generation ────────────────────────────────────────────────
source = pdf_txt or text_in

if gen_btn:
    if not key:
        st.error("❌ Enter your Groq API key in the sidebar (free at console.groq.com)")
    elif not source.strip():
        st.error("❌ Paste content or upload a PDF first." if lang_code=="English"
                 else "❌ پہلے مواد پیسٹ کریں یا PDF اپ لوڈ کریں۔")
    else:
        prog   = st.progress(0, "Starting…")
        status = st.empty()
        try:
            # Script
            lang_label = "اردو" if lang_code=="اردو" else "English"
            prog.progress(8, f"🤖 Writing {minutes}-min script in {lang_label}…")
            script = generate_script(source, minutes, key, lang_code)
            slides = build_slides(script)
            wc     = len(script.split())
            prog.progress(30, f"✅ Script: {wc} words, {len(slides)} slides")
            status.success(f"📝 Script ready in {lang_label}: {wc} words, {len(slides)} sections")

            with st.expander("📝 View Full Script / مکمل اسکرپٹ دیکھیں", expanded=False):
                if lang_code == "اردو":
                    st.markdown(f'<div class="urdu-box">{script}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(script)

            # Audio
            prog.progress(35, f"🎙 Generating {lang_label} audio — {voice_name}…")
            status.info(f"🎙 Generating MP3 using **{voice_name}**… please wait (~30s)")
            mp3 = b""
            if TTS_OK:
                mp3 = generate_mp3(script, selected_voice, gtts_lang)
                dur = get_audio_duration(mp3)
                prog.progress(60, f"✅ Audio: {dur/60:.1f} min MP3 ready")
                status.success(f"🎙 Audio ready: {dur/60:.1f} min — {voice_name}")
            else:
                status.warning("TTS engine not available.")

            # Video
            vid_data = None
            if CV2_OK and PIL_OK and mp3:
                def upd(msg): status.info(msg)
                prog.progress(63, "🎬 Building MP4 video…")
                vid_data = generate_video(slides, mp3, minutes, lang_code, upd)
                if vid_data:
                    sz = len(vid_data)/1024/1024
                    prog.progress(95, f"✅ Video: {sz:.1f} MB MP4 ready")
                    status.success(f"🎬 Video ready: {sz:.1f} MB")

            prog.progress(100, "🎉 Done!")
            status.empty()

            # Results
            c1, c2 = st.columns(2)
            fname_prefix = "NoteVision-Urdu" if lang_code=="اردو" else "NoteVision-English"

            with c1:
                st.markdown("### 🎙 Audio / آڈیو")
                if mp3:
                    dur = get_audio_duration(mp3)
                    st.caption(f"🎤 {voice_name} • {dur/60:.1f} min • MP3 • {lang_label}")
                    st.audio(mp3, format="audio/mp3")
                    st.download_button("⬇ Download MP3", mp3,
                        f"{fname_prefix}-audio.mp3", "audio/mpeg",
                        use_container_width=True)
                else:
                    st.warning("Audio not available.")

            with c2:
                st.markdown("### 🎬 Video / ویڈیو")
                if vid_data:
                    dur = get_audio_duration(mp3) if mp3 else minutes*60
                    st.caption(f"🎤 {voice_name} • {dur/60:.1f} min • MP4 • {lang_label}")
                    st.video(vid_data)
                    st.download_button("⬇ Download MP4", vid_data,
                        f"{fname_prefix}-video.mp4", "video/mp4",
                        use_container_width=True)
                else:
                    st.warning("Video not generated.")

            dur = get_audio_duration(mp3) if mp3 else 0
            st.markdown(f"""<div class="success-box">
            ✅ <b>Complete!</b> {lang_label} MP3 & MP4 generated using <b>{voice_name}</b>.<br>
            Duration: {dur/60:.1f} minutes. Ready to play and download!
            </div>""", unsafe_allow_html=True)

        except Exception as e:
            err = str(e)
            prog.progress(0, "❌ Failed")
            if "401" in err or "invalid_api_key" in err.lower():
                st.error("❌ Invalid Groq key. Copy again from console.groq.com")
            elif "429" in err:
                st.error("❌ Rate limit. Wait 1 minute and try again.")
            else:
                st.error(f"❌ Error: {err}")
