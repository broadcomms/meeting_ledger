# app/websockets/webrtc_ws.py

from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import request
from flask_login import current_user
from threading import Lock

WEBRTC_USERS = {}
WEBRTC_USERS_LOCK = Lock()

def register_webrtc_events(socketio: SocketIO):
    @socketio.on("connect", namespace="/webrtc")
    def webrtc_connect(auth):
        with WEBRTC_USERS_LOCK:
            WEBRTC_USERS[request.sid] = {
                "user_id": current_user.user_id,
                "username": current_user.username,
                "meeting_id": None
            }
        print(f"[webrtc_connect] {request.sid} => user {current_user.username}")

    @socketio.on("disconnect", namespace="/webrtc")
    def webrtc_disconnect(*args):
        """
        Immediately notify other participants that this user left.
        """
        with WEBRTC_USERS_LOCK:
            user_info = WEBRTC_USERS.pop(request.sid, None)
        if user_info and user_info["meeting_id"]:
            meeting_id = user_info["meeting_id"]
            # **Emit 'webrtc_peer_left' so others can remove this tile immediately**
            emit(
                "webrtc_peer_left",
                {"peer_sid": request.sid},
                room=f"meeting_{meeting_id}",
                include_self=False,
                namespace="/webrtc"
            )
        print(f"[webrtc_disconnect] {request.sid} disconnected.")

    @socketio.on("webrtc_join", namespace="/webrtc")
    def handle_webrtc_join(data):
        meeting_id = data.get("meeting_id")
        join_room(f"meeting_{meeting_id}")

        with WEBRTC_USERS_LOCK:
            user_info = WEBRTC_USERS.get(request.sid)
            if user_info:
                user_info["meeting_id"] = meeting_id
                print(f"[webrtc_join] sid={request.sid}, meeting_id={meeting_id}, user_id={user_info['user_id']}, username={user_info['username']}")
        # Send the new user a list of existing participants (excluding self)
        existing_participants = []
        with WEBRTC_USERS_LOCK:
            for sid, info in WEBRTC_USERS.items():
                if info["meeting_id"] == meeting_id and sid != request.sid:
                    existing_participants.append({
                        "peer_sid": sid,
                        "user_id": info["user_id"],
                        "username": info["username"]
                    })
        emit("webrtc_current_participants", existing_participants, namespace="/webrtc")

        # Notify existing participants that this user joined
        emit(
            "webrtc_peer_joined",
            {
                "peer_sid": request.sid,
                "user_id": user_info["user_id"] if user_info else None,
                "username": user_info["username"] if user_info else "Unknown"
            },
            room=f"meeting_{meeting_id}",
            include_self=False,
            namespace="/webrtc"
        )

        # ✅ Send an event to signal that remote audio should be handled
        emit(
            "webrtc_remote_audio",
            {
                "peer_sid": request.sid,
                "username": user_info["username"] if user_info else "Unknown"
            },
            room=f"meeting_{meeting_id}",
            include_self=False,
            namespace="/webrtc"
        )
        
    @socketio.on("webrtc_offer", namespace="/webrtc")
    def handle_webrtc_offer(data):
        target = data.get("target")
        offer = data.get("offer")
        sender = request.sid
        with WEBRTC_USERS_LOCK:
            sender_info = WEBRTC_USERS.get(sender, {})
        sender_username = sender_info.get("username", "Unknown")

        emit(
            "webrtc_offer",
            {"offer": offer, "sender": sender, "username": sender_username},
            room=target,
            namespace="/webrtc"
        )

    @socketio.on("webrtc_answer", namespace="/webrtc")
    def handle_webrtc_answer(data):
        target = data.get("target")
        answer = data.get("answer")
        sender = request.sid
        with WEBRTC_USERS_LOCK:
            sender_info = WEBRTC_USERS.get(sender, {})
        sender_username = sender_info.get("username", "Unknown")

        emit(
            "webrtc_answer",
            {"answer": answer, "sender": sender, "username": sender_username},
            room=target,
            namespace="/webrtc"
        )

    @socketio.on("webrtc_ice_candidate", namespace="/webrtc")
    def handle_webrtc_ice_candidate(data):
        target = data.get("target")
        candidate = data.get("candidate")
        sender = request.sid
        emit(
            "webrtc_ice_candidate",
            {"candidate": candidate, "sender": sender},
            room=target,
            namespace="/webrtc"
        )

    @socketio.on("media_update", namespace="/webrtc")
    def handle_media_update(data):
        meeting_id = data.get("meeting_id")
        emit(
            "media_update",
            data,
            room=f"meeting_{meeting_id}",
            include_self=False,
            namespace="/webrtc"
        )