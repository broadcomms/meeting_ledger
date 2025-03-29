// app/static/js/transcription.js

document.addEventListener("DOMContentLoaded", function () {
  // Pull config from window
  const MEETING_ID = window.config.meetingId;
  const USER_ID = window.config.userId;

  const transcriptionSocket = io("/transcription", { 
    query: "meeting_id=" + MEETING_ID 
  });

  let audioContext;
  let recorderNode;

  // Grab DOM elements
  const startBtn = document.getElementById("startBtn");
  const stopBtn = document.getElementById("stopBtn");
  const statusEl = document.getElementById("status");
  // The container where individual transcript dialogs will be appended
  const transcriptContainer = document.getElementById("transcriptDiv");
  // Map to hold current live dialog elements per speaker
  const currentDialogs = {};

  /*****************************************************************
   * Socket.io event handlers
   *****************************************************************/
  transcriptionSocket.onAny((event, data) => {
    console.log("[TranscriptionSocket] Event Received: ", event, data);
  });

  transcriptionSocket.on("connect", () => {
    console.log("[TranscriptionSocket] Connected Successful");
  });

  transcriptionSocket.on("transcription_started", (data) => {
    console.log("[TranscriptionSocket] Transcription Started", data);
    statusEl.textContent = data.message || "Transcription Started.";
  });

  transcriptionSocket.on("transcription_stopped", (data) => {
    console.log("[TranscriptionSocket] Transcription Stopped", data);
    statusEl.textContent = data.message || "Transcription stopped.";
  });

  transcriptionSocket.on("disconnect", () => {
    console.log("[TranscriptionSocket] Disconnected");
  });

  // Handle interim updates (update existing dialog for the speaker)
  transcriptionSocket.on("transcript_update_interim", (data) => { 
    const speakerId = data.speaker_id; 
    let dialog = currentDialogs[speakerId]; 
    if (!dialog) { 
      // Create a new dialog if not present
      dialog = createDialog(data); 
      currentDialogs[speakerId] = dialog; 
      transcriptContainer.appendChild(dialog); 
    } else { 
      // Update the body text of the dialog
      const body = dialog.querySelector(".dialog-body"); 
      body.textContent = data.transcript;
      // Optionally update timestamp if desired 
    } 
    transcriptContainer.scrollTop = transcriptContainer.scrollHeight; 
  });


  // Handle final updates (append a new dialog and clear interim dialog)
  transcriptionSocket.on("transcript_update", (data) => {
    // Check if an interim dialog exists for the speaker
    const interimDialog = currentDialogs[data.speaker_id];
    if (interimDialog) {
      // Remove the interim dialog element from the container
      transcriptContainer.removeChild(interimDialog);
      // Remove it from the currentDialogs map
      delete currentDialogs[data.speaker_id];
    }
    // Create and append the final dialog
    const dialog = createDialog(data);
    transcriptContainer.appendChild(dialog);
    transcriptContainer.scrollTop = transcriptContainer.scrollHeight;

  });




  transcriptionSocket.on("transcript_saved", (data) => {
    console.log("[TranscriptionSocket] Transcript Saved", data);
    // Optionally, update a separate "saved transcripts" list.
  });
  

  transcriptionSocket.on("error_message", (data) => {
    alert(data.error);
  });

  function createDialog(data) {
    const dialog = document.createElement("div");
    dialog.className = "transcript-dialog mb-3 p-2 border rounded";
  
    const header = document.createElement("div");
    header.className = "dialog-header d-flex align-items-center mb-1";
    
    const img = document.createElement("img");
    img.className = "profile-icon me-2";
    img.style.width = "30px";
    img.style.height = "30px";
    img.style.objectFit = "cover";
    img.style.borderRadius = "50%";
    img.src = data.profile_pic_url || "/static/default-profile.png";
    
    const usernameSpan = document.createElement("strong");
    usernameSpan.textContent =
      data.speaker_id == USER_ID ? "You" : data.speaker_username;
    
    const timestampSpan = document.createElement("span");
    timestampSpan.className = "ms-2 text-muted";
    timestampSpan.style.fontSize = "0.9em";
    timestampSpan.textContent = new Date(data.created_timestamp).toLocaleTimeString();
    
    header.appendChild(img);
    header.appendChild(usernameSpan);
    header.appendChild(timestampSpan);
    
    const body = document.createElement("div");
    body.className = "dialog-body";
    body.textContent = data.transcript;
    
    dialog.appendChild(header);
    dialog.appendChild(body);
    
    return dialog;
  }



  /*****************************************************************
   * Start / Stop Transcription
   *****************************************************************/
  async function startTranscription() {
    console.log("[transcription.js] startTranscription() called");
    startBtn.disabled = true;
    stopBtn.disabled = false;

    // Send start event with meeting_id and user_id (speaker id)
    transcriptionSocket.emit("start_transcription", {
      meeting_id: MEETING_ID,
      user_id: USER_ID,
    });

    // Create AudioContext with desired sample rate
    audioContext = new AudioContext({ sampleRate: 16000 });
    

    const localTracks = window.localStream
      ? window.localStream.getAudioTracks()
      : [];
    if (localTracks.length === 0) {
      console.warn("[Transcription] No local audio track found.");
      stopBtn.disabled = true;
      startBtn.disabled = false;
      return;
    }

    try {
      // Load the audio worklet module and resume the AudioContext
      await audioContext.audioWorklet.addModule("/static/record-worklet.js");
      await audioContext.resume();

      // Create a MediaStream using only the local audio track
      const micStream = new MediaStream([localTracks[0]]);


      // INTERCEPT AUDIO TO GET SCREEN DISPLAY PLUS AUDIO

      //////////////////////////////////////////////////////


     // const mediaStream = await navigator.mediaDevices.getDisplayMedia({
     //   video: true,
      //  audio: true
     // });



      ///////////////////////////////////////////////////////
      const source = audioContext.createMediaStreamSource(micStream);
      //const source = audioContext.createMediaStreamSource(mediaStream); // INTERCEPTED






      
      // Create the recorder node
      recorderNode = new AudioWorkletNode(audioContext, "recorder-processor");
      recorderNode.port.onmessage = (event) => {
        const inputData = event.data;
        if (!inputData || inputData.length === 0) {
          console.warn(
            "[transcription.js] Received empty audio buffer from worklet"
          );
          return;
        }




        // Convert float samples [-1..1] to 16-bit PCM
        let buffer = new ArrayBuffer(inputData.length * 2);
        let view = new DataView(buffer);
        for (let i = 0; i < inputData.length; i++) {
          let s = Math.max(-1, Math.min(1, inputData[i]));
          view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        }

        // Encode to Base64
        const binary = String.fromCharCode(...new Uint8Array(buffer));
        const base64String = btoa(binary);

        // Send the audio chunk to the server with meeting_id and speaker info
        transcriptionSocket.emit("audio_chunk", {
          meeting_id: MEETING_ID,
          chunk: base64String,
          user_id: USER_ID, // include speaker id if desired
        });
      };

      // Connect the source to the recorder node and then to the destination (if you want to hear playback)
      source.connect(recorderNode).connect(audioContext.destination);
    } catch (err) {
      alert("[transcription.js] AudioContext or microphone error: " + err);
      stopBtn.disabled = true;
      startBtn.disabled = false;
    }
  }

  function stopTranscription() {
    console.log("[transcription.js] stopTranscription() called");
    stopBtn.disabled = true;
    startBtn.disabled = false;
    transcriptionSocket.emit("stop_transcription", { 
      meeting_id: MEETING_ID, 
      user_id: USER_ID 
    });
    if (recorderNode) recorderNode.disconnect();
    if (audioContext) audioContext.close();
    recorderNode = null;
    audioContext = null;
  }

  /*****************************************************************
   * Bind the start/stop buttons
   *****************************************************************/
  startBtn.addEventListener("click", startTranscription);
  stopBtn.addEventListener("click", stopTranscription);


  
// Function to edit a transcript.
// Opens a prompt to get updated text and then sends a POST request to update.
function editTranscript(transcriptId) {
  const transcriptElement = document.getElementById("transcript-text-" + transcriptId);
  const currentText = transcriptElement.textContent;
  const newText = prompt("Edit transcript:", currentText);
  if (newText !== null) {
    fetch(`/meetings/transcript/${transcriptId}/update`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ processed_transcript: newText })
    })
    .then(response => response.json())
    .then(data => {
      transcriptElement.textContent = data.processed_transcript;
      alert("Transcript updated successfully.");
    })
    .catch(error => {
      console.error("Error updating transcript:", error);
      alert("Failed to update transcript.");
    });
  }
}

