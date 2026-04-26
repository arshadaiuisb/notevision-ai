import streamlit as st
import tempfile, os, re, io, math, textwrap
from groq import Groq

try:
    import fitz
    PDF_OK = True
except ImportError:
    PDF_OK = False

try:
    from gtts import gTTS
    TTS_OK = True
except ImportError:
    TTS_OK = False

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import numpy as np
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False

try:
    from pydub import AudioSegment
    PYDUB_OK = True
except ImportError:
    PYDUB_OK = False

st.set_page_config(page_title="NoteVision AI", page_icon="📚",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.stApp{background:#0f1117}
.main-title{font-size:2rem;font-weight:700;
  background:linear-gradient(135deg,#667eea,#764ba2);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.subtitle{color:#8b8fa8;font-size:.9rem;margin-bottom:1rem}
.sec{color:#a78bfa;font-size:.75rem;font-weight:600;text-transform:uppercase;
     letter-spacing:.6px;border-bottom:1px solid #2a2d3e;padding-bottom:4px;margin-bottom:8px}
.success-box{background:#1e2a1e;border:1px solid #2a4a2a;border-radius:8px;
             padding:12px;color:#7dc47d;font-size:.9rem}
.info-box{background:#1a1d2e;border:1px solid #2a2d3e;border-radius:8px;
          padding:10px;color:#b0b3cc;font-size:.85rem;line-height:1.6}
div[data-testid="stButton"]>button{
  background:linear-gradient(135deg,#667eea,#764ba2)!important;
  color:#fff!important;border:none!important;border-radius:10px!important;
  font-weight:600!important;width:100%!important}
</style>
""", unsafe_allow_html=True)

# ── helpers ──────────────────────────────────────────────────

def get_key():
    try:    return st.secrets["GROQ_API_KEY"]
    except: return st.session_state.get("groq_key","")

def extract_pdf(f):
    if not PDF_OK: return ""
    with tempfile.NamedTemporaryFile(delete=False,suffix=".pdf") as t:
        t.write(f.read()); path=t.name
    doc=fitz.open(path)
    txt="\n".join(p.get_text() for p in doc)
    doc.close(); os.unlink(path)
    return txt[:10000]

def generate_script(content, minutes, key):
    client=Groq(api_key=key)
    words=minutes*130
    r=client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=6000,
        messages=[
            {"role":"system","content":(
                f"You are a professional documentary narrator. "
                f"Write a {minutes}-minute spoken narration script — exactly {words} words minimum. "
                "Divide into 8-12 sections. Start every section heading with '## ' on its own line. "
                "Each section must have at least 3-4 full paragraphs of narration text. "
                "Write naturally as if speaking aloud. No bullet points. No lists. Only flowing prose."
            )},
            {"role":"user","content":f"Write a full {minutes}-minute narration script about:\n\n{content[:7000]}"}
        ])
    return r.choices[0].message.content

def build_slides(script):
    parts=re.split(r'^## ',script,flags=re.MULTILINE)
    slides=[]
    for p in parts:
        if not p.strip(): continue
        lines=p.strip().split('\n')
        title=lines[0].strip()
        body=' '.join(lines[1:]).strip()
        slides.append({"title":title,"body":body})
    if not slides:
        chunks=[script[i:i+600] for i in range(0,len(script),600)]
        slides=[{"title":f"Section {i+1}","body":c} for i,c in enumerate(chunks)]
    return slides

def split_text_for_tts(script, max_chars=4500):
    """Split script into chunks safe for gTTS."""
    clean=re.sub(r'^##[^\n]*','',script,flags=re.MULTILINE).strip()
    sentences=re.split(r'(?<=[.!?])\s+',clean)
    chunks=[]; cur=""
    for s in sentences:
        if len(cur)+len(s)+1 <= max_chars:
            cur+=" "+s if cur else s
        else:
            if cur: chunks.append(cur.strip())
            cur=s
    if cur: chunks.append(cur.strip())
    return chunks if chunks else [clean[:max_chars]]

def generate_mp3_chunks(script):
    """Generate MP3 audio in chunks and merge."""
    chunks=split_text_for_tts(script)
    tmp=tempfile.mkdtemp()
    parts=[]
    for i,chunk in enumerate(chunks):
        tts=gTTS(text=chunk,lang='en',slow=False)
        p=os.path.join(tmp,f"part{i}.mp3")
        tts.save(p); parts.append(p)

    # Merge all parts
    merged_path=os.path.join(tmp,"merged.mp3")
    if PYDUB_OK and len(parts)>1:
        combined=AudioSegment.empty()
        for p in parts:
            combined+=AudioSegment.from_mp3(p)
        combined.export(merged_path,format="mp3")
    else:
        # Simple binary concat (works for most players)
        with open(merged_path,"wb") as out:
            for p in parts:
                with open(p,"rb") as f: out.write(f.read())

    data=open(merged_path,"rb").read()
    for p in parts:
        try: os.unlink(p)
        except: pass
    try: os.unlink(merged_path); os.rmdir(tmp)
    except: pass
    return data

def get_audio_duration_seconds(mp3_bytes):
    """Estimate audio duration from MP3 bytes."""
    if PYDUB_OK:
        try:
            seg=AudioSegment.from_file(io.BytesIO(mp3_bytes),format="mp3")
            return len(seg)/1000.0
        except: pass
    # Fallback: estimate ~128kbps
    return len(mp3_bytes)*8/(128*1000)

def make_slide_pil(slide, idx, total, W=1280, H=720):
    """Draw a slide using PIL — robust fallback fonts."""
    bg=(15,17,23)
    img=Image.new("RGB",(W,H),bg)
    draw=ImageDraw.Draw(img)

    # Gradient-like background rectangles
    for i in range(H):
        r=int(15+10*(i/H)); g=int(17+8*(i/H)); b=int(23+20*(i/H))
        draw.line([(0,i),(W,i)],fill=(r,g,b))

    # Decorative accent circle (top right)
    cx,cy=W-140,130
    for r in range(200,0,-1):
        alpha=int(60*(1-(r/200)))
        col=(102+alpha,126+alpha//2,234)
        draw.ellipse([cx-r,cy-r,cx+r,cy+r],outline=col)

    # Header bar
    draw.rectangle([0,0,W,70],fill=(26,29,46))
    draw.rectangle([0,68,W,70],fill=(102,126,234))

    # Logo text in header
    try:
        fh=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",20)
        ft=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",52)
        fb=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",24)
        fs=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",16)
    except:
        try:
            fh=ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",20)
            ft=ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",52)
            fb=ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",24)
            fs=ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",16)
        except:
            fh=ft=fb=fs=ImageFont.load_default()

    draw.text((30,24),"📚 NoteVision AI",fill=(167,139,250),font=fh)
    draw.text((W-120,24),f"Slide {idx+1} of {total}",fill=(139,143,168),font=fs)

    # Progress bar
    draw.rectangle([0,H-12,W,H],fill=(26,29,46))
    pw=int(W*(idx+1)/total)
    draw.rectangle([0,H-12,pw,H],fill=(102,126,234))
    pct=int((idx+1)/total*100)
    draw.text((W//2-20,H-11),f"{pct}%",fill=(167,139,250),font=fs)

    # Section number badge
    draw.rectangle([60,100,180,138],fill=(45,53,101))
    draw.text((70,108),f"SECTION {idx+1}",fill=(167,139,250),font=fs)

    # Title
    title=slide["title"]
    if len(title)>52: title=title[:49]+"..."
    draw.text((60,155),title,fill=(255,255,255),font=ft)

    # Underline accent
    try: tw=draw.textlength(title,font=ft)
    except: tw=min(len(title)*30,W-120)
    draw.rectangle([60,218,60+min(int(tw),W-120),222],fill=(102,126,234))

    # Body text — word wrap properly
    body=slide["body"]
    # show first ~500 chars
    if len(body)>520: body=body[:517]+"..."
    wrapped=textwrap.wrap(body,width=72)
    y=245
    for line in wrapped:
        if y>H-55: break
        draw.text((60,y),line,fill=(176,179,204),font=fb)
        y+=36

    # Footer
    draw.rectangle([0,H-44,W,H-13],fill=(15,17,23))
    draw.text((60,H-38),"Generated by NoteVision AI  •  Powered by Groq & Llama 3  •  Free Edition",
              fill=(74,78,106),font=fs)
    return img

def make_slide_numpy(slide, idx, total, W=1280, H=720):
    """Convert PIL slide to numpy BGR array for OpenCV."""
    img=make_slide_pil(slide,idx,total,W,H)
    arr=np.array(img)
    return cv2.cvtColor(arr,cv2.COLOR_RGB2BGR)

def generate_video(slides, mp3_bytes, target_minutes, prog_cb=None):
    """
    Build MP4 video where total duration matches audio duration.
    Each slide gets equal screen time.
    """
    if not CV2_OK or not PIL_OK:
        return None, None, None

    W,H=1280,720
    FPS=24
    tmp=tempfile.mkdtemp()

    # Get actual audio duration
    audio_dur=get_audio_duration_seconds(mp3_bytes)
    # Ensure minimum duration
    audio_dur=max(audio_dur, target_minutes*60)
    secs_per_slide=audio_dur/len(slides)

    if prog_cb: prog_cb(f"🎬 Rendering {len(slides)} slides × {secs_per_slide:.1f}s = {audio_dur/60:.1f} min video…")

    # Write silent video
    silent_path=os.path.join(tmp,"silent.mp4")
    fourcc=cv2.VideoWriter_fourcc(*"mp4v")
    writer=cv2.VideoWriter(silent_path,fourcc,FPS,(W,H))

    frames_per_slide=int(FPS*secs_per_slide)
    for i,slide in enumerate(slides):
        if prog_cb: prog_cb(f"🎨 Rendering slide {i+1}/{len(slides)}…")
        frame=make_slide_numpy(slide,i,len(slides),W,H)
        for _ in range(frames_per_slide):
            writer.write(frame)
    writer.release()

    # Save audio
    audio_path=os.path.join(tmp,"audio.mp3")
    with open(audio_path,"wb") as f: f.write(mp3_bytes)

    # Merge video + audio using ffmpeg
    final_path=os.path.join(tmp,"final.mp4")
    if prog_cb: prog_cb("🔊 Merging audio into video with ffmpeg…")

    ret=os.system(
        f'ffmpeg -y -i "{silent_path}" -i "{audio_path}" '
        f'-c:v copy -c:a aac -shortest "{final_path}" -loglevel error'
    )

    if ret==0 and os.path.exists(final_path) and os.path.getsize(final_path)>10000:
        data=open(final_path,"rb").read()
        for fn in os.listdir(tmp):
            try: os.unlink(os.path.join(tmp,fn))
            except: pass
        try: os.rmdir(tmp)
        except: pass
        return data,"mp4","video/mp4"

    # ffmpeg failed — try moviepy
    if prog_cb: prog_cb("🎬 Trying moviepy fallback…")
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips
        vc=VideoFileClip(silent_path)
        ac=AudioFileClip(audio_path)
        if ac.duration < vc.duration:
            loops=int(vc.duration/ac.duration)+1
            ac=concatenate_audioclips([ac]*loops).subclip(0,vc.duration)
        else:
            ac=ac.subclip(0,vc.duration)
        vc.set_audio(ac).write_videofile(
            final_path,codec="libx264",audio_codec="aac",
            verbose=False,logger=None)
        data=open(final_path,"rb").read()
        for fn in os.listdir(tmp):
            try: os.unlink(os.path.join(tmp,fn))
            except: pass
        try: os.rmdir(tmp)
        except: pass
        return data,"mp4","video/mp4"
    except Exception as e:
        st.warning(f"moviepy also failed: {e}")

    # Last resort — return silent video
    if os.path.exists(silent_path):
        data=open(silent_path,"rb").read()
        return data,"mp4","video/mp4"

    return None,None,None

# ── UI ────────────────────────────────────────────────────────

st.markdown('<h1 class="main-title">📚 NoteVision AI</h1>',unsafe_allow_html=True)
st.markdown('<p class="subtitle">AI narrated video & audio overviews — Groq + Llama 3 (Free)</p>',
            unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="sec">🔑 Groq API Key</div>',unsafe_allow_html=True)
    key=get_key()
    if not key:
        key=st.text_input("Groq API key",type="password",placeholder="gsk_…")
        if key: st.session_state["groq_key"]=key
        st.markdown("""<div class="info-box">
        🆓 Free at <b>console.groq.com</b><br><br>
        Sign up → API Keys → Create Key<br>
        Key starts with <b>gsk_</b>
        </div>""",unsafe_allow_html=True)
    else:
        st.success("✅ Groq key ready")

    st.markdown('<div class="sec">📋 Content</div>',unsafe_allow_html=True)
    src=st.radio("Input",["Text / Topic","Upload PDF"],label_visibility="collapsed")
    text_in=pdf_txt=""
    if src=="Text / Topic":
        text_in=st.text_area("Topic or paste article",height=160,
            placeholder="e.g. 'The history of the Mughal Empire'\nor paste any article…")
    else:
        up=st.file_uploader("PDF",type=["pdf"])
        if up:
            with st.spinner("Reading…"):
                pdf_txt=extract_pdf(up)
            (st.success(f"✅ {len(pdf_txt)} chars") if pdf_txt
             else st.error("Could not read PDF"))

    st.markdown('<div class="sec">⚙️ Settings</div>',unsafe_allow_html=True)
    minutes=st.select_slider("Duration",[5,8,10,12],value=5,
                             format_func=lambda x:f"{x} minutes")
    go=st.button("✨ Generate Overview")

source=pdf_txt or text_in

if go:
    if not key:
        st.error("❌ Enter your Groq API key in the sidebar (free at console.groq.com)")
    elif not source.strip():
        st.error("❌ Paste some content or upload a PDF first.")
    else:
        prog=st.progress(0,"Starting…")
        status=st.empty()
        try:
            # Script
            prog.progress(8,f"🤖 Writing {minutes}-minute script…")
            script=generate_script(source,minutes,key)
            slides=build_slides(script)
            wc=len(script.split())
            prog.progress(30,f"✅ Script: {wc} words, {len(slides)} slides")
            status.success(f"📝 Script ready: {wc} words across {len(slides)} sections")

            with st.expander("📝 View Full Script",expanded=False):
                st.markdown(script)

            # Audio
            prog.progress(35,"🎙 Generating MP3 narration…")
            status.info("🎙 Converting script to speech (this takes ~30s)…")
            mp3=b""
            if TTS_OK:
                mp3=generate_mp3_chunks(script)
                dur=get_audio_duration_seconds(mp3)
                prog.progress(60,f"✅ Audio: {dur/60:.1f} minutes MP3 ready")
                status.success(f"🎙 Audio ready: {dur/60:.1f} minutes")
            else:
                status.warning("gTTS not available")

            # Video
            vid_data=vid_ext=vid_mime=None
            if CV2_OK and PIL_OK and mp3:
                def upd(msg): status.info(msg)
                prog.progress(63,"🎬 Building video…")
                vid_data,vid_ext,vid_mime=generate_video(slides,mp3,minutes,upd)
                if vid_data:
                    vsize=len(vid_data)/1024/1024
                    prog.progress(94,f"✅ Video: {vsize:.1f} MB MP4 ready")
                    status.success(f"🎬 Video ready: {vsize:.1f} MB")
                else:
                    status.warning("Video generation failed — check server logs.")
            else:
                status.warning("OpenCV or PIL not available for video generation.")

            prog.progress(100,"🎉 All done!")
            status.empty()

            # Results
            c1,c2=st.columns(2)
            with c1:
                st.markdown("### 🎙 Audio Overview")
                if mp3:
                    dur=get_audio_duration_seconds(mp3)
                    st.caption(f"Duration: {dur/60:.1f} minutes • MP3 format")
                    st.audio(mp3,format="audio/mp3")
                    st.download_button("⬇ Download MP3",mp3,
                        "NoteVision-audio.mp3","audio/mpeg",
                        use_container_width=True)
                else:
                    st.warning("Audio not available.")

            with c2:
                st.markdown("### 🎬 Video Overview")
                if vid_data:
                    vd=get_audio_duration_seconds(mp3) if mp3 else minutes*60
                    st.caption(f"Duration: {vd/60:.1f} minutes • MP4 with narration audio")
                    st.video(vid_data)
                    st.download_button("⬇ Download MP4",vid_data,
                        "NoteVision-video.mp4","video/mp4",
                        use_container_width=True)
                else:
                    st.warning("Video not generated.")

            st.markdown("""<div class="success-box">
            ✅ <b>Complete!</b> Both MP3 audio and MP4 video (with narration) are ready.<br>
            The video duration matches your audio — minimum 5 minutes as requested.
            </div>""",unsafe_allow_html=True)

        except Exception as e:
            err=str(e)
            prog.progress(0,"❌ Failed")
            if "401" in err or "invalid_api_key" in err.lower():
                st.error("❌ Invalid Groq key. Copy again from console.groq.com")
            elif "429" in err:
                st.error("❌ Rate limit hit. Wait 1 minute and try again.")
            else:
                st.error(f"❌ Error: {err}")
