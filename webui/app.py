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

def _safe_int(value, default):
    try:
        return int(value)
    except Exception:
        return default

def _safe_float(value, default):
    try:
        return float(value)
    except Exception:
        return default

def _normalize_path(path):
    if not path:
        return path
    return os.path.normpath(str(path))

def _build_subtitle_config(font_name, font_size, font_color, highlight_color, outline_color, outline_thickness, shadow_color, shadow_size, is_bold, is_italic, is_uppercase, vertical_pos, alignment, h_size, w_block, gap, mode, under, strike, border_s, remove_punc):
    return {
        "font": font_name,
        "base_size": _safe_int(font_size, 12),
        "base_color": convert_color_to_ass(font_color),
        "highlight_color": convert_color_to_ass(highlight_color),
        "outline_color": convert_color_to_ass(outline_color),
        "outline_thickness": _safe_float(outline_thickness, 1.5),
        "shadow_color": convert_color_to_ass(shadow_color),
        "shadow_size": _safe_float(shadow_size, 2),
        "vertical_position": _safe_int(vertical_pos, 210),
        "alignment": _safe_int(alignment, 2),
        "bold": 1 if is_bold else 0,
        "italic": 1 if is_italic else 0,
        "underline": 1 if under else 0,
        "strikeout": 1 if strike else 0,
        "border_style": _safe_int(border_s, 1),
        "words_per_block": _safe_int(w_block, 3),
        "gap_limit": _safe_float(gap, 0.5),
        "mode": mode,
        "highlight_size": _safe_int(h_size, 14),
        "uppercase": 1 if is_uppercase else 0,
        "remove_punctuation": bool(remove_punc),
    }

