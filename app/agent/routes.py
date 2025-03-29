# app/agent/routes.py

from flask import (
    Blueprint,
    request,
    jsonify,
    current_app
)
from flask_login import login_required, current_user
from datetime import datetime
import json, re
# Import models needed for data aggregation and storage
from app.models import (
    Meeting,
    Transcript,
    ActionItem,
    ChatMessage,
    ChatFile,
    Summary,
    Participant,
    User,
    CalendarEvent,
    TaskFile
)
from app.extensions import db, mail, socketio
from app.config import Config

# Import Watsonx LLM wrapper and prompt template
from langchain_ibm import WatsonxLLM, ChatWatsonx
from langchain_core.prompts import PromptTemplate
from flask_mail import Message
from concurrent.futures import ThreadPoolExecutor

from app.transcription.transcription import TranscriptionSession
from flask_socketio import emit

agent_bp = Blueprint("agent_bp", __name__, template_folder="templates", url_prefix="/agent")

# Enhance aggregation to also include task documents metadata
def aggregate_pre_meeting_data(meeting_id):
    print("AGGREGATING PRE MEETING DATA")
    """
    Aggregate all pre-meeting inputs for the given meeting_id.
    This includes meeting details, transcripts, past action items,
    chat messages, and any uploaded documents from chat and tasks.
    """
    
    # Check for invalid meeting_id
    if not meeting_id:
        meeting = 0
        pre_meeting_data = f"""
        Meeting Title: ""
        Meeting Description: ""
        Meeting Data and Time: ""
        Meeting Duration: ""
        Transcripts: ""
        Calendar Events: ""
        Action Items: ""
        Chat Messages: ""
        Uploaded Chat Documents: ""
        Uploaded Task Documents: ""
        """
        return meeting, pre_meeting_data
    
    meeting = Meeting.query.get_or_404(meeting_id)
    # Get transcripts
    transcripts = Transcript.query.filter_by(meeting_id=meeting_id).all()
    transcript_text = " ".join([
        t.processed_transcript if t.processed_transcript else t.raw_transcript
        for t in transcripts
    ])

    # Get past action items
    action_items = ActionItem.query.filter_by(meeting_id=meeting_id).all()
    action_text = " ".join([ai.description for ai in action_items])

    # Get chat messages
    chat_msgs = ChatMessage.query.filter_by(meeting_id=meeting_id).all()
    chat_text = " ".join([cm.message for cm in chat_msgs])

    # Uploaded chat files
    chat_files = ChatFile.query.filter_by(meeting_id=meeting_id).all()
    chat_file_list = ", ".join([cf.filename for cf in chat_files])
    
    # Uploaded task files (via ActionItems)
    task_files_query = TaskFile.query.join(ActionItem).filter(ActionItem.meeting_id == meeting_id).all()
    task_file_list = ", ".join([tf.filename for tf in task_files_query])
   
    # Calendar events
    participants = Participant.query.filter_by(meeting_id=meeting_id).all()
    calendar_events = CalendarEvent.query.filter(
        CalendarEvent.user_id.in_([p.user_id for p in participants]),
        CalendarEvent.start_date >= datetime.utcnow()
    ).all()
    calendar_event_text = " ".join([f"{ce.title} on {ce.start_date.strftime('%Y-%m-%d')}" for ce in calendar_events])
    
    pre_meeting_data = f"""
        Meeting Title: {meeting.title}
        Meeting Description: {meeting.description}
        Meeting Data and Time: {meeting.date_time}
        Meeting Duration: {meeting.duration}
        Transcripts: {transcript_text}
        Calendar Events: {calendar_event_text}
        Action Items: {action_text}
        Chat Messages: {chat_text}
        Uploaded Chat Documents: {chat_file_list}
        Uploaded Task Documents: {task_file_list}
        """
    
    return meeting, pre_meeting_data





#--------------------------------------------
# Generate Agent Output
#-------------------------------------------

