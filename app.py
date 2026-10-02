import streamlit as st
from prompts import SYSTEM_PROMPT,DEADLINE_EXTRACTION_PROMPT,WELCOME_MSG_TEMPLATE

from google import genai
from google.genai import types

import json
import os
import smtplib


from datetime import datetime, date

from email.message import EmailMessage



#GEMINI LLM

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
LLM_MODEL = "gemini-3.5-flash"

#GMAIL
SMTP_HOST = st.secrets["SMTP_HOST"]
SMTP_PORT = st.secrets["SMTP_PORT"]
SMTP_USERNAME = st.secrets["SMTP_USERNAME"]
SMTP_PASSWORD = st.secrets["SMTP_PASSWORD"]

#DATA 
DATA_FILE = "data/deadlines.json"

@st.cache_resource
def get_gemini_client():

    return genai.Client(
        api_key=GEMINI_API_KEY
    )


gemini_client = get_gemini_client()


#ALL FUNCTIONS NEEDED
def render_message(message):
    """
    Display a saved message in Streamlit.
    """

    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.write(message["content"])

        elif message["kind"] == "image":
            st.image(message["content"])


def add_message(role,kind,content):
    """
    Add a message to session state
    and display it.
    """

    message = {
        "role": role,
        "kind": kind,
        "content": content
    }

    st.session_state.messages.append(
        message
    )

    render_message(
        message
    )


def extract_deadlines(file_bytes,mime_type):
    try:

        # Convert uploaded file into a Gemini Part.
        document_part = types.Part.from_bytes(
            data=file_bytes,
            mime_type=mime_type
        )

        # Ask Gemini to analyze the document.
        response = gemini_client.models.generate_content(

            model=LLM_MODEL,

            contents=[
                document_part,
                DEADLINE_EXTRACTION_PROMPT
            ],

            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                # Ask Gemini to return JSON.
                response_mime_type="application/json"
            )
        )

        # Gemini response is JSON text.
        result = json.loads(response.text)

        return result
    
    except json.JSONDecodeError:

        return {
            "success": False,
            "message": "Gemini returned invalid JSON.",
            "deadlines": []
        }

    except Exception as error:

        return {
            "success": False,
            "message": str(error),
            "deadlines": []
        }

def is_valid_date(date_string):
    """
    Check whether the supplied date
    follows YYYY-MM-DD.
    """

    try:
        datetime.strptime(date_string,"%Y-%m-%d")
        return True

    except (ValueError,TypeError):
        return False


def clean_deadlines(result):
    cleaned_deadlines = []
    raw_deadlines = result.get("deadlines",[])

    # Make sure deadlines is actually a list.

    if not isinstance(raw_deadlines,list):
        return []

    for item in raw_deadlines:

        # Ignore invalid items.
        if not isinstance(item,dict):
            continue


        title = str(item.get("title","")).strip()

        deadline_date = item.get("date")

        deadline_type = str(item.get("type","Other")).strip()

        description = str(item.get("description","")).strip()

        confidence = str(item.get("confidence","unclear")).strip().lower()

        # Skip records without a title.
        if not title:
            continue

        # ----------------------------------
        # DATE VALIDATION
        # ----------------------------------

        if (deadline_date and is_valid_date(deadline_date)):
            final_date = deadline_date

        else:

            # IMPORTANT:
            # We do NOT guess the date.
            final_date = None

            confidence = "unclear"

        cleaned_deadlines.append(
            {
                "title": title,
                "date": final_date,
                "type": deadline_type,
                "description": description,
                "confidence": confidence
            }
        )

    return cleaned_deadlines


def load_deadlines():
    """
    Read deadlines from deadlines.json.
    """

    # If the file doesn't exist,
    # return an empty list.
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE,"r",encoding="utf-8") as file:
            return json.load(file)

    except (json.JSONDecodeError, OSError):

        return []




# SAVE DEADLINES

def save_deadlines(deadlines):
    """
    Save deadlines to deadlines.json.
    """

    # Make sure the data folder exists.
    os.makedirs(
        "data",
        exist_ok=True
    )

    with open(DATA_FILE,"w",encoding="utf-8") as file:
        json.dump(
            deadlines,
            file,
            indent=4,
            ensure_ascii=False
        )