def run_viral_cutter(input_source, project_name, url, video_file, segments, viral, themes, min_duration, max_duration, model, ai_backend, api_key, ai_model_name, chunk_size, workflow, face_model, face_mode, face_detect_interval, no_face_mode, 
                     face_filter_thresh, face_two_thresh, face_conf_thresh, face_dead_zone, focus_active_speaker, active_speaker_mar, active_speaker_score_diff, include_motion, active_speaker_motion_threshold, active_speaker_motion_sensitivity, active_speaker_decay,
                     use_custom_subs, font_name, font_size, font_color, highlight_color, outline_color, outline_thickness, shadow_color, shadow_size, is_bold, is_italic, is_uppercase, vertical_pos, alignment,
                     h_size, w_block, gap, mode, under, strike, border_s, remove_punc, video_quality, use_youtube_subs, translate_target):
    
    global current_process
    progress_state = empty_progress_state(i18n("Starting"))
    error_items = []
    logs = []

    def fail(message, *, keep_start_enabled=False):
        error_items.append(message)
        progress_state["current"] = message
        return (
            "\n".join(logs + [f"ERROR: {message}"]),
            gr.update(value=i18n("Start Processing"), interactive=True),
            gr.update(visible=False, interactive=not keep_start_enabled),
            None,
            render_progress_html(progress_state),
            render_tasks_html(progress_state),
            render_error_html(error_items),
        )

    def set_progress(stage, percent, message):
        progress_state[stage] = {"percent": int(percent), "message": message}
        progress_state["current"] = message
        progress_state["overall"] = int(sum(progress_state[s]["percent"] for s in PROGRESS_ORDER) / len(PROGRESS_ORDER))

    def emit_log(message):
        logs.append(message)
        return "\n".join(logs)

    try:
        set_progress("download", 0, i18n("Preparing"))
        emit_log(i18n("Preparing run..."))
        yield "", gr.update(value=i18n("Running..."), interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)

        cmd = [sys.executable, MAIN_SCRIPT_PATH]
        input_source = input_source or "YouTube URL"
        workflow = workflow or "Full"
        ai_backend = ai_backend or "manual"
        face_mode = face_mode or "auto"
        no_face_mode = no_face_mode or "padding"

        if input_source == "Existing Project":
            if not project_name:
                yield fail(i18n("Error: No project selected."))
                return
            full_project_path = os.path.join(VIRALS_DIR, project_name)
            if not os.path.exists(full_project_path):
                yield fail(i18n("Error: Project path not found."))
                return
            cmd.extend(["--project-path", full_project_path])
        elif input_source == "Upload Video":
            if not video_file:
                yield fail(i18n("Error: No video file uploaded."))
                return
            original_filename = os.path.basename(video_file)
            name_no_ext = os.path.splitext(original_filename)[0]
            safe_name = "".join([c for c in name_no_ext if c.isalnum() or c in " _-"]).strip() or "Untitled_Upload"
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            project_name_upload = f"{safe_name}_{timestamp}"
            project_path = os.path.join(VIRALS_DIR, project_name_upload)
            os.makedirs(project_path, exist_ok=True)
            target_path = os.path.join(project_path, "input.mp4")
            shutil.copy2(video_file, target_path)
            cmd.extend(["--project-path", project_path, "--skip-youtube-subs"])
            emit_log(f"Copied upload to {target_path}")
        else:
            if url:
                cmd.extend(["--url", url])
            else:
                yield fail(i18n("Error: No URL provided."))
                return
            if video_quality:
                cmd.extend(["--video-quality", video_quality])
            if not use_youtube_subs:
                cmd.append("--skip-youtube-subs")

        if translate_target and translate_target != "None":
            cmd.extend(["--translate-target", translate_target])

        cmd.extend(["--segments", str(_safe_int(segments, 3))])
        if viral:
            cmd.append("--viral")
        if themes:
            cmd.extend(["--themes", themes])
        cmd.extend(["--min-duration", str(_safe_int(min_duration, 15))])
        cmd.extend(["--max-duration", str(_safe_int(max_duration, 90))])
        cmd.extend(["--model", model or "large-v3-turbo"])
        cmd.extend(["--ai-backend", ai_backend])
        if api_key:
            cmd.extend(["--api-key", api_key])
        if ai_model_name:
            cmd.extend(["--ai-model-name", str(ai_model_name)])
        if chunk_size not in (None, ""):
            cmd.extend(["--chunk-size", str(_safe_int(chunk_size, 70000))])

        workflow_map = {"Full": "1", "Cut Only": "2", "Subtitles Only": "3"}
        cmd.extend(["--workflow", workflow_map.get(workflow, "1")])
        cmd.extend(["--face-model", face_model])
        cmd.extend(["--face-mode", face_mode])
        if face_detect_interval:
            cmd.extend(["--face-detect-interval", str(face_detect_interval)])
        if no_face_mode:
            cmd.extend(["--no-face-mode", no_face_mode])

        if face_filter_thresh is not None:
            cmd.extend(["--face-filter-threshold", str(face_filter_thresh)])
        if face_two_thresh is not None:
            cmd.extend(["--face-two-threshold", str(face_two_thresh)])
        if face_conf_thresh is not None:
            cmd.extend(["--face-confidence-threshold", str(face_conf_thresh)])
        if face_dead_zone is not None:
            cmd.extend(["--face-dead-zone", str(face_dead_zone)])

        cmd.append("--skip-prompts")
        if focus_active_speaker:
            cmd.append("--focus-active-speaker")
            if active_speaker_mar is not None:
                cmd.extend(["--active-speaker-mar", str(active_speaker_mar)])
            if active_speaker_score_diff is not None:
                cmd.extend(["--active-speaker-score-diff", str(active_speaker_score_diff)])
            if include_motion:
                cmd.append("--include-motion")
            if active_speaker_motion_threshold is not None:
                cmd.extend(["--active-speaker-motion-threshold", str(active_speaker_motion_threshold)])
            if active_speaker_motion_sensitivity is not None:
                cmd.extend(["--active-speaker-motion-sensitivity", str(active_speaker_motion_sensitivity)])
            if active_speaker_decay is not None:
                cmd.extend(["--active-speaker-decay", str(active_speaker_decay)])

        if use_custom_subs:
            subtitle_config = _build_subtitle_config(
                font_name, font_size, font_color, highlight_color, outline_color,
                outline_thickness, shadow_color, shadow_size, is_bold, is_italic,
                is_uppercase, vertical_pos, alignment, h_size, w_block, gap, mode,
                under, strike, border_s, remove_punc,
            )
            subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
            with open(subtitle_config_path, "w", encoding="utf-8") as f:
                json.dump(subtitle_config, f, indent=4)
            cmd.extend(["--subtitle-config", subtitle_config_path])

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
        debug_cmd = " ".join([str(x) for x in cmd if x])
        emit_log(f"Command: {debug_cmd}")
        yield "\n".join(logs), gr.update(value=i18n("Running..."), interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)

        current_process = subprocess.Popen(
            cmd,
            cwd=WORKING_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env,
        )
        project_folder_path = None
        last_update_time = time.time()
        last_progress_tick = 0.0
        current_stage = None
        current_buffer = []

        while True:
            line = current_process.stdout.readline()
            if not line and current_process.poll() is not None:
                break
            if not line:
                continue

            line = line.rstrip("\n")
            if line.startswith("PROGRESS|"):
                try:
                    _, stage, percent, message = line.split("|", 3)
                    if stage in progress_state:
                        progress_state[stage] = {"percent": int(percent), "message": message}
                        progress_state["current"] = message
                        progress_state["overall"] = int(sum(progress_state[s]["percent"] for s in PROGRESS_ORDER) / len(PROGRESS_ORDER))
                    current_stage = stage
                    last_progress_tick = time.time()
                except Exception as e:
                    error_items.append(f"Bad progress line: {e}")
                continue

            current_buffer.append(line)
            if len(current_buffer) > 200:
                current_buffer = current_buffer[-200:]
            logs.append(line)
            if "Project Folder:" in line:
                parts = line.split("Project Folder:")
                if len(parts) > 1:
                    project_folder_path = parts[1].strip()

            current_time = time.time()
            if current_time - last_update_time > 0.2:
                yield "\n".join(logs), gr.update(visible=True, interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
                last_update_time = current_time

        return_code = current_process.poll()
        if return_code not in (0, None):
            tail = "\n".join(current_buffer[-30:])
            if tail:
                error_items.append(f"Process exited with code {return_code}.\n{tail}")
            else:
                error_items.append(f"Process exited with code {return_code}.")
            yield "\n".join(logs), gr.update(value=i18n("Start Processing"), interactive=True), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
            return

        yield "\n".join(logs), gr.update(visible=True, interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
    except FileNotFoundError as e:
        yield fail(f"{i18n('Error: Missing file or tool.')} {e}")
        return
    except subprocess.CalledProcessError as e:
        yield fail(f"{i18n('Error: Process failed.')} {e}")
        return
    except Exception as e:
        error_items.append(f"Error running process: {str(e)}")
        yield "\n".join(logs + [f"Error running process: {str(e)}"]), gr.update(visible=True, interactive=False), gr.update(visible=True, interactive=True), None, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)
    finally:
        if current_process:
            if current_process.stdout:
                try:
                    current_process.stdout.close()
                except Exception:
                    pass
            if current_process.poll() is None:
                try:
                    current_process.terminate()
                    current_process.wait(timeout=5)
                except Exception:
                    try:
                        current_process.kill()
                    except Exception:
                        pass
            current_process = None
        time.sleep(0.5)
        if use_custom_subs:
            try:
                subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
                if os.path.exists(subtitle_config_path):
                    os.remove(subtitle_config_path)
            except Exception:
                pass

    html_output = ""
    if project_folder_path and os.path.exists(project_folder_path):
        html_output = library.generate_project_gallery(project_folder_path, is_full_path=True)
    else:
        html_output = f"<h3>{i18n('Error: Project folder could not be determined from logs.')}</h3>"
    set_progress("done", 100, i18n("Completed"))
    yield "\n".join(logs), gr.update(value=tr("Start Processing"), interactive=True), gr.update(visible=True, interactive=False), html_output, render_progress_html(progress_state), render_tasks_html(progress_state), render_error_html(error_items)

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
                        if source == "Upload Video":
                            return gr.update(visible=False), gr.update(visible=False), gr.update(visible=True), gr.update(value="Full"), gr.update(visible=True)
                        projs = library.refresh_projects().kwargs.get("choices", []) if hasattr(library.refresh_projects(), "kwargs") else library.get_existing_projects(force_refresh=True)
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
                    with gr.Row():
                        ai_model_input = gr.Dropdown(choices=GEMINI_MODELS, label="نموذج الذكاء الاصطناعي", value=GEMINI_MODELS[1], allow_custom_value=True, visible=True, scale=5)
                        refresh_models_btn = gr.Button("🔄", size="sm", visible=False, scale=0, min_width=50)
                        chunk_size_input = gr.Number(label="حجم الجزء", value=70000, precision=0, scale=2)

                    def update_ai_ui(backend):
                        show_api = (backend == "gemini")
                        show_refresh = (backend == "local")
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
                        else:
                            new_choices = ai_model_input.choices or []
                            new_val = ai_model_input.value
                            new_chunk = chunk_size_input.value
                        return gr.update(visible=show_api), gr.update(choices=new_choices, value=new_val, visible=(backend != "manual")), gr.update(visible=show_refresh), gr.update(value=new_chunk)

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
                    input_source.change(on_source_change, inputs=input_source, outputs=[url_input, project_selector, video_upload, workflow_input, upload_hint])

                with gr.Row():
                    logs_output = gr.Textbox(label="السجل", lines=14, autoscroll=True, elem_id="logs_output")
                    logs_output.change(fn=None, inputs=[], outputs=[], js="function() { var ta = document.querySelector('#logs_output textarea'); if (ta) { if (!ta._scrollerSetup) { ta._isSticky = true; ta.addEventListener('scroll', function() { var diff = ta.scrollHeight - ta.scrollTop - ta.clientHeight; ta._isSticky = diff <= 50; }); ta._scrollerSetup = true; } if (ta._isSticky === undefined || ta._isSticky === true) { ta.scrollTop = ta.scrollHeight; } } }")
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
                preset_input.change(subs.apply_preset, inputs=[preset_input], outputs=manual_inputs)
                for inp in manual_inputs:
                    inp.change(subs.generate_preview_html, inputs=manual_inputs, outputs=preview_html)
                preview_vid_btn.click(subs.render_preview_video, inputs=manual_inputs, outputs=preview_vid)
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
                editor_status = gr.Textbox(label="الحالة", interactive=False)
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
                if not proj_name:
                    return gr.update(choices=[])
                proj_path = os.path.join(VIRALS_DIR, proj_name)
                files = editor.list_editable_files(proj_path)
                return gr.update(choices=files, value=files[0] if files else None)

            editor_project_dropdown.change(update_file_list, inputs=editor_project_dropdown, outputs=editor_status)

            def preview_row(json_path, dataframe):
                if not json_path or not dataframe:
                    return None, i18n("No row selected.")
                row_index = 0
                video_path, msg = editor.build_preview_clip(json_path, int(row_index))
                return video_path, msg

            def render_single(json_path, use_custom, font_name, font_size, font_color, highlight_color, 
                              outline_color, outline_thickness, shadow_color, shadow_size, 
                              is_bold, is_italic, is_uppercase, 
                              h_size, w_block, gap, mode, under, strike, border_s, 
                              vertical_pos, alignment, remove_punc):
                if not json_path:
                    return i18n("No file loaded.")
                subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
                if use_custom:
                    subtitle_config = _build_subtitle_config(font_name, font_size, font_color, highlight_color, outline_color, outline_thickness, shadow_color, shadow_size, is_bold, is_italic, is_uppercase, vertical_pos, alignment, h_size, w_block, gap, mode, under, strike, border_s, remove_punc)
                    with open(subtitle_config_path, "w", encoding="utf-8") as f:
                        json.dump(subtitle_config, f, indent=4)
                else:
                    try:
                        if os.path.exists(subtitle_config_path):
                            os.remove(subtitle_config_path)
                    except Exception:
                        pass
                return editor.render_specific_video(json_path)

            editor_render_single_btn.click(render_single, inputs=[current_json_path, use_custom_subs] + manual_inputs, outputs=editor_status)

            def render_all(proj_name, use_custom, font_name, font_size, font_color, highlight_color, 
                           outline_color, outline_thickness, shadow_color, shadow_size, 
                           is_bold, is_italic, is_uppercase, 
                           h_size, w_block, gap, mode, under, strike, border_s, 
                           vertical_pos, alignment, remove_punc):
                if not proj_name:
                    return i18n("No project selected.")
                if use_custom:
                    subtitle_config = _build_subtitle_config(font_name, font_size, font_color, highlight_color, outline_color, outline_thickness, shadow_color, shadow_size, is_bold, is_italic, is_uppercase, vertical_pos, alignment, h_size, w_block, gap, mode, under, strike, border_s, remove_punc)
                    subtitle_config_path = os.path.join(WORKING_DIR, "temp_subtitle_config.json")
                    with open(subtitle_config_path, "w", encoding="utf-8") as f:
                        json.dump(subtitle_config, f, indent=4)
                proj_path = os.path.join(VIRALS_DIR, proj_name)
                cmd = [sys.executable, MAIN_SCRIPT_PATH, "--project-path", proj_path, "--workflow", "3", "--skip-prompts"]
                if use_custom and os.path.exists(os.path.join(WORKING_DIR, "temp_subtitle_config.json")):
                    cmd.extend(["--subtitle-config", os.path.join(WORKING_DIR, "temp_subtitle_config.json")])
                try:
                    subprocess.Popen(cmd, cwd=WORKING_DIR)
                    return i18n("Render All started in background... Check terminal/logs.")
                except Exception as e:
                    return i18n("Error starting render: {}").format(e)

            editor_render_all_btn.click(render_all, inputs=[editor_project_dropdown, use_custom_subs] + manual_inputs, outputs=editor_status)

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
                project_dropdown = gr.Dropdown(choices=library.get_existing_projects(force_refresh=True), label="اختر مشروعًا", value=None)
                refresh_btn = gr.Button(i18n("Refresh List"))
            project_gallery_html = gr.HTML()
            refresh_btn.click(library.refresh_projects, outputs=project_dropdown)
            lib_filter_btn.click(library.filter_projects, inputs=[lib_query_input, lib_date_from_input, lib_date_to_input], outputs=project_dropdown)
            def on_select_project(proj_name): return library.generate_project_gallery(proj_name)
            project_dropdown.change(on_select_project, project_dropdown, project_gallery_html)
    

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--colab", action="store_true", help="Run in Google Colab mode")
    args = parser.parse_args()

    if args.colab:
        print("Running in Colab mode. Generating public link with Static Mounts...")
        library.set_url_mode("fastapi")
        allowed_dirs = [VIRALS_DIR, WORKING_DIR, os.getcwd(), "."]
        try:
            gr.set_static_paths(paths=allowed_dirs)
        except AttributeError:
            pass
        app, local_url, share_url = demo.queue().launch(
            share=True,
            allowed_paths=allowed_dirs,
            prevent_thread_lock=True,
        )
        app.mount("/virals", StaticFiles(directory=VIRALS_DIR), name="virals")
        demo.block_thread()
    else:
        is_windows = (os.name == 'nt')
        library.set_url_mode("fastapi")
        allowed_dirs = [VIRALS_DIR, WORKING_DIR, os.getcwd(), "."]
        try:
            gr.set_static_paths(paths=allowed_dirs)
        except AttributeError:
            pass
        from fastapi.responses import FileResponse
        from fastapi import BackgroundTasks

        def attach_extra_routes(fastapi_app):
            fastapi_app.mount("/virals", StaticFiles(directory=VIRALS_DIR), name="virals")
            @fastapi_app.get("/export_xml_api")
            def export_xml_api(project: str, segment: int, background_tasks: BackgroundTasks, format: str = "premiere"):
                try:
                    project_path = os.path.join(VIRALS_DIR, project)
                    script_path = os.path.join(WORKING_DIR, "scripts", "export_xml.py")
                    if not os.path.exists(project_path):
                        return {"error": "Project not found."}
                    if not os.path.exists(script_path):
                        return {"error": "Export script not found."}
                    cmd = [sys.executable, script_path, "--project", project_path, "--segment", str(segment), "--format", format]
                    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
                    if result.returncode != 0:
                        return {"error": result.stderr.strip() or result.stdout.strip() or "Export failed."}
                    proj_name = os.path.basename(project_path)
                    zip_filename = f"export_{proj_name}_seg{segment}.zip"
                    file_path = os.path.join(project_path, zip_filename)
                    if os.path.exists(file_path):
                        return FileResponse(file_path, filename=zip_filename, media_type='application/zip')
                    return {"error": f"File generation failed. Expected: {file_path}"}
                except Exception as e:
                    return {"error": str(e)}
            print(f"Mounted /virals to {VIRALS_DIR}")

        if is_windows:
            print("Running in Windows environment (using Gradio launch for convenience).")
            app, local_url, share_url = demo.queue().launch(
                share=False,
                allowed_paths=allowed_dirs,
                inbrowser=True,
                server_name="0.0.0.0",
                server_port=7860,
                prevent_thread_lock=True,
            )
            attach_extra_routes(app)
            demo.block_thread()
        else:
            print("Running in Linux/Container environment (using Uvicorn for stability).")
            app = FastAPI()
            attach_extra_routes(app)
            app = gr.mount_gradio_app(app, demo.queue(), path="/", allowed_paths=allowed_dirs, ssr_mode=False)
            uvicorn.run(app,
                host="0.0.0.0",
                port=7860,
                log_level="info",
            )
