import streamlit as st
import anthropic
import tempfile
import os
import re
from pathlib import Path

# ── PDF support ──────────────────────────────────────────────
try:
    import fitz  # PyMuPDF
    PDF_OK = True
except ImportError:
    PDF_OK = False

# ── TTS / Audio ──────────────────────────────────────────────
try:
    from gtts import gTTS
    TTS_OK = True
except ImportError:
    TTS_OK = False

# ── Video ────────────────────────────────────────────────────
try:
    from moviepy.editor import (ImageClip, AudioFileClip,
                                concatenate_videoclips, ColorClip)
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

# ── Custom CSS ───────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0f1117; }
    .main-title {
        font-size: 2.2rem; font-weight: 700;
        background: linear-gradient(135deg, #667eea, #764ba2);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .subtitle { color: #8b8fa8; font-size: 0.95rem; margin-bottom: 1.5rem; }
    .section-header {
        color: #a78bfa; font-size: 0.8rem; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.6px;
        border-bottom: 1px solid #2a2d3e; padding-bottom: 6px;
        margin-bottom: 12px;
    }
    .success-box {
        background: #1e2a1e; border: 1px solid #2a4a2a;
        border-radius: 8px; padding: 12px; color: #7dc47d; font-size: 0.9rem;
    }
    .info-box {
        background: #1a1d2e; border: 1px solid #2a2d3e;
        border-radius: 8px; padding: 12px; color: #b0b3cc; font-size: 0.9rem;
    }
    div[data-testid="stButton"] button {
        background: linear-gradient(135deg, #667eea, #764ba2);
        color: white; border: none; border-radius: 10px;
        padding: 0.6rem 1.2rem; font-weight: 600; width: 100%;
    }
    div[data-testid="stButton"] button:hover { opacity: 0.9; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────

def get_api_key():
    """Get API key from secrets or session state."""
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return st.session_state.get("api_key", "")


def extract_pdf_text(uploaded_file) -> str:
    if not PDF_OK:
        return ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
        f.write(uploaded_file.read())
        tmp_path = f.name
    doc = fitz.open(tmp_path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    os.unlink(tmp_path)
    return text[:8000]


def generate_script(content: str, minutes: int, api_key: str) -> str:
    words = minutes * 140
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=f"""You are an expert narrator creating a {minutes}-minute audio/video overview script.
Write approximately {words} words. Start each major section with "## Section Title" on its own line.
Write in flowing conversational paragraphs. Be engaging, informative, and comprehensive.""",
        messages=[{
            "role": "user",
            "content": f"Create a {minutes}-minute detailed overview about:\n\n{content[:6000]}"
        }]
    )
    return msg.content[0].text


def build_slides(script: str):
    parts = re.split(r'^## ', script, flags=re.MULTILINE)
    slides = []
    for p in parts:
        if not p.strip():
            continue
        lines = p.strip().split('\n')
        title = lines[0].strip()
        body = ' '.join(lines[1:]).strip()[:350]
        slides.append({"title": title, "body": body})
    if not slides:
        chunks = [script[i:i+400] for i in range(0, len(script), 400)]
        slides = [{"title": f"Part {i+1}", "body": c} for i, c in enumerate(chunks)]
    return slides


def generate_audio_mp3(script: str) -> bytes:
    """Generate MP3 audio using gTTS (real MP3, no conversion needed)."""
    clean = re.sub(r'^##[^\n]*', '', script, flags=re.MULTILINE).strip()
    tts = gTTS(text=clean, lang='en', slow=False)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tts.save(f.name)
        tmp_path = f.name
    with open(tmp_path, "rb") as f:
        audio_bytes = f.read()
    os.unlink(tmp_path)
    return audio_bytes


def make_slide_image(slide: dict, idx: int, total: int,
                     width=1280, height=720) -> Image.Image:
    img = Image.new("RGB", (width, height), "#0f1117")
    draw = ImageDraw.Draw(img)

    # Try to load a font, fall back to default
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
        font_body  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except Exception:
        font_title = ImageFont.load_default()
        font_body  = font_title
        font_small = font_title

    # Background accent circle
    for r in range(180, 0, -2):
        alpha = int(255 * (1 - r / 180) * 0.15)
        draw.ellipse([width-100-r, 100-r, width-100+r, 100+r],
                     fill=(102, 126, 234, alpha))

    # Header
    draw.text((48, 20), "NoteVision AI", fill="#a78bfa55", font=font_small)
    draw.text((width-90, 20), f"{idx+1} / {total}", fill="#4a4e6a", font=font_small)

    # Progress bar
    draw.rectangle([48, 55, width-48, 58], fill="#2a2d3e")
    prog_w = int((width-96) * (idx+1) / total)
    draw.rectangle([48, 55, 48+prog_w, 58], fill="#667eea")

    # Title
    title = slide["title"][:55] + ("..." if len(slide["title"]) > 55 else "")
    draw.text((80, 180), title, fill="#ffffff", font=font_title)
    # Accent line
    tw = draw.textlength(title, font=font_title)
    draw.rectangle([80, 232, 80+min(tw, 480), 235], fill="#667eea")

    # Body text word-wrap
    words = slide["body"].split()
    line, y = "", 270
    for w in words:
        test = (line + " " + w).strip()
        if draw.textlength(test, font=font_body) > width-180 and line:
            draw.text((80, y), line, fill="#b0b3cc", font=font_body)
            line, y = w, y+36
            if y > height-70:
                break
        else:
            line = test
    if line and y <= height-70:
        draw.text((80, y), line, fill="#b0b3cc", font=font_body)

    # Footer
    draw.rectangle([0, height-40, width, height-39], fill="#2a2d3e")
    draw.text((80, height-26),
              "Generated by NoteVision AI — Powered by Claude",
              fill="#4a4e6a", font=font_small)
    return img


def generate_video_mp4(slides: list, audio_bytes: bytes,
                       secs_per_slide: int = 8) -> bytes:
    """Build real MP4 using moviepy."""
    clips = []
    tmp_dir = tempfile.mkdtemp()

    for i, slide in enumerate(slides):
        img = make_slide_image(slide, i, len(slides))
        img_path = os.path.join(tmp_dir, f"slide_{i}.png")
        img.save(img_path)
        clip = ImageClip(img_path).set_duration(secs_per_slide)
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")

    # Save audio
    audio_path = os.path.join(tmp_dir, "narration.mp3")
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    audio_clip = AudioFileClip(audio_path)
    # Loop or trim audio to match video duration
    vid_dur = video.duration
    if audio_clip.duration < vid_dur:
        loops = int(vid_dur / audio_clip.duration) + 1
        from moviepy.editor import concatenate_audioclips
        audio_clip = concatenate_audioclips([audio_clip] * loops).subclip(0, vid_dur)
    else:
        audio_clip = audio_clip.subclip(0, vid_dur)

    final = video.set_audio(audio_clip)
    out_path = os.path.join(tmp_dir, "output.mp4")
    final.write_videofile(out_path, fps=24, codec="libx264",
                          audio_codec="aac", verbose=False, logger=None)

    with open(out_path, "rb") as f:
        mp4_bytes = f.read()

    # Cleanup
    for fn in os.listdir(tmp_dir):
        try: os.unlink(os.path.join(tmp_dir, fn))
        except: pass
    try: os.rmdir(tmp_dir)
    except: pass

    return mp4_bytes


# ── UI ───────────────────────────────────────────────────────

st.markdown('<h1 class="main-title">📚 NoteVision AI</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">AI-powered audio & video overview generator — Powered by Claude</p>',
            unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown('<div class="section-header">⚙️ Settings</div>', unsafe_allow_html=True)

    # API Key input if not in secrets
    api_key = get_api_key()
    if not api_key:
        st.markdown('<div class="section-header">🔑 API Key</div>', unsafe_allow_html=True)
        api_key = st.text_input("Anthropic API Key", type="password",
                                placeholder="sk-ant-...")
        if api_key:
            st.session_state["api_key"] = api_key

    st.markdown('<div class="section-header">📋 Source</div>', unsafe_allow_html=True)
    source_type = st.radio("Input type", ["Text / Topic", "Upload PDF"], label_visibility="collapsed")

    text_input = ""
    pdf_text = ""

    if source_type == "Text / Topic":
        text_input = st.text_area("Paste content or enter a topic",
                                  height=180,
                                  placeholder="e.g. 'The history of the Mughal Empire'\nor paste a full article...")
    else:
        uploaded = st.file_uploader("Upload PDF", type=["pdf"])
        if uploaded:
            with st.spinner("Reading PDF..."):
                pdf_text = extract_pdf_text(uploaded)
            if pdf_text:
                st.success(f"✅ PDF loaded — {len(pdf_text)} characters extracted")
            else:
                st.error("Could not extract text. Try a different PDF.")

    st.markdown('<div class="section-header">⏱ Length</div>', unsafe_allow_html=True)
    minutes = st.select_slider("Overview length",
                               options=[5, 8, 10, 12],
                               value=5,
                               format_func=lambda x: f"{x} minutes")

    secs_per_slide = st.slider("Seconds per slide (video)", 6, 20, 8)

    generate_btn = st.button("✨ Generate Overview", use_container_width=True)

# ── Main content area ────────────────────────────────────────
source = pdf_text or text_input

if generate_btn:
    if not api_key:
        st.error("Please enter your Anthropic API key in the sidebar.")
    elif not source.strip():
        st.error("Please paste some content or upload a PDF first.")
    else:
        # Progress
        progress = st.progress(0, text="Starting generation...")
        col1, col2 = st.columns(2)

        try:
            # Step 1: Script
            progress.progress(10, text="🤖 Claude is writing your script...")
            script = generate_script(source, minutes, api_key)
            slides = build_slides(script)
            progress.progress(35, text=f"✅ Script ready — {len(script.split())} words, {len(slides)} slides")

            # Show script
            with st.expander("📝 View Generated Script", expanded=False):
                st.markdown(script)

            # Step 2: Audio
            progress.progress(40, text="🎙 Generating MP3 audio narration...")
            if TTS_OK:
                audio_bytes = generate_audio_mp3(script)
                progress.progress(65, text="✅ Audio ready!")
                with col1:
                    st.markdown("### 🎙 Audio Overview")
                    st.audio(audio_bytes, format="audio/mp3")
                    st.download_button(
                        label="⬇ Download MP3",
                        data=audio_bytes,
                        file_name="NoteVision-overview.mp3",
                        mime="audio/mpeg",
                        use_container_width=True
                    )
            else:
                audio_bytes = b""
                st.warning("gTTS not available — audio skipped.")

            # Step 3: Video
            progress.progress(68, text="🎬 Building MP4 video slideshow... (this takes a moment)")
            if VIDEO_OK and audio_bytes:
                video_bytes = generate_video_mp4(slides, audio_bytes, secs_per_slide)
                progress.progress(95, text="✅ Video ready!")
                with col2:
                    st.markdown("### 🎬 Video Overview")
                    st.video(video_bytes)
                    st.download_button(
                        label="⬇ Download MP4",
                        data=video_bytes,
                        file_name="NoteVision-overview.mp4",
                        mime="video/mp4",
                        use_container_width=True
                    )
            else:
                st.warning("moviepy/PIL not available — video skipped. Install requirements.")

            progress.progress(100, text="🎉 All done! Play or download your overview above.")

            st.markdown("""
            <div class="success-box">
            ✅ <strong>Generation complete!</strong><br>
            Your MP3 audio and MP4 video are ready to play and download.
            Files are real MP3 and MP4 — no conversion needed!
            </div>
            """, unsafe_allow_html=True)

        except anthropic.AuthenticationError:
            st.error("❌ Invalid API key. Check your Anthropic API key and try again.")
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            st.info("Make sure all requirements are installed and your API key is valid.")