// Function to reset a transcript.
// Sends a POST request to reset the transcript and then updates the DOM.
function resetTranscript(transcriptId) {
  if (confirm("Are you sure you want to reset this transcript?")) {
    fetch(`/meetings/transcript/${transcriptId}/reset`, {
      method: "POST"
    })
    .then(response => response.json())
    .then(data => {
      const transcriptElement = document.getElementById("transcript-text-" + transcriptId);
      transcriptElement.textContent = data.raw_transcript;
      alert("Transcript has been reset.");
    })
    .catch(error => {
      console.error("Error resetting transcript:", error);
      alert("Failed to reset transcript.");
    });
  }
}

// Function to delete a transcript.
// Sends a POST request to delete the transcript and removes it from the DOM.
function deleteTranscript(transcriptId) {
  if (confirm("Are you sure you want to delete this transcript?")) {
    fetch(`/meetings/transcript/${transcriptId}/delete`, {
      method: "POST"
    })
    .then(response => response.json())
    .then(data => {
      const liElement = document.getElementById("transcript-li-" + transcriptId);
      if (liElement) {
        liElement.remove();
      }
      alert("Transcript deleted successfully.");
    })
    .catch(error => {
      console.error("Error deleting transcript:", error);
      alert("Failed to delete transcript.");
    });
  }
}

// ... (rest of your code)

