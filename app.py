import os
import uuid
import subprocess
import requests

from flask import Flask, request, jsonify, send_file


app = Flask(__name__)


# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------

@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "Nex Archive Video Renderer is running"
    })


# ---------------------------------------------------------
# RENDER ENDPOINT
# ---------------------------------------------------------

@app.route("/render", methods=["GET", "POST"])
def render_video():

    # Enkel test i nettleseren
    if request.method == "GET":
        return jsonify({
            "status": "render endpoint is ready"
        })

    try:
        data = request.get_json(silent=True)

        if not data:
            return jsonify({
                "error": "No JSON body received"
            }), 400

        audio_url = data.get("audio_url")
        image_urls = data.get("image_urls", [])

        if not audio_url:
            return jsonify({
                "error": "audio_url is required"
            }), 400

        if not image_urls:
            return jsonify({
                "error": "image_urls is required"
            }), 400

        if not isinstance(image_urls, list):
            return jsonify({
                "error": "image_urls must be an array"
            }), 400

        # -------------------------------------------------
        # CREATE TEMP WORK DIRECTORY
        # -------------------------------------------------

        job_id = str(uuid.uuid4())

        workdir = os.path.join("/tmp", job_id)
        os.makedirs(workdir, exist_ok=True)

        audio_path = os.path.join(workdir, "audio.mp3")

        # -------------------------------------------------
        # DOWNLOAD AUDIO
        # -------------------------------------------------

        audio_response = requests.get(
            audio_url,
            timeout=180
        )

        audio_response.raise_for_status()

        with open(audio_path, "wb") as audio_file:
            audio_file.write(audio_response.content)

        # -------------------------------------------------
        # DOWNLOAD IMAGES
        # -------------------------------------------------

        image_paths = []

        for index, image_url in enumerate(image_urls):

            image_path = os.path.join(
                workdir,
                f"image_{index + 1:02d}.png"
            )

            image_response = requests.get(
                image_url,
                timeout=180
            )

            image_response.raise_for_status()

            with open(image_path, "wb") as image_file:
                image_file.write(image_response.content)

            image_paths.append(image_path)

        # -------------------------------------------------
        # READ AUDIO DURATION
        # -------------------------------------------------

        duration_result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_path
            ],
            capture_output=True,
            text=True,
            check=True
        )

        audio_duration = float(
            duration_result.stdout.strip()
        )

        if audio_duration <= 0:
            return jsonify({
                "error": "Could not determine audio duration"
            }), 500

        # Fordel bildene jevnt gjennom hele voiceoveren
        image_duration = audio_duration / len(image_paths)

        # -------------------------------------------------
        # CREATE CONCAT FILE
        # -------------------------------------------------

        concat_file = os.path.join(
            workdir,
            "images.txt"
        )

        with open(concat_file, "w") as concat:

            for image_path in image_paths:

                concat.write(
                    f"file '{image_path}'\n"
                )

                concat.write(
                    f"duration {image_duration}\n"
                )

            # FFmpeg concat trenger siste bilde én ekstra gang
            concat.write(
                f"file '{image_paths[-1]}'\n"
            )

        # -------------------------------------------------
        # OUTPUT FILE
        # -------------------------------------------------

        output_path = os.path.join(
            workdir,
            "output.mp4"
        )

        # -------------------------------------------------
        # FFMPEG
        # -------------------------------------------------

        ffmpeg_command = [
            "ffmpeg",
            "-y",

            "-f",
            "concat",

            "-safe",
            "0",

            "-i",
            concat_file,

            "-i",
            audio_path,

            "-vf",
            (
                "scale=1280:720:"
                "force_original_aspect_ratio=increase,"
                "crop=1280:720,"
                "fps=30,"
                "format=yuv420p"
            ),

            "-c:v",
            "libx264",

            "-preset",
            "veryfast",

            "-crf",
            "20",

            "-c:a",
            "aac",

            "-b:a",
            "192k",

            "-shortest",

            "-movflags",
            "+faststart",

            output_path
        ]

        subprocess.run(
            ffmpeg_command,
            check=True,
            capture_output=True,
            text=True
        )

        # -------------------------------------------------
        # VERIFY OUTPUT
        # -------------------------------------------------

        if not os.path.exists(output_path):
            return jsonify({
                "error": "FFmpeg did not create output video"
            }), 500

        if os.path.getsize(output_path) == 0:
            return jsonify({
                "error": "Output video is empty"
            }), 500

        # -------------------------------------------------
        # RETURN MP4 TO N8N
        # -------------------------------------------------

        return send_file(
            output_path,
            mimetype="video/mp4",
            as_attachment=True,
            download_name="nex_archive_episode.mp4"
        )

    except requests.RequestException as error:

        return jsonify({
            "error": "Media download failed",
            "details": str(error)
        }), 500

    except subprocess.CalledProcessError as error:

        return jsonify({
            "error": "FFmpeg failed",
            "details": error.stderr
        }), 500

    except Exception as error:

        return jsonify({
            "error": "Unexpected renderer error",
            "details": str(error)
        }), 500


# ---------------------------------------------------------
# START SERVER
# ---------------------------------------------------------

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )

