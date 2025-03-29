// app/static/js/meetingChat.js

// 1. Setup socket reference
const meetingId = window.config.meetingId;  // or however your template sets window.config.meetingId
console.log(meetingId);
const chatSocket = io("/chat", {
  auth: {
    meeting_id: meetingId
  },
  transports: ["websocket"]
});






// 2. On socket connect
chatSocket.on("connect", () => {
  console.log("Connected to chat namespace");
});

// 3. On chat_message
chatSocket.on("chat_message", (data) => {
    const chatMessages = document.getElementById("chatMessages");
    const msgDiv = document.createElement("div");
    msgDiv.classList.add("chat-message");

    // Fallback to default-profile.png if profilePicUrl is empty
    const profilePicUrl =
      data.profile_pic_url && data.profile_pic_url.trim() !== ""
        ? data.profile_pic_url
        : "/static/default-profile.png";

    // Convert "YYYY-MM-DD HH:MM:SS" (UTC) into local HH:MM:SS AM/PM
    const localTimeString = new Date(data.timestamp).toLocaleTimeString(
      "en-US",
      { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true }
    );

    msgDiv.innerHTML = `
      <img src="${profilePicUrl}" alt="Profile Pic" class="chat-avatar">
      <div class="message-content">
          <strong>${data.username}</strong> ${localTimeString}<br>${data.message}
      </div>
    `;
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
});

// 4. Handle text messages
document.getElementById("chatForm").addEventListener("submit", function (e) {
    e.preventDefault();
    const chatInput = document.getElementById("chatInput");
    const message = chatInput.value.trim();
    if (message !== "") {
        console.log("Emit Socket.IO ==> Chat_message Request Sent");
        console.log(meetingId);
        // Emit Socket.IO event to server
        chatSocket.emit("chat_message", {
            meeting_id: meetingId,
            message: message
        });
        chatInput.value = "";
    }
});

// 5. Handle file upload
document.getElementById("fileForm").addEventListener("submit", function (event) {
  event.preventDefault();
  let fileInput = document.getElementById("fileInput");
  let file = fileInput.files[0];
  if (!file) {
    alert("Please select a file to upload.");
    return;
  }

  let formData = new FormData();
  formData.append("file", file);
  // IMPORTANT: use meetingId, not "meeting_id" if your global var is named meetingId
  formData.append("meeting_id", meetingId);

  fetch("/chat/upload_file", {
    method: "POST",
    body: formData
  })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // Once the file is successfully saved on the server,
        // notify Socket.IO that there's a new file link to show
        chatSocket.emit("file_upload", {
          meeting_id: meetingId,
          filename: data.filename,
          file_url: data.file_url
        });
        fileInput.value = ""; // Clear file field after upload
      } else {
        alert("File upload failed: " + data.error);
      }
    })
    .catch(error => console.error("Upload error:", error));
});