def add_new_deadlines(new_deadlines):

    
    #Add new deadlines to JSON storage.

    #Duplicate deadlines are ignored.
    

    existing_deadlines = load_deadlines()

    added_count = 0

    for new_item in new_deadlines:
        is_duplicate = False
        for existing_item in existing_deadlines:
            same_title = (existing_item.get("title","").lower() == new_item.get("title","").lower())
            same_date = (existing_item.get("date")==new_item.get("date"))

            if same_title and same_date:
                is_duplicate = True
                break

        # Add only if it is not a duplicate.
        if not is_duplicate:
            new_item["created_at"] = (
                datetime.now().isoformat()
            )

            existing_deadlines.append(
                new_item
            )

            added_count += 1

    save_deadlines(
        existing_deadlines
    )

    return added_count



def create_email_body(deadlines):
    """
    Create a simple email digest.
    """
    if not deadlines:
        return (
            "Hello!\n\n"
            "You have no upcoming deadlines "
            "in the next 7 days.\n\n"
            "Deadline Tracker"
        )

    body = (
        "Hello!\n\n"
        "Here are your upcoming academic "
        "deadlines:\n\n"
    )

    for item in deadlines:

        title = item.get(
            "title",
            "Untitled"
        )

        deadline_date = item.get(
            "date",
            "Date unclear"
        )

        deadline_type = item.get(
            "type",
            "Other"
        )

        description = item.get(
            "description",
            ""
        )

        body += (
            f"📌 {title}\n"
        )

        body += (
            f"📅 Date: {deadline_date}\n"
        )

        body += (
            f"📚 Type: {deadline_type}\n"
        )

        if description:

            body += (
                f"📝 {description}\n"
            )

        body += "\n"

    body += (
        "Good luck with your work! 📚\n\n"
        "Deadline Tracker"
    )

    return body

def send_email(
    recipient,
    subject,
    body
):
    """
    Send an email through SMTP.
    """

    try:

        # Create email object.
        message = EmailMessage()

        message["From"] = (SMTP_USERNAME)

        message["To"] = (
            recipient
        )

        message["Subject"] = (
            subject
        )

        message.set_content(
            body
        )

        # Connect to SMTP server.
        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT
        ) as server:

            # Secure the connection.
            server.starttls()

            # Login.
            server.login(
                SMTP_USERNAME,
                SMTP_PASSWORD
            )

            # Send.
            server.send_message(
                message
            )

        return True, "Email sent successfully."

    except Exception as error:

        return False, str(error)


def get_upcoming_deadlines(days=7):
    """
    Get deadlines occurring within
    the next specified number of days.
    """

    deadlines = load_deadlines()

    today = date.today()

    upcoming = []

    for item in deadlines:

        deadline_date = item.get(
            "date"
        )

        # Ignore deadlines with
        # unknown dates.
        if not deadline_date:

            continue

        if not is_valid_date(
            deadline_date
        ):

            continue

        deadline = datetime.strptime(
            deadline_date,
            "%Y-%m-%d"
        ).date()

        difference = (
            deadline - today
        ).days

        if 0 <= difference <= days:

            upcoming.append(
                item
            )

    # Sort by date.
    upcoming.sort(
        key=lambda item: item["date"]
    )

    return upcoming



#SESSION STATES

if "onboarded" not in st.session_state:
    st.session_state.onboarded = False

if "name" not in st.session_state:
    st.session_state.name = ""

if "email" not in st.session_state:
    st.session_state.email = ""

if "messages" not in st.session_state:
    st.session_state.messages = []



#UI

if not st.session_state.onboarded:

    st.title(
        "📚 Deadline Tracker"
    )

    st.caption(
        "Upload your academic documents "
        "and let Gemini find your deadlines."
    )

    with st.form("onboarding_form"):
        name = st.text_input("Your Name")
        email = st.text_input(
            "Email Address",
            placeholder="you@example.com",
            help="Your deadline digest will be sent here."
        )

        submitted = st.form_submit_button(
            "Let's Get Started!"
        )

        if submitted:

            # Validate inputs.
            if (not name.strip() or not email.strip() ):
                st.warning(
                    "Please enter your name and email."
                )

            else:

                st.session_state.name = (
                    name.strip()
                )

                st.session_state.email = (
                    email.strip()
                )

                st.session_state.messages = []

                st.session_state.onboarded = True

                # Reload the page.
                st.rerun()

    st.stop()


#main Header

header_col, button_col = st.columns(
    [5, 2],
    vertical_alignment="center"
)

with header_col:

    st.title(
        "📚 Deadline Tracker"
    )

    st.caption(
        f"Hey {st.session_state.name}, "
        f"your reminders will be sent to "
        f"{st.session_state.email}"
    )


#EMPTY BUTTON 
email_button = button_col.empty()

#chat History 

if not st.session_state.messages:
    add_message("assistant","text",WELCOME_MSG_TEMPLATE.format(name=st.session_state.name))
else:
    for message in st.session_state.messages:
        render_message(message)


#file Uploading 

user_input = st.chat_input(
    "Upload a syllabus, timetable, assignment sheet...",
    accept_file=True,
    file_type=[
        "jpg",
        "jpeg",
        "png",
        "webp",
        "pdf"
    ]
)

#process upload

if user_input:
    uploaded_file = (user_input.files[0] if user_input.files else None)
    text = user_input.text
    
    # HANDLE UPLOADED FILE

    if uploaded_file is not None:

        file_bytes = (
            uploaded_file.getvalue()
        )

        mime_type = (
            uploaded_file.type
        )

        # Display images in the chat.
        if mime_type.startswith(
            "image/"
        ):

            add_message(
                "user",
                "image",
                file_bytes
            )

        else:

            add_message(
                "user",
                "text",
                f"📄 Uploaded: {uploaded_file.name}"
            )


        
        # SEND DOCUMENT TO GEMINI
        

        with st.spinner(
            "Reading your document..."
        ):

            result = extract_deadlines(
                file_bytes,
                mime_type
            )


        # ----------------------------------
        # CHECK GEMINI RESULT
        # ----------------------------------

        if not result.get("success",True):
            st.error("I couldn't process that document.")
            st.caption(result.get("message","Unknown error"))

        else:
            # Validate Gemini data.
            extracted_deadlines = (
                clean_deadlines(
                    result
                )
            )


            # ----------------------------------
            # SAVE DEADLINES
            # ----------------------------------

            added_count = (
                add_new_deadlines(
                    extracted_deadlines
                )
            )


            # ----------------------------------
            # SHOW RESULT
            # ----------------------------------

            if not extracted_deadlines:

                add_message(
                    "assistant",
                    "text",
                    "I couldn't find any clear "
                    "academic deadlines in that document."
                )

            else:

                message = (
                    f"✅ I found "
                    f"{len(extracted_deadlines)} "
                    f"deadline(s).\n\n"
                    f"💾 Added "
                    f"{added_count} "
                    f"new deadline(s) to your tracker."
                )

                add_message(
                    "assistant",
                    "text",
                    message
                )


                # ----------------------------------
                # DISPLAY EXTRACTED DEADLINES
                # ----------------------------------

                st.subheader(
                    "📅 Extracted Deadlines"
                )

                for item in extracted_deadlines:

                    st.markdown(
                        f"### 📌 {item['title']}"
                    )

                    if item["date"]:

                        st.write(
                            f"**Date:** "
                            f"{item['date']}"
                        )

                    else:

                        st.write(
                            "**Date:** ⚠️ Unclear"
                        )

                    st.write(
                        f"**Type:** "
                        f"{item['type']}"
                    )

                    if item["description"]:

                        st.write(
                            f"**Details:** "
                            f"{item['description']}"
                        )

                    st.divider()



# SIDEBAR

with st.sidebar:

    st.header(
        "📅 Your Deadlines"
    )

    deadlines = load_deadlines()

    if not deadlines:

        st.info(
            "No deadlines saved yet."
        )

    else:

        # Sort deadlines.
        sorted_deadlines = sorted(
            deadlines,
            key=lambda item: (
                item.get("date") is None,
                item.get(
                    "date"
                ) or "9999-12-31"
            )
        )

        for item in sorted_deadlines:

            title = item.get(
                "title",
                "Untitled"
            )

            deadline_date = item.get(
                "date"
            )

            if deadline_date:

                st.markdown(
                    f"**{title}**  \n"
                    f"📅 {deadline_date}"
                )

            else:

                st.markdown(
                    f"**{title}**  \n"
                    f"⚠️ Date unclear"
                )

            st.divider()



# EMAIL DIGEST -- main part of the project 


upcoming_deadlines = (get_upcoming_deadlines(days=7))

with email_button:

    if st.button("📩 Send 7-Day Digest",use_container_width=True):
        if not upcoming_deadlines:
            st.info(
                "You don't have any dated "
                "deadlines in the next 7 days."
            )

        else:

            with st.spinner(
                "Preparing your email..."
            ):

                email_body = (
                    create_email_body(
                        upcoming_deadlines
                    )
                )

                success, info = (
                    send_email(
                        st.session_state.email,
                        "📚 Your Upcoming Academic Deadlines",
                        email_body
                    )
                )

            if success:

                st.success(
                    "Sent! Check your email 📩"
                )

            else:

                st.error(
                    f"Couldn't send the email: {info}"
                )
