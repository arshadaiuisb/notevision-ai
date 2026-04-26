import streamlit as st
import tempfile, os, re, struct, wave, io
from groq import Groq

# ── PDF ──────────────────────────────────────────────────────
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

# ── Image / Video ─────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFont
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
    from moviepy.editor import (ImageClip, AudioFileClip,
                                concatenate_videoclips,
                                concatenate_audioclips)
    MOVIEPY_OK = True
except Exception:
    MOVIEPY_OK = False

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
     letter-spacing:.6px;border-bottom:1px solid #2a2d3e;
     padding-bottom:5px;margin-bottom:10px}
.success-box{background:#1e2a1e;border:1px solid #2a4a2a;
             border-radius:8px;padding:12px;color:#7dc47d;font-size:.9rem}
.info-box{background:#1a1d2e;border:1px solid #2a2d3e;
          border-radius:8px;padding:12px;color:#b0b3cc;
          font-size:.88rem;line-height:1.6}
div[data-testid="stButton"]>button{
  background:linear-gradient(135deg,#667eea,#764ba2)!important;
  color:#fff!important;border:none!important;border-radius:10px!important;
  font-weight:600!important;width:100%!important}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def get_api_key():
    try:    return st.secrets["GROQ_API_KEY"]
    except: return st.session_state.get("groq_key","")


def extract_pdf(f) -> str:
    if not PDF_OK: return ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(f.read()); path = tmp.name
    doc = fitz.open(path)
    txt = "\n".join(p.get_text() for p in doc)
    doc.close(); os.unlink(path)
    return txt[:8000]


def generate_script(content:str, minutes:int, api_key:str) -> str:
    client = Groq(api_key=api_key)
    words  = minutes * 140
    resp   = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=4000,
        messages=[
            {"role":"system","content":(
                f"You are an expert narrator creating a {minutes}-minute "
                f"audio/video overview script. Write approximately {words} words. "
                "Start each major section with '## Section Title' on its own line. "
                "Write in flowing conversational paragraphs. Be engaging and comprehensive.")},
            {"role":"user","content":
                f"Create a {minutes}-minute detailed overview about:\n\n{content[:6000]}"}
        ])
    return resp.choices[0].message.content


def build_slides(script:str):
    parts = re.split(r'^## ', script, flags=re.MULTILINE)
    slides=[]
    for p in parts:
        if not p.strip(): continue
        lines = p.strip().split('\n')
        title = lines[0].strip()
        body  = ' '.join(lines[1:]).strip()[:350]
        slides.append({"title":title,"body":body})
    if not slides:
        chunks=[script[i:i+400] for i in range(0,len(script),400)]
        slides=[{"title":f"Part {i+1}","body":c} for i,c in enumerate(chunks)]
    return slides


def generate_mp3(script:str) -> bytes:
    clean = re.sub(r'^##[^\n]*','',script,flags=re.MULTILINE).strip()
    tts   = gTTS(text=clean, lang='en', slow=False)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tts.save(f.name); path=f.name
    data=open(path,"rb").read(); os.unlink(path)
    return data


def make_slide_image(slide, idx, total, W=1280, H=720) -> Image.Image:
    img  = Image.new("RGB",(W,H),"#0f1117")
    draw = ImageDraw.Draw(img)
    try:
        ft=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",44)
        fb=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",22)
        fs=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",14)
    except:
        ft=fb=fs=ImageFont.load_default()

    # Accent blob
    for r in range(160,0,-4):
        alpha=int(40*(1-r/160))
        draw.ellipse([W-110-r,90-r,W-110+r,90+r],fill=(102,126,234))

    draw.text((48,18),"NoteVision AI",fill="#a78bfa",font=fs)
    draw.text((W-90,18),f"{idx+1} / {total}",fill="#4a4e6a",font=fs)
    draw.rectangle([48,52,W-48,56],fill="#2a2d3e")
    pw=int((W-96)*(idx+1)/total)
    draw.rectangle([48,52,48+pw,56],fill="#667eea")

    title=slide["title"][:55]+("..." if len(slide["title"])>55 else "")
    draw.text((80,175),title,fill="#ffffff",font=ft)
    try: tw=draw.textlength(title,font=ft)
    except: tw=400
    draw.rectangle([80,228,80+min(tw,480),231],fill="#667eea")

    words=slide["body"].split(); line=""; y=268
    for w in words:
        test=(line+" "+w).strip()
        try: wide=draw.textlength(test,font=fb)
        except: wide=len(test)*12
        if wide>W-180 and line:
            draw.text((80,y),line,fill="#b0b3cc",font=fb)
            line=w; y+=34
            if y>H-65: break
        else: line=test
    if line and y<=H-65:
        draw.text((80,y),line,fill="#b0b3cc",font=fb)

    draw.rectangle([0,H-38,W,H-37],fill="#2a2d3e")
    draw.text((80,H-24),"Generated by NoteVision AI — Powered by Groq & Llama 3",
              fill="#4a4e6a",font=fs)
    return img


# ── Video builder — tries moviepy first, falls back to cv2, then GIF ──

def generate_mp4_moviepy(slides, mp3_bytes:bytes, secs:int) -> bytes:
    tmp=tempfile.mkdtemp(); clips=[]
    for i,slide in enumerate(slides):
        img=make_slide_image(slide,i,len(slides))
        p=os.path.join(tmp,f"s{i}.png"); img.save(p)
        clips.append(ImageClip(p).set_duration(secs))
    video=concatenate_videoclips(clips,method="compose")
    ap=os.path.join(tmp,"audio.mp3")
    with open(ap,"wb") as f: f.write(mp3_bytes)
    ac=AudioFileClip(ap)
    vd=video.duration
    if ac.duration<vd:
        loops=int(vd/ac.duration)+1
        ac=concatenate_audioclips([ac]*loops).subclip(0,vd)
    else:
        ac=ac.subclip(0,vd)
    out=os.path.join(tmp,"out.mp4")
    video.set_audio(ac).write_videofile(
        out,fps=24,codec="libx264",
        audio_codec="aac",verbose=False,logger=None)
    data=open(out,"rb").read()
    for fn in os.listdir(tmp):
        try: os.unlink(os.path.join(tmp,fn))
        except: pass
    try: os.rmdir(tmp)
    except: pass
    return data


def generate_mp4_cv2(slides, mp3_bytes:bytes, secs:int) -> bytes:
    """Fallback: use OpenCV to write video frames."""
    tmp=tempfile.mkdtemp()
    out=os.path.join(tmp,"out.mp4")
    fps=24
    W,H=1280,720
    fourcc=cv2.VideoWriter_fourcc(*"mp4v")
    writer=cv2.VideoWriter(out,fourcc,fps,(W,H))
    import numpy as np
    for i,slide in enumerate(slides):
        img=make_slide_image(slide,i,len(slides),W,H)
        frame=cv2.cvtColor(np.array(img),cv2.COLOR_RGB2BGR)
        for _ in range(fps*secs):
            writer.write(frame)
    writer.release()
    data=open(out,"rb").read()
    try: os.unlink(out); os.rmdir(tmp)
    except: pass
    return data


def generate_gif(slides, secs:int) -> bytes:
    """Last resort: animated GIF slideshow."""
    frames=[]
    for i,slide in enumerate(slides):
        img=make_slide_image(slide,i,len(slides),640,360)
        frames.append(img)
    buf=io.BytesIO()
    frames[0].save(buf,format="GIF",save_all=True,
                   append_images=frames[1:],
                   duration=secs*1000,loop=0)
    return buf.getvalue()


def build_video(slides, mp3_bytes:bytes, secs:int, prog_cb=None):
    """Try moviepy → cv2 → GIF, return (bytes, ext, mime)."""
    if MOVIEPY_OK:
        try:
            if prog_cb: prog_cb("🎬 Building MP4 with moviepy…")
            data=generate_mp4_moviepy(slides,mp3_bytes,secs)
            return data,"mp4","video/mp4"
        except Exception as e:
            st.warning(f"moviepy failed ({e}), trying cv2…")

    if CV2_OK and PIL_OK:
        try:
            if prog_cb: prog_cb("🎬 Building MP4 with OpenCV…")
            data=generate_mp4_cv2(slides,mp3_bytes,secs)
            return data,"mp4","video/mp4"
        except Exception as e:
            st.warning(f"cv2 failed ({e}), generating GIF…")

    if PIL_OK:
        if prog_cb: prog_cb("🎬 Building animated GIF slideshow…")
        data=generate_gif(slides,secs)
        return data,"gif","image/gif"

    return None,None,None


# ─────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────

st.markdown('<h1 class="main-title">📚 NoteVision AI</h1>',unsafe_allow_html=True)
st.markdown('<p class="subtitle">AI-powered audio & video overview — Groq + Llama 3 (Free)</p>',
            unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="sec">🔑 Groq API Key (Free)</div>',unsafe_allow_html=True)
    api_key=get_api_key()
    if not api_key:
        api_key=st.text_input("Paste Groq API key",type="password",placeholder="gsk_...")
        if api_key: st.session_state["groq_key"]=api_key
        st.markdown("""<div class="info-box">
        🆓 Free key at:<br><b>console.groq.com</b><br><br>
        1. Sign up with Google<br>
        2. API Keys → Create Key<br>
        3. Copy key starting with gsk_
        </div>""",unsafe_allow_html=True)
    else:
        st.success("✅ Groq API Key loaded")

    st.markdown('<div class="sec">📋 Source</div>',unsafe_allow_html=True)
    src=st.radio("Input",["Text / Topic","Upload PDF"],label_visibility="collapsed")
    text_in=pdf_txt=""
    if src=="Text / Topic":
        text_in=st.text_area("Content or topic",height=160,
                             placeholder="e.g. 'History of Pakistan'\nor paste a full article…")
    else:
        up=st.file_uploader("Upload PDF",type=["pdf"])
        if up:
            with st.spinner("Reading PDF…"):
                pdf_txt=extract_pdf(up)
            st.success(f"✅ {len(pdf_txt)} characters") if pdf_txt else st.error("Could not read PDF")

    st.markdown('<div class="sec">⏱ Settings</div>',unsafe_allow_html=True)
    minutes   =st.select_slider("Length",[5,8,10,12],value=5,
                                format_func=lambda x:f"{x} minutes")
    secs_slide=st.slider("Seconds per slide",6,20,8)
    gen_btn   =st.button("✨ Generate Overview")

# ── Generation ────────────────────────────────────────────────
source=pdf_txt or text_in

if gen_btn:
    if not api_key:
        st.error("❌ Please enter your Groq API key. Get one free at console.groq.com")
    elif not source.strip():
        st.error("❌ Please paste content or upload a PDF first.")
    else:
        prog=st.progress(0,"Starting…")
        try:
            # 1 Script
            prog.progress(10,"🤖 Llama 3 is writing your script…")
            script=generate_script(source,minutes,api_key)
            slides=build_slides(script)
            prog.progress(35,f"✅ Script ready — {len(script.split())} words, {len(slides)} slides")

            with st.expander("📝 View Generated Script",expanded=False):
                st.markdown(script)

            # 2 Audio
            prog.progress(40,"🎙 Generating MP3…")
            mp3=b""
            if TTS_OK:
                mp3=generate_mp3(script)
                prog.progress(60,"✅ MP3 ready!")
            else:
                st.warning("gTTS not available — audio skipped.")

            # 3 Video
            status_holder=st.empty()
            def update_status(msg): status_holder.info(msg)

            prog.progress(63,"🎬 Building video…")
            vid_data,vid_ext,vid_mime=build_video(slides,mp3,secs_slide,update_status)
            status_holder.empty()

            # 4 Show results
            prog.progress(95,"✅ Almost done…")
            c1,c2=st.columns(2)

            with c1:
                st.markdown("### 🎙 Audio Overview")
                if mp3:
                    st.audio(mp3,format="audio/mp3")
                    st.download_button("⬇ Download MP3",mp3,
                                       "NoteVision-overview.mp3","audio/mpeg",
                                       use_container_width=True)
                else:
                    st.warning("Audio not available.")

            with c2:
                st.markdown("### 🎬 Video Overview")
                if vid_data:
                    if vid_ext=="mp4":
                        st.video(vid_data)
                        st.download_button("⬇ Download MP4",vid_data,
                                           "NoteVision-overview.mp4",vid_mime,
                                           use_container_width=True)
                    elif vid_ext=="gif":
                        st.image(vid_data,caption="Animated slideshow (GIF)")
                        st.download_button("⬇ Download GIF Slideshow",vid_data,
                                           "NoteVision-slides.gif","image/gif",
                                           use_container_width=True)
                        st.info("💡 GIF generated (moviepy unavailable on this server). "
                                "Download & combine with MP3 using any video editor.")
                else:
                    st.error("Video could not be generated. "
                             "Try installing moviepy or opencv-python.")

            prog.progress(100,"🎉 Done!")
            st.markdown("""<div class="success-box">
            ✅ <b>Generation complete!</b><br>
            Your <b>MP3</b> audio and <b>MP4/GIF</b> video are ready!
            </div>""",unsafe_allow_html=True)

        except Exception as e:
            err=str(e)
            if "401" in err or "invalid_api_key" in err.lower():
                st.error("❌ Invalid Groq API key. Copy again from console.groq.com")
            elif "429" in err or "rate" in err.lower():
                st.error("❌ Rate limit. Wait 1 minute and try again.")
            else:
                st.error(f"❌ Error: {err}")
