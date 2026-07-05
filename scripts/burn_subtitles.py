import os
import subprocess
import sys


def _detect_best_encoder():
    try:
        result = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
        output = result.stdout or ""
        if "h264_nvenc" in output:
            return "h264_nvenc", "p1"
        if "h264_amf" in output:
            return "h264_amf", "quality"
        if "h264_qsv" in output:
            return "h264_qsv", "veryfast"
        if "h264_videotoolbox" in output:
            return "h264_videotoolbox", "default"
    except Exception:
        pass
    return "libx264", "ultrafast"


def burn_video_file(video_path, subtitle_path, output_path, prefer_hardware_acceleration=None):
    """Burn subtitles into a single video file with safe fallback handling."""
    subtitle_file_ffmpeg = subtitle_path.replace('\\', '/').replace(':', '\\:')

    def run_ffmpeg(encoder, preset, additional_args=None):
        additional_args = additional_args or []
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error", "-hide_banner",
            "-i", video_path,
            "-vf", f"subtitles='{subtitle_file_ffmpeg}'",
            "-c:v", encoder,
            "-preset", preset,
            "-b:v", "5M",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            output_path,
        ] + additional_args
        subprocess.run(cmd, check=True, capture_output=True)

    try:
        if prefer_hardware_acceleration is False:
            raise subprocess.CalledProcessError(1, ["ffmpeg"])

        encoder, preset = _detect_best_encoder()
        if encoder == "libx264":
            raise subprocess.CalledProcessError(1, ["ffmpeg"])
        run_ffmpeg(encoder, preset)
        return True, f"{encoder} Success"
    except subprocess.CalledProcessError as e:
        print(f"Hardware encoder failed ({str(e)}). Trying CPU libx264...")
        try:
            run_ffmpeg("libx264", "ultrafast")
            return True, "CPU Success"
        except subprocess.CalledProcessError as e2:
            err_msg = f"Fatal error burning subtitles for {os.path.basename(video_path)}: {e2}"
            if getattr(e2, 'stderr', None):
                err_msg += f" | FFmpeg Log: {e2.stderr.decode('utf-8', errors='replace')}"
            print(err_msg)
            return False, err_msg
    except Exception as e:
        return False, str(e)


def burn(project_folder="tmp", prefer_hardware_acceleration=None):
    if project_folder and not os.path.isabs(project_folder):
        project_folder_abs = os.path.abspath(project_folder)
    else:
        project_folder_abs = project_folder

    subs_folder = os.path.join(project_folder_abs, 'subs_ass')
    videos_folder = os.path.join(project_folder_abs, 'final')
    output_folder = os.path.join(project_folder_abs, 'burned_sub')

    os.makedirs(output_folder, exist_ok=True)

    if not os.path.exists(videos_folder):
        print(f"Final video folder not found: {videos_folder}")
        return

    files = os.listdir(videos_folder)
    if not files:
        print("No files found in final folder for subtitle burning.")
        return

    for video_file in files:
        if video_file.endswith(('.mp4', '.mkv', '.avi')):
            if "temp_video_no_audio" in video_file:
                continue

            video_name = os.path.splitext(video_file)[0]
            subtitle_file = os.path.join(subs_folder, f"{video_name}.ass")
            if not os.path.exists(subtitle_file):
                subtitle_file_processed = os.path.join(subs_folder, f"{video_name}_processed.ass")
                if os.path.exists(subtitle_file_processed):
                    subtitle_file = subtitle_file_processed

            if os.path.exists(subtitle_file):
                output_file = os.path.join(output_folder, f"{video_name}_subtitled.mp4")
                print(f"Burning: {video_name}...")
                success, msg = burn_video_file(os.path.join(videos_folder, video_file), subtitle_file, output_file, prefer_hardware_acceleration=prefer_hardware_acceleration)
                if success:
                    print(f"Done: {output_file}")
                else:
                    print(f"Fail: {msg}")
            else:
                print(f"Subtitle not found for: {video_name} at {subtitle_file}")
