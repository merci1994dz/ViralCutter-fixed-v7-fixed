from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
from scripts import cut_json


def _parse_time_value(value, treat_int_as_ms=False):
    if isinstance(value, (int, float)):
        if treat_int_as_ms and isinstance(value, int):
            return value / 1000.0
        if isinstance(value, (int, float)) and value >= 1000 and treat_int_as_ms:
            return float(value) / 1000.0
        return float(value)

    try:
        return float(value)
    except Exception:
        parts = str(value).strip().split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        return 0.0


def _duration_to_seconds(duration):
    if isinstance(duration, (int, float)):
        return float(duration) / 1000.0 if float(duration) >= 1000 else float(duration)
    try:
        return float(duration)
    except Exception:
        return 0.0


def _detect_best_encoder():
    try:
        result = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
        output = result.stdout or ""
        if "h264_nvenc" in output:
            print("Encoder Detected: NVIDIA (h264_nvenc)")
            return "h264_nvenc", "p1", ["-b:v", "5M"]
        if "h264_amf" in output:
            print("Encoder Detected: AMD (h264_amf)")
            return "h264_amf", "quality", ["-b:v", "5M"]
        if "h264_qsv" in output:
            print("Encoder Detected: Intel QSV (h264_qsv)")
            return "h264_qsv", "veryfast", ["-b:v", "5M"]
        if "h264_videotoolbox" in output:
            print("Encoder Detected: Apple VideoToolbox (h264_videotoolbox)")
            return "h264_videotoolbox", "default", ["-b:v", "5M"]
    except Exception as e:
        print(f"Error checking encoders: {e}")

    print("Encoder Detected: CPU (libx264)")
    return "libx264", "ultrafast", ["-crf", "23"]


def _safe_duration(start_seconds, duration_seconds):
    start_seconds = max(0.0, float(start_seconds))
    duration_seconds = max(0.1, float(duration_seconds))
    return start_seconds, duration_seconds


def _process_segment(segment_index, segment, project_folder, input_file, cuts_folder, subs_folder, skip_video, video_codec, video_preset, video_extra_args):
    start_time = segment.get("start_time", segment.get("start", "00:00:00"))
    duration = segment.get("duration", 0)
    title = segment.get("title", f"Segment_{segment_index}")
    safe_title = "".join([c for c in title if c.isalnum() or c in " _-"]).strip().replace(" ", "_")[:60]
    base_name = f"{segment_index:03d}_{safe_title}"

    output_filename = f"{base_name}_original_scale.mp4"
    output_path = os.path.join(cuts_folder, output_filename)
    json_output_filename = f"{base_name}_processed.json"
    json_output_path = os.path.join(subs_folder, json_output_filename)

    start_time_seconds = _parse_time_value(start_time, treat_int_as_ms=True)
    duration_seconds = _duration_to_seconds(duration)
    start_time_seconds, duration_seconds = _safe_duration(start_time_seconds, duration_seconds)
    start_time_str = f"{start_time_seconds:.3f}"
    duration_str = f"{duration_seconds:.3f}"

    try:
        if not skip_video:
            command = [
                "ffmpeg",
                "-y",
                "-loglevel", "error",
                "-hide_banner",
                "-ss", start_time_str,
                "-i", input_file,
                "-t", duration_str,
                "-c:v", video_codec,
                "-preset", video_preset,
                *video_extra_args,
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                output_path,
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                print(f"Generated segment: {output_filename}, Size: {file_size} bytes")
        else:
            print(f"Skipping video generation for {output_filename} (using existing).")

        end_time_seconds = start_time_seconds + duration_seconds
        input_json_path = os.path.join(project_folder, "input.json")
        cut_json.cut_json_transcript(input_json_path, json_output_path, start_time_seconds, end_time_seconds)
        return {
            "index": segment_index,
            "ok": True,
            "output": output_filename,
            "json": json_output_filename,
        }
    except subprocess.CalledProcessError as e:
        print(f"Error executing ffmpeg for segment {segment_index + 1}: {e}")
        try:
            input_json_path = os.path.join(project_folder, "input.json")
            end_time_seconds = start_time_seconds + duration_seconds
            cut_json.cut_json_transcript(input_json_path, json_output_path, start_time_seconds, end_time_seconds)
        except Exception as json_error:
            print(f"Error generating JSON for segment {segment_index + 1}: {json_error}")
        return {
            "index": segment_index,
            "ok": False,
            "output": output_filename,
            "json": json_output_filename,
            "error": str(e),
        }
    except Exception as e:
        print(f"Error processing segment {segment_index + 1}: {e}")
        return {
            "index": segment_index,
            "ok": False,
            "output": output_filename,
            "json": json_output_filename,
            "error": str(e),
        }


def cut(segments, project_folder="tmp", skip_video=False, workers=None):
    def generate_segments(response, project_folder, skip_video, workers):
        input_file = os.path.join(project_folder, "input.mp4")
        if not os.path.exists(input_file):
            input_file_legacy = os.path.join(project_folder, "input_video.mp4")
            if os.path.exists(input_file_legacy):
                input_file = input_file_legacy
            else:
                print(f"Input file not found in {project_folder}")
                return

        cuts_folder = os.path.join(project_folder, "cuts")
        os.makedirs(cuts_folder, exist_ok=True)

        subs_folder = os.path.join(project_folder, "subs")
        os.makedirs(subs_folder, exist_ok=True)

        video_codec, video_preset, video_extra_args = _detect_best_encoder()
        segments_list = response.get("segments", [])
        if not segments_list:
            print("No segments to process.")
            return

        if workers is None or workers <= 0:
            cpu_count = os.cpu_count() or 4
            workers = max(1, min(len(segments_list), max(2, cpu_count // 2)))
        else:
            workers = max(1, workers)

        print(f"Processing {len(segments_list)} segments with {workers} worker(s)...")

        if workers == 1 or len(segments_list) == 1:
            for i, segment in enumerate(segments_list):
                result = _process_segment(i, segment, project_folder, input_file, cuts_folder, subs_folder, skip_video, video_codec, video_preset, video_extra_args)
                if result.get("ok"):
                    print("\n" + "=" * 50 + "\n")
            return

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_segment,
                    i,
                    segment,
                    project_folder,
                    input_file,
                    cuts_folder,
                    subs_folder,
                    skip_video,
                    video_codec,
                    video_preset,
                    video_extra_args,
                ): i
                for i, segment in enumerate(segments_list)
            }

            for future in as_completed(futures):
                result = future.result()
                if result.get("ok"):
                    print(f"Finished segment {result['index'] + 1}/{len(segments_list)}")
                else:
                    print(f"Segment {result['index'] + 1} failed: {result.get('error', 'Unknown error')}")
                print("\n" + "=" * 50 + "\n")

    if segments is None:
        json_path = os.path.join(project_folder, 'viral_segments.txt')
        with open(json_path, 'r', encoding='utf-8') as file:
            response = json.load(file)
    else:
        response = segments

    generate_segments(response, project_folder, skip_video, workers)
