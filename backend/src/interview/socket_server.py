import copy
import json
import os
import io
import base64
import threading

import jwt
import socketio
import ffmpeg
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async
from gtts import gTTS

from users.models import User
from .models import Interview
from .views import JWT_ALGORITHM
from .transcript_helper import get_transcript
from .llm_client import LLMClient
from .utils import MediaBuffer, Chat

# Constants
SAMPLING_RATE = 16000
WINDOW_SIZE_SAMPLES = 1536  # Number of samples in a single audio chunk

mgr = socketio.AsyncManager()
sio = socketio.AsyncServer(client_manager=mgr, async_mode="asgi", cors_allowed_origins="*")

NO_RESPONSES = False


class ConnectionHandler:
    def __init__(self, sid, interview: Interview, user: User):

        # Set the time gap threshold in seconds
        self.threshold = 5
        self.event = threading.Event()

        # Store important details
        self.sid = sid
        self.interview_id = interview.uid
        self.interview_data = interview.__dict__
        self.user_name = f"{user.first_name} {user.last_name}"

        # Disconnector
        self.disconnecting = False

        self.output_dir = f"output/{self.interview_id}-{sid}"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # Initialize buffers
        self.current_question_audio_buffer = MediaBuffer(SAMPLING_RATE)
        self.total_audio_buffer = MediaBuffer(SAMPLING_RATE)
        self.total_video_bytes = MediaBuffer(SAMPLING_RATE)

        # Initialize flags
        self.getting_next_question = False
        self.is_responding = False

        if NO_RESPONSES:
            return

        # Chats
        self.chats: list[Chat] = []
        self.llm_client = LLMClient(interview_data=self.interview_data, user_name=self.user_name)

    async def on_connect(self):
        print("Client connected:", self.sid)

        if NO_RESPONSES:
            return

        interview_done, first_question = await self.llm_client.start_interview()
        first_chat = Chat(first_question, "assistant", interview_done)
        self.chats.append(first_chat)
        await self.send_chat(first_chat)

    async def on_disconnect(self):
        if self.disconnecting:
            return

        self.disconnecting = True

        print("Client disconnecting:", self.sid)

        try:
            # Save the audio to a wav file
            wav_file = f"{self.output_dir}/audio.wav"
            self.total_audio_buffer.create_wav(wav_file)

            # Save the video buffer to a file
            raw_video_file = f"{self.output_dir}/video.raw"
            self.total_video_bytes.write_bytes(raw_video_file)

            # Convert the raw video to mp4
            video_file = f"{self.output_dir}/video.mp4"
            ffmpeg.input(raw_video_file).output(
                video_file, vcodec="libx264", crf=23, f="mp4", r=30, loglevel="quiet"
            ).run()
            os.remove(raw_video_file)

            if not NO_RESPONSES:
                feedback = await self.llm_client.get_feedback(self.user_name, self.chats)

                with open(f"{self.output_dir}/feedback.json", "w") as f:
                    json.dump(feedback, f)

                with open(f"{self.output_dir}/transcript.json", "w") as f:
                    json.dump([i.to_dict() for i in self.chats], f)

                # Check whether the interview object exists
                interview_exists = await sync_to_async(
                    Interview.objects.filter(uid=self.interview_id).exists
                )()
                if not interview_exists:
                    return

                interview: Interview = await sync_to_async(Interview.objects.get)(
                    uid=self.interview_id
                )
                interview.transcript = json.dumps([i.to_dict() for i in self.chats])
                interview.feedback = json.dumps(feedback)
                interview.completed = True
                await sync_to_async(interview.save)()

        except Exception as e:
            print(e)

        print("Client disconnected:", self.sid)
        self.disconnecting = False
        del active_connections[self.sid]

    async def send_chat(self, chat: Chat):
        chat_data = chat.to_dict()

        tts = gTTS(chat_data["message"], lang="en")
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)

        audio_base64 = base64.b64encode(audio_buffer.read()).decode("utf-8")
        chat_data["audio"] = audio_base64

        await sio.emit("chat", chat_data, to=self.sid)

    async def process_video(self, message):
        if not self.is_responding:
            return

        # Append video data to the buffer
        if isinstance(message, bytes):
            self.total_video_bytes.append(message)

    async def process_audio(self, message):
        if not self.is_responding:
            return

        if isinstance(message, bytes):
            self.total_audio_buffer.append(message)
            self.current_question_audio_buffer.append(message)

    async def manage_responding_status(self, message):
        if self.getting_next_question:
            await sio.emit(
                "getRespondingStatus",
                {
                    "status": self.is_responding,
                    "message": "Please wait for the next question before answering",
                },
                to=self.sid,
            )
            return

        if message == self.is_responding:
            await sio.emit(
                "getRespondingStatus",
                {
                    "status": self.is_responding,
                    "message": f"You are {'already responding' if self.is_responding else 'not responding'}",
                },
                to=self.sid,
            )

        self.is_responding = message

        await sio.emit(
            event="getRespondingStatus",
            data={"status": self.is_responding, "message": "Success"},
            to=self.sid,
            ignore_queue=True,
        )

        if not self.is_responding:
            await self.ask_next_question()

    async def ask_next_question(self):
        if self.getting_next_question:
            return

        if NO_RESPONSES:
            self.getting_next_question = False
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

        os.remove(wav_file)

        # Get the next question from the LLM
        interview_ended, text = await self.llm_client.get_question(transcript)
        print("Question:", text)
        chat = Chat(text, "assistant", interview_ended)
        self.chats.append(chat)

        # Send the chat to the client
        await self.send_chat(chat)

        if interview_ended:
            await self.on_disconnect()

        self.getting_next_question = False
        print()