def clean_llm_output(raw_text: str) -> str:
    """
    Optionally remove any Markdown code fences or triple backticks
    if you want to strip them from the raw text. This is optional 
    since you are no longer requiring valid JSON, but it can help 
    avoid clutter in the final string.
    """
    cleaned = re.sub(r"```(?:json)?", "", raw_text, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^```\s*$", "", cleaned, flags=re.MULTILINE).strip()
    return cleaned












#--------------------------------------------
# Generate Agent Output
#-------------------------------------------

def generate_agent_output(pre_meeting_data):
    """
    Calls three Watsonx models in parallel (one each for agenda, invitation, 
    and recommendations), returning raw text from each. 
    No JSON parsing is done here.
    """

    # 1) Define separate prompt templates
    agenda_prompt_template = """
    Based on the following pre-meeting data,
    generate a structured meeting agenda (plain text).
    Create a well-structured agenda that includes a brief introduction, key discussion points, and a logical flow for the meeting. 
    Ensure the agenda is professional and concise, aligning with the meeting objectives.
    Do NOT return JSON. 
    Ensure that the content is in such a way that can be directly posted into a document without further changes required.
    Do not include characters such as **
    
    Pre-meeting data: {pre_meeting_data}
    """

    invitation_prompt_template = """
    Based on the following pre-meeting data,
    generate a concise meeting invitation (plain text).
    Do NOT return JSON. 
    Ensure that the content is in such a way that can be directly posted into a document without further changes required.
    Do not include characters such as **
    
    Pre-meeting data: {pre_meeting_data}
    """

    recommendations_prompt_template = """
    Based on the following pre-meeting data, 
    provide a list of recommendations for topics, materials, and highlights of prior action items (plain text). 
    Do NOT return JSON. 
    Ensure that the content is in such a way that can be directly posted into a document without further changes required.
    Do not include characters such as **

    Pre-meeting data: {pre_meeting_data}
    """

    # Define functions for each call
    def get_agenda():
        agenda_prompt = PromptTemplate.from_template(agenda_prompt_template)
        watsonx_llm_agenda = WatsonxLLM(
            model_id=Config.WATSONX_MODEL_ID_1,
            url=Config.WATSONX_URL,
            project_id=Config.WATSONX_PROJECT_ID,
            apikey=Config.WATSONX_API_KEY,
            params={
                "decoding_method": "sample",
                "max_new_tokens": 800,
                "temperature": 0.6,
                "top_k": 38,
                "top_p": 0.8,
            }
        )
        chain = agenda_prompt | watsonx_llm_agenda
        raw_agenda = chain.invoke({"pre_meeting_data": pre_meeting_data})
        return clean_llm_output(raw_agenda)
        #return raw_agenda

    def get_invitation():
        invitation_prompt = PromptTemplate.from_template(invitation_prompt_template)
        watsonx_llm_invitation = WatsonxLLM(
            model_id=Config.WATSONX_MODEL_ID_2,
            url=Config.WATSONX_URL,
            project_id=Config.WATSONX_PROJECT_ID,
            apikey=Config.WATSONX_API_KEY,
            params={
                "decoding_method": "sample",
                "max_new_tokens": 200,
                "temperature": 0.7,
                "top_k": 25,
                "top_p": 1,
            }
        )
        chain = invitation_prompt | watsonx_llm_invitation
        raw_invitation = chain.invoke({"pre_meeting_data": pre_meeting_data})
        return clean_llm_output(raw_invitation)
        #return raw_invitation

    def get_recommendations():
        recommendations_prompt = PromptTemplate.from_template(recommendations_prompt_template)
        watsonx_llm_recommendations = WatsonxLLM(
            model_id=Config.WATSONX_MODEL_ID_3,
            url=Config.WATSONX_URL,
            project_id=Config.WATSONX_PROJECT_ID,
            apikey=Config.WATSONX_API_KEY,
            params={
                "decoding_method": "sample",
                "max_new_tokens": 800,
                "temperature": 0.7,
                "top_k": 45,
                "top_p": 1,
            }
        )
        chain = recommendations_prompt | watsonx_llm_recommendations
        raw_recommendations = chain.invoke({"pre_meeting_data": pre_meeting_data})
        return clean_llm_output(raw_recommendations)
        # return raw_recommendations


    # Run the three calls concurrently
    with ThreadPoolExecutor() as executor:
        future_agenda = executor.submit(get_agenda)
        future_invitation = executor.submit(get_invitation)
        future_recommendations = executor.submit(get_recommendations)

        agenda_text = future_agenda.result()
        invitation_text = future_invitation.result()
        recommendations_text = future_recommendations.result()

    return {
        "agenda": agenda_text,
        "invitation": invitation_text,
        "recommendations": recommendations_text
    }




def send_invitations(meeting, invitation_content):
    """
    Loop through meeting participants and send invitation emails.
    """
    # Get all participants for the meeting
    participants = Participant.query.filter_by(meeting_id=meeting.meeting_id).all()

    # Also include the organizer if desired
    recipient_emails = set()
    for participant in participants:
        user = User.query.get(participant.user_id)
        if user and user.email:
            recipient_emails.add(user.email)

    subject = f"Meeting Invitation: {meeting.title}"
    for email in recipient_emails:
        msg = Message(
            subject=subject,
            recipients=[email],
            html=invitation_content,
            sender=Config.MAIL_DEFAULT_SENDER
        )
        try:
            mail.send(msg)
        except Exception as e:
            current_app.logger.error(f"Failed to send email to {email}: {str(e)}")













# ------------------------------------------------------------
# Generate Agenda, Invitation and Recommendation
# ------------------------------------------------------------


@agent_bp.route("/get_agenda/<int:meeting_id>", methods=["POST"])
@login_required
def get_agenda(meeting_id):
    """
    Endpoint to get the meeting agenda, invitation and recommendation from database
    
    """
    # Retrieve the latest 'agenda' summary from the DB
    agenda_summary = Summary.query.filter_by(
        meeting_id=meeting_id, 
        summary_type="agenda"
        ).order_by(Summary.created_timestamp.desc()).first()
    
    # Parse the stored JSON from the summary_text if available
    agenda_data = {}
    if agenda_summary:
        try:
            agenda_data = json.loads(agenda_summary.summary_text)
        except Exception as e:
            current_app.logger.error("Failed to parse agenda summary JSON: %s", e)
            agenda_data = {}
            
    return jsonify({"meeting_id": meeting_id, "agenda": agenda_data})




@agent_bp.route("/generate_agenda/<int:meeting_id>", methods=["POST"])
@login_required
def generate_agenda(meeting_id):
    """
    Endpoint to generate the meeting agenda and invitation using the agent.
    Aggregates pre-meeting data, calls three Watsonx models for raw text,
    sends out meeting invitations, and returns the results.
    """
    try:
        meeting, pre_meeting_data = aggregate_pre_meeting_data(meeting_id)
        agent_output = generate_agent_output(pre_meeting_data)  # dict of raw strings
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Save the generated output in the database as a Summary with type "agenda"
    summary = Summary(
        meeting_id=meeting_id,
        summary_text=json.dumps(agent_output),
        summary_type="agenda",
        created_timestamp=datetime.utcnow()
    )
    db.session.add(summary)
    db.session.commit()

    # Send out meeting invitations using the invitation raw text.
    # invitation_content = agent_output.get("invitation", "You are invited to the meeting.")
    # send_invitations(meeting, invitation_content)

    # Emit a websocket event to update the UI in real time.
    socketio.emit(
        "agenda_generated",
        {"meeting_id": meeting_id, "agenda": agent_output},
        room=f"meeting_{meeting_id}",
        namespace="agent"
    )

    return jsonify({"success": True, "data": agent_output})

@agent_bp.route("/refine_agenda/<int:meeting_id>", methods=["POST"])
@login_required
def refine_agenda(meeting_id):
    """
    (Optional) Endpoint for users to request further refinements or
    clarifications on the agenda. Expects a JSON payload with a 
    "refinement" key containing user input. The agent will use 
    the additional input to refine the previously generated agenda.
    """
    user_input = request.get_json().get("refinement", "")
    if not user_input:
        return jsonify({"error": "No refinement input provided."}), 400

    # For simplicity, re-aggregate data and add the user’s input into the prompt.
    meeting, pre_meeting_data = aggregate_pre_meeting_data(meeting_id)
    prompt_template = """
    You are a virtual meeting assistant. The meeting agenda has already been generated 
    based on the following pre-meeting data: {pre_meeting_data}

    The user has requested the following refinement or clarification: "{refinement}"

    Please provide a refined version of the agenda, invitation, and recommendations. 
    Output only valid JSON with keys "agenda", "invitation", and "recommendations".
    """

    prompt = PromptTemplate.from_template(prompt_template)

    watsonx_llm = WatsonxLLM(
        model_id=Config.WATSONX_MODEL_ID_3,
        url=Config.WATSONX_URL,
        project_id=Config.WATSONX_PROJECT_ID,
        apikey=Config.WATSONX_API_KEY,
        params={
            "decoding_method": "sample",
            "max_new_tokens": 800,
            "temperature": 0.7,
            "top_k": 45,
            "top_p": 1,
        }
    )

    llm_chain = prompt | watsonx_llm
    try:
        result = llm_chain.invoke({"pre_meeting_data": pre_meeting_data, "refinement": user_input})
        refined_output = json.loads(result)
    except Exception as e:
        return jsonify({"error": f"Failed to refine agenda: {str(e)}"}), 500

    # Optionally update the Summary record or create a new one.
    summary = Summary(
        meeting_id=meeting_id,
        summary_text=json.dumps(refined_output),
        summary_type="agenda_refined",
        created_timestamp=datetime.utcnow()
    )
    db.session.add(summary)
    db.session.commit()

    # Optionally emit a websocket event with the refined output.
    socketio.emit(
        "agenda_refined",
        {"meeting_id": meeting_id, "agenda": refined_output},
        room=f"meeting_{meeting_id}"
    )

    return jsonify({"success": True, "data": refined_output})


# Endpoint: Ask a transcript clarification question
@agent_bp.route("/ask_transcript_question/<int:meeting_id>", methods=["POST"])
@login_required
def ask_transcript_question(meeting_id):
    """
    Accepts a user question regarding the meeting transcript and returns a clarification answer.
    """
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Question is required."}), 400

    meeting, pre_meeting_data = aggregate_pre_meeting_data(meeting_id)
    
    clarification_prompt_template = """
    You are a virtual meeting assistant. Based on the following meeting data:
    {pre_meeting_data}
    Answer the following user question with a clear, concise explanation:
    "{question}"
    Provide your answer in plain text.
    """
    prompt = PromptTemplate.from_template(clarification_prompt_template)
    
    watsonx_llm_clarification = WatsonxLLM(
        model_id=Config.WATSONX_MODEL_ID_3,  # Using model 3 for clarifications
        url=Config.WATSONX_URL,
        project_id=Config.WATSONX_PROJECT_ID,
        apikey=Config.WATSONX_API_KEY,
        params={
            "decoding_method": "sample",
            "max_new_tokens": 400,
            "temperature": 0.7,
            "top_k": 45,
            "top_p": 1,
        }
    )
    
    llm_chain = prompt | watsonx_llm_clarification
    try:
        raw_answer = llm_chain.invoke({"pre_meeting_data": pre_meeting_data, "question": question})
        answer = raw_answer.strip()
    except Exception as e:
        return jsonify({"error": f"LLM error: {str(e)}"}), 500
    
    return jsonify({"success": True, "answer": answer})

# Endpoint: Mark a chat message as an action item
@agent_bp.route("/mark_action_item/<int:meeting_id>", methods=["POST"])
@login_required
def mark_action_item(meeting_id):
    """
    Marks a chat message as an action item.
    Expects JSON payload with "message" field.
    """
    data = request.get_json() or {}
    message_text = data.get("message", "").strip()
    if not message_text:
        return jsonify({"error": "Message text is required."}), 400
    
    action_item = ActionItem(
        meeting_id=meeting_id,
        assigned_to=current_user.user_id,
        description=message_text,
        status="pending",
        priority="medium",
        created_timestamp=datetime.utcnow()
    )
    db.session.add(action_item)
    db.session.commit()
    
    # Emit a real-time update via Socket.IO
    socketio.emit("action_item_marked", {
        "meeting_id": meeting_id,
        "action_item": {
            "action_item_id": action_item.action_item_id,
            "description": action_item.description,
            "status": action_item.status,
            "priority": action_item.priority
        }
    }, room=f"meeting_{meeting_id}")
    
    return jsonify({"success": True, "action_item_id": action_item.action_item_id})

# Endpoint: Search for meeting-related data and documents
@agent_bp.route("/search_meeting_data/<int:meeting_id>", methods=["POST"])
@login_required
def search_meeting_data(meeting_id):
    """
    Searches meeting data (transcripts, summaries, and document metadata) based on a user query.
    """
    data = request.get_json() or {}
    query = data.get("query", "").strip().lower()
    if not query:
        return jsonify({"error": "Query text is required."}), 400
    
    meeting, pre_meeting_data = aggregate_pre_meeting_data(meeting_id)
    # A simple keyword-based search in the aggregated data
    results = []
    for segment in pre_meeting_data.split("\n"):
        if query in segment.lower():
            results.append(segment.strip())
    if not results:
        results.append(pre_meeting_data.strip())
    
    return jsonify({"success": True, "results": results})

# Endpoint: Analyze sentiment of provided text
@agent_bp.route("/analyze_sentiment", methods=["POST"])
@login_required
def analyze_sentiment():
    """
    Analyzes the sentiment of the provided text using an LLM prompt.
    """
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Text is required for sentiment analysis."}), 400
    
    sentiment_prompt_template = """
    Analyze the sentiment of the following text and provide:
    1. A sentiment score between -1 (very negative) and 1 (very positive).
    2. A brief explanation of the sentiment.
    
    Text: {text}
    """
    prompt = PromptTemplate.from_template(sentiment_prompt_template)
    
    watsonx_llm_sentiment = WatsonxLLM(
        model_id=Config.WATSONX_MODEL_ID_3,
        url=Config.WATSONX_URL,
        project_id=Config.WATSONX_PROJECT_ID,
        apikey=Config.WATSONX_API_KEY,
        params={
            "decoding_method": "sample",
            "max_new_tokens": 150,
            "temperature": 0.5,
            "top_k": 45,
            "top_p": 1,
        }
    )
    
    llm_chain = prompt | watsonx_llm_sentiment
    try:
        raw_sentiment = llm_chain.invoke({"text": text})
        sentiment_analysis = raw_sentiment.strip()
    except Exception as e:
        return jsonify({"error": f"Sentiment analysis failed: {str(e)}"}), 500
    
    return jsonify({"success": True, "sentiment": sentiment_analysis})

def determine_intent(message):
    """
    Simple heuristic to decide if the user query is about transcript clarification,
    marking an action item, or a general query.
    """
    msg_lower = message.lower()
    if "transcript" in msg_lower or "clarify" in msg_lower:
        return "transcript"
    elif msg_lower.startswith("action:"):
        return "action"
    else:
        return "general"

def process_transcript_question(meeting_id, question):
    """
    Uses the existing pre-meeting data aggregation and calls a Watsonx LLM chain
    to generate a clarification answer for transcript-related queries.
    """
    meeting, pre_meeting_data = aggregate_pre_meeting_data(meeting_id)
    clarification_prompt_template = """
    You are a virtual meeting assistant. Based on the following meeting data:
    {pre_meeting_data}
    Answer the following user question with a clear, concise explanation:
    "{question}"
    Provide your answer in plain text.
    """
    prompt = PromptTemplate.from_template(clarification_prompt_template)
    watsonx_llm_clarification = WatsonxLLM(
        model_id=Config.WATSONX_MODEL_ID_3,  # Use model 3 for clarifications
        url=Config.WATSONX_URL,
        project_id=Config.WATSONX_PROJECT_ID,
        apikey=Config.WATSONX_API_KEY,
        params={
            "decoding_method": "sample",
            "max_new_tokens": 400,
            "temperature": 0.7,
            "top_k": 45,
            "top_p": 1,
        }
    )
    llm_chain = prompt | watsonx_llm_clarification
    try:
        raw_answer = llm_chain.invoke({"pre_meeting_data": pre_meeting_data, "question": question})
        answer = raw_answer.strip()
    except Exception as e:
        answer = f"Error processing transcript clarification: {str(e)}"
    return answer

def process_action_item(meeting_id, action_text):
    """
    Creates a new ActionItem in the database (like the /mark_action_item endpoint)
    and emits a socket event so that all participants are notified.
    """
    if not action_text:
        return "No action text provided."
    action_item = ActionItem(
        meeting_id=meeting_id,
        assigned_to=current_user.user_id,
        description=action_text,
        status="pending",
        priority="medium",
        created_timestamp=datetime.utcnow()
    )
    db.session.add(action_item)
    db.session.commit()
    # Emit a real-time update via Socket.IO for the new task
    socketio.emit("action_item_marked", {
        "meeting_id": meeting_id,
        "action_item": {
            "action_item_id": action_item.action_item_id,
            "description": action_item.description,
            "status": action_item.status,
            "priority": action_item.priority
        }
    }, room=f"meeting_{meeting_id}")
    return f"Action item marked: {action_text}"

def process_general_query(meeting_id, query):
    # Aggregate pre-meeting data
    meeting, pre_meeting_data = aggregate_pre_meeting_data(meeting_id)
    # Filter out the "Chat Messages:" portion to avoid clutter
    filtered_data = "\n".join(
        line for line in pre_meeting_data.split("\n")
        if not line.strip().startswith("Chat Messages:")
    )
    
    # Define a prompt template for general queries
    general_prompt_template = """
    You are a virtual meeting assistant. Based on the following meeting data:
    {pre_meeting_data}
    And considering the following user query:
    "{query}"
    Please provide a clear and concise answer that is helpful and relevant to the meeting context.
    """
    
    # Create a PromptTemplate object
    prompt = PromptTemplate.from_template(general_prompt_template)
    
    # Create an LLM object (using model 3 here)
    llm = WatsonxLLM(
        model_id=Config.WATSONX_MODEL_ID_3,
        url=Config.WATSONX_URL,
        project_id=Config.WATSONX_PROJECT_ID,
        apikey=Config.WATSONX_API_KEY,
        params={
            "decoding_method": "sample",
            "max_new_tokens": 400,
            "temperature": 0.8,
            "top_k": 45,
            "top_p": 1,
        }
    )
    
    # Build and invoke the chain
    llm_chain = prompt | llm
    try:
        raw_answer = llm_chain.invoke({"pre_meeting_data": filtered_data, "query": query})
        answer = raw_answer.strip()
    except Exception as e:
        answer = f"Error generating answer: {str(e)}"
    return answer














# //////////////////////////////
################################
# LLM-powered agent architecture design
################################
# //////////////////////////////



from langgraph.prebuilt import create_react_agent
from langchain.agents import Tool, initialize_agent
from langchain.tools import tool
from langchain_core.prompts import PromptTemplate
from app.agent.routes import aggregate_pre_meeting_data, send_invitations
from app.models import ActionItem
from app.extensions import db, socketio
from flask_login import current_user
from datetime import datetime
from app.config import Config
from langchain.schema import HumanMessage, SystemMessage
from langgraph.graph import START, MessagesState, StateGraph
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver


# //////////////////////////////
# 1. === MODEL SETUP =====
# //////////////////////////////

# Instantiate the chat model object using IBM watsonx endpoints
llm = ChatWatsonx(
    model_id=Config.WATSONX_MODEL_ID_3,
    url=Config.WATSONX_URL,
    project_id=Config.WATSONX_PROJECT_ID,
    apikey=Config.WATSONX_API_KEY,
    params={
        "decoding_method": "sample",
        "max_new_tokens": 500,
        "temperature": 0.6,
        "top_k": 40,
        "top_p": 0.8,
    }
)

# //////////////////////////////
# 2. === SYSTEM MESSAGE =====
# //////////////////////////////

system_message = """
                You are a virtual meeting assistant.
                """

#////////////////////////////////////
# 3. === CONVERSATIONAL WORKFLOW ====
#////////////////////////////////////

# Define the conversation workflow using a StateGraph.
# The StateGraph helps manage the flow of messages between the user and the model.
workflow = StateGraph(state_schema=MessagesState)
# Define the function that processes messages by invoking the model.
def call_model(state: MessagesState):
    """
    This function is responsible for sending the current conversation messages
    to the model and returning the model's response. It takes the current state,
    extracts the messages, invokes the model, and then returns the new messages.
    """
    system_msg = SystemMessage(content=system_message)
    # Ensure the system message is the first message in the conversation
    messages = [system_msg] + state["messages"]
    
    response = llm.invoke(messages)
    # Ensure the response is in dictionary format
    if not isinstance(response, dict):
        response = {"message": response}
    
    return {"messages": response}

workflow.add_edge(START, "model")
# Add a node named "model" that uses the call_model function.
# This node represents the processing step where the model generates a response
# based on the conversation's messages.
workflow.add_node("model", call_model)

# Setup persistent memory with SQLite
conn = sqlite3.connect("app/agent/chat_memory.sqlite", check_same_thread=False)
memory = SqliteSaver(conn)
app = workflow.compile(checkpointer=memory)

# //////////////////////////////
# 4. === TOOLS SETUP =====
# //////////////////////////////

# -----------------------------
# a. PDF Retrieval + Q&A Tool
# -----------------------------
def pdf_qa(input_str: str) -> str:
    """
    Expects a JSON or simple string input with two keys: 
      - "pdf_path": path to the PDF
      - "question": question to ask
    Example input:
        {
            "pdf_path": "path/to/file.pdf",
            "question": "What does the document say about XYZ?"
        }
    """
    try:
        data = json.loads(input_str)
        pdf_path = data.get("pdf_path", "").strip()
        question = data.get("question", "").strip()
        if not pdf_path or not question:
            return "Error: Please provide both 'pdf_path' and 'question'."
    except:
        return ("Error: Input must be valid JSON with 'pdf_path' and 'question' keys. "
                "Example: {\"pdf_path\": \"sample.pdf\", \"question\": \"...\"}")

    # Load and process PDF document
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()

    # Split documents into manageable chunks.
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    splitted_docs = text_splitter.split_documents(docs)

    # Create embeddings using WatsonxEmbeddings
    embeddings = WatsonxEmbeddings(
        model_id="ibm/slate-125m-english-rtrvr",
        project_id=Config.WATSONX_PROJECT_ID,
    )

    # Build in-memory FAISS vector store for retrieval.
    vector_store = FAISS.from_documents(splitted_docs, embeddings)

    # Setup a retrieval-based Q&A chain with a nested LLM.
    qa_llm = ChatWatsonx(
        model_id="ibm/granite-3-8b-instruct", 
        url=Config.WATSONX_URL,
        project_id=Config.WATSONX_PROJECT_ID,
        # Model Parameters for ChatWatsonx
        params={
            "temperature": 0, 
            "max_tokens": 2500
        },
    )
    qa_chain = RetrievalQA.from_chain_type(
        llm=qa_llm,
        chain_type="stuff",
        retriever=vector_store.as_retriever(),
    )

    # Ask the question with retrieved PDF context
    answer = qa_chain.run(question)
    return answer

# Wrap the PDF Q&A function as a Tool object
pdf_qa_tool = Tool(
    name="PdfQA",
    func=pdf_qa,
    description=(
        "Use this tool to answer questions about the contents of a PDF. "
        "Input must be JSON with 'pdf_path' and 'question' keys."
    ),
)

# -----------------------------
# b. Mark Action Item Tool
# -----------------------------

def mark_action_item_tool_func(meeting_id: int, description: str) -> str:
    """
    Adds an action item to the meeting and emits a socket event.
    """
    action_item = ActionItem(
        meeting_id=meeting_id,
        assigned_to=current_user.user_id,
        description=description,
        status="pending",
        priority="medium",
        created_timestamp=datetime.utcnow()
    )
    db.session.add(action_item)
    db.session.commit()

    socketio.emit("action_item_marked", {
        "meeting_id": meeting_id,
        "action_item": {
            "action_item_id": action_item.action_item_id,
            "description": action_item.description,
            "status": action_item.status,
            "priority": action_item.priority
        }
    }, room=f"meeting_{meeting_id}")

    return f"Action item added: {description}"

# Wrap the Mark Action Item Tool as a Tool object
action_item_tool = Tool(
            name="mark_action_item",
            func=lambda description: mark_action_item_tool_func(meeting_id, description),
            description=(
                    "Use this tool to add action items."
                ),
        )



# //////////////////////////////
# 6. === AGENT EXECUTOR =====
# //////////////////////////////

def create_agent_executor(meeting_id):
    
    # Combine All Tools
    tools = [
        pdf_qa_tool,
        action_item_tool
    ]

    # Create the agent executor using the ReACT agent with Model and Tools.
    agent_executor = create_react_agent(llm, tools, checkpointer=memory)


    return agent_executor

    # Meeting ID for conversation persistence
    # Config = {"configurable": {"thread_id": meeting_id}}

# 3. === MAIN FUNCTION =====

def process_user_query(meeting_id, user_query):
    print("PROCESSING USER QUERY") # DEBUG CODE
    meeting, pre_meeting_data = aggregate_pre_meeting_data(meeting_id)
    print("AGGREGATE DATA ACQUIRED")
    agent_executor = create_agent_executor(meeting_id)
    
    prompt = f"""
    You are a helpful virtual assistant for meetings.

    Meeting Context:
    {pre_meeting_data}

    User Query:
    {user_query}

    Please respond accurately or execute any required actions.
    """
    # Create a state dictionary with a "messages" key
    state = {"messages": [HumanMessage(content=prompt)]}
    config = {"configurable": {"thread_id": meeting_id}}
    
    try:
        result = agent_executor.invoke(state, config)
        
        # If the result contains messages, extract the last message only
        if isinstance(result, dict) and "messages" in result:
            messages = result["messages"]
            if isinstance(messages, list) and messages:
                last_message = messages[-1]
                message_text = last_message.content if hasattr(last_message, "content") else str(last_message)
                print(message_text) # DEBUG CODE
                return message_text  # Return only the last agent reply
                
            elif hasattr(messages, "content"):
                return messages.content
            else:
                return str(messages)
        else:
            return str(result)
    except Exception as e:
        return f"Agent execution error: {str(e)}"
    



@agent_bp.route("/chat_message", methods=["POST"])
# @login_required
def chat_message():
    data = request.get_json() or {}
    print("AGENT Chat Message ", data.get("meeting_id", 0))
    print("AGENT Chat MeetingID ", data.get("user_id", 0))
    user_message = data.get("message", "").strip()
    meeting_id = data.get("meeting_id", 0)
    
    
    if not user_message:
        return jsonify({"error": "Message required."}), 400
    
    
    # Check if current_user is authenticated and has the necessary attributes.
    if hasattr(current_user, "is_authenticated") and current_user.is_authenticated:
        uid = getattr(current_user, "user_id", 0)
        uname = getattr(current_user, "username", "anonymous")
    else:
        uid = 0
        uname = "anonymous"
    
    # Save the user's message in the DB
    chat_msg = ChatMessage(
        meeting_id=meeting_id,
        user_id=uid,
        username=uname,
        message=user_message,
        timestamp=datetime.utcnow()
    )
    db.session.add(chat_msg)
    db.session.commit()
    
    # Use the unified LLM chain to process the query
    agent_response = process_user_query(meeting_id, user_message)
    
    socketio.emit("agent_response", {
        "message": agent_response,
        "type": "unified",
        "username": "Agent"
    }, room=f"meeting_{meeting_id}", namespace="/agent") 
    current_app.logger.info(f"Agent response emitted to meeting_{meeting_id}")

    return jsonify({"ok": True}), 200



#
#
# agent/generate_summary 
#
#





@agent_bp.route("/generate_summary/<int:meeting_id>", methods=["POST"])
@login_required
def generate_summary(meeting_id):
    
    """
    Endpoint to generate the meeting summary from transcript
    Aggregates all transcripts for the meeting, passes them to
    a model for summarization, streams the output, and saves the final summary.
    """
    
    # Option 1: Get meeting_id from JSON data included in fetch javascript request.
    data = request.get_json()
    print("SUMMARY CALLED")
    print(data)
    meeting_id = data.get("meeting_id")
    
    # Option 2: Use the meeting_id included in fetch javascript request URL
    if not meeting_id:
        return jsonify({"success": False, "error": "No meeting_id provided for summary generation."}), 400

    # Collect transcripts
    transcripts = Transcript.query.filter_by(meeting_id=meeting_id).all()
    full_transcript_text = " ".join([
        t.processed_transcript if t.processed_transcript else t.raw_transcript
        for t in transcripts
    ])

    print(f"[Transcription] Summarizing transcripts for meeting {meeting_id}: {full_transcript_text}") # DEBUG CODE
    
    # Define llm prompt
    summary_prompt_template = """
            Summarize the following meeting transcript concisely and clearly
            Avoid using emotional or sensationalist tone.
            Capture the main points and preserve the original flow of the meeting.
            Output only the final summary text.
            
            Meeting transcript: {full_transcript_text}
            """
    # initialize the watsonx summary llm       
    watsonx_llm_summary = WatsonxLLM(
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
    
    # Define llm prompt
    summary_prompt = PromptTemplate.from_template(summary_prompt_template)
    
    # Invoke the llm chain
    chain = summary_prompt | watsonx_llm_summary
    raw_summary = chain.invoke({"full_transcript_text": full_transcript_text})
    
    print(f"[Transcription] Summary Result: {meeting_id}: {raw_summary}") # DEBUG CODE
   


        
    # summary = clean_llm_output(raw_summary) # return clean llm output or
    summary = raw_summary # return raw llm output
    
    
    
    # Save summary in the DB
    with current_app.app_context():
        serialized_summary = json.dumps(summary)  # summary_data should be your dictionary
        existing = Summary.query.filter_by(meeting_id=meeting_id, summary_type='detailed').first()
        if existing:
            existing.summary_text = serialized_summary
        else:
            new_summary = Summary(
                meeting_id=meeting_id, 
                summary_text=serialized_summary, 
                summary_type='detailed'
                )
            db.session.add(new_summary)
        db.session.commit()

    
    return jsonify({"success": True, "data": summary})

#----------------
#
# agent/get_summary 
#
#----------------
@agent_bp.route("/get_summary/<int:meeting_id>", methods=["POST"])
@login_required
def get_summary(meeting_id):
    """
    
    Endpoint to get the meeting summary from database
    
    """
    
    print("GET SUMMARY DATA CALLED")
    # Retrieve the detailed meeting summary from the DB
    meeting_summary = Summary.query.filter_by(
        meeting_id=meeting_id, 
        summary_type="detailed"
        ).order_by(Summary.created_timestamp.desc()).first()
    print(meeting_summary)
    # Parse the stored JSON from the summary_text if available
    summary_data = {}
    if meeting_summary and meeting_summary.summary_text.strip():
        try:
            summary_data = json.loads(meeting_summary.summary_text)
            
        except Exception as e:
            current_app.logger.error("Failed to parse meeting summary JSON: %s", e)
            summary_data = {}
    print(summary_data)   
    return jsonify({"meeting_id": meeting_id, "summary": summary_data})
