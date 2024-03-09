from datetime import datetime
import os
import time
import threading
import concurrent.futures

import jwt
import torch
import socketio
import ffmpeg
import numpy as np
import asyncio
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async

from interview.models import Interview
from interview.views import JWT_ALGORITHM
from interview import worker
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

mgr = socketio.AsyncRedisManager("redis://0.0.0.0:6379/0")
sio = socketio.AsyncServer(client_manager=mgr, async_mode="asgi", cors_allowed_origins="*")


FAKE_RESPONSES = True


class ConnectionHandler:
    def __init__(self, sid, interview: Interview, user: User):

        # Set the time gap threshold in seconds
        self.threshold = 10

        # Store important details
        self.sid = sid
        if FAKE_RESPONSES:
            self.interview_id = "test"
        else:
            self.interview_id = str(interview.uid)

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

        if FAKE_RESPONSES:
            return

        self.openai_client = OpenAIClient()

        interview_done, first_question = self.openai_client.ask(
            f"Company Name: {interview.company_name}\nJob Description: {interview.job_description}\n Candidate Name: {user.first_name} {user.last_name}"
        )
        first_chat = Chat(first_question, "assistant", interview_done)
        self.chats.append(first_chat)

    async def on_connect(self):
        print("Client connected:", self.sid)

        self.check_gap_task = asyncio.create_task(self.check_time_gap())

        if FAKE_RESPONSES:
            chat = Chat("Test", "assistant", False)
            self.chats.append(chat)
            await self.send_chat(chat)

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
        print("Audio saved to", wav_file)

        # Save the video buffer to a file
        raw_video_file = f"{self.output_dir}/video.raw"
        self.total_audio_buffer.write_bytes(raw_video_file)

        # Convert the raw video to mp4
        video_file = f"{self.output_dir}/video.mp4"
        ffmpeg.input(raw_video_file).output(
            video_file, vcodec="libx264", crf=23, f="mp4", r=30, loglevel="quiet"
        ).run()

        print("Video saved to", video_file)
        print("Connection closed successfully", self.sid)

        if FAKE_RESPONSES:
            return

        interview = await sync_to_async(Interview.objects.get)(uid=self.interview_id)
        worker.process_media(self.output_dir, interview)

    async def send_chat(self, chat: Chat):
        print(datetime.now().time(), "Sending chat")
        await sio.emit("chat", chat.__dict__, to=self.sid)

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
                self.last_vad_time = time.time()

    async def ask_next_question(self):
        if self.getting_next_question:
            return

        self.getting_next_question = True

        # Save the audio to a wav file
        wav_file = f"{self.output_dir}/latest_question.wav"
        self.current_question_audio_buffer.create_wav(wav_file)
        self.current_question_audio_buffer.clear()

        if FAKE_RESPONSES:
            chat = Chat(f"Test, question {len(self.chats)}", "assistant", False)
            self.chats.append(chat)

            # Send the chat to the client
            await self.send_chat(chat)

        else:
            # Create a transcript from the audio
            transcript = worker.get_transcript(wav_file)
            chat = Chat(transcript, "user", False)
            self.chats.append(chat)

            # Get the next question from OpenAI
            interview_ended, text = self.openai_client.get_question(transcript)
            chat = Chat(text, "assistant", interview_ended)
            self.chats.append(chat)

            # Send the chat to the client
            await self.send_chat(chat)

        self.getting_next_question = False


active_connections = {}


@sio.event
async def connect(sid, environ):

    if FAKE_RESPONSES:
        active_connections[sid] = ConnectionHandler(sid, {}, {})
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
        print(f"Authenticated user: {user.email}")
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
