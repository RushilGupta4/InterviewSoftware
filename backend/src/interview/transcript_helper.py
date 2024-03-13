import os
import requests

url = f'{os.environ.get("WHISPER_SERVICE_URL", "http://localhost:5000")}/predictions'
base_output_url = os.environ.get("WEB_SERVICE_URL", "http://host.docker.internal:6000/")


def get_transcript(audio_path):
    audio_file = f"{base_output_url}/{audio_path}"

    response = requests.post(
        url, json={"input": {"audio_file": audio_file, "batch_size": 16, "language": "en"}}
    )
    if response.status_code == 200:
        try:

            transcript = response.json()
            transcript = "".join([i["text"] for i in transcript["output"]["segments"]]).strip()
            return transcript
        except:
            pass

    # TODO: What to do when transcript fails
    return ""


if __name__ == "__main__":
    t = get_transcript(
        "https://verbose-tribble-p67wq9p45prc6vq4-8000.preview.app.github.dev/audio.wav"
    )
    print(t)
