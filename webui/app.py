import gradio as gr
import subprocess
import os
import sys
import json
import psutil
import shutil
import datetime
import time
import urllib.parse
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn


import re
import library # Module for Library Logic
import subtitle_handler as subs # Module for Subtitles
import subtitle_editor as editor # Module for Editor Logic

# Path to the main script
MAIN_SCRIPT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main_improved.py")
WORKING_DIR = os.path.dirname(MAIN_SCRIPT_PATH)
sys.path.append(WORKING_DIR)

from i18n.i18n import I18nAuto
i18n = I18nAuto("ar_SA")

def tr(key):
    return AR_LABELS.get(key, i18n(key))

AR_LABELS = {
    "Start Processing": "بدء المعالجة",
    "Stop": "إيقاف",
    "Logs": "السجل",
    "Results": "النتائج",
    "Library": "المكتبة",
    "Create New": "إنشاء جديد",
    "Input Source": "مصدر الإدخال",
    "YouTube URL": "رابط يوتيوب",
    "Existing Project": "مشروع موجود",
    "Upload Video": "رفع فيديو",
    "Select Project": "اختر مشروعًا",
    "Segments": "عدد المقاطع",
    "Viral Mode": "وضع الفيروسية",
    "Themes": "المواضيع",
    "Min Duration (s)": "أقل مدة (ث)",
    "Max Duration (s)": "أقصى مدة (ث)",
    "AI Backend": "محرك الذكاء الاصطناعي",
    "AI Model": "نموذج الذكاء الاصطناعي",
    "Chunk Size": "حجم الجزء",
    "Whisper Model": "نموذج Whisper",
    "Workflow": "طريقة العمل",
    "Face Model": "نموذج الوجه",
    "Face Mode": "وضع الوجه",
    "Face Det. Interval": "فاصل كشف الوجه",
    "Subtitle Settings (alpha)": "إعدادات الترجمة (تجريبي)",
    "Quick Presets": "إعدادات سريعة",
    "Enable Subtitle Customization (Includes Preset)": "تفعيل تخصيص الترجمة (يشمل الإعداد المسبق)",
    "Animated Preview": "معاينة متحركة",
    "Advanced Settings": "إعدادات متقدمة",
    "Appearance": "المظهر",
    "Font Name": "اسم الخط",
    "Font Size (Base)": "حجم الخط (الأساسي)",
    "Highlight Size": "حجم التمييز",
    "Base Color": "اللون الأساسي",
    "Highlight Color": "لون التمييز",
    "Outline Color": "لون الإطار",
    "Shadow Color": "لون الظل",
    "Styling & Effects": "التنسيق والمؤثرات",
    "Outline Thickness": "سماكة الإطار",
    "Shadow Size": "حجم الظل",
    "Border Style": "نمط الإطار",
    "Bold": "عريض",
    "Italic": "مائل",
    "Uppercase": "أحرف كبيرة",
    "Underline": "تحته خط",
    "Strikeout": "مشطوب",
    "Positioning & Layout": "الموضع والتخطيط",
    "Alignment": "المحاذاة",
    "Gap Limit": "حد الفجوة",
    "Mode": "الوضع",
    "Words per Block": "كلمات بكل كتلة",
    "Results": "النتائج",
    "Task Progress": "تقدم المهام",
    "Error Report": "تقرير الأخطاء",
    "Loading...": "جارٍ التحميل...",
    "Completed": "اكتمل",
    "Running...": "جارٍ التشغيل...",
    "Process terminated.": "تم إيقاف العملية.",
    "Process stopped by user.": "أوقفها المستخدم.",
    "No process running.": "لا توجد عملية قيد التشغيل.",
    "Templates store subtitle styling plus face mode/model.": "تخزن القوالب تنسيق الترجمة مع وضع الوجه ونموذجه.",
    "No files found in final folder for subtitle burning.": "لا توجد ملفات في مجلد final لحرق الترجمة.",
}

def empty_progress_state(current=None):
    current = current or tr("Loading...")
    return {k: {"percent": 0, "message": tr("Loading...")} for k in ["download", "transcribe", "ai", "cut", "edit", "subtitles", "done"]} | {"overall": 0, "current": current}

# --- PRESETS DEFINITIONS ---
FACE_PRESETS = {
    "Default (Balanced)": {"thresh": 0.35, "two_face": 0.60, "conf": 0.40, "dead_zone": 150},
    "Stable (Focus Main)": {"thresh": 0.60, "two_face": 0.80, "conf": 0.60, "dead_zone": 200},
    "Sensitive (Catch All)": {"thresh": 0.10, "two_face": 0.40, "conf": 0.30, "dead_zone": 100},
    "High Precision": {"thresh": 0.40, "two_face": 0.65, "conf": 0.75, "dead_zone": 150},
}

EXPERIMENTAL_PRESETS = {
    "Default (Off)": {"focus": False, "mar": 0.03, "score": 1.5, "motion": False, "motion_th": 3.0, "motion_sens": 0.05, "decay": 2.0},
    "Active Speaker (Balanced)": {"focus": True, "mar": 0.03, "score": 1.5, "motion": True, "motion_th": 3.0, "motion_sens": 0.05, "decay": 2.0},
    "Active Speaker (Sensitive)": {"focus": True, "mar": 0.02, "score": 1.0, "motion": True, "motion_th": 2.0, "motion_sens": 0.10, "decay": 1.0},
    "Active Speaker (Stable)": {"focus": True, "mar": 0.05, "score": 2.5, "motion": False, "motion_th": 5.0, "motion_sens": 0.02, "decay": 3.0},
}
# ---------------------------

VIRALS_DIR = os.path.join(WORKING_DIR, "VIRALS")
MODELS_DIR = os.path.join(WORKING_DIR, "models")

