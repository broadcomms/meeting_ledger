# app/websockets/transcription_ws.py

import base64
import time
from threading import Lock

from flask import current_app, request
from flask_socketio import SocketIO, emit, join_room

from app.config import Config
from app.extensions import db
from app.models import Transcript, Summary
from app.transcription.transcription import TranscriptionSession
from langchain_ibm import WatsonxLLM
from langchain_core.prompts import PromptTemplate

ACTIVE_SESSIONS = {}
ACTIVE_SESSIONS_LOCK = Lock()

def register_transcription_events(socketio: SocketIO):
    @socketio.on("connect", namespace="/transcription")
    def transcription_connect():
        meeting_id = request.args.get("meeting_id")
        if meeting_id:
            join_room(f"meeting_{meeting_id}")
            print(f"[Transcription] Client joined room meeting_{meeting_id}")

    @socketio.on("start_transcription", namespace="/transcription")
    def handle_start_transcription(data):
        meeting_id = str(data.get("meeting_id"))
        user_id = data.get("user_id")  # speaker id
        if not meeting_id or not user_id:
            emit("error_message", {"error": "Missing meeting_id or user_id."})
            return

        key = f"{meeting_id}_{user_id}"
        with ACTIVE_SESSIONS_LOCK:
            if key in ACTIVE_SESSIONS:
                emit("transcription_started", {"message": "Transcription already running."})
                return

            session = TranscriptionSession(
                api_key=Config.WATSONX_API_KEY,
                stt_url=Config.WATSONX_STT_URL,
                meeting_id=meeting_id,
                user_id=user_id,  # speaker id
                app=current_app._get_current_object(),
                socketio_instance=socketio
            )
            session.start()
            ACTIVE_SESSIONS[key] = session

        join_room(f"meeting_{meeting_id}")
        emit("transcription_started", {"message": "Transcription started."}, room=f"meeting_{meeting_id}")

    @socketio.on("audio_chunk", namespace="/transcription")
    def handle_audio_chunk(data):
        meeting_id = str(data.get("meeting_id"))
        user_id = data.get("user_id")  # may be included from the client if needed
        chunk_b64 = data.get("chunk")
        if not meeting_id or not chunk_b64:
            return

        key = f"{meeting_id}_{user_id}"
        with ACTIVE_SESSIONS_LOCK:
            session = ACTIVE_SESSIONS.get(key)
        if not session:
            return

        if "data:" in chunk_b64:
            chunk_b64 = chunk_b64.split(",")[1]
        audio_bytes = base64.b64decode(chunk_b64)
        session.add_audio_chunk(audio_bytes)  # Inside session, ensure that when a transcript is produced, you add speaker_id

    @socketio.on("stop_transcription", namespace="/transcription")
    def handle_stop_transcription(data):
        meeting_id = str(data.get("meeting_id"))
        user_id = data.get("user_id")
        if not meeting_id or not user_id:
            return
        key = f"{meeting_id}_{user_id}"
        with ACTIVE_SESSIONS_LOCK:
            session = ACTIVE_SESSIONS.pop(key, None)
        if session:
            session.stop()
            emit("transcription_stopped", {"message": "Transcription stopped."}, room=f"meeting_{meeting_id}")
        else:
            emit("transcription_stopped", {"message": "No active transcription found."}, room=f"meeting_{meeting_id}")


    @socketio.on("generate_summary", namespace="/transcription")
    def handle_generate_summary(data):
        """
        Aggregates all transcripts for the meeting, passes them to
        a model for summarization, streams partial output, and saves the final summary.
        """
        meeting_id = data.get("meeting_id")
        if not meeting_id:
            emit("error_message", {"error": "No meeting_id provided for summary generation."})
            return

        # Collect transcripts
        transcripts = Transcript.query.filter_by(meeting_id=meeting_id).all()
        full_text = " ".join([
            t.processed_transcript if t.processed_transcript else t.raw_transcript
            for t in transcripts
        ])
        print("HANDLE_GENERATE_SUMMARY trascription_ws.ps")# DEBUG CODE
        print(f"[Transcription] Summarizing transcripts for meeting {meeting_id}: {full_text}")

  
        from langchain_ibm import WatsonxLLM
        from langchain_core.prompts import PromptTemplate

        watsonx_llm = WatsonxLLM(
            model_id=Config.WATSONX_MODEL_ID_3,
            url=Config.WATSONX_URL,
            project_id=Config.WATSONX_PROJECT_ID,
            apikey=Config.WATSONX_API_KEY,
            params={
                "decoding_method": "sample",
                "max_new_tokens": 1200,
                "min_new_tokens": 10,
                "temperature": 0.7,
                "top_k": 45,
                "top_p": 1
            }
        )

        template = """
        Summarize the following meeting transcripts concisely and clearly:

        {text}

        Avoid using emotional or sensationalist tone.
        Capture the main points and preserve the original flow of the meeting.
        Output only the final summary text.
        """
        prompt = PromptTemplate.from_template(template)
        llm_chain = prompt | watsonx_llm

        summary_text = ""
        summary_text = llm_chain.invoke({"text": full_text})

        
        
        print(f"[Transcription] Summary Result: {meeting_id}: {summary_text}")
        # Stream summary chunks to clients

        emit("summary_update", {"summary_chunk": summary_text}, namespace="/transcription", room=f"meeting_{meeting_id}")

        # Save summary in the DB
        with current_app.app_context():
            existing = Summary.query.filter_by(meeting_id=meeting_id).first()
            if existing:
                existing.summary_text = summary_text
            else:
                new_summary = Summary(meeting_id=meeting_id, summary_text=summary_text)
                db.session.add(new_summary)
            db.session.commit()

        emit("summary_complete", {"message": "Summary generation complete."}, namespace="/transcription", room=f"meeting_{meeting_id}")

    @socketio.on("start_autocorrect", namespace="/transcription")
    def handle_autocorrect(data):
        """
        Streams an autocorrection of a transcript's raw text to the client, chunk by chunk.
        Fixes detached instance errors by ensuring an active session.
        """
        transcript_id = data.get("transcript_id")
        if not transcript_id:
            emit("error_message", {"error": "No transcript_id provided."})
            return

        # Ensure we fetch the transcript within a fresh session
        with current_app.app_context():
            transcript = db.session.get(Transcript, transcript_id)
            if not transcript:
                emit("error_message", {"error": "Transcript not found."})
                return

            text_to_correct = transcript.raw_transcript.strip()

            watsonx_llm = WatsonxLLM(
                model_id=Config.WATSONX_MODEL_ID_1,
                url=Config.WATSONX_URL,
                project_id=Config.WATSONX_PROJECT_ID,
                apikey=Config.WATSONX_API_KEY,
                params={
                    "decoding_method": "sample",
                    "max_new_tokens": 1200,
                    "temperature": 0.8,
                    "top_k": 25,
                    "top_p": 1,
                }
            )

            template = """
            Correct grammar without changing the original meaning or style of the transcript.

            Text to correct:
            {text}

            Output only the final corrected text.
            """
            prompt = PromptTemplate.from_template(template)
            llm_chain = prompt | watsonx_llm

            corrected_text = ""
            for chunk in llm_chain.stream({"text": text_to_correct}):
                corrected_text += chunk
                emit(
                    "autocorrect_update",
                    {"transcript_id": transcript_id, "chunk": chunk},
                    namespace="/transcription",
                    room=request.sid
                )

            # Ensure the transcript instance is attached before updating it
            transcript = db.session.merge(transcript)
            transcript.processed_transcript = corrected_text.strip()

            # Commit inside the session to prevent detachment
            db.session.commit()

            # Send the final autocorrect update to all users in the meeting
            """
            socketio.emit("autocorrect_update", {
                    "transcript_id": transcript.transcript_id,
                    "chunk": transcript.processed_transcript
                }, room=f"meeting_{transcript.meeting_id}", namespace="/transcription")
            """
            
            # Notify completion without resending the entire corrected text
            socketio.emit(
                "autocorrect_complete",
                {"transcript_id": transcript.transcript_id},
                room=f"meeting_{transcript.meeting_id}",
                namespace="/transcription"
            )