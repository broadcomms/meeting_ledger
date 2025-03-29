# Meeting Ledger
**Smart Meetings for small and mid-market enteprises**

Meeting Ledger is a Smarts Meetings Platform levaging IBM watsonx.ai Granite 3.2 Open Source enteprise grade Foundation models. The application analyses historic meeting data and current meeting details, automatically generates a consice structured meeting agenda and email invitation along with recommendations from analysis of meeting data. The application captures speakers computer microphone and transcribes the discussions and saves copies to the database and updates the UI in real-time. Users can interact with the Foundation Model to query saved meeting transcripts, chat messages, agenda and uploaded documents to clarify discussion points without interuption meeting flow in real-time. After meetings the AI model generates a consise summary using the saved meeting transcript and extract task items and save them to the project management system for immediate assignment and follow up.

## Key features
The solution performs the following operations:
1. Analyzes historic data and meeting details
2. Generates structured meeting agenda
3. Generates meeting email invitation
4. Generates recommendations
5. Generates meeting summary
6. Extracts action-items and assign tasks



## Architecture
The application is implemented with Python and JavaScript using Flask and LangChain libraries, IBM watsonx STT, IBM watsonx.ai Foundation Models.


# Structure
```
app/
    agent/
        templates/
            agent_main.html
        routes.py
    chat_memory.sqlite
    calendar/
        routes.py
    documents/
        routes.py
    meeting/
        templates/
            meeting_agenda.html
            meeting_details.html
            meeting_form.html
        routes.py
    tasks/
        routes.py
    websockets/
        agent_ws.py
        transcription_ws.py
        webrtc_ws.py
    main/
        /templates
            index.html
            base.html
        routes.py
    static/
        /images
        /js
            transcription.js
            videoConference.js
        scripts.js
        styles.css
    __init__.py
    confit.py
    model.py
    extensions.py
requirements.txt
run.py
```

