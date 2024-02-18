from datetime import datetime
import os
import time
import threading

import jwt
import wave
import torch
import socketio
import ffmpeg
import numpy as np
from django.contrib.auth import get_user_model
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async

from interview.models import Interview
from interview.views import JWT_ALGORITHM
from interview.worker import process_media


User = get_user_model()

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


class ConnectionHandler:
    def __init__(self, sid, interview_id):
        # Set the time gap threshold in seconds
        self.threshold = 2

        # Store important details
        self.sid = sid
        self.interview_id = interview_id
        self.output_dir = f"output/{interview_id}-{sid}"

        # Initialize buffers
        self.tmp_audio_buffer = np.array([], dtype=np.float32)
        self.total_audio_buffer = b""
        self.total_video_bytes = b""

        # Initialize VAD iterator
        self.vad_iterator = VADIterator(model)

        # Initialize lists for VAD results and gaps
        self.last_vad_time = None

        # Create an event for time gap checking
        self.event = threading.Event()
        self.gap_check_thread = threading.Thread(target=self.check_time_gap, daemon=True)
        self.gap_check_thread.start()

    async def process_video(self, message):
        # Append video data to the buffer
        if isinstance(message, bytes):
            self.total_video_bytes += message

    async def process_audio(self, message):
        if isinstance(message, bytes):
            self.total_audio_buffer += message

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

    def check_time_gap(self):
        # Check event.is_set to see if the thread should stop
        while not self.event.is_set():
            self.event.wait(0.2)

            if not self.last_vad_time:
                continue
            gap = time.time() - self.last_vad_time

            if gap > self.threshold:
                print(f"Time gap exceeded {self.threshold} seconds ({gap:.2f} seconds)")

    async def on_connect(self):
        print("Client connected:", self.sid)

    async def on_disconnect(self):
        print("Client disconnected:", self.sid)

        # Kill the thread
        self.event.set()
        self.gap_check_thread.join()

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # Save the audio to a wav file
        wav_file = f"{self.output_dir}/audio.wav"

        # Rescale the audio data back to int16 range before saving
        audio_buffer = (
            np.frombuffer(self.total_audio_buffer, dtype=np.int16).astype(np.float32) / 32768
        )
        scaled_audio = (audio_buffer * 32768).astype(np.int16)

        print(len(self.total_audio_buffer))

        # Write the audio data to a WAV file
        with wave.open(wav_file, "wb") as wf:
            wf.setnchannels(1)  # Mono audio
            wf.setsampwidth(2)  # 16-bit audio
            wf.setframerate(SAMPLING_RATE)
            wf.writeframes(scaled_audio.tobytes())

        print("Audio saved to", wav_file)

        # Save the video buffer to a file
        raw_video_file = f"{self.output_dir}/video.raw"
        video_file = f"{self.output_dir}/video.mp4"
        with open(raw_video_file, "wb") as f:
            f.write(self.total_video_bytes)

        ffmpeg.input(raw_video_file).output(
            video_file, vcodec="libx264", crf=23, f="mp4", r=30, loglevel="quiet"
        ).run()

        print("Video saved to", video_file)
        print("Connection closed successfully", self.sid)

        interview = await sync_to_async(Interview.objects.get)(uid=self.interview_id)
        process_media(self.output_dir, interview)


active_connections = {}


@sio.event
async def connect(sid, environ):
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
        active_connections[sid] = ConnectionHandler(sid, interview_id)
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
