import os
import uuid
import subprocess
import requests
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

@app.get("/")
def health():
    return {"status": "Nex Archive Video Renderer is running"}

@app.post("/render")
def render_video():
    data = request.get_json()

    audio_url = data.get("audio_url")
    image_urls = data.get("image_urls", [])

    if not audio_url or not image_urls:
        return jsonify({"error": "audio_url and image_urls are required"}), 400

    job_id = str(uuid.uuid4())
    workdir = f"/tmp/{job_id}"
    os.makedirs(workdir, exist_ok=True)

    audio_path = os.path.join(workdir, "audio.mp3")

    r = requests.get(audio_url, timeout=120)
    r.raise_for_status()

    with open(audio_path, "wb") as f:
        f.write(r.content)

    image_paths = []

    for i, url in enumerate(image_urls):
        path = os.path.join(workdir, f"image_{i:02d}.png")

        r = requests.get(url, timeout=120)
        r.raise_for_status()

        with open(path, "wb") as f:
            f.write(r.content)

        image_paths.append(path)

    duration_result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path
        ],
        capture_output=True,
        text=True,
        check=True
    )

    audio_duration = float(duration_result.stdout.strip())
    image_duration = audio_duration / len(image_paths)

    concat_file = os.path.join(workdir, "images.txt")

    with open(concat_file, "w") as f:
        for path in image_paths:
            f.write(f"file '{path}'\n")
            f.write(f"duration {image_duration}\n")

        f.write(f"file '{image_paths[-1]}'\n")

    output_path = os.path.join(workdir, "output.mp4")

    command = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-i", audio_path,
        "-vf",
        "scale=1280:720:force_original_aspect_ratio=increase,"
        "crop=1280:720,"
        "fps=30,"
        "format=yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        output_path
    ]

    subprocess.run(command, check=True)

    return send_file(
        output_path,
        mimetype="video/mp4",
        as_attachment=True,
        download_name="nex_archive_episode.mp4"
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

