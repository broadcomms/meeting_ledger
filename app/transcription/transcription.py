# app/transcription/transcription.py

import logging
import queue
import threading
import io
from datetime import datetime
from ibm_watson import SpeechToTextV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibm_watson.websocket import RecognizeCallback, AudioSource

logging.basicConfig(level=logging.INFO)

##############################################################################
# Custom AudioSource that reads from our audio generator.
##############################################################################
class QueueAudioSource(AudioSource):
    def __init__(self, audio_generator):
        super().__init__(io.BytesIO())
        self.input = self
        self._audio_generator = audio_generator
        self._buffer = b""

    def read(self, n=-1):
        while (n < 0 or len(self._buffer) < n):
            try:
                chunk = next(self._audio_generator)
                self._buffer += chunk
            except StopIteration:
                break
        if n < 0 or n > len(self._buffer):
            data = self._buffer
            self._buffer = b""
        else:
            data = self._buffer[:n]
            self._buffer = self._buffer[n:]
        return data

    def close(self):
        pass

##############################################################################
# Watson STT Callback with Socket.IO integration.
##############################################################################
class WSRecognizeCallback(RecognizeCallback):
    def __init__(self, meeting_id, user_id, app, socketio_instance):
        super().__init__()
        self.meeting_id = meeting_id
        self.user_id = user_id
        self.full_transcript = ""
        self.app = app
        self.socketio = socketio_instance

    def on_data(self, data):
        # Push an application context for each callback execution.
        ctx = self.app.app_context()
        ctx.push()
        try:
            print("Watson STT response:", data)  # DEBUG
            if not data.get("results"):
                print("Watson STT returned empty results.")
                return

            def get_username(user_id):
                from app.models import User
                user = User.query.get(user_id)
                return user.username if user else "Unknown"

            def get_profile_pic(user_id):
                from app.models import User
                user = User.query.get(user_id)
                if user and user.profile_pic_url:
                    return f"/static/{user.profile_pic_url}"
                else:
                    return "/static/default-profile.png"

            for result in data["results"]:
                transcript_text = result["alternatives"][0]["transcript"].strip()
                transcript_created = datetime.utcnow()
                payload = {
                    "transcript": transcript_text,
                    "speaker_id": self.user_id,
                    "speaker_username": get_username(self.user_id),
                    "profile_pic_url": get_profile_pic(self.user_id),
                    "created_timestamp": transcript_created.isoformat(),
                    "final": result.get("final", False)
                }
                event_name = "transcript_update" if payload["final"] else "transcript_update_interim"
                try:
                    self.socketio.emit(
                        event_name,
                        payload,
                        namespace="/transcription",
                        room=f"meeting_{self.meeting_id}"
                    )
                except Exception as e:
                    print(f"Error during emit ({event_name}):", e)
                if payload["final"]:
                    self.full_transcript += transcript_text + " "
        finally:
            ctx.pop()

    def on_error(self, error):
        logging.error(f"STT on_error: {error}")

    def on_inactivity_timeout(self, error):
        logging.warning(f"STT on_inactivity_timeout: {error}")

##############################################################################
# Transcription Session: Streams audio to Watson in a background thread.
##############################################################################
class TranscriptionSession:
    def __init__(self, api_key, stt_url, meeting_id, user_id, app, socketio_instance):
        self.api_key = api_key
        self.stt_url = stt_url
        self.meeting_id = meeting_id
        self.user_id = user_id
        self.app = app
        self.socketio = socketio_instance
        self.audio_queue = queue.Queue()
        self.stopped_event = threading.Event()
        self.thread = None
        self.callback = None

    def _audio_generator(self):
        while not self.stopped_event.is_set():
            try:
                chunk = self.audio_queue.get(timeout=0.1)
                yield chunk
            except queue.Empty:
                continue

    def start(self):
        self.stopped_event.clear()
        print(f"Starting transcription session for meeting {self.meeting_id}")  # DEBUG
        self.thread = threading.Thread(target=self._run_stt)
        self.thread.start()

    def _run_stt(self):
        print(f"Connecting to Watson STT for meeting {self.meeting_id}...")  # DEBUG
        authenticator = IAMAuthenticator(self.api_key)
        stt_client = SpeechToTextV1(authenticator=authenticator)
        stt_client.set_service_url(self.stt_url)

        callback = WSRecognizeCallback(self.meeting_id, self.user_id, self.app, self.socketio)
        self.callback = callback
        audio_source = QueueAudioSource(self._audio_generator())

        try:
            print("Sending audio to Watson STT...")  # DEBUG
            stt_client.recognize_using_websocket(
                audio=audio_source,
                content_type="audio/l16; rate=16000",
                model="en-US_BroadbandModel",
                recognize_callback=callback,
                interim_results=True,
                inactivity_timeout=-1
            )
        except Exception as e:
            print(f"Error streaming to Watson STT: {e}")
        finally:
            print(f"Transcription thread finished for meeting {self.meeting_id}")

    def add_audio_chunk(self, chunk):
        self.audio_queue.put(chunk)

    def stop(self):
        self.stopped_event.set()
        if self.thread:
            self.thread.join()
        logging.info(f"Transcription session stopped for meeting {self.meeting_id}")

        # Save the final transcript to the database.
        from app import db
        from app.models import Transcript
        with self.app.app_context():
            transcript = Transcript(
                meeting_id=self.meeting_id,
                speaker_id=self.user_id,
                raw_transcript=self.callback.full_transcript
            )
            db.session.add(transcript)
            db.session.commit()
            logging.info("Transcript saved to the database.")

            transcript_data = {
                "transcript_id": transcript.transcript_id,
                "meeting_id": transcript.meeting_id,
                "speaker_id": transcript.speaker_id,
                "raw_transcript": transcript.raw_transcript,
                "created_timestamp": transcript.created_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.socketio.emit(
                "transcript_saved",
                transcript_data,
                namespace="/transcription",
                room=f"meeting_{self.meeting_id}"
            )