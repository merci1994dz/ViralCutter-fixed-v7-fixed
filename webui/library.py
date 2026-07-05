import os
import json
import urllib.parse
import gradio as gr
import datetime
import time

# Setup Virals Dir relative to this file
# This file is in webui/library.py
# VIRALS dir is in ../VIRALS (root of project)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.append(BASE_DIR)
from i18n.i18n import I18nAuto
i18n = I18nAuto()

VIRALS_DIR = os.path.join(BASE_DIR, "VIRALS")


# URL Mode: "fastapi" (default) or "gradio"
URL_MODE = "fastapi"
_PROJECTS_CACHE = {"stamp": 0.0, "data": []}
_GALLERY_CACHE = {}
_GALLERY_CACHE_TTL = 2.0


def invalidate_caches():
    _PROJECTS_CACHE["stamp"] = 0.0
    _PROJECTS_CACHE["data"] = []
    _GALLERY_CACHE.clear()


def set_url_mode(mode):
    global URL_MODE
    URL_MODE = mode


def _dir_signature(path):
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0


def get_existing_projects(force_refresh=False):
    if not os.path.exists(VIRALS_DIR):
        return []
    now = time.time()
    if not force_refresh and _PROJECTS_CACHE["data"] and now - _PROJECTS_CACHE["stamp"] < _GALLERY_CACHE_TTL:
        return list(_PROJECTS_CACHE["data"])
    try:
        projects = []
        with os.scandir(VIRALS_DIR) as entries:
            for entry in entries:
                if entry.is_dir():
                    projects.append(entry.name)
        projects.sort(key=lambda x: os.path.getctime(os.path.join(VIRALS_DIR, x)), reverse=True)
        _PROJECTS_CACHE["stamp"] = now
        _PROJECTS_CACHE["data"] = list(projects)
        return projects
    except Exception:
        return list(_PROJECTS_CACHE["data"])


def refresh_projects():
    invalidate_caches()
    projs = get_existing_projects(force_refresh=True)
    return gr.update(choices=projs, value=projs[0] if projs else None)


def filter_projects(query="", date_from="", date_to=""):
    projects = get_existing_projects()
    q = (query or "").strip().lower()
    filtered = []
    for project in projects:
        if q and q not in project.lower():
            continue
        if date_from or date_to:
            try:
                ts = os.path.getctime(os.path.join(VIRALS_DIR, project))
                created = datetime.datetime.fromtimestamp(ts)
                if date_from:
                    df = datetime.datetime.fromisoformat(date_from)
                    if created < df:
                        continue
                if date_to:
                    dt = datetime.datetime.fromisoformat(date_to)
                    if created > dt:
                        continue
            except Exception:
                pass
        filtered.append(project)
    return gr.update(choices=filtered, value=filtered[0] if filtered else None)


def _find_segment_video(project_folder_path, seg, index):
    title = seg.get("title", f"{i18n('Segment')} {index+1}")
    video_path = seg.get("filepath", None)
    if video_path and os.path.exists(video_path):
        return video_path

    idx_str = f"{index:03d}"
    potential_paths = [
        os.path.join(project_folder_path, "burned_sub", f"final-output{idx_str}_processed_subtitled.mp4"),
        os.path.join(project_folder_path, "burned_sub", f"output{idx_str}.mp4"),
        os.path.join(project_folder_path, f"final-output{idx_str}_processed.mp4"),
        os.path.join(project_folder_path, f"output{idx_str}_original_scale.mp4"),
        os.path.join(project_folder_path, f"output{idx_str}.mp4"),
        os.path.join(project_folder_path, "cuts", f"output{idx_str}_original_scale.mp4"),
        os.path.join(project_folder_path, "cuts", f"segment_{idx_str}.mp4"),
        os.path.join(project_folder_path, "cuts", f"{idx_str}.mp4"),
    ]
    if isinstance(seg.get("filename"), str):
        potential_paths.insert(0, os.path.join(project_folder_path, seg["filename"]))
        potential_paths.insert(0, os.path.join(project_folder_path, "burned_sub", seg["filename"]))

    for path in potential_paths:
        if os.path.exists(path):
            return path

    for sd in [os.path.join(project_folder_path, "burned_sub"), os.path.join(project_folder_path, "cuts")]:
        if os.path.exists(sd):
            for filename in sorted(os.listdir(sd)):
                if filename.endswith(".mp4") and idx_str in filename:
                    return os.path.join(sd, filename)

    return None


