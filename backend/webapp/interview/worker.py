import replicate
import os
from datetime import datetime
import json
from .models import Interview


BASE_PROMPT = """
Based on the provided interview transcript and job description, conduct a stringent evaluation of the interviewee's responses. Concentrate particularly on identifying and critiquing instances where their answers fell short in relevance, clarity, or professionalism, and how they poorly aligned with the job requirements. Highlight and scrutinize any deficiencies in their knowledge or skills, and point out specific areas where their responses lacked depth or were overly general. Assess their communication for lack of precision. Examine their tonality for insufficient confidence or enthusiasm. Your analysis should incisively critique the interviewee's performance, underscoring significant weaknesses and pinpointing precise areas for improvement, while using the job description as a critical benchmark. Additionally, provide a total score out of 100, reflecting the overall performance of the interviewee in relation to the job criteria. Include 3-5 key bullet points as feedback that summarize the main areas of concern or suggested areas for improvement.

Ensure your response is in a proper JSON format and includes the following fields: `text`, `confidence`, `total_score`, and `key_points`.

Format your response as follows:

{{
"text": "[Provide a specific, detailed analysis and feedback, focusing on the interviewee's areas of weakness in about 200 words]",
"confidence": "[Evaluate the interviewee's level of confidence out of 100, offering a critical perspective]",
"total_score": "[Provide a total score out of 100, reflecting the overall interview performance]",
"key_points": [
"[First key point or area of concern]",
"[Second key point or area of concern]",
"[Third key point or area of concern]",
"... [Additional points if necessary]"
]
}}

Company Name:
{comapany_name}

Job Description:
{job_description}

Transcript:
{transcript}

"""

LLM_MODEL = "mistralai/mixtral-8x7b-instruct-v0.1"
TRANSCRIBE_MODEL = (
    "victor-upmeet/whisperx:449341d3543eeb95b79efd803c615a8751a2676dcac4b6b090d86df44db493cf"
)


def _print(text):
    print(f"{datetime.now()} | {text}")


def get_feedback(dir_path, comapany_name, job_description):
    with open(f"{dir_path}/transcript.txt", "r") as f:
        transcript = f.read()

    prompt = BASE_PROMPT.format(
        job_description=job_description,
        transcript=transcript,
        comapany_name=comapany_name,
    )
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

    try:
        resp = json.loads(resp)
    except:
        pass

    with open(f"{dir_path}/feedback.json", "w") as f:
        json.dump(resp, f)

    return resp


def get_transcript(audio_file):
    audio_file = audio_file.replace("output/", "")

    transcript = replicate.run(
        TRANSCRIBE_MODEL,
        input={
            "audio_file": f"https://verbose-tribble-p67wq9p45prc6vq4-7000.preview.app.github.dev/{audio_file}"
        },
    )

    transcript = "".join([i["text"] for i in transcript["segments"]])
    return transcript


def process_audio(output_dir, comapany_name, job_description):
    _print("Creating transcript...")
    get_transcript(output_dir)
    _print("Got transcript!")

    _print("Getting feedback...")
    get_feedback(output_dir, comapany_name, job_description)
    _print("Got feedback!")


def process_media(output_dir, interview):
    comapany_name = interview.company_name
    job_description = interview.job_description

    process_audio(output_dir, comapany_name, job_description)


if __name__ == "__main__":
    job_description = "N/A"
    comapany_name = "N/A"
    process_media("test", comapany_name, job_description)
