from datetime import datetime
import os
import time
import threading
import numpy as np
import wave
import torch
import socketio
import ffmpeg
from interview.models import Interview

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
    def __init__(self, sid):
        # Set the time gap threshold in seconds
        self.threshold = 2

        # Store the socket id
        self.sid = sid
        self.output_dir = f"output/{datetime.now().strftime('%Y%m%d-%H%M%S')}_{sid}"

        # Initialize buffers
        self.tmp_audio_buffer = np.array([], dtype=np.float32)
        self.total_audio_buffer = np.array([], dtype=np.float32)
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
            new_audio_data = np.frombuffer(message, dtype=np.int16).astype(np.float32) / 32768
            self.tmp_audio_buffer = np.concatenate((self.tmp_audio_buffer, new_audio_data))
            self.total_audio_buffer = np.concatenate((self.total_audio_buffer, new_audio_data))

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
        scaled_audio = (self.total_audio_buffer * 32768).astype(np.int16)

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


active_connections = {}


@sio.event
async def connect(sid, environ):
    print("Client connected:", sid)
    active_connections[sid] = ConnectionHandler(sid)
    await active_connections[sid].on_connect()


@sio.event
async def disconnect(sid):
    print("Client disconnected:", sid)
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
