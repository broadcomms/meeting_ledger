// static/js/videoConference.js

(function() {
  // Configuration from server (via window.config)
  const conferenceActive = window.config.conferenceActive;
  const isOrganizer = window.config.isOrganizer;
  const meetingId = window.config.meetingId;
  const userId = window.config.userId;

  // Establish a Socket.IO connection for WebRTC signaling.
  const webrtcSocket = io("/webrtc", { query: "meeting_id=" + meetingId });

  let localStream = null;
  // Use Google’s public STUN server.
  const configuration = { iceServers: [{ urls: "stun:stun.l.google.com:19302" }] };
  const peers = {}; // Map of peerSid => RTCPeerConnection

  // DOM elements
  const localVideoTile = document.getElementById("tile_" + userId);
  const localVideo = document.getElementById("localVideo");
  const remoteVideos = document.getElementById("remoteVideos");
  const startConferenceBtn = document.getElementById("startConferenceBtn");
  const hangupBtn = document.getElementById("hangupBtn");
  const joinConferenceBtn = document.getElementById("joinConferenceBtn");
  const toggleCameraBtn = document.getElementById("toggleCameraBtn");
  const toggleMicBtn = document.getElementById("toggleMicBtn");

  let participantJoined = false;

  //----------------------------------------------------------
  // 1) Conference Start and End Event handlers
  //----------------------------------------------------------
  webrtcSocket.on("conference_ended", () => {
    alert("The conference was ended by the organizer.");
    leaveConference();
  });

  webrtcSocket.on("conference_started", (data) => {
    console.log("[conference_started]", data);
    window.config.conferenceActive = true;
    // For attendees, show the "Join Meeting" button
    if (!isOrganizer && joinConferenceBtn) {
      joinConferenceBtn.style.display = "inline-block";
      joinConferenceBtn.disabled = false;
    }
  });

  // Auto-join logic on page load.
  window.addEventListener("load", () => {
    if (conferenceActive && isOrganizer) {
      joinConference();
    }
    if (conferenceActive && !isOrganizer) {
      const joinedKey = `joined_meeting_${meetingId}`;
      if (localStorage.getItem(joinedKey) === "true") {
        participantJoined = true;
        if (joinConferenceBtn) {
          joinConferenceBtn.textContent = "Leave Meeting";
        }
        joinConference();
      }
    }
  });

  //----------------------------------------------------------
  // 2) Organizer Start/Stop Handlers
  //----------------------------------------------------------
  if (isOrganizer && startConferenceBtn && hangupBtn) {
    startConferenceBtn.addEventListener("click", async () => {
      try {
        const response = await fetch(`/conference/start/${meetingId}`, { method: "POST" });
        const res = await response.json();
        if (res.success) {
          startConferenceBtn.disabled = true;
          hangupBtn.disabled = false;
          // Organizer must join to share media.
          joinConference();
        } else {
          alert("Error starting conference: " + res.error);
        }
      } catch (err) {
        alert("Error starting conference: " + err.message);
      }
    });

    hangupBtn.addEventListener("click", async () => {
      try {
        const response = await fetch(`/conference/stop/${meetingId}`, { method: "POST" });
        const res = await response.json();
        if (res.success) {
          leaveConference();
          startConferenceBtn.disabled = false;
          hangupBtn.disabled = true;
        } else {
          alert("Error stopping conference: " + res.error);
        }
      } catch (err) {
        alert("Error stopping conference: " + err.message);
      }
    });
  }

  //----------------------------------------------------------
  // 3) Attendee Join/Leave Handlers
  //----------------------------------------------------------
  if (!isOrganizer && joinConferenceBtn) {
    joinConferenceBtn.addEventListener("click", () => {
      const joinedKey = `joined_meeting_${meetingId}`;
      if (!participantJoined) {
        joinConference();
        participantJoined = true;
        localStorage.setItem(joinedKey, "true");
        joinConferenceBtn.textContent = "Leave Meeting";
      } else {
        leaveConference();
        participantJoined = false;
        localStorage.removeItem(joinedKey);
        joinConferenceBtn.textContent = "Join Meeting";
      }
    });
  }

  //----------------------------------------------------------
  // 4) joinConference(): Get local stream then join the room
  //----------------------------------------------------------
  async function joinConference() {
    console.log("[joinConference] sending webrtc_join");
    try {
      // Get both video and audio.
      localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      // For testing, enable both by default so others can see/hear.
      localStream.getVideoTracks().forEach(track => (track.enabled = true));
      localStream.getAudioTracks().forEach(track => (track.enabled = true));
      
      // Attach the stream to local video element.
      localVideo.srcObject = localStream;
      localVideoTile.style.display = "block";

      // Expose the localStream globally so transcript.js can use it.
      window.localStream = localStream

      webrtcSocket.emit("webrtc_join", { meeting_id: meetingId });

      // Add a local mute/unmute button if not already present.
      if (!document.getElementById("localMuteBtn")) {
        const localMuteBtn = document.createElement("button");
        localMuteBtn.id = "localMuteBtn";
        localMuteBtn.textContent = "Mute";
        localMuteBtn.className = "btn btn-sm btn-secondary";
        localMuteBtn.style.position = "absolute";
        localMuteBtn.style.top = "10px";
        localMuteBtn.style.right = "10px";
        localMuteBtn.addEventListener("click", () => {
          const audioTracks = localStream.getAudioTracks();
          if (audioTracks && audioTracks.length > 0) {
            audioTracks[0].enabled = !audioTracks[0].enabled;
            localMuteBtn.textContent = audioTracks[0].enabled ? "Mute" : "Unmute";
            broadcastMediaUpdate();
          }
        });
        localVideoTile.appendChild(localMuteBtn);
      }









    } catch (err) {
      alert("Error accessing camera/mic: " + err.message);
    }
  }

  //----------------------------------------------------------
  // 5) leaveConference(): Clean up PeerConnections and streams
  //----------------------------------------------------------
  function leaveConference() {
    // Close each PeerConnection.
    for (let peerSid in peers) {
      peers[peerSid].close();
      delete peers[peerSid];
    }
    if (localStream) {
      localStream.getTracks().forEach(track => track.stop());
      localStream = null;
      window.localStream = null;
    }
    remoteVideos.innerHTML = "";
    localVideoTile.style.display = "none";
    if (toggleCameraBtn) toggleCameraBtn.textContent = "Turn Camera Off";
    if (toggleMicBtn) toggleMicBtn.textContent = "Turn Mic Off";
  }

  //----------------------------------------------------------
  // 6) WebRTC Signaling Handlers
  //----------------------------------------------------------
  // (A) When joining, receive list of existing participants.
  webrtcSocket.on("webrtc_current_participants", (existingPeers) => {
    console.log("[webrtc_current_participants]", existingPeers);
    existingPeers.forEach(peer => {
      createOffer(peer.peer_sid, peer.username);
    });
  });

  // (B) When another user joins, log the event (the new user will create offers).
  webrtcSocket.on("webrtc_peer_joined", (data) => {
    console.log("[webrtc_peer_joined]", data);
    // Do not create an offer here to avoid double negotiation.
  });

  // (C) When a peer leaves, remove their tile and close the connection.
  webrtcSocket.on("webrtc_peer_left", (data) => {
    console.log("[webrtc_peer_left]", data);
    const { peer_sid } = data;
    if (peers[peer_sid]) {
      peers[peer_sid].close();
      delete peers[peer_sid];
    }
    const tileEl = document.getElementById("remoteTile_" + peer_sid);
    if (tileEl) tileEl.remove();
  });

  // (D) Handle incoming offer.
  webrtcSocket.on("webrtc_offer", async (data) => {
    console.log("[webrtc_offer]", data);
    const { sender, offer, username } = data;
    let pc = peers[sender];
    if (!pc) {
      pc = createPeerConnection(sender, username);
    }
    try {
      await pc.setRemoteDescription(new RTCSessionDescription(offer));
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      webrtcSocket.emit("webrtc_answer", {
        target: sender,
        answer: pc.localDescription
      });
    } catch (err) {
      console.error("Error handling offer:", err);
    }
  });

  // (E) Handle incoming answer.
  webrtcSocket.on("webrtc_answer", async (data) => {
    console.log("[webrtc_answer]", data);
    const { sender, answer } = data;
    const pc = peers[sender];
    if (!pc) return;
    try {
      await pc.setRemoteDescription(new RTCSessionDescription(answer));
    } catch (err) {
      console.error("Error handling answer:", err);
    }
  });

  // (F) Handle incoming ICE candidates.
  webrtcSocket.on("webrtc_ice_candidate", async (data) => {
    const { sender, candidate } = data;
    const pc = peers[sender];
    if (!pc) return;
    try {
      await pc.addIceCandidate(new RTCIceCandidate(candidate));
    } catch (err) {
      console.error("Error adding ICE candidate:", err);
    }
  });

  //----------------------------------------------------------
  // 7) createOffer: Called by the new user for each existing participant.
  //----------------------------------------------------------
  async function createOffer(peerSid, username) {
    let pc = peers[peerSid];
    if (!pc) {
      pc = createPeerConnection(peerSid, username);
    }
    try {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      webrtcSocket.emit("webrtc_offer", {
        target: peerSid,
        offer: pc.localDescription
      });
    } catch (err) {
      console.error("Error creating offer:", err);
    }
  }

  //----------------------------------------------------------
  // 8) createPeerConnection: Attach local tracks and handle remote streams.
  //----------------------------------------------------------
  function createPeerConnection(peerSid, username) {
    const pc = new RTCPeerConnection(configuration);
    peers[peerSid] = pc;

    // Add local tracks (if available) so that remote peers get our stream.
    if (localStream) {
      localStream.getTracks().forEach(track => {
        pc.addTrack(track, localStream);
      });
    }

    pc.ontrack = (event) => {
      console.log("[ontrack] Received remote stream:", peerSid, username, event.streams);
      
      let tile = document.getElementById("remoteTile_" + peerSid);
      if (!tile) {
          tile = document.createElement("div");
          tile.id = "remoteTile_" + peerSid;
          tile.className = "video-tile";
          tile.style.position = "relative";
          tile.style.height = "180px";
          tile.style.margin = "5px";
  
          const remoteVideo = document.createElement("video");
          remoteVideo.id = "remoteVideo_" + peerSid;
          remoteVideo.autoplay = true;
          remoteVideo.playsInline = true;
          remoteVideo.style.width = "100%";
          remoteVideo.style.height = "100%";
          remoteVideo.style.objectFit = "cover";
          remoteVideo.style.border = "1px solid #ccc";
          tile.appendChild(remoteVideo);
  
          const overlay = document.createElement("div");
          overlay.style.position = "absolute";
          overlay.style.bottom = "0";
          overlay.style.left = "0";
          overlay.style.background = "rgba(0,0,0,0.5)";
          overlay.style.color = "#fff";
          overlay.style.padding = "2px 5px";
          overlay.style.fontSize = "0.9em";
          overlay.textContent = username;
          tile.appendChild(overlay);
  
          remoteVideos.appendChild(tile);
      }
  
      const remoteVideoEl = document.getElementById("remoteVideo_" + peerSid);
      remoteVideoEl.srcObject = event.streams[0];
  
      // ✅ FIX: Create a separate <audio> element for remote audio
      let remoteAudio = document.createElement("audio");
      remoteAudio.id = `remoteAudio_${peerSid}`;
      remoteAudio.srcObject = event.streams[0];
      remoteAudio.autoplay = true;
      remoteAudio.style.display = "none"; // Hide from UI
      document.body.appendChild(remoteAudio);
  
      // ✅ Ensure transcription system knows about this audio
      if (window.remoteAudioStreams === undefined) {
          window.remoteAudioStreams = new MediaStream();
      }
      event.streams[0].getAudioTracks().forEach((track) => {
          window.remoteAudioStreams.addTrack(track);
          console.log(`[Transcription] Added remote audio track from ${peerSid}`);
      });
  };
  

    pc.onicecandidate = (evt) => {
      if (evt.candidate) {
        webrtcSocket.emit("webrtc_ice_candidate", {
          target: peerSid,
          candidate: evt.candidate
        });
      }
    };

    return pc;
  }

  // Expose Remote Audio Elements to ensure that it is actually playing in browser
  function handleRemoteStream(peerID, remoteStream) {
    console.log(`[WebRTC] Remote stream received from peer: ${peerID}`);

    let audioElement = document.createElement("audio");
    audioElement.srcObject = remoteStream;
    audioElement.autoplay = true;
    audioElement.controls = false; 
    audioElement.style.display = "none"; // Hide it from the UI

    document.body.appendChild(audioElement); // Append to DOM for playback
}






  //----------------------------------------------------------
  // 9) Toggle Camera / Mic: Simply flip track.enabled on existing tracks.
  //----------------------------------------------------------
  if (toggleCameraBtn) {
    toggleCameraBtn.addEventListener("click", () => {
      if (!localStream) return;
      const videoTracks = localStream.getVideoTracks();
      if (!videoTracks || videoTracks.length === 0) return;
      const track = videoTracks[0];
      track.enabled = !track.enabled;
      const isOn = track.enabled;
      toggleCameraBtn.textContent = isOn ? "Turn Camera Off" : "Turn Camera On";
      broadcastMediaUpdate();
    });
  }

  if (toggleMicBtn) {
    toggleMicBtn.addEventListener("click", () => {
      if (!localStream) return;
      const audioTracks = localStream.getAudioTracks();
      if (!audioTracks || audioTracks.length === 0) return;
      const track = audioTracks[0];
      track.enabled = !track.enabled;
      const isOn = track.enabled;
      toggleMicBtn.textContent = isOn ? "Turn Mic Off" : "Turn Mic On";
      broadcastMediaUpdate();
    });
  }

  function broadcastMediaUpdate() {
    const videoEnabled = localStream?.getVideoTracks()?.[0]?.enabled ?? false;
    const audioEnabled = localStream?.getAudioTracks()?.[0]?.enabled ?? false;
    webrtcSocket.emit("media_update", {
      meeting_id: meetingId,
      user_id: userId,
      video_enabled: videoEnabled,
      audio_enabled: audioEnabled
    });
  }
})();