active_connections: dict[str, ConnectionHandler] = {}


@sio.event
async def connect(sid, environ):

    if True:

        class U:
            def __init__(self):
                self.first_name = "Rushil"
                self.last_name = "Gupta"

        class I:
            def __init__(self):
                self.company_name = "Mecha Tech"
                self.job_description = "Job brief We are looking for a passionate Software Engineer to design, develop and install software solutions. Software Engineer responsibilities include gathering user requirements, defining system functionality and writing code in various languages, like Java, Ruby on Rails or .NET programming languages (e.g. C++ or JScript.NET.) Our ideal candidates are familiar with the software development life cycle (SDLC) from preliminary system analysis to tests and deployment. Ultimately, the role of the Software Engineer is to build high-quality, innovative and fully performing software that complies with coding standards and technical design. Responsibilities Execute full software development life cycle (SDLC) Develop flowcharts, layouts and documentation to identify requirements and solutions Write well-designed, testable code Produce specifications and determine operational feasibility Integrate software components into a fully functional software system Develop software verification plans and quality assurance procedures Document and maintain software functionality Troubleshoot, debug and upgrade existing systems Deploy programs and evaluate user feedback Comply with project plans and industry standards Ensure software is updated with latest features Requirements and skills Proven work experience as a Software Engineer or Software Developer Experience designing interactive applications Ability to develop software in Java, Ruby on Rails, C++ or other programming languages Excellent knowledge of relational databases, SQL and ORM technologies (JPA2, Hibernate) Experience developing web applications using at least one popular web framework (JSF, Wicket, GWT, Spring MVC) Experience with test-driven development Proficiency in software engineering tools Ability to document requirements and specifications BSc degree in Computer Science, Engineering or relevant field"
                self.uid = "test"
                self.user = U()
                self.sid = "asmdkasndajsnd"

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

    user: User = await sync_to_async(User.objects.get)(email=email)

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

        interview: Interview = await sync_to_async(Interview.objects.get)(
            uid=interview_id, user=user
        )
        interview.sid = sid
        interview.started = True
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


@sio.on("audioData")
async def process_audio(sid, data):
    if sid in active_connections:
        await active_connections[sid].process_audio(data)


@sio.on("videoData")
async def process_video(sid, data):
    if sid in active_connections:
        await active_connections[sid].process_video(data)


@sio.on("respondingStatus")
async def manage_responding_status(sid, data):
    if sid in active_connections:
        await active_connections[sid].manage_responding_status(data)
