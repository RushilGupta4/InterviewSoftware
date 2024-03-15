from datetime import datetime

import wave
import numpy as np
import scipy


class MediaBuffer:
    def __init__(self, SAMPLING_RATE):
        self.buffer = b""
        self.SAMPLING_RATE = SAMPLING_RATE

    def append(self, data):
        self.buffer += data

    def clear(self):
        self.buffer = b""

    def get(self):
        return self.buffer

    def create_wav(self, wav_path, speed=1):
        audio_buffer = np.frombuffer(self.buffer, dtype=np.int16).astype(np.float32) / 32768

        new_length = int(len(audio_buffer) / speed)
        resampled_audio = scipy.signal.resample(audio_buffer, new_length)
        scaled_audio = (resampled_audio * 32768).astype(np.int16)

        # Write the audio data to a WAV file
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)  # Mono audio
            wf.setsampwidth(2)  # 16-bit audio
            wf.setframerate(self.SAMPLING_RATE)
            wf.writeframes(scaled_audio.tobytes())

    def write_bytes(self, file_path):
        with open(file_path, "wb") as f:
            f.write(self.buffer)


class Chat:
    def __init__(self, message, role, interview_ended):
        self.message = message
        self.role = role
        self.interview_ended = interview_ended
        self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        return {
            "message": self.message,
            "role": self.role,
            "interview_ended": self.interview_ended,
            "timestamp": self.timestamp,
        }
