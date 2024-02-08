import replicate
import os
from datetime import datetime
import json


BASE_DIR = "output"
BASE_PROMPT = """
I have provided a transcript of an interview along with the job description. Please analyze the interviewee's responses with a focus on their relevance, clarity, professionalism, and alignment with the job requirements detailed in the job description. Highlight specific instances where the candidate demonstrated exceptional skills or knowledge, as well as any areas where the responses lacked depth or specificity. Evaluate the clarity and precision of their communication, noting any specific skills or qualifications that are missing, or any responses that were overly vague. Additionally, assess the tonality of the interviewee's responses to gauge their confidence and enthusiasm for the role. Provide a succinct analysis of the interviewee's performance, identifying distinct strengths and pinpointing precise areas for improvement. Your insights should offer a clear understanding of the interviewee's potential fit for the role, considering the job description as a guideline.

Limit your response to 100 words or less and reply in the following format:

{{
  "text": "[Your specific, detailed analysis and feedback]",
  "confidence": "[Evaluation of the interviewee's confidence level out of 100]"
}}

Job Description:
{job_description}

Transcript:
{transcript}"
"""

LLM_MODEL = "mistralai/mixtral-8x7b-instruct-v0.1"
TRANSCRIBE_MODEL = (
    "victor-upmeet/whisperx:449341d3543eeb95b79efd803c615a8751a2676dcac4b6b090d86df44db493cf"
)


def _print(text):
    print(f"{datetime.now()} | {text}")


def get_feedback(dir_path, job_description):
    transcript_json = json.load(open(f"{dir_path}/transcript.json"))
    transcript = "".join([i["text"] for i in transcript_json["segments"]])

    prompt = BASE_PROMPT.format(job_description=job_description, transcript=transcript)
    output = replicate.run(
        LLM_MODEL,
        input={
            "prompt": prompt,
            "max_new_tokens": 1000,
        },
    )

    resp = ""
    for i in output:
        resp += i

    with open(f"{dir_path}/feedback.json", "w") as f:
        json.dump(resp, f)

    return resp


def get_transcript(dir_path, audio_file):
    audio_file = audio_file.split("/")[1:]
    audio_file = "/".join(audio_file)

    transcript = replicate.run(
        TRANSCRIBE_MODEL,
        input={
            "audio_file": f"https://verbose-tribble-p67wq9p45prc6vq4-8000.preview.app.github.dev/{audio_file}"
        },
    )

    with open(f"{dir_path}/transcript.json", "w") as f:
        json.dump(transcript, f)

    return transcript


def main(input_file, job_description):
    process_no = os.listdir(BASE_DIR)

    try:
        process_no = max([int(i) for i in process_no] + [0]) + 1
    except ValueError:
        process_no = len(process_no) + 1

    _print(f"Processing #{process_no}: {input_file}")

    dir_path = os.path.join(BASE_DIR, str(process_no))
    os.mkdir(dir_path)
    audio_file = f"{dir_path}/audio.wav"

    # Extract audio from video
    print("Extracting audio...")
    video = VideoFileClip(input_file)
    video.audio.write_audiofile(audio_file, ffmpeg_params=["-ar", "16000"])
    print("Extracted audio!")

    _print("Creating transcript...")
    get_transcript(dir_path, audio_file)
    _print("Got transcript!")

    _print("Getting feedback...")
    get_feedback(dir_path, job_description)
    _print("Got feedback!")

    return dir_path


if __name__ == "__main__":
    video_file = "demo2.mp4"
    video_file = "demo3.MOV"
    job_description = "Not Available"
    main(video_file, job_description)
