import copy
import json
from datetime import datetime
import os
import time
import io
import base64

import jwt
import torch
import socketio
import ffmpeg
import numpy as np
import asyncio
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async
from gtts import gTTS

from interview.models import Interview
from interview.views import JWT_ALGORITHM
from .transcript_helper import get_transcript
from users.models import User
from .openai_client import OpenAIClient
from .utils import MediaBuffer, Chat

# Load Silero VAD model and utilities
model, utils = torch.hub.load(
    repo_or_dir="snakers4/silero-vad",
    model="silero_vad",
    force_reload=False,
    onnx=False,
)
(_, _, _, VADIterator, _) = utils

# Constants
SAMPLING_RATE = 16000
WINDOW_SIZE_SAMPLES = 1536  # Number of samples in a single audio chunk

# mgr = socketio.AsyncRedisManager("redis://0.0.0.0:6379/0")
mgr = socketio.AsyncManager()
sio = socketio.AsyncServer(client_manager=mgr, async_mode="asgi", cors_allowed_origins="*")


class ConnectionHandler:
    def __init__(self, sid, interview: Interview, user: User):

        # Set the time gap threshold in seconds
        self.threshold = 5

        # Store important details
        self.sid = sid
        self.interview_id = "test"
        self.user_name = f"{user.first_name} {user.last_name}"

        self.output_dir = f"output/{self.interview_id}-{sid}"

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # Initialize buffers
        self.tmp_audio_buffer = np.array([], dtype=np.float32)
        self.current_question_audio_buffer = MediaBuffer(SAMPLING_RATE)
        self.total_audio_buffer = MediaBuffer(SAMPLING_RATE)
        self.total_video_bytes = MediaBuffer(SAMPLING_RATE)

        # Initialize VAD iterator
        self.vad_iterator = VADIterator(model)
        self.last_vad_time = None
        self.getting_next_question = False

        # Create an event for time gap checking
        self.running = True
        self.check_gap_task = None

        # Chats
        self.chats = []

        self.openai_client = OpenAIClient()

        interview_done, first_question = self.openai_client.get_question(
            f"Company Name: {interview.company_name}\nJob Description: {interview.job_description}\n Candidate Name: {self.user_name}"
        )
        first_chat = Chat(first_question, "assistant", interview_done)
        self.chats.append(first_chat)

    async def on_connect(self):
        print("Client connected:", self.sid)

        self.check_gap_task = asyncio.create_task(self.check_time_gap())
        first_chat = self.chats[0]
        await self.send_chat(first_chat)

    async def on_disconnect(self):
        print("Client disconnected:", self.sid)

        # Kill the thread
        self.running = False
        if self.check_gap_task:  # Ensure there's a task to cancel
            self.check_gap_task.cancel()
            try:
                await self.check_gap_task  # Await the task to handle the cancellation
            except asyncio.CancelledError:
                pass  # Task cancellation will raise CancelledError, which can be ignored

        # Save the audio to a wav file
        wav_file = f"{self.output_dir}/audio.wav"
        self.total_audio_buffer.create_wav(wav_file)

        # Save the video buffer to a file
        raw_video_file = f"{self.output_dir}/video.raw"
        self.total_audio_buffer.write_bytes(raw_video_file)

        # Convert the raw video to mp4
        video_file = f"{self.output_dir}/video.mp4"
        ffmpeg.input(raw_video_file).output(
            video_file, vcodec="libx264", crf=23, f="mp4", r=30, loglevel="quiet"
        ).run()

        chats = [i.__dict__ for i in self.chats]
        with open(f"{self.output_dir}/transcript.json", "w") as f:
            json.dump(chats, f)

        feedback = self.openai_client.get_feedback(self.user_name)
        with open(f"{self.output_dir}/feedback.json", "w") as f:
            json.dump(feedback, f)

        # TODO: Save the interview details to the database

        del active_connections[self.sid]

    async def send_chat(self, chat: Chat):
        chat_data = chat.__dict__

        tts = gTTS(chat_data["message"], lang="en")
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)

        audio_base64 = base64.b64encode(audio_buffer.read()).decode("utf-8")
        chat_data["audio"] = audio_base64

        await sio.emit("chat", chat_data, to=self.sid)

    async def process_video(self, message):
        # Append video data to the buffer
        if isinstance(message, bytes):
            self.total_video_bytes.append(message)

    async def process_audio(self, message):
        if isinstance(message, bytes):
            self.total_audio_buffer.append(message)
            self.current_question_audio_buffer.append(message)

            new_audio_data = np.frombuffer(message, dtype=np.int16).astype(np.float32) / 32768
            self.tmp_audio_buffer = np.concatenate((self.tmp_audio_buffer, new_audio_data))

            while len(self.tmp_audio_buffer) >= WINDOW_SIZE_SAMPLES:
                chunk = self.tmp_audio_buffer[:WINDOW_SIZE_SAMPLES]
                self.tmp_audio_buffer = self.tmp_audio_buffer[WINDOW_SIZE_SAMPLES:]

                chunk_tensor = torch.from_numpy(chunk).unsqueeze(0)
                vad_result = self.vad_iterator(chunk_tensor, return_seconds=True)

                if not vad_result:
                    continue

                if "start" not in vad_result and "end" not in vad_result:
                    continue

                print("Detected voice activity")
                self.last_vad_time = time.time()

        self.vad_iterator.reset_states()  # Reset VAD model states after processing is complete

    async def check_time_gap(self):
        # Check event.is_set to see if the thread should stop
        while self.running:
            await asyncio.sleep(0.2)

            if self.getting_next_question:
                continue

            if not self.last_vad_time:
                continue

            gap = time.time() - self.last_vad_time

            if gap > self.threshold:
                await self.ask_next_question()
                await asyncio.sleep(0.2)
                self.last_vad_time = None

    async def ask_next_question(self):
        if self.getting_next_question:
            return

        self.getting_next_question = True

        # Save the audio to a wav file
        wav_file = f"{self.output_dir}/latest_question.wav"
        latest_audio = copy.deepcopy(self.current_question_audio_buffer)
        self.current_question_audio_buffer.clear()
        latest_audio.create_wav(wav_file, speed=1.2)

        # Create a transcript from the audio
        transcript = get_transcript(wav_file)
        print("Transcript:", transcript)
        chat = Chat(transcript, "user", False)
        self.chats.append(chat)

        # Get the next question from OpenAI
        interview_ended, text = self.openai_client.get_question(transcript)
        print(text)
        chat = Chat(text, "assistant", interview_ended)
        self.chats.append(chat)

        # Send the chat to the client
        await self.send_chat(chat)

        if interview_ended:
            await self.on_disconnect()

        self.getting_next_question = False
        print()