def generate_project_gallery(project_path_name, is_full_path=False):
    """
    Generates HTML gallery for a given project folder using FastAPI Static Files mounting.
    """
    if not project_path_name:
        return f'<div style="padding: 20px; text-align: center;">{i18n("No project selected.")}</div>'
    
    if is_full_path:
        project_folder_path = project_path_name
    else:
        project_folder_path = os.path.join(VIRALS_DIR, project_path_name)

    if not os.path.exists(project_folder_path):
        return f'<div style="padding: 20px; text-align: center;">{i18n("Project path not found: {}").format(project_folder_path)}</div>'

    try:
        json_path = os.path.join(project_folder_path, "viral_segments.txt")
        folder_sig = (
            _dir_signature(project_folder_path),
            _dir_signature(json_path),
            URL_MODE,
        )
        cached = _GALLERY_CACHE.get(project_folder_path)
        if cached and cached.get("sig") == folder_sig:
            return cached["html"]

        segments_data = {}
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                segments_data = json.load(f)
        
        segments_list = segments_data.get("segments", [])
        
        if not segments_list:
             found_files = []
             for subdir in ["burned_sub", "cuts", "."]:
                 d = os.path.join(project_folder_path, subdir)
                 if os.path.exists(d):
                     for f in os.listdir(d):
                         if f.endswith(".mp4") and "input" not in f.lower():
                             found_files.append(os.path.join(d, f))
             found_files = sorted(list(set(found_files)))
             segments_list = [{"title": os.path.basename(f), "score": "N/A", "description": "No metadata found.", "filepath": f} for f in found_files]

        html_cards = ""
        
        for i, seg in enumerate(segments_list):
            title = seg.get("title", f"{i18n('Segment')} {i+1}")
            score = seg.get("score", "N/A")
            description = seg.get("description", i18n("No description available."))
            video_path = _find_segment_video(project_folder_path, seg, i)

            video_tag = ""
            download_link = ""
            export_link = ""
            if video_path:
                try:
                    abs_video = os.path.abspath(video_path)
                    
                    if URL_MODE == "gradio":
                        try:
                            cwd = os.getcwd()
                            abs_video_path = os.path.abspath(video_path)
                            rel_path = os.path.relpath(abs_video_path, cwd)
                            if not rel_path.startswith(".."):
                                final_path = rel_path.replace("\\", "/")
                            else:
                                final_path = abs_video_path.replace("\\", "/")
                            path_encoded = urllib.parse.quote(final_path, safe="/:")
                            video_src = f"/file/{path_encoded}"
                        except Exception:
                            video_src = ""

                        video_tag = f"""
                        <video controls preload="metadata" playsinline style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: contain;">
                            <source src="{video_src}" type="video/mp4">
                            Your browser does not support the video tag.
                        </video>
                        """
                        download_link = f'<a href="{video_src}" target="_blank" download="{os.path.basename(video_path)}" style="color: #aaa; display: flex; align-items: center; justify-content: center; padding: 5px; border-radius: 50%; transition: color 0.2s;" title="Download" onmouseover="this.style.color=\'#fff\'" onmouseout="this.style.color=\'#aaa\'"><svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg></a>'
                    else:
                        abs_virals = os.path.abspath(VIRALS_DIR)
                        if abs_video.startswith(abs_virals):
                            rel_path = os.path.relpath(abs_video, abs_virals)
                            url_path = urllib.parse.quote(rel_path.replace("\\", "/"))
                            timestamp = int(time.time())
                            video_src = f"/virals/{url_path}?t={timestamp}"
                            video_tag = f"""
                            <video controls preload="metadata" playsinline style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: contain;">
                                <source src="{video_src}" type="video/mp4">
                                Your browser does not support the video tag.
                            </video>
                            """
                            download_link = f'<a href="{video_src}" download="{os.path.basename(video_path)}" style="color: #aaa; display: flex; align-items: center; justify-content: center; padding: 5px; border-radius: 50%; transition: color 0.2s;" title="Download" onmouseover="this.style.color=\'#fff\'" onmouseout="this.style.color=\'#aaa\'"><svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg></a>'
                            proj_name_api = os.path.basename(project_path_name)
                            def make_export_btn(fmt, label, color_hover, svg_path):
                                src = f"/export_xml_api?project={proj_name_api}&segment={i}&format={fmt}"
                                return f'<a href="{src}" target="_blank" style="color: #aaa; display: flex; align-items: center; justify-content: center; padding: 5px; border-radius: 50%; transition: color 0.2s;" title="{label}" onmouseover="this.style.color=\'{color_hover}\'" onmouseout="this.style.color=\'#aaa\'"><svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{svg_path}</svg></a>'

                            export_pr = make_export_btn("premiere", "Export Premiere XML (Split Screen – known bug)", "#d064ff", '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><path d="M9 15h6"></path><path d="M12 12v6"></path>')
                            export_link = f"{export_pr}"
                        else:
                            video_tag = f'<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; background: #222; color: #666;"><span>⚠️</span><br>{i18n("External Video")}</div>'
                except Exception as e:
                    video_tag = f'<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; background: #222; color: #666;"><span>⚠️</span><br>{i18n("Error: {}").format(str(e))}</div>'
            else:
                video_tag = f'<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; background: #222; color: #666;"><span>⚠️</span><br>{i18n("Not Found")}</div>'
            
            score_color = "#22c55e"
            try:
                if isinstance(score, int) or (isinstance(score, str) and score.isdigit()):
                    val = int(score)
                    if val < 70: score_color = "#ef4444" 
                    elif val < 85: score_color = "#eab308"
            except Exception:
                pass

            card_html = f"""
            <div style="display: flex; flex-direction: column; background: transparent; overflow: visible;">
                <div style="position: relative; width: 100%; padding-top: 177.77%; background: #111; border-radius: 12px; overflow: hidden; margin-bottom: 12px; border: 1px solid #333; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
                    {video_tag}
                </div>
                <div style="display: flex; flex-direction: column; gap: 6px; padding: 0 4px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 28px; font-weight: 900; line-height: 1; color: {score_color}; font-family: sans-serif;">{score}</span>
                        <div style="display: flex; align-items: center; gap: 4px;">
                            {export_link}
                            {download_link}
                        </div>
                    </div>
                    <h4 style="margin: 4px 0 0 0; color: #e5e5e5; font-size: 15px; font-weight: 600; line-height: 1.4; font-family: sans-serif; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; text-align: center;" title="{title}">{title}</h4>
                </div>
            </div>
            """
            html_cards += card_html
        
        if not html_cards:
             return f'<div style="padding: 40px; text-align: center; color: #888; font-size: 1.2em;">{i18n("No viral segments found.")}</div>'

        html = f"""
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 30px; width: 100%; padding: 10px 0;">
            {html_cards}
        </div>
        """
        _GALLERY_CACHE[project_folder_path] = {"sig": folder_sig, "html": html, "ts": time.time()}
        return html

    except Exception as e:
        return i18n("Error loading gallery: {}").format(e)