// Function to edit a transcript.
function editTranscript(transcriptId) {
  const transcriptElement = document.getElementById("transcript-text-" + transcriptId);
  const currentText = transcriptElement.textContent;
  const newText = prompt("Edit transcript:", currentText);
  if (newText !== null) {
    fetch(`/meetings/transcript/${transcriptId}/update`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ processed_transcript: newText })
    })
    .then(response => response.json())
    .then(data => {
      transcriptElement.textContent = data.processed_transcript;
      alert("Transcript updated successfully.");
    })
    .catch(error => {
      console.error("Error updating transcript:", error);
      alert("Failed to update transcript.");
    });
  }
}

// Function to reset a transcript.
function resetTranscript(transcriptId) {
  if (confirm("Are you sure you want to reset this transcript?")) {
    fetch(`/meetings/transcript/${transcriptId}/reset`, {
      method: "POST"
    })
    .then(response => response.json())
    .then(data => {
      const transcriptElement = document.getElementById("transcript-text-" + transcriptId);
      transcriptElement.textContent = data.raw_transcript;
      alert("Transcript has been reset.");
    })
    .catch(error => {
      console.error("Error resetting transcript:", error);
      alert("Failed to reset transcript.");
    });
  }
}

// Function to delete a transcript.
function deleteTranscript(transcriptId) {
  if (confirm("Are you sure you want to delete this transcript?")) {
    fetch(`/meetings/transcript/${transcriptId}/delete`, {
      method: "POST"
    })
    .then(response => response.json())
    .then(data => {
      const liElement = document.getElementById("transcript-li-" + transcriptId);
      if (liElement) {
        liElement.remove();
      }
      alert("Transcript deleted successfully.");
    })
    .catch(error => {
      console.error("Error deleting transcript:", error);
      alert("Failed to delete transcript.");
    });
  }
}


// Function to auto-correct a transcript using the server endpoint.
function autoCorrectTranscript(transcriptId) {
  if (confirm("Do you want to auto correct this transcript?")) {
    fetch(`/meetings/transcript/${transcriptId}/autocorrect`, {
      method: "POST"
    })
    .then(response => response.json())
    .then(data => {
      const transcriptElement = document.getElementById("transcript-text-" + transcriptId);
      transcriptElement.textContent = data.processed_transcript;
      alert("Transcript auto corrected successfully.");
    })
    .catch(error => {
      console.error("Error auto correcting transcript:", error);
      alert("Failed to auto correct transcript.");
    });
  }
}

// Expose autoCorrectTranscript globally.
window.autoCorrectTranscript = autoCorrectTranscript;

// Expose functions globally so inline onclick attributes can access them.
window.editTranscript = editTranscript;
window.resetTranscript = resetTranscript;
window.deleteTranscript = deleteTranscript;










// Bind the Generate Summary button click event
//const generateSummaryBtn = document.getElementById("generateSummaryBtn");
//const summaryContainer = document.getElementById("summaryContainer");

//if (generateSummaryBtn) {
//  generateSummaryBtn.addEventListener("click", () => {
    // Clear the previous summary content
//    summaryContainer.innerHTML = "";



    // Emit the generate_summary event with the meeting ID
//    transcriptionSocket.emit("generate_summary", { meeting_id: MEETING_ID }); // GENERATE SUMMARY




//  });
//}

// Listen for summary update events from the server
//transcriptionSocket.on("summary_update", (data) => { // UPDATE SUMMARY



  // Append each chunk to the summary container
//  summaryContainer.innerHTML += data.summary_chunk;
//  summaryContainer.scrollTop = summaryContainer.scrollHeight;
//});

// Listen for the summary complete event
//transcriptionSocket.on("summary_complete", (data) => {
//  alert(data.message || "Summary generation complete.");
//});





// Bind the Extract Tasks button to send a POST request to extract tasks.
const extractTasksBtn = document.getElementById("extractTasksBtn");
const taskContainer = document.getElementById("taskContainer");

if (extractTasksBtn) {
  
  extractTasksBtn.addEventListener("click", () => {
    
    fetch("/meetings/extract_tasks", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ meeting_id: MEETING_ID })
    })
    .then(response => response.json())
    .then(data => {
      // Clear any previous tasks
      taskContainer.innerHTML = "";
      if (data.tasks && data.tasks.length > 0) {
        data.tasks.forEach(task => {
          // Create a container for each task
          const div = document.createElement("div");
          div.id = `task-${task.action_item_id}`;
          div.className = "d-flex align-items-center border-bottom py-2";
          div.innerHTML = `
            <input type="checkbox" class="form-check-input me-2" ${task.status === 'complete' ? 'checked' : ''} onchange="updateTaskStatus('${task.action_item_id}', this.checked ? 'complete' : 'pending')">
            <span id="task-desc-${task.action_item_id}" class="flex-grow-1">${task.description}</span>
            <button onclick="editTask('${task.action_item_id}')" class="btn btn-sm btn-secondary ms-2">Edit</button>
          `;
          taskContainer.appendChild(div);
        });
      } else {
        taskContainer.innerHTML = "<p>No tasks extracted.</p>";
      }
    })
    .catch(error => {
      console.error("Error extracting tasks:", error);
      alert("Failed to extract tasks.");
    });
  });
}


});