# Ensure directories exist
os.makedirs(VIRALS_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# Global variables
current_process = None

PROGRESS_ORDER = ["download", "transcribe", "ai", "cut", "edit", "subtitles", "done"]

# Helpers
def convert_color_to_ass(hex_color, alpha="00"):
    try:
        if not hex_color:
            return f"&H{alpha}FFFFFF&"
        hex_clean = hex_color.lstrip('#').strip()
        if hex_clean.lower().startswith("rgb"):
            nums = re.findall(r"[\d\.]+", hex_clean)
            if len(nums) >= 3:
                r, g, b = [max(0, min(255, int(float(n)))) for n in nums[:3]]
                return f"&H{alpha}{b:02X}{g:02X}{r:02X}&".upper()
        if len(hex_clean) == 3:
            hex_clean = ''.join(c*2 for c in hex_clean)
        if len(hex_clean) == 6:
            r, g, b = hex_clean[0:2], hex_clean[2:4], hex_clean[4:6]
            return f"&H{alpha}{b}{g}{r}&".upper()
    except Exception:
        pass
    return f"&H{alpha}FFFFFF&"

def kill_process():
    global current_process
    if current_process:
        try:
            parent = psutil.Process(current_process.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
            current_process = None
            state = empty_progress_state(tr("Process stopped by user."))
            return (
                tr("Process terminated."),
                gr.update(value=tr("Start Processing"), interactive=True),
                gr.update(interactive=False),
                render_progress_html(state),
                render_tasks_html(state),
                render_error_html([tr("Process stopped by user.")]),
            )
        except Exception as e:
            return (tr("Error terminating process: {}").format(e), gr.update(), gr.update(), gr.update(), gr.update(), gr.update())
    state = empty_progress_state(tr("No process running."))
    return (tr("No process running."), gr.update(), gr.update(interactive=False), render_progress_html(state), render_tasks_html(state), render_error_html([]))

GEMINI_MODELS = [
    'gemini-3-pro-preview',
    'gemini-2.5-flash',
    'gemini-2.5-flash-preview-09-2025',
    'gemini-2.5-flash-lite',
    'gemini-2.5-flash-lite-preview-09-2025',
    'gemini-2.5-pro',
    'gemini-2.0-flash',
    'gemini-2.0-flash-lite'
]

G4F_MODELS = [
    'gpt-4o',
    'gpt-4o-mini',
    'gpt-4',
    'o1-mini',
    'o1',
    'deepseek-r1',
    'deepseek-v3',
    'llama-3.3-70b',
    'llama-3.1-405b',
    'claude-3.5-sonnet',
    'claude-3.7-sonnet',
    'gemini-2.0-flash',
    'qwen-2.5-72b'
]

def get_local_models():
    if not os.path.exists(MODELS_DIR): return []
    return [f for f in os.listdir(MODELS_DIR) if f.endswith(".gguf")]

TEMPLATES_FILE = os.path.join(WORKING_DIR, "settings_templates.json")


def load_templates():
    if not os.path.exists(TEMPLATES_FILE):
        return {}
    try:
        with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_template(name, payload):
    templates = load_templates()
    templates[name] = payload
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2, ensure_ascii=False)
    return templates


def template_choices():
    templates = load_templates()
    return sorted(templates.keys())


def render_progress_html(state):
    order = [
        ("download", "تحميل الفيديو"),
        ("transcribe", "تفريغ الصوت"),
        ("ai", "تحليل AI"),
        ("cut", "قص المقاطع"),
        ("edit", "معالجة الوجه"),
        ("subtitles", "الترجمة / الترجمة النهائية"),
        ("done", "تم"),
    ]
    bars = []
    for key, label in order:
        item = state.get(key, {})
        pct = max(0, min(100, int(item.get("percent", 0))))
        message = item.get("message", label)
        bars.append(f"""
        <div style="margin:8px 0;">
          <div style="display:flex;justify-content:space-between;gap:12px;font-size:12px;color:#d1d5db;">
            <span>{label}</span><span>{pct}%</span>
          </div>
          <div style="height:10px;background:#1f2937;border-radius:999px;overflow:hidden;">
            <div style="width:{pct}%;height:100%;background:linear-gradient(90deg,#f97316,#fb7185);border-radius:999px;transition:width .2s ease;"></div>
          </div>
          <div style="font-size:11px;color:#9ca3af;margin-top:4px;">{message}</div>
        </div>
        """)
    overall = state.get("overall", 0)
    current = state.get("current", "Waiting")
    return f"""
    <div style="background:#0f172a;border:1px solid #334155;border-radius:16px;padding:14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;color:#fff;">
        <strong>Progress</strong><span>{overall}% — {current}</span>
      </div>
      {''.join(bars)}
    </div>
    """


def render_tasks_html(state):
    order = [
        ("download", "تحميل الفيديو"),
        ("transcribe", "تفريغ الصوت"),
        ("ai", "تحليل AI"),
        ("cut", "قص المقاطع"),
        ("edit", "معالجة الوجه"),
        ("subtitles", "الترجمة / الترجمة النهائية"),
        ("done", "تم"),
    ]
    rows = []
    for key, label in order:
        item = state.get(key, {})
        pct = max(0, min(100, int(item.get("percent", 0))))
        status = "✓" if pct >= 100 else "…" if pct > 0 else "•"
        color = "#22c55e" if pct >= 100 else "#f59e0b" if pct > 0 else "#64748b"
        rows.append(f"""
        <div style="display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:12px;background:rgba(15,23,42,0.55);border:1px solid {color};margin-bottom:8px;">
          <div style="width:26px;height:26px;border-radius:999px;display:flex;align-items:center;justify-content:center;background:{color};color:#fff;font-weight:700;">{status}</div>
          <div style="flex:1;">
            <div style="color:#fff;font-size:13px;font-weight:600;">{label}</div>
            <div style="color:#94a3b8;font-size:11px;">{pct}%</div>
          </div>
        </div>
        """)
    overall = state.get("overall", 0)
    return f"""
    <div style="background:#020617;border:1px solid #334155;border-radius:16px;padding:14px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;color:#fff;">
        <strong>Tasks</strong><span>{overall}%</span>
      </div>
      {''.join(rows)}
    </div>
    """


def render_error_html(errors):
    if not errors:
        return "<div style='background:#111827;border:1px solid #334155;border-radius:16px;padding:14px;color:#cbd5e1;'>لا توجد أخطاء حتى الآن.</div>"
    rows = ''.join(f"<li style='margin-bottom:8px;'>{e}</li>" for e in errors)
    return f"<div style='background:#111827;border:1px solid #7f1d1d;border-radius:16px;padding:14px;color:#fecaca;'><div style='color:#fff;font-weight:700;margin-bottom:8px;'>Error Report</div><ul style='padding-left:18px;margin:0;'>{rows}</ul></div>"


def apply_face_preset(preset_name):
    if preset_name not in FACE_PRESETS:
        return [gr.update() for _ in range(4)] # No change
    
    p = FACE_PRESETS[preset_name]
    return p["thresh"], p["two_face"], p["conf"], p["dead_zone"]

def apply_experimental_preset(preset_name):
    if preset_name not in EXPERIMENTAL_PRESETS:
        return [gr.update() for _ in range(7)] # No change
        
    p = EXPERIMENTAL_PRESETS[preset_name]
    return p["focus"], p["mar"], p["score"], p["motion"], p["motion_th"], p["motion_sens"], p["decay"]

# Subtitle logic moved to subtitle_handler.py


def run_viral_cutter(input_source, project_name, url, video_file, segments, viral, themes, min_duration, max_duration, model, ai_backend, api_key, ai_model_name, chunk_size, workflow, face_model, face_mode, face_detect_interval, no_face_mode, 
                     face_filter_thresh, face_two_thresh, face_conf_thresh, face_dead_zone, focus_active_speaker, active_speaker_mar, active_speaker_score_diff, include_motion, active_speaker_motion_threshold, active_speaker_motion_sensitivity, active_speaker_decay,
                     use_custom_subs, font_name, font_size, font_color, highlight_color, outline_color, outline_thickness, shadow_color, shadow_size, is_bold, is_italic, is_uppercase, vertical_pos, alignment,
                     h_size, w_block, gap, mode, under, strike, border_s, remove_punc, video_quality, use_youtube_subs, translate_target):
    
    global current_process
    progress_state = empty_progress_state(i18n("Starting"))
    error_items = []
    def set_progress(stage, percent, message):
        progress_state[stage] = {"percent": int(percent), "message": message}
        progress_state["current"] = message
        progress_state["overall"] = int(sum(progress_state[s]["percent"] for s in PROGRESS_ORDER) / len(PROGRESS_ORDER))
    set_progress("download", 0, i18n("Preparing"))
    yield "", gr.update(value=i18n("Running..."), interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)

    cmd = [sys.executable, MAIN_SCRIPT_PATH]
    
    # Input Source Logic
    if input_source == "Existing Project":
        if not project_name:
             yield i18n("Error: No project selected."), gr.update(value=i18n("Start Processing"), interactive=True), gr.update(visible=False), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
             return
        full_project_path = os.path.join(VIRALS_DIR, project_name)
        cmd.extend(["--project-path", full_project_path])
    elif input_source == "Upload Video":
        if not video_file:
             yield i18n("Error: No video file uploaded."), gr.update(value=i18n("Start Processing"), interactive=True), gr.update(visible=False), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
             return
        
        # Determine project name from filename
        original_filename = os.path.basename(video_file)
        name_no_ext = os.path.splitext(original_filename)[0]
        # Sanitize: Allow alphanumeric, space, dash, underscore
        safe_name = "".join([c for c in name_no_ext if c.isalnum() or c in " _-"]).strip()
        if not safe_name: safe_name = "Untitled_Upload"
        
        # Always append timestamp as requested
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name_upload = f"{safe_name}_{timestamp}"
        project_path = os.path.join(VIRALS_DIR, project_name_upload)
             
        os.makedirs(project_path, exist_ok=True)
        
        target_path = os.path.join(project_path, "input.mp4")
        shutil.copy(video_file, target_path)
        
        cmd.extend(["--project-path", project_path])
        # Skip YouTube subs as it is a local upload
        cmd.append("--skip-youtube-subs")
        
    else:
        if url: cmd.extend(["--url", url])
        # Pass Video Quality
        if video_quality: cmd.extend(["--video-quality", video_quality])
        # Pass Subtitle Option (if False, we skip)
        if not use_youtube_subs: cmd.append("--skip-youtube-subs")
        
    # Translation
    if translate_target and translate_target != "None":
            cmd.extend(["--translate-target", translate_target])

    
    cmd.extend(["--segments", str(int(segments))])
    if viral: cmd.append("--viral")
    if themes: cmd.extend(["--themes", themes])
    cmd.extend(["--min-duration", str(int(min_duration))])
    cmd.extend(["--max-duration", str(int(max_duration))])
    cmd.extend(["--model", model])
    cmd.extend(["--ai-backend", ai_backend])
    if api_key: cmd.extend(["--api-key", api_key])
    
    # New AI Params
    if ai_model_name: cmd.extend(["--ai-model-name", str(ai_model_name)])
    if chunk_size: cmd.extend(["--chunk-size", str(int(chunk_size))])

    workflow_map = {"Full": "1", "Cut Only": "2", "Subtitles Only": "3"}
    cmd.extend(["--workflow", workflow_map.get(workflow, "1")])
    cmd.extend(["--face-model", face_model])
    cmd.extend(["--face-mode", face_mode])
    if face_detect_interval: cmd.extend(["--face-detect-interval", str(face_detect_interval)])
    if no_face_mode: cmd.extend(["--no-face-mode", no_face_mode])
    
    # New Face Params
    if face_filter_thresh is not None: cmd.extend(["--face-filter-threshold", str(face_filter_thresh)])
    if face_two_thresh is not None: cmd.extend(["--face-two-threshold", str(face_two_thresh)])
    if face_conf_thresh is not None: cmd.extend(["--face-confidence-threshold", str(face_conf_thresh)])
    if face_dead_zone is not None: cmd.extend(["--face-dead-zone", str(face_dead_zone)])


    
    cmd.append("--skip-prompts")
    
    if focus_active_speaker:
        cmd.append("--focus-active-speaker")
        if active_speaker_mar is not None: cmd.extend(["--active-speaker-mar", str(active_speaker_mar)])
        if active_speaker_score_diff is not None: cmd.extend(["--active-speaker-score-diff", str(active_speaker_score_diff)])
        if include_motion: cmd.append("--include-motion")
        if active_speaker_motion_threshold is not None: cmd.extend(["--active-speaker-motion-threshold", str(active_speaker_motion_threshold)])
        if active_speaker_motion_sensitivity is not None: cmd.extend(["--active-speaker-motion-sensitivity", str(active_speaker_motion_sensitivity)])
        if active_speaker_decay is not None: cmd.extend(["--active-speaker-decay", str(active_speaker_decay)])

    cmd.append("--skip-prompts") # Always skip prompts in WebUI to prevent freezing

    if use_custom_subs:
        subtitle_config = {
            "font": font_name, "base_size": int(font_size), "base_color": convert_color_to_ass(font_color), "highlight_color": convert_color_to_ass(highlight_color),
            "outline_color": convert_color_to_ass(outline_color), "outline_thickness": outline_thickness, "shadow_color": convert_color_to_ass(shadow_color),
            "shadow_size": shadow_size, "vertical_position": vertical_pos, "alignment": alignment, "bold": 1 if is_bold else 0, "italic": 1 if is_italic else 0, 
            "underline": 1 if under else 0, "strikeout": 1 if strike else 0, "border_style": border_s, "words_per_block": int(w_block), "gap_limit": gap,
            "mode": mode, "highlight_size": int(h_size), "remove_punctuation": remove_punc
        }
        # Uppercase is handled in main script or logic? 
        # Actually subtitle_config doesn't seem to natively support "uppercase" in get_subtitle_config default, but app.py was using it. 
        # I should probably add it back if I want to support it, but user said "PROHIBITED to remove existing ones".
        # I'll re-add 'uppercase': 1 if is_uppercase else 0 to the dict if the backend supports it, otherwise it's just ignored.
        # But wait, main_improved.py doesn't have 'uppercase' in get_subtitle_config. 
        # I'll keep it in the dict just in case logic uses it elsewhere or if I missed it.
        # Actually, standard ASS doesn't support uppercase flag directly in Style, it needs to be text transform.
        # But I'll leave it in the dict.
        subtitle_config["uppercase"] = 1 if is_uppercase else 0

        subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
        try:
            with open(subtitle_config_path, "w", encoding="utf-8") as f:
                json.dump(subtitle_config, f, indent=4)
            cmd.extend(["--subtitle-config", subtitle_config_path])
        except Exception: pass 
    
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    try:
        current_process = subprocess.Popen(cmd, cwd=WORKING_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True, env=env)
        logs = ""
        project_folder_path = None
        if input_source == "Existing Project" and project_name:
             # If using existing project, we already know the path, but let's see if logs confirm it
             project_folder_path = os.path.join(VIRALS_DIR, project_name)

        last_update_time = time.time()
        
        while True:
            line = current_process.stdout.readline()
            if not line and current_process.poll() is not None:
                break
            
            if line:
                logs += line
                if line.startswith("PROGRESS|"):
                    try:
                        _, stage, percent, message = line.strip().split("|", 3)
                        if stage in progress_state:
                            progress_state[stage] = {"percent": int(percent), "message": message}
                            progress_state["current"] = message
                            progress_state["overall"] = int(sum(progress_state[s]["percent"] for s in PROGRESS_ORDER) / len(PROGRESS_ORDER))
                    except Exception:
                        pass

                if "Project Folder:" in line:
                    parts = line.split("Project Folder:")
                    if len(parts) > 1: project_folder_path = parts[1].strip()
                
                # Throttle updates to avoid browser freeze (0.2s interval)
                current_time = time.time()
                if current_time - last_update_time > 0.2:
                    yield logs, gr.update(visible=True, interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
                    last_update_time = current_time
        
        # Final yield to ensure all logs are shown
        yield logs, gr.update(visible=True, interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
    except Exception as e:
        logs += f"\nError running process: {str(e)}\n"
        error_items.append(f"Error running process: {str(e)}")
        yield logs, gr.update(visible=True, interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
    finally:
        if current_process:
            if current_process.stdout:
                try:
                    current_process.stdout.close()
                except Exception: pass
            if current_process.poll() is None:
                # If we are here, it means we finished reading or errored out, but process is still running.
                # If it was a normal break from loop, process should be done or close to done.
                # If we are stopping, current_process.terminate() might be needed outside? 
                # But here we just wait.
                try:
                    current_process.wait()
                except Exception: pass
            current_process = None
    
    # Wait to ensure filesystem flush
    time.sleep(1.0)
    
    html_output = ""
    if project_folder_path and os.path.exists(project_folder_path):
        html_output = library.generate_project_gallery(project_folder_path, is_full_path=True)
    else:
        html_output = f"<h3>{i18n('Error: Project folder could not be determined from logs.')}</h3>"
    set_progress("done", 100, i18n("Completed"))
    yield logs, gr.update(value=tr("Start Processing"), interactive=True), gr.update(visible=True, interactive=False), html_output, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)

css = """
#logs_output textarea {
    min-height: 300px !important;
    max-height: 520px !important;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
    line-height: 1.6 !important;
}

.vc-topbar {
    position: sticky;
    top: 0;
    z-index: 20;
    background: rgba(2, 6, 23, 0.92);
    backdrop-filter: blur(10px);
    padding: 10px 0;
    margin-bottom: 12px;
}

.vc-panels > div {
    min-width: 0;
}

body, .gradio-container {
    background-color: #0b0b0b !important;
    color: #ffffff !important;
}

input[type="password"], textarea, select {
    background-color: #1f1f1f !important;
    color: #ffffff !important;
    border: 1px solid #333 !important;
}

footer {visibility: hidden}

.gradio-container {
    max-width: 98% !important;
    width: 98% !important;
    margin: 0 auto !important;
}
"""

import header

with gr.Blocks(title="ViralCutter", theme=gr.themes.Soft(primary_hue="orange", neutral_hue="slate"), css=css) as demo:
    gr.Markdown("")
    gr.Markdown("## ViralCutter\nواجهة عربية كاملة ومحسّنة، مع سجل أوضح وتقدّم أدق وتنظيم أبسط.")
    with gr.Row(elem_classes=["vc-topbar"]):
        start_btn = gr.Button("بدء المعالجة", variant="primary")
        stop_btn = gr.Button("إيقاف", variant="stop", visible=True, interactive=False)
    with gr.Row(elem_classes=["vc-panels"]):
        with gr.Column(scale=1, min_width=280):
            progress_panel = gr.HTML(value=render_progress_html(empty_progress_state()))
        with gr.Column(scale=1, min_width=280):
            tasks_panel = gr.HTML(value=render_tasks_html(empty_progress_state()))
        with gr.Column(scale=1, min_width=280):
            errors_panel = gr.HTML(value=render_error_html([]))
    with gr.Tabs():
        with gr.Tab("إنشاء جديد"):
             with gr.Row():
                with gr.Column(scale=1):
                    input_source = gr.Radio([("رابط يوتيوب", "YouTube URL"), ("مشروع موجود", "Existing Project"), ("رفع فيديو", "Upload Video")], label="مصدر الإدخال", value="YouTube URL")
                    
                    url_input = gr.Textbox(label="رابط يوتيوب", placeholder="https://www.youtube.com/watch?v=...", visible=True)
                    video_upload = gr.File(label=i18n("Drag & drop a video here or click to browse"), file_count="single", file_types=["video"], visible=False, elem_id="video_upload_box")
                    upload_hint = gr.Markdown(i18n("Drop a video here for fastest upload."), visible=False)
                    
                    with gr.Row():
                        video_quality_input = gr.Dropdown(choices=["best", "1080p", "720p", "480p"], label="جودة الفيديو", value="best")
                        translate_input = gr.Dropdown(choices=["None", "pt", "en", "es", "fr", "de", "it", "ru", "ja", "ko", "zh-CN", "ar"], label="ترجمة الترجمة إلى", value="None")
                        use_youtube_subs_input = gr.Checkbox(label="استخدام ترجمات يوتيوب", value=True, info=i18n("Download and use official subtitles if available. (Recommended, it speeds up the process)"))

                    project_selector = gr.Dropdown(choices=[], label="اختر مشروعًا", visible=False)
                    
                    def on_source_change(source):
                        if source == "YouTube URL":
                            return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False), gr.update(value="Full"), gr.update(visible=False)
                        elif source == "Upload Video":
                             return gr.update(visible=False), gr.update(visible=False), gr.update(visible=True), gr.update(value="Full"), gr.update(visible=True)
                        else:
                            # Load projects
                            projs = library.get_existing_projects()
                            return gr.update(visible=False), gr.update(choices=projs, visible=True), gr.update(visible=False), gr.update(value="Subtitles Only"), gr.update(visible=False)
                    
                    
                    with gr.Row():
                        segments_input = gr.Number(label="عدد المقاطع", value=3, precision=0)
                        viral_input = gr.Checkbox(label="وضع الفيروسية", value=True)
                    themes_input = gr.Textbox(label="المواضيع", placeholder=i18n("funny, sad..."), visible=False)
                    viral_input.change(lambda x: gr.update(visible=not x), viral_input, themes_input)
                    with gr.Row():
                        min_dur_input = gr.Number(label="أقل مدة (ث)", value=15)
                        max_dur_input = gr.Number(label="أقصى مدة (ث)", value=90)
                with gr.Column(scale=1):
                    with gr.Row():
                        ai_backend_input = gr.Dropdown(choices=[(i18n("Gemini"), "gemini"), (i18n("G4F"), "g4f"), (i18n("Local (GGUF)"), "local"), (i18n("Manual"), "manual")], label="محرك الذكاء الاصطناعي", value="gemini", scale=2)
                        api_key_input = gr.Textbox(label="مفتاح Gemini API", type="password", scale=3)
                    
                    # New Dynamic Inputs
                    with gr.Row():
                        ai_model_input = gr.Dropdown(choices=GEMINI_MODELS, label="نموذج الذكاء الاصطناعي", value=GEMINI_MODELS[1], allow_custom_value=True, visible=True, scale=5)
                        refresh_models_btn = gr.Button("🔄", size="sm", visible=False, scale=0, min_width=50) # Only local
                        chunk_size_input = gr.Number(label="حجم الجزء", value=70000, precision=0, scale=2)
                    
                    # Update listeners with logic to hide/show API key
                    def update_ai_ui(backend):
                        show_api = (backend == "gemini")
                        show_refresh = (backend == "local")
                        
                        # Definições padrão para evitar que fiquem vazios
                        new_choices = []
                        new_val = ""
                        new_chunk = 70000
                        
                        if backend == "gemini":
                            new_choices = GEMINI_MODELS
                            new_val = GEMINI_MODELS[1]
                            new_chunk = 70000
                        elif backend == "g4f":
                            new_choices = G4F_MODELS
                            new_val = G4F_MODELS[5]
                            new_chunk = 70000
                        elif backend == "local":
                            models = get_local_models()
                            new_choices = models if models else [i18n("No models found")]
                            new_val = new_choices[0]
                            new_chunk = 30000
                        else: # Manual
                             pass

                        return (
                            gr.update(visible=show_api), # API Key Visibility (Fixes hole 1)
                            gr.update(choices=new_choices, value=new_val, visible=(backend != "manual")), # Model Dropdown
                            gr.update(visible=show_refresh), # Refresh Button
                            gr.update(value=new_chunk) # Chunk Size
                        )

                    def refresh_local_models():
                        models = get_local_models()
                        val = models[0] if models else i18n("No models found")
                        return gr.update(choices=models, value=val)

                    refresh_models_btn.click(refresh_local_models, outputs=ai_model_input)
                    ai_backend_input.change(update_ai_ui, inputs=ai_backend_input, outputs=[api_key_input, ai_model_input, refresh_models_btn, chunk_size_input])

                    model_input = gr.Dropdown(["tiny", "small", "medium", "large", "large-v1", "large-v2", "large-v3", "turbo", "large-v3-turbo", "distil-large-v2", "distil-medium.en", "distil-small.en", "distil-large-v3"], label="نموذج Whisper", value="large-v3-turbo")
                    with gr.Row():
                        workflow_input = gr.Dropdown(choices=[(i18n("Full"), "Full"), (i18n("Cut Only"), "Cut Only"), (i18n("Subtitles Only"), "Subtitles Only")], label="طريقة العمل", value="Full")
                        face_model_input = gr.Dropdown(["insightface", "mediapipe"], label="نموذج الوجه", value="insightface")
                    with gr.Row():
                        face_mode_input = gr.Dropdown(choices=[(i18n("Auto"), "auto"), ("1", "1"), ("2", "2")], label="وضع الوجه", value="auto")
                        face_detect_interval_input = gr.Textbox(label="فاصل كشف الوجه", value="0.17,1.0")
                        no_face_mode_input = gr.Dropdown(choices=[(i18n("Padding (9:16)"), "padding"), (i18n("Zoom (Center)"), "zoom")], label=i18n("No Face Fallback"), value="zoom")
                    
                    # Update listeners now that all components are defined
                    input_source.change(on_source_change, inputs=input_source, outputs=[url_input, project_selector, video_upload, workflow_input, upload_hint])

                with gr.Row():
                    logs_output = gr.Textbox(label="السجل", lines=14, autoscroll=True, elem_id="logs_output")
                    logs_output.change(fn=None, inputs=[], outputs=[], js="""
                        function() {
                            var ta = document.querySelector('#logs_output textarea');
                            if (ta) {
                                if (!ta._scrollerSetup) {
                                    ta._isSticky = true;
                                    ta.addEventListener('scroll', function() {
                                        var diff = ta.scrollHeight - ta.scrollTop - ta.clientHeight;
                                        ta._isSticky = diff <= 50;
                                    });
                                    ta._scrollerSetup = true;
                                }
                                if (ta._isSticky === undefined || ta._isSticky === true) {
                                    ta.scrollTop = ta.scrollHeight;
                                }
                            }
                        }
                    """)
                    gr.Markdown(tr("تظهر تحديثات التقدم هنا أثناء التشغيل."))
                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("### تقدم المهام")
                        with gr.Column(scale=1):
                            gr.Markdown("### تقرير الأخطاء")
                    stop_btn.click(kill_process, outputs=[logs_output, start_btn, stop_btn, tasks_panel, errors_panel])
            
             with gr.Accordion(i18n("Advanced Face Settings"), open=False):
                 face_preset_input = gr.Dropdown(choices=[(i18n(k), k) for k in FACE_PRESETS.keys()], label=i18n("Configuration Presets"), value="Default (Balanced)", interactive=True)
                 with gr.Row():
                      face_filter_thresh_input = gr.Slider(label=i18n("Ignore Small Faces (0.0 - 1.0)"), minimum=0.0, maximum=1.0, value=0.35, step=0.05, info=i18n("Relative size to ignore background."))
                      face_two_thresh_input = gr.Slider(label=i18n("Threshold for 2 Faces (0.0 - 1.0)"), minimum=0.0, maximum=1.0, value=0.60, step=0.05, info=i18n("Size of 2nd face to activate split mode."))
                      face_conf_thresh_input = gr.Slider(label=i18n("Minimum Confidence (0.0 - 1.0)"), minimum=0.0, maximum=1.0, value=0.40, step=0.05, info=i18n("Ignore detections with low confidence."))
                      face_dead_zone_input = gr.Slider(label=i18n("Dead Zone (Stabilization)"), minimum=0, maximum=200, value=150, step=5, info=i18n("Movement pixels to ignore."))
                 
                 face_preset_input.change(apply_face_preset, inputs=face_preset_input, outputs=[face_filter_thresh_input, face_two_thresh_input, face_conf_thresh_input, face_dead_zone_input])

                 with gr.Accordion(i18n("Experimental: Active Speaker & Motion"), open=False):
                        experimental_preset_input = gr.Dropdown(choices=[(i18n(k), k) for k in EXPERIMENTAL_PRESETS.keys()], label=i18n("Configuration Presets"), value="Default (Off)", interactive=True)
                        focus_active_speaker_input = gr.Checkbox(label=i18n("Experimental: Focus on Speaker"), value=False, info=i18n("Tries to focus only on the speaking person instead of split screen."))
                        with gr.Row():
                            active_speaker_mar_input = gr.Slider(label=i18n("MAR Threshold (Mouth Open)"), minimum=0.01, maximum=0.20, value=0.03, step=0.005, info=i18n("Mouth open sensitivity."))
                            active_speaker_score_diff_input = gr.Slider(label=i18n("Score Difference"), minimum=0.5, maximum=10.0, value=1.5, step=0.5, info=i18n("Minimum difference to focus on 1 face."))
                            
                        with gr.Row():
                            include_motion_input = gr.Checkbox(label=i18n("Consider Motion"), value=False, info=i18n("Increases score with motion (gestures)."))
                            
                        with gr.Row():
                            active_speaker_motion_threshold_input = gr.Slider(label=i18n("Motion Dead Zone"), minimum=0.0, maximum=20.0, value=3.0, step=0.5, info=i18n("Pixels ignored."))
                            active_speaker_motion_sensitivity_input = gr.Slider(label=i18n("Motion Sensitivity"), minimum=0.01, maximum=0.5, value=0.05, step=0.01, info=i18n("Points per pixel."))
                            active_speaker_decay_input = gr.Slider(label=i18n("Switch Speed"), minimum=0.5, maximum=5.0, value=2.0, step=0.5, info=i18n("Speed to lose focus."))

                        experimental_preset_input.change(apply_experimental_preset, inputs=experimental_preset_input, outputs=[focus_active_speaker_input, active_speaker_mar_input, active_speaker_score_diff_input, include_motion_input, active_speaker_motion_threshold_input, active_speaker_motion_sensitivity_input, active_speaker_decay_input])
             with gr.Accordion("إعدادات الترجمة (تجريبي)", open=False):
                preset_input = gr.Dropdown(choices=[(i18n("Manual"), "Manual")] + [(i18n(k), k) for k in subs.SUBTITLE_PRESETS.keys()], label="إعدادات سريعة", value="Hormozi (Classic)")
                use_custom_subs = gr.Checkbox(label="تفعيل تخصيص الترجمة (يشمل الإعداد المسبق)", value=True)
                
                # Previews (Always Visible)
                preview_html = gr.HTML(value=f"<div style='text-align:center; padding:10px; color:#666;'>{i18n('Select options or preset to preview')}</div>")
                
                with gr.Row():
                    preview_vid_btn = gr.Button(i18n("🎬 Render Animated Preview (Slow)"), size="sm")
                preview_vid = gr.Video(label="معاينة متحركة", height=300, autoplay=True, interactive=False)
                
                with gr.Accordion("إعدادات متقدمة", open=False):
                    gr.Markdown("### " + tr("Appearance"))
                    with gr.Row():
                        font_name_input = gr.Textbox(label="اسم الخط", value="Montserrat-Regular")
                        font_size_input = gr.Slider(label="حجم الخط (الأساسي)", minimum=8, maximum=80, value=12)
                        highlight_size_input = gr.Slider(label="حجم التمييز", minimum=8, maximum=80, value=14)
                    
                    with gr.Row():
                        font_color_input = gr.ColorPicker(label="اللون الأساسي", value="#FFFFFF")
                        highlight_color_input = gr.ColorPicker(label="لون التمييز", value="#00FF00")
                        outline_color_input = gr.ColorPicker(label="لون الإطار", value="#000000")
                        shadow_color_input = gr.ColorPicker(label="لون الظل", value="#000000")
                    
                    gr.Markdown("### " + tr("Styling & Effects"))
                    with gr.Row():
                        outline_thickness_input = gr.Slider(label="سماكة الإطار", minimum=0, maximum=10, value=1.5)
                        shadow_size_input = gr.Slider(label="حجم الظل", minimum=0, maximum=10, value=2)
                        border_style_input = gr.Dropdown(choices=[(i18n("Outline"), 1), (i18n("Opaque Box"), 3)], label="نمط الإطار", value=1)
                    
                    with gr.Row():
                        bold_input = gr.Checkbox(label="عريض")
                        italic_input = gr.Checkbox(label="مائل")
                        uppercase_input = gr.Checkbox(label="أحرف كبيرة")
                        remove_punc_input = gr.Checkbox(label=i18n("Remove Punctuation"), value=True)
                        underline_input = gr.Checkbox(label="تحته خط")
                        strikeout_input = gr.Checkbox(label="مشطوب")
                        
                    gr.Markdown("### " + tr("Positioning & Layout"))
                    with gr.Row():
                        vertical_pos_input = gr.Slider(label=i18n("V-Pos (Margin V)"), minimum=0, maximum=500, value=210)
                        alignment_input = gr.Dropdown(choices=[(i18n("Left"), 1), (i18n("Center"), 2), (i18n("Right"), 3)], label="المحاذاة", value=2)
                        gap_limit_input = gr.Slider(label="حد الفجوة", minimum=0.0, maximum=5.0, value=0.5, step=0.1)
                        mode_input = gr.Dropdown(choices=[(i18n("Highlight"), "highlight"), (i18n("Word by Word"), "word_by_word"), (i18n("No Highlight"), "no_highlight")], label="الوضع", value="highlight")
                        words_per_block_input = gr.Slider(label="كلمات بكل كتلة", minimum=1, maximum=20, value=3, step=1)

                manual_inputs = [
                    font_name_input, font_size_input, font_color_input, highlight_color_input, 
                    outline_color_input, outline_thickness_input, shadow_color_input, shadow_size_input, 
                    bold_input, italic_input, uppercase_input,
                    highlight_size_input, words_per_block_input, gap_limit_input, mode_input,
                    underline_input, strikeout_input, border_style_input,
                    vertical_pos_input, alignment_input,
                    remove_punc_input
                ]
                
                # Update manual inputs when preset changes
                preset_input.change(subs.apply_preset, inputs=[preset_input], outputs=manual_inputs)
                
                # Auto-update PREVIEW HTML on any change
                for inp in manual_inputs:
                    inp.change(subs.generate_preview_html, inputs=manual_inputs, outputs=preview_html)
                
                # Render video button
                preview_vid_btn.click(
                    subs.render_preview_video,
                    inputs=manual_inputs,
                    outputs=preview_vid
                )
                
                # Initial load
                demo.load(subs.generate_preview_html, inputs=manual_inputs, outputs=preview_html)
                demo.load(subs.apply_preset, inputs=[preset_input], outputs=manual_inputs)

                with gr.Accordion(i18n("Saved Settings Templates"), open=False):
                    with gr.Row():
                        template_name_input = gr.Textbox(label="اسم القالب", placeholder=i18n("e.g. clean-shorts"))
                        save_template_btn = gr.Button(tr("Save Template"), variant="primary")
                    with gr.Row():
                        template_dropdown = gr.Dropdown(choices=template_choices(), label="تحميل القالب", value=None)
                        load_template_btn = gr.Button(tr("Apply Template"), variant="secondary")
                    template_status = gr.Textbox(label="حالة القالب", interactive=False)

                def build_template_payload():
                    return {
                        "font_name": font_name_input.value,
                        "font_size": font_size_input.value,
                        "font_color": font_color_input.value,
                        "highlight_color": highlight_color_input.value,
                        "outline_color": outline_color_input.value,
                        "outline_thickness": outline_thickness_input.value,
                        "shadow_color": shadow_color_input.value,
                        "shadow_size": shadow_size_input.value,
                        "is_bold": bold_input.value,
                        "is_italic": italic_input.value,
                        "is_uppercase": uppercase_input.value,
                        "vertical_pos": vertical_pos_input.value,
                        "alignment": alignment_input.value,
                        "h_size": highlight_size_input.value,
                        "w_block": words_per_block_input.value,
                        "gap": gap_limit_input.value,
                        "mode": mode_input.value,
                        "under": underline_input.value,
                        "strike": strikeout_input.value,
                        "border_s": border_style_input.value,
                        "remove_punc": remove_punc_input.value,
                        "face_model": face_model_input.value,
                        "face_mode": face_mode_input.value,
                        "no_face_mode": no_face_mode_input.value,
                        "face_detect_interval": face_detect_interval_input.value,
                    }

                def save_template_ui(name):
                    name = (name or "").strip()
                    if not name:
                        return i18n("Template name is required."), gr.update(choices=template_choices())
                    save_template(name, build_template_payload())
                    return i18n("Saved template: {}").format(name), gr.update(choices=template_choices(), value=name)

                def load_template_ui(name):
                    templates = load_templates()
                    payload = templates.get(name)
                    if not payload:
                        return [gr.update() for _ in range(26)] + [i18n("Template not found.")]
                    return [
                        gr.update(value=payload.get("font_name", font_name_input.value)),
                        gr.update(value=payload.get("font_size", font_size_input.value)),
                        gr.update(value=payload.get("font_color", font_color_input.value)),
                        gr.update(value=payload.get("highlight_color", highlight_color_input.value)),
                        gr.update(value=payload.get("outline_color", outline_color_input.value)),
                        gr.update(value=payload.get("outline_thickness", outline_thickness_input.value)),
                        gr.update(value=payload.get("shadow_color", shadow_color_input.value)),
                        gr.update(value=payload.get("shadow_size", shadow_size_input.value)),
                        gr.update(value=payload.get("is_bold", bold_input.value)),
                        gr.update(value=payload.get("is_italic", italic_input.value)),
                        gr.update(value=payload.get("is_uppercase", uppercase_input.value)),
                        gr.update(value=payload.get("vertical_pos", vertical_pos_input.value)),
                        gr.update(value=payload.get("alignment", alignment_input.value)),
                        gr.update(value=payload.get("h_size", highlight_size_input.value)),
                        gr.update(value=payload.get("w_block", words_per_block_input.value)),
                        gr.update(value=payload.get("gap", gap_limit_input.value)),
                        gr.update(value=payload.get("mode", mode_input.value)),
                        gr.update(value=payload.get("under", underline_input.value)),
                        gr.update(value=payload.get("strike", strikeout_input.value)),
                        gr.update(value=payload.get("border_s", border_style_input.value)),
                        gr.update(value=payload.get("remove_punc", remove_punc_input.value)),
                        gr.update(value=payload.get("face_model", face_model_input.value)),
                        gr.update(value=payload.get("face_mode", face_mode_input.value)),
                        gr.update(value=payload.get("no_face_mode", no_face_mode_input.value)),
                        gr.update(value=payload.get("face_detect_interval", face_detect_interval_input.value)),
                        i18n("Applied template: {}").format(name),
                    ]

                save_template_btn.click(save_template_ui, inputs=[template_name_input], outputs=[template_status, template_dropdown])
                load_template_btn.click(load_template_ui, inputs=[template_dropdown], outputs=[
                    font_name_input, font_size_input, font_color_input, highlight_color_input,
                    outline_color_input, outline_thickness_input, shadow_color_input, shadow_size_input,
                    bold_input, italic_input, uppercase_input, vertical_pos_input, alignment_input,
                    highlight_size_input, words_per_block_input, gap_limit_input, mode_input,
                    underline_input, strikeout_input, border_style_input, remove_punc_input,
                    face_model_input, face_mode_input, no_face_mode_input, face_detect_interval_input,
                    template_status,
                ])

                results_html = gr.HTML(label=tr("Results"))
                with gr.Row():
                    gr.Markdown(tr("سجل مباشر واضح، تقدّم مرئي، ورسائل خطأ مفهومة."))

                start_btn.click(run_viral_cutter, inputs=[
                    input_source, project_selector, url_input, video_upload, segments_input, viral_input, themes_input, min_dur_input, max_dur_input,
                    model_input, ai_backend_input, api_key_input, ai_model_input, chunk_size_input,
                    workflow_input, face_model_input, face_mode_input, face_detect_interval_input, no_face_mode_input,
                    face_filter_thresh_input, face_two_thresh_input, face_conf_thresh_input, face_dead_zone_input, focus_active_speaker_input,
                    active_speaker_mar_input, active_speaker_score_diff_input, include_motion_input, active_speaker_motion_threshold_input, active_speaker_motion_sensitivity_input, active_speaker_decay_input,
                    use_custom_subs,
                    font_name_input, font_size_input, font_color_input, highlight_color_input,
                    outline_color_input, outline_thickness_input, shadow_color_input, shadow_size_input,
                    bold_input, italic_input, uppercase_input, vertical_pos_input, alignment_input,
                    highlight_size_input, words_per_block_input, gap_limit_input, mode_input,
                    underline_input, strikeout_input, border_style_input, remove_punc_input,
                    video_quality_input, use_youtube_subs_input, translate_input
                ], outputs=[logs_output, start_btn, stop_btn, results_html, progress_panel, tasks_panel, errors_panel])
        with gr.Tab(i18n("Subtitle Editor")):
            gr.Markdown("### تحرير الترجمات (الوضع الذكي)")
            
            with gr.Group():
                editor_project_dropdown = gr.Dropdown(choices=library.get_existing_projects(), label="اختر مشروعًا", value=None)
                editor_refresh_btn = gr.Button(tr("Refresh"), size="sm")
            
            with gr.Group():
                editor_file_dropdown = gr.Dropdown(choices=[], label="اختر ملف الترجمة", interactive=True)
                editor_load_btn = gr.Button(tr("Load Subtitles"), variant="secondary")

            template_name_input = gr.Textbox(label="اسم القالب", placeholder=i18n("e.g. clean-captions"))
            template_dropdown = gr.Dropdown(choices=template_choices(), label="القوالب المحفوظة", value=None)
            save_template_btn = gr.Button("حفظ القالب", variant="secondary")
            load_template_btn = gr.Button("تحميل القالب", variant="secondary")
            gr.Markdown(tr("تخزن القوالب تنسيق الترجمة مع وضع الوجه ونموذجه."))

            # Hidden state to store full path of currently loaded JSON
            current_json_path = gr.State()

            # The Dataframe Editor
            # Headers: Start, End, Text
            subtitle_dataframe = gr.Dataframe(
                headers=["Start", "End", "Text"],
                datatype=["str", "str", "str"],
                col_count=(3, "fixed"),
                interactive=True,
                label="مقاطع الترجمة",
                wrap=True
            )
            subtitle_preview = gr.Video(label="معاينة حية", interactive=False, height=300)

            with gr.Row():
                editor_save_btn = gr.Button(i18n("💾 Save Changes"), variant="primary")
                editor_render_single_btn = gr.Button(i18n("⚡ Render This Segment (Very-Fast)"), variant="secondary")
                editor_render_all_btn = gr.Button(i18n("🎬 Render All (Fast)"), variant="stop")
                editor_export_all_btn = gr.Button(i18n("📦 Export All Segments"), variant="secondary")
            
            editor_status = gr.Textbox(label="الحالة", interactive=False)

            # --- Callbacks for Editor ---
            editor_refresh_btn.click(library.refresh_projects, outputs=editor_project_dropdown)

            def save_settings_template(name, proj_name, use_custom, font_name, font_size, font_color, highlight_color, outline_color, outline_thickness, shadow_color, shadow_size, is_bold, is_italic, is_uppercase, vertical_pos, alignment, h_size, w_block, gap, mode, under, strike, border_s, remove_punc, face_mode, face_model, no_face_mode, face_detect_interval):
                if not name:
                    return i18n("Template name required.")
                payload = {
                    "subtitle": {
                        "use_custom": bool(use_custom),
                        "font_name": font_name,
                        "font_size": int(font_size),
                        "font_color": font_color,
                        "highlight_color": highlight_color,
                        "outline_color": outline_color,
                        "outline_thickness": outline_thickness,
                        "shadow_color": shadow_color,
                        "shadow_size": shadow_size,
                        "is_bold": bool(is_bold),
                        "is_italic": bool(is_italic),
                        "is_uppercase": bool(is_uppercase),
                        "vertical_pos": int(vertical_pos),
                        "alignment": alignment,
                        "highlight_size": int(h_size),
                        "words_per_block": int(w_block),
                        "gap": gap,
                        "mode": mode,
                        "under": bool(under),
                        "strike": bool(strike),
                        "border_s": border_s,
                        "remove_punc": bool(remove_punc),
                    },
                    "face": {
                        "face_mode": face_mode,
                        "face_model": face_model,
                        "no_face_mode": no_face_mode,
                        "face_detect_interval": face_detect_interval,
                    },
                }
                save_template(name, payload)
                return i18n("Template saved: {}").format(name)

            def load_settings_template(name):
                templates = load_templates()
                payload = templates.get(name)
                if not payload:
                    return [gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), i18n("Template not found.")]
                sub = payload.get("subtitle", {})
                face = payload.get("face", {})
                return [
                    gr.update(value=sub.get("use_custom", True)),
                    gr.update(value=sub.get("font_name", "Montserrat-Regular")),
                    gr.update(value=sub.get("font_size", 12)),
                    gr.update(value=sub.get("font_color", "#FFFFFF")),
                    gr.update(value=sub.get("highlight_color", "#00FF00")),
                    gr.update(value=sub.get("outline_color", "#000000")),
                    gr.update(value=sub.get("outline_thickness", 1.5)),
                    gr.update(value=sub.get("shadow_color", "#000000")),
                    gr.update(value=sub.get("shadow_size", 2)),
                    gr.update(value=sub.get("is_bold", False)),
                    gr.update(value=sub.get("is_italic", False)),
                    gr.update(value=sub.get("is_uppercase", False)),
                    gr.update(value=sub.get("vertical_pos", 210)),
                    gr.update(value=sub.get("alignment", 2)),
                    gr.update(value=sub.get("highlight_size", 14)),
                    gr.update(value=sub.get("words_per_block", 3)),
                    gr.update(value=sub.get("gap", 0.5)),
                    gr.update(value=sub.get("mode", "highlight")),
                    gr.update(value=sub.get("under", False)),
                    gr.update(value=sub.get("strike", False)),
                    gr.update(value=sub.get("border_s", 1)),
                    gr.update(value=sub.get("remove_punc", True)),
                    gr.update(value=face.get("face_mode", "auto")),
                    gr.update(value=face.get("face_model", "insightface")),
                    gr.update(value=face.get("no_face_mode", "zoom")),
                    gr.update(value=face.get("face_detect_interval", "0.17,1.0")),
                    i18n("Template loaded: {} | Face: {} / {}").format(name, face.get("face_mode", "auto"), face.get("face_model", "insightface")),
                ]

            save_template_btn.click(save_settings_template, inputs=[template_name_input, editor_project_dropdown, use_custom_subs] + manual_inputs + [face_mode_input, face_model_input, no_face_mode_input, face_detect_interval_input], outputs=editor_status)
            load_template_btn.click(load_settings_template, inputs=template_dropdown, outputs=[use_custom_subs] + manual_inputs + [face_mode_input, face_model_input, no_face_mode_input, face_detect_interval_input, editor_status])

            def update_file_list(proj_name):
                if not proj_name: return gr.update(choices=[])
                proj_path = os.path.join(VIRALS_DIR, proj_name)
                files = editor.list_editable_files(proj_path)
                return gr.update(choices=files, value=files[0] if files else None)

            editor_project_dropdown.change(update_file_list, inputs=editor_project_dropdown, outputs=editor_file_dropdown)

            def load_subs(proj_name, file_name):
                if not proj_name or not file_name:
                    return [], None, None, i18n("Please select project and file.")

                full_path = os.path.join(VIRALS_DIR, proj_name, 'subs', file_name)
                data = editor.load_transcription_for_editor(full_path)
                preview_path = None
                if data:
                    preview_path, preview_msg = editor.build_preview_clip(full_path, 0)
                else:
                    preview_msg = i18n("No segments to preview.")
                return data, full_path, preview_path, i18n("Loaded {} segments. {}").format(len(data), preview_msg)


            editor_load_btn.click(load_subs, inputs=[editor_project_dropdown, editor_file_dropdown], outputs=[subtitle_dataframe, current_json_path, subtitle_preview, editor_status])

            def save_subs(json_path, df):
                if not json_path: return i18n("No file loaded.")
                data_list = df.values.tolist() if hasattr(df, 'values') else df
                msg = editor.save_editor_changes(json_path, data_list)
                return msg

            editor_save_btn.click(save_subs, inputs=[current_json_path, subtitle_dataframe], outputs=editor_status)

            def preview_row(json_path, df, evt: gr.SelectData):
                if not json_path or evt is None:
                    return None, i18n("No row selected.")
                row_index = getattr(evt, "index", None)
                if row_index is None:
                    return None, i18n("No row selected.")
                video_path, msg = editor.build_preview_clip(json_path, int(row_index))
                return video_path, msg

            subtitle_dataframe.select(preview_row, inputs=[current_json_path, subtitle_dataframe], outputs=[subtitle_preview, editor_status])

            def render_single(json_path, use_custom, font_name, font_size, font_color, highlight_color, 
                              outline_color, outline_thickness, shadow_color, shadow_size, 
                              is_bold, is_italic, is_uppercase, 
                              h_size, w_block, gap, mode, under, strike, border_s, 
                              vertical_pos, alignment, remove_punc):
                
                if not json_path: return i18n("No file loaded.")
                
                subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
                
                # Save config if custom subs enabled
                if use_custom:
                    subtitle_config = {
                        "font": font_name, "base_size": int(font_size), 
                        "base_color": convert_color_to_ass(font_color), 
                        "highlight_color": convert_color_to_ass(highlight_color),
                        "outline_color": convert_color_to_ass(outline_color), 
                        "outline_thickness": outline_thickness, 
                        "shadow_color": convert_color_to_ass(shadow_color),
                        "shadow_size": shadow_size, "vertical_position": vertical_pos, 
                        "alignment": alignment, "bold": 1 if is_bold else 0, 
                        "italic": 1 if is_italic else 0, 
                        "underline": 1 if under else 0, "strikeout": 1 if strike else 0, 
                        "border_style": border_s, "words_per_block": int(w_block), 
                        "gap_limit": gap, "mode": mode, "highlight_size": int(h_size),
                        "uppercase": 1 if is_uppercase else 0,
                        "remove_punctuation": remove_punc
                    }
                    try:
                        with open(subtitle_config_path, "w", encoding="utf-8") as f:
                            json.dump(subtitle_config, f, indent=4)
                    except Exception: pass
                else:
                    # Remove temp config if it exists to ensure defaults are used
                    try:
                        if os.path.exists(subtitle_config_path):
                            os.remove(subtitle_config_path)
                    except Exception: pass
                
                # We expect user to SAVE first, but we could auto-save.
                # For now assume saved.
                msg = editor.render_specific_video(json_path)
                return msg

            editor_render_single_btn.click(
                render_single, 
                inputs=[current_json_path, use_custom_subs] + manual_inputs, 
                outputs=editor_status
            )

            def render_all(proj_name, use_custom, font_name, font_size, font_color, highlight_color, 
                           outline_color, outline_thickness, shadow_color, shadow_size, 
                           is_bold, is_italic, is_uppercase, 
                           h_size, w_block, gap, mode, under, strike, border_s, 
                           vertical_pos, alignment, remove_punc):
                if not proj_name: return i18n("No project selected.")
                
                # Save config
                if use_custom:
                    subtitle_config = {
                        "font": font_name, "base_size": int(font_size), 
                        "base_color": convert_color_to_ass(font_color), 
                        "highlight_color": convert_color_to_ass(highlight_color),
                        "outline_color": convert_color_to_ass(outline_color), 
                        "outline_thickness": outline_thickness, 
                        "shadow_color": convert_color_to_ass(shadow_color),
                        "shadow_size": shadow_size, "vertical_position": vertical_pos, 
                        "alignment": alignment, "bold": 1 if is_bold else 0, 
                        "italic": 1 if is_italic else 0, 
                        "underline": 1 if under else 0, "strikeout": 1 if strike else 0, 
                        "border_style": border_s, "words_per_block": int(w_block), 
                        "gap_limit": gap, "mode": mode, "highlight_size": int(h_size),
                        "uppercase": 1 if is_uppercase else 0,
                        "remove_punctuation": remove_punc
                    }
                    subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
                    try:
                        with open(subtitle_config_path, "w", encoding="utf-8") as f:
                            json.dump(subtitle_config, f, indent=4)
                    except Exception: pass

                proj_path = os.path.join(VIRALS_DIR, proj_name)
                
                # IMPORTANT: Pass the config file path to the command
                subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
                cmd = [sys.executable, MAIN_SCRIPT_PATH, "--project-path", proj_path, "--workflow", "3", "--skip-prompts"]
                
                if use_custom and os.path.exists(subtitle_config_path):
                     cmd.extend(["--subtitle-config", subtitle_config_path])

                try:
                    subprocess.Popen(cmd, cwd=WORKING_DIR)
                    return i18n("Render All started in background... Check terminal/logs.")
                except Exception as e:
                    return i18n("Error starting render: {}").format(e)

            editor_render_all_btn.click(
                render_all, 
                inputs=[editor_project_dropdown, use_custom_subs] + manual_inputs, 
                outputs=editor_status
            )

            def export_all(project_name):
                if not project_name:
                    return i18n("No project selected.")
                proj_path = os.path.join(VIRALS_DIR, project_name)
                return editor.export_all_segments(proj_path)

            editor_export_all_btn.click(export_all, inputs=[editor_project_dropdown], outputs=editor_status)


        with gr.Tab(i18n("Library")):
            gr.Markdown(f"### {i18n('Existing Projects')}")
            with gr.Row():
                lib_query_input = gr.Textbox(label=i18n("Search by name"), placeholder=i18n("Type part of a project name"))
                lib_date_from_input = gr.Textbox(label=i18n("From date"), placeholder="YYYY-MM-DD")
                lib_date_to_input = gr.Textbox(label=i18n("To date"), placeholder="YYYY-MM-DD")
                lib_filter_btn = gr.Button(i18n("Filter"))
            with gr.Row():
                project_dropdown = gr.Dropdown(choices=library.get_existing_projects(), label="اختر مشروعًا", value=None)
                refresh_btn = gr.Button(i18n("Refresh List"))
            project_gallery_html = gr.HTML()
            refresh_btn.click(library.refresh_projects, outputs=project_dropdown)
            lib_filter_btn.click(library.filter_projects, inputs=[lib_query_input, lib_date_from_input, lib_date_to_input], outputs=project_dropdown)
            def on_select_project(proj_name): return library.generate_project_gallery(proj_name)
            project_dropdown.change(on_select_project, project_dropdown, project_gallery_html)
    

if __name__ == "__main__":
    import webbrowser
    import threading
    import time
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--colab", action="store_true", help="Run in Google Colab mode")
    args = parser.parse_args()

    if args.colab:
        print("Running in Colab mode. Generating public link with Static Mounts...")
        library.set_url_mode("fastapi")
        
        # Broaden allowed paths for Colab
        allowed_dirs = [VIRALS_DIR, WORKING_DIR, os.getcwd(), "."]
        
        # Explicitly set static paths
        try:
            gr.set_static_paths(paths=allowed_dirs)
            print(f"DEBUG: Registered static paths: {allowed_dirs}")
        except AttributeError:
            print("DEBUG: gr.set_static_paths not available")
        
        print(f"DEBUG: Allowed paths for Gradio: {allowed_dirs}")
        
        # Launch with prevent_thread_lock to allow mounting
        app, local_url, share_url = demo.queue().launch(
            share=True, 
            allowed_paths=allowed_dirs,
            prevent_thread_lock=True
        )
        
        # Mount the VIRALS directory explicitly
        app.mount("/virals", StaticFiles(directory=VIRALS_DIR), name="virals")
        print(f"Mounted /virals to {VIRALS_DIR}")
        
        demo.block_thread()
    else:
        # Check environment
        is_windows = (os.name == 'nt')
        
        library.set_url_mode("fastapi")
        allowed_dirs = [VIRALS_DIR, WORKING_DIR, os.getcwd(), "."]
        try:
            gr.set_static_paths(paths=allowed_dirs)
        except AttributeError: pass
        
        from fastapi.responses import FileResponse
        from fastapi import BackgroundTasks

        # Helper to attach routes to any FastAPI app (whether created by Gradio or us)
        def attach_extra_routes(fastapi_app):
            fastapi_app.mount("/virals", StaticFiles(directory=VIRALS_DIR), name="virals")
            
            @fastapi_app.get("/export_xml_api")
            def export_xml_api(project: str, segment: int, background_tasks: BackgroundTasks, format: str = "premiere"):
                try:
                    project_path = os.path.join(VIRALS_DIR, project)
                    script_path = os.path.join(WORKING_DIR, "scripts", "export_xml.py")
                    cmd = [sys.executable, script_path, "--project", project_path, "--segment", str(segment), "--format", format]
                    subprocess.run(cmd, check=True)
                    proj_name = os.path.basename(project_path)
                    zip_filename = f"export_{proj_name}_seg{segment}.zip"
                    file_path = os.path.join(project_path, zip_filename)
                    if os.path.exists(file_path):
                        return FileResponse(file_path, filename=zip_filename, media_type='application/zip')
                    else:
                        return {"error": f"File generation failed. Expected: {file_path}"}
                except Exception as e:
                    return {"error": str(e)}
            
            print(f"Mounted /virals to {VIRALS_DIR}")

        if is_windows:
            print("Running in Windows environment (using Gradio launch for convenience).")
            # Windows: Use demo.launch() for convenience (auto-browser, etc)
            app, local_url, share_url = demo.queue().launch(
                share=False, 
                allowed_paths=allowed_dirs, 
                inbrowser=True,
                server_name="0.0.0.0",
                server_port=7860,
                prevent_thread_lock=True
            )
            attach_extra_routes(app)
            demo.block_thread()
        else:
            print("Running in Linux/Container environment (using Uvicorn for stability).")
            # Linux/HF: Use Uvicorn for explicit loop control
            app = FastAPI()
            attach_extra_routes(app)
            # Disable SSR to prevent Node proxying issues on HF Spaces
            app = gr.mount_gradio_app(app, demo.queue(), path="/", allowed_paths=allowed_dirs, ssr_mode=False)
            uvicorn.run(app, host="0.0.0.0", port=7860)