active_connections = {}


@sio.event
async def connect(sid, environ):

    if True:
        class U:
            first_name = "Rushil"
            last_name = "Gupta"

        class I:
            company_name = "Mecha Tech"
            job_description = "Job brief We are looking for a passionate Software Engineer to design, develop and install software solutions. Software Engineer responsibilities include gathering user requirements, defining system functionality and writing code in various languages, like Java, Ruby on Rails or .NET programming languages (e.g. C++ or JScript.NET.) Our ideal candidates are familiar with the software development life cycle (SDLC) from preliminary system analysis to tests and deployment. Ultimately, the role of the Software Engineer is to build high-quality, innovative and fully performing software that complies with coding standards and technical design. Responsibilities Execute full software development life cycle (SDLC) Develop flowcharts, layouts and documentation to identify requirements and solutions Write well-designed, testable code Produce specifications and determine operational feasibility Integrate software components into a fully functional software system Develop software verification plans and quality assurance procedures Document and maintain software functionality Troubleshoot, debug and upgrade existing systems Deploy programs and evaluate user feedback Comply with project plans and industry standards Ensure software is updated with latest features Requirements and skills Proven work experience as a Software Engineer or Software Developer Experience designing interactive applications Ability to develop software in Java, Ruby on Rails, C++ or other programming languages Excellent knowledge of relational databases, SQL and ORM technologies (JPA2, Hibernate) Experience developing web applications using at least one popular web framework (JSF, Wicket, GWT, Spring MVC) Experience with test-driven development Proficiency in software engineering tools Ability to document requirements and specifications BSc degree in Computer Science, Engineering or relevant field"
            uid = "test"
            user = U()
            sid = "asmdkasndajsnd"

        active_connections[sid] = ConnectionHandler(sid, I(), U())
        await active_connections[sid].on_connect()
        return

    try:
        query = environ.get("asgi.scope").get("query_string")
        if not query:
            await sio.disconnect(sid)
            return

        query = query.decode("utf-8")
        query_params = parse_qs(query)

        token = query_params.get("interviewToken")[0]
        email = query_params.get("email")[0]

    except:
        await sio.disconnect(sid)
        return

    if not token or not email:
        await sio.disconnect(sid)
        return

    user_exists = await sync_to_async(User.objects.filter(email=email).exists)()
    if not user_exists:
        await sio.disconnect(sid)
        return

    user = await sync_to_async(User.objects.get)(email=email)

    # Validate the token
    try:
        payload = jwt.decode(token, user.secret_key, algorithms=[JWT_ALGORITHM])
        interview_id = payload["interviewId"]
    except:
        await sio.disconnect(sid)
        return

    try:
        interview_exists = await sync_to_async(
            Interview.objects.filter(uid=interview_id, user=user).exists
        )()
        if not interview_exists:
            raise ValueError("Invalid interview token.")

        interview = await sync_to_async(Interview.objects.get)(uid=interview_id, user=user)
        interview.sid = sid
        await sync_to_async(interview.save)()

        # Proceed with creating a connection handler
        active_connections[sid] = ConnectionHandler(sid, interview)
        await active_connections[sid].on_connect()

    except Exception as e:
        # Invalid token
        print("Error:", str(e))
        await sio.disconnect(sid)


@sio.event
async def disconnect(sid):
    if sid in active_connections:
        await active_connections[sid].on_disconnect()
        del active_connections[sid]


@sio.on("audioData")
async def process_audio(sid, data):
    if sid in active_connections:
        await active_connections[sid].process_audio(data)


@sio.on("videoData")
async def process_video(sid, data):
    if sid in active_connections:
        await active_connections[sid].process_video(data)
