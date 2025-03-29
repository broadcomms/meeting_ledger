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

## Setup Virtual Environment
```sh
mkdir meeting_ledger
cd meeting_ledger
python --version
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip --version
```

## Install dependent libraries

## Install Dependent Libraries
```sh
pip install -r requirements.txt
```
## Initialize Flask Application
```sh
touch run.py
mkdir app
touch app/__init__.py
mkdir app/main app/main/templates
touch app/main/templates/index.html touch app/main/templates/base.html 
touch app/main/routes.py

touch app/config.py app/model.py app/extensions.py
```

## Create authentication module
```sh
mkdir app/auth
mkdir app/auth/templates
touch app/auth/routes.py app/auth/templates/login.html app/auth/templates/register.html app/auth/templates/change_password.html
```

## Create dashboard module
```sh
mkdir app/dashboard
mkdir app/dashboard/templates
touch app/dashboard/routes.py app/dashboard/templates/dashboard.html
```

## Create meeting module
```sh
mkdir app/meeting
mkdir app/meeting/templates
touch app/meeting/routes.py app/meeting/templates/meeting.html app/meeting/templates/meeting_agenda.html app/meeting/templates/meeting_details.html
touch app/meeting/templates/add_participant.html app/meeting/templates/live_chat.html app/meeting/templates/meeting_form.html
touch app/meeting/templates/meeting_list.html app/meeting/templates/video_conference.html
```

# Containerize the application
```sh
docker build -t meeting_ledger:latest .
# Test local before live deployment
docker run --env-file .env -p 5001:5001 meeting_ledger:latest
```

# Tag container image and push to BroadComms docker
```sh
docker tag meeting_ledger:latest broadcomms/meeting_ledger:latest
docker login 
docker push broadcomms/meeting_ledger:latest
```