from frontend.GUI import (
GraphicalUserInterface,
SetAssistantStatus,
ShowTextToScreen,
TempDirectoryPath,
SetMicrophoneStatus,
AnswerModifier,
QueryModifier,
GetMicrophoneStatus,
GetAssistantStatus,
GetActiveChatLogPath,
ActivateConversation,
UpdateConversationOrbCategory,
SetSpeechLevel,
SelectGeneratedImage,
QueueImageGallery )
from backend.model import FirstLayerDMM
from backend.RealtimeSearchEngine import RealtimeSearchEngine
from backend.Automation import (
    Automation, OpenApp, CloseApp, PlayYoutube, content,
    YouTubeSearch, System, GoogleSearch as GoogleSearchAuto
)
from backend.SpeechToText import SpeechRecognition
from backend.TextToSpeech import TextToSpeech
from backend.ImageGeneration import GenerateImage, ExtractImagePrompt
from backend.Reminders import ParseReminderRequest, SaveReminder, TakeDueReminders
from dotenv import dotenv_values
from time import sleep
import threading
import json
import os
import sys


# Additional imports for chatbot functionality
from json import load, dump
import datetime
import glob
import re
from backend.chatbot import ChatBot as BackendChatBot


# Try to import the local realtime search engine module and helpers; continue gracefully if unavailable
try:
    from backend.RealtimeSearchEngine import RealtimeSearchEngine as realtime_module
    RealtimeSearchEngine_import = getattr(realtime_module, "RealtimeSearchEngine", None)
    GoogleSearch = getattr(realtime_module, "GoogleSearch", None)
    GetWeatherFunc = getattr(realtime_module, "GetWeather", None)
except Exception:
    RealtimeSearchEngine_import = None
    GoogleSearch = None
    GetWeatherFunc = None


env_vars = dotenv_values(".env")
Username = env_vars.get("Username", env_vars.get("USERNAME", "User"))
AssistantName = env_vars.get("AssistantName", env_vars.get("ASSISTANT_NAME", "AIKO"))
DefaultMessage = f'''{Username} : Hello {AssistantName}, How are you?
{AssistantName} : Welcome {Username}, I am doing great, how can I assist you today?'''
SupportedFunctions = ["open", "close", "play", "system", "content", "google search", "youtube search", "generate image"]


# Additional env vars for chatbot
GroqAPIKEY = env_vars.get("GroqApiKey")


# Debug flag: set to True to enable debug prints added for troubleshooting
DEBUG = False
_speech_lock = threading.Lock()


# Initialize an empty list to store chat messages.
messages = []


# Define the original system message
system = f"""
hello, I am {Username}, you are a very intelligent AI assistant named {AssistantName} with advanced capabilities.
*** Do not tell time until I ask, Answer in short sentences ***
*** Reply in a sarcastic but friendly and helpful manner ***
*** Do not provide notes in the output, just the answer and never mention training data ***
"""


# A list of system instructions for the chatbot.
SystemChatBot = [
    {"role": "system", "content": system},
]


# Chatbot helper functions
def _list_chatlog_files():
    os.makedirs(r"Data", exist_ok=True)
    pattern = os.path.join(r"Data", "ChatLog*.json")
    files = glob.glob(pattern)
    # Ensure the base ChatLog.json is included even if no suffix
    base = os.path.join(r"Data", "ChatLog.json")
    if base not in files:
        files.append(base)


    # Sort files by numeric suffix (ChatLog.json -> 0, ChatLog_1.json -> 1, ...)
    def _index_from_name(p):
        name = os.path.basename(p)
        m = re.match(r"ChatLog(?:_(\d+))?\.json$", name, re.IGNORECASE)
        if not m:
            return 0
        return int(m.group(1)) if m.group(1) else 0


    unique_files = {os.path.normcase(os.path.abspath(path)): path for path in files}
    files = sorted(unique_files.values(), key=_index_from_name)
    return files


# Attempt to load the chat log from a JSON file.
try:
    # Load all existing chatlog files (preserve history across ChatLog.json, ChatLog_1.json, ...)
    def _load_all_chatlogs():
        messages_acc = []
        for p in _list_chatlog_files():
            if not os.path.exists(p):
                continue
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        data = load(open(p, "r", encoding="utf-8"))
                        if isinstance(data, list):
                            messages_acc.extend(data)
            except Exception:
                # ignore malformed files
                continue
        return messages_acc


    messages = _load_all_chatlogs()
except FileNotFoundError:
    # If the file does not exist, create an empty JSON file to store chat logs.
    os.makedirs(r"Data", exist_ok=True)
    with open(r"Data\ChatLog.json", "w", encoding="utf-8") as f:
        dump([], f, indent=4)
    messages = []


def ShowDefaultChatIfNoChats():
    chatlog_path = r'Data\ChatLog.json'
    if os.path.exists(chatlog_path):
        with open(chatlog_path, 'r', encoding='utf-8') as file:
            if len(file.read().strip()) > 0:  # Check if the chat log is not empty
                return  # Do nothing if the chat log already exists and is not empty


    # If the chat log does not exist or is empty, initialize it with default messages
    if not os.path.exists(chatlog_path):
        with open(chatlog_path, 'w', encoding='utf-8') as file:
            json.dump([], file, indent=4)


    with open(TempDirectoryPath('Database.data'), 'w', encoding='utf-8') as file:
        file.write("")


    with open(TempDirectoryPath('Respnses.data'), 'w', encoding='utf-8') as file:
        file.write(DefaultMessage)


def ReadChatLogJson():
      with open(GetActiveChatLogPath(), 'r', encoding='utf-8') as file:
          chatlog_data = json.load(file)
      return chatlog_data


def ChatLogIntegration():
      json_data = ReadChatLogJson()
      formatted_chatlog = ""
      for entry in json_data:
            if entry["role"] == "user":
                 formatted_chatlog += f"User: {entry['content']}\n"
            elif entry["role"] == "assistant":
                 formatted_chatlog += f"Assistant: {entry['content']}\n"
      formatted_chatlog = formatted_chatlog.replace("User", Username +" ")
      formatted_chatlog = formatted_chatlog.replace("Assistant", AssistantName + " ")


      with open(TempDirectoryPath('Database.data'), 'w', encoding='utf-8') as file:
          file.write(AnswerModifier(formatted_chatlog))


def ShowChatsOnGUI():
      File = open(TempDirectoryPath('Database.data'), "r", encoding= 'utf-8')
      Data = File.read()
      if len(str(Data))>0:
           lines = Data.split('\n')
           result = '\n'.join(lines)
           File.close()
           File = open(TempDirectoryPath('Respnses.data'), "w", encoding= 'utf-8')
           File.write(result)
           File.close()


def _get_latest_chatlog_path():
    return GetActiveChatLogPath()


def append_to_chatlogs(role, content):
    """Append a message to the active conversation's dedicated chatlog."""
    latest_path = _get_latest_chatlog_path()
    with open(latest_path, "r", encoding="utf-8") as f:
        data = load(f)
    if not isinstance(data, list):
        raise ValueError(f"Chat history must contain a list: {latest_path}")


    # Append the new entry
    data.append({"role": role, "content": content})


    with open(latest_path, "w", encoding="utf-8") as f:
        dump(data, f, indent=4)


def RealTimeInformation():
    current_time = datetime.datetime.now()
    day = current_time.strftime("%A")
    date = current_time.strftime("%d")
    month = current_time.strftime("%B")
    year = current_time.strftime("%Y")
    hour = current_time.strftime("%H")
    minute = current_time.strftime("%M")
    second = current_time.strftime("%S")
    data = f"Please use this real-time information if needed,\n"
    data += f"Day: {day}\n"
    data += f"Date: {date}\n"
    data += f"Month: {month}\n"
    data += f"Year: {year}\n"
    data += f"Time: {hour} hours : {minute} minutes : {second} seconds.\n"
    return data


def ChatBot(Query, retry_count=0, max_retries=3):
    """Wrapper to use the backend ChatBot."""
    return BackendChatBot(Query, retry_count, max_retries)
def InitalExecution():
    SetMicrophoneStatus("False")
    active_chat = GetActiveChatLogPath()
    ActivateConversation(active_chat)
    SetAssistantStatus("Available...")




def _normalize_command_request(query):
    normalized = query.strip()
    normalized = re.sub(r"^please\s+", "", normalized, flags=re.IGNORECASE)
    request_frame = re.match(
        r"^(?:(?:can|could|would|will)\s+you\s+"
        r"(?:please\s+)?|(?:i|we)\s+(?:want|need)\s+you\s+to\s+|"
        r"(?:i|we)(?:\s+would|\s*['’]d)\s+like\s+you\s+to\s+|"
        r"would you mind\s+)(.+)$",
        normalized,
        re.IGNORECASE,
    )
    if request_frame:
        normalized = request_frame.group(1).strip()

    command_start = re.match(
        r"^(?:open|launch|start|close|exit|quit|play|find|look for|search|"
        r"google|youtube|generate|create|make|draw|design|render|paint|"
        r"write|remind|set|save|add|schedule|plan|turn|mute|unmute|increase|"
        r"decrease|volume)\b",
        normalized,
        re.IGNORECASE,
    )
    if not command_start:
        return query.strip()

    normalized = re.sub(
        r"\s+for\s+(?:me|us)\s*[?.!]*$",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"^(?P<verb>play|find|write|create|make|generate|draw|design)\s+"
        r"(?:me|us)\s+(?=(?:a|an|the|some)\b)",
        r"\g<verb> ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"^(search\s+for)\s+(?:me|us)\s+(?=(?:a|an|the|some)\b)",
        r"\g<1> ",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized.strip()


def _classify_query(query):
    original = query.strip()
    normalized = _normalize_command_request(original)
    lowered = normalized.lower()
    close_request = re.match(
        r"^(?:please\s+)?(?:close|exit|quit)\s+(.+)$",
        normalized,
        re.IGNORECASE,
    )
    if close_request:
        return f"close {close_request.group(1).strip()}"
    if lowered in {"exit", "quit"}:
        return "exit"
    if re.search(
        r"^(?:remind(?:\s+me)?\b|reminder\b|set\s+(?:a\s+)?reminder\b|"
        r"schedule\b|plan\s+for\b|(?:save|add)\s+(?:(?:an?|the|this)\s+)?"
        r"(?:reminder|event)\b)",
        normalized,
        re.IGNORECASE,
    ):
        return f"reminder {normalized}"
    option_match = re.match(
        r"^(?:please\s+)?(?:i(?:\s+would|\s*['’]d)?\s+"
        r"(?:choose|chose|pick|picked|select|selected|like|prefer|want)\s+(?:the\s+)?|"
        r"(?:choose|pick|select|keep|save|take)\s+(?:the\s+)?|option\s+)"
        r"(?:image\s+)?(?:option\s+)?(?:number\s+)?"
        r"#?(1|one|first|2|two|second|3|three|third)\b",
        normalized,
        re.IGNORECASE,
    )
    if option_match:
        option_number = {
            "1": 1, "one": 1, "first": 1,
            "2": 2, "two": 2, "second": 2,
            "3": 3, "three": 3, "third": 3,
        }[option_match.group(1).lower()]
        return f"choose image {option_number}"
    if re.fullmatch(r"(?:please\s+)?generate[.!?]*", normalized, re.IGNORECASE):
        return "generate image()"

    blueprint_request = re.match(
        r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
        r"(?:create|make|generate|draw|design)\s+"
        r"(?:(?:me)\s+)?(?:an?\s+)?blueprint\b"
        r"(?:\s+(?:of|for|showing|about))?\s*(.*)$",
        normalized,
        re.IGNORECASE,
    )
    if blueprint_request:
        blueprint_subject = blueprint_request.group(1).strip(" \t\r\n.,!?")
        image_prompt = "blueprint"
        if blueprint_subject:
            image_prompt = f"blueprint of {blueprint_subject}"
        return f"generate image({image_prompt})"

    image_request = re.match(
        r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
        r"(?:generate|create|make|draw|design|render|paint)\s+"
        r"(?:(?:me)\s+)?(?:(?:an?|the)\s+)?"
        r"(?:image|iamge|picture|photo|photograph|illustration|artwork|art)\b"
        r"(?:\s+(?:of|about|showing|depicting|with))?\s*(.*)$",
        normalized,
        re.IGNORECASE,
    )
    if not image_request:
        image_request = re.match(
            r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
            r"make\s+(?:me\s+)?a\s+(.+)$",
            normalized,
            re.IGNORECASE,
        )
    if image_request:
        image_prompt = image_request.group(1).strip(" \t\r\n.,!?")
        image_prompt = re.sub(
            r"^(?:(?:an?|the)\s+)?(?:image|picture|photo|artwork|art)\s+"
            r"(?:of|about|showing|depicting|with)\s+",
            "",
            image_prompt,
            flags=re.IGNORECASE,
        ).strip(" \t\r\n.,!?")
        return f"generate image({image_prompt})"

    youtube_open_request = re.match(
        r"^(?:(?:please|can you|could you|would you)\s+)?"
        r"(?:open|launch|start)\s+(?:up\s+)?youtube\b"
        r"(?:\s+(?:(?:and\s+)?(?:search|find)\s+(?:for\s+)?)|"
        r"\s+for\s+)?(.*)$",
        normalized,
        re.IGNORECASE,
    )
    if youtube_open_request:
        youtube_query = youtube_open_request.group(1).strip(" \t\r\n.,!?")
        youtube_query = re.sub(
            r"^(?:(?:a|the)\s+)?(?:video|videos)\s+"
            r"(?:(?:about|of|on|for)\s+)?",
            "",
            youtube_query,
            flags=re.IGNORECASE,
        ).strip(" \t\r\n.,!?")
        if youtube_query:
            return f"play {youtube_query}"
        return "open youtube"

    find_video_request = re.match(
        r"^(?:(?:please|can you|could you|would you)\s+)?"
        r"(?:find|look for|search for)\s+(?:(?:me)\s+)?"
        r"(?:a\s+|the\s+)?videos?\b"
        r"(?:\s+(?:about|of|on|for))?\s*(.*)$",
        normalized,
        re.IGNORECASE,
    )
    if find_video_request:
        video_query = find_video_request.group(1).strip(" \t\r\n.,!?")
        return f"play {video_query}" if video_query else "open youtube"

    play_request = re.match(
        r"^(?:(?:please|can you|could you|would you|"
        r"i want(?: you)? to|we want(?: you)? to|"
        r"i(?:\s*['’]d| would) like(?: you)? to|"
        r"we(?:\s*['’]d| would) like(?: you)? to)\s+)?"
        r"play\b(.*)$",
        normalized,
        re.IGNORECASE,
    )
    if play_request:
        play_query = play_request.group(1).strip(" \t\r\n.,!?")
        play_query = re.sub(
            r"^(?:(?:me|us)\s+)",
            "",
            play_query,
            flags=re.IGNORECASE,
        )
        play_query = re.sub(
            r"\s+for\s+(?:me|us)\s*[?.!]*$",
            "",
            play_query,
            flags=re.IGNORECASE,
        )
        generic_media = re.match(
            r"^(?:(?:a|an|the|some)\s+)?(?:songs?|music|videos?)\b",
            play_query,
            re.IGNORECASE,
        )
        if generic_media:
            play_query = play_query[generic_media.end():].strip()
            play_query = re.sub(
                r"^(?:by|from|called|named|about|of|on)\s+",
                "",
                play_query,
                flags=re.IGNORECASE,
            )
        play_query = re.sub(
            r"^(?:a|an|the)\s+",
            "",
            play_query,
            flags=re.IGNORECASE,
        )
        play_query = re.sub(
            r"^(?:by|from|called|named|about|of|on)\s+",
            "",
            play_query,
            flags=re.IGNORECASE,
        )
        play_query = re.sub(
            r"\s+(?:song|songs|video|videos|music)\s*[?.!]*$",
            "",
            play_query,
            flags=re.IGNORECASE,
        ).strip(" \t\r\n.,!?")
        return f"play {play_query}"

    google_query = re.sub(
        r"^(?:(?:please|can you|could you|would you)\s+)?",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    google_query = re.sub(
        r"^(?:(?:open|search)\s+)?google(?:\s+search)?"
        r"(?:\s+for)?\s*",
        "",
        google_query,
        flags=re.IGNORECASE,
    )
    google_query = re.sub(
        r"^search\s+for\s*",
        "",
        google_query,
        flags=re.IGNORECASE,
    )
    google_query = re.sub(
        r"\s+(?:on|using)\s+google\s*[?.!]*$",
        "",
        google_query,
        flags=re.IGNORECASE,
    ).strip(" \t\r\n.,!?")
    if re.search(r"\bgoogle\b|\bsearch\s+for\b", lowered):
        return f"google search {google_query or normalized}"

    direct_commands = (
        ("open ", "open"),
        ("close ", "close"),
        ("play ", "play"),
        ("google search ", "google search"),
        ("search google for ", "google search"),
        ("youtube search ", "youtube search"),
        ("search youtube for ", "youtube search"),
        ("content ", "content"),
        ("write about ", "content"),
        ("system ", "system"),
    )
    for prefix, intent in direct_commands:
        if lowered.startswith(prefix):
            payload = normalized[len(prefix):].strip()
            return f"{intent}({payload})" if intent == "generate image" else f"{intent} {payload}"

    realtime_terms = (
        "weather", "forecast", "temperature", "latest news", "current news",
        "stock price", "today's", "today ", "right now", "current ",
        "search for ", "look up ",
    )
    if any(term in lowered for term in realtime_terms):
        return f"realtime {normalized}"

    try:
        decision = FirstLayerDMM(normalized)
    except Exception as error:
        print(f"[ERROR] Intent classification failed; using general chat: {error}")
        return f"general {original}"

    if isinstance(decision, (list, tuple)):
        candidates = [str(item).strip() for item in decision if str(item).strip()]
    else:
        candidates = [str(decision).strip()]
    for candidate in candidates:
        if candidate.startswith("(") or candidate.lower() in {"unknown", "(unknown)", "(error)"}:
            continue
        if re.match(r"^(general|realtime|generate image|open|close|play|system|content|google search|youtube search|exit)\b", candidate, re.I):
            return candidate
    print(f"[ERROR] Intent classifier returned no usable intent for query: {original}")
    return f"general {original}"


def _intent_payload(decision, intent):
    payload = re.sub(rf"^{re.escape(intent)}\b", "", decision, count=1, flags=re.IGNORECASE).strip()
    if payload.startswith("(") and payload.endswith(")"):
        payload = payload[1:-1].strip()
    return payload


def _speech_response(answer):
    """Keep long or formatted code in chat instead of reading it aloud."""
    if re.search(
        r"```|data:image/|!\[[^\]]*\]\([^)]*\)|<\s*/?\s*(?:svg|html|!doctype)\b",
        answer,
        re.IGNORECASE | re.MULTILINE,
    ):
        return "I've shared the image or code in the chat. Please take a look there."

    lines = [line for line in answer.splitlines() if line.strip()]
    code_line = re.compile(
        r"^\s*(?:#|//|/\*|\*|import\b|from\b|def\b|class\b|function\b|"
        r"(?:const|let|var)\b|return\b|if\b.*[:{]|for\b.*[:{]|while\b.*[:{]|"
        r"try:|except\b|print\(|console\.log\(|[{}\[\];])"
    )
    code_lines = sum(bool(code_line.search(line)) for line in lines)
    if len(lines) >= 3 and code_lines >= 3 and code_lines / len(lines) >= 0.35:
        return "I've shared the full code in the chat. Please take a look there."
    return answer


def MainExecution(Query):
    query = Query.strip()
    if not query:
        return
    handled_by_chat_service = False
    user_logged = False
    assistant_logged = False
    try:
        SetAssistantStatus("Processing...")
        active_chat = GetActiveChatLogPath()
        os.environ["AIKO_CHAT_LOG"] = active_chat
        decision = _classify_query(query)
        intent = decision.split("(", 1)[0].split(" ", 1)[0].lower()
        print(f"[DEBUG] Intent: {decision}")
        answer = ""
        handled_by_chat_service = intent in {"general", "realtime"}

        if intent == "generate":
            intent = "generate image"
        if intent == "choose":
            intent = "choose image"
            option_number = int(_intent_payload(decision, "choose image"))
            append_to_chatlogs("user", query)
            user_logged = True
            answer = SelectGeneratedImage(option_number)
        elif intent == "generate image":
            image_prompt = ExtractImagePrompt(decision)
            if not image_prompt:
                image_prompt = _intent_payload(decision, "generate image")
            if not image_prompt:
                append_to_chatlogs("user", query)
                user_logged = True
                answer = "Are we designing something? What would you like me to generate?"
            else:
                append_to_chatlogs("user", query)
                user_logged = True
                SetAssistantStatus("Generating Image...")
                image_paths = GenerateImage(image_prompt)
                QueueImageGallery(image_prompt, image_paths)
                answer = (
                    f"I generated three image options for '{image_prompt}'. "
                    "Which one do you like best? Choose it to keep it; I’ll delete the other two."
                )
        elif intent == "reminder":
            append_to_chatlogs("user", query)
            user_logged = True
            try:
                reminder_title, due_at = ParseReminderRequest(query)
            except ValueError as error:
                answer = str(error)
            else:
                saved_reminder = SaveReminder(reminder_title, due_at)
                due_label = datetime.datetime.fromisoformat(
                    saved_reminder["due_at"]
                ).strftime("%A, %B %d at %I:%M %p")
                answer = f"I'll remind you about {reminder_title} on {due_label}."
        elif intent == "play" and not _intent_payload(decision, "play"):
            append_to_chatlogs("user", query)
            user_logged = True
            answer = "What would you like me to play on YouTube?"
        elif intent in {"open", "close", "play", "system", "content", "google", "youtube"}:
            payload = _intent_payload(decision, intent)
            if intent == "google":
                intent = "google search"
                payload = _intent_payload(decision, intent)
            elif intent == "youtube":
                intent = "youtube search"
                payload = _intent_payload(decision, intent)
            if not payload:
                raise ValueError(f"Please specify what to {intent}.")
            append_to_chatlogs("user", query)
            user_logged = True
            SetAssistantStatus("Executing Task...")
            if intent == "open":
                if payload.strip().lower() in {"youtube", "youtube.com"}:
                    YouTubeSearch("")
                    answer = "Opening YouTube."
                else:
                    OpenApp(payload)
                    answer = f"Opening {payload}."
            elif intent == "close":
                if not CloseApp(payload):
                    raise RuntimeError(f"Could not close {payload}.")
                answer = f"Closing {payload}."
            elif intent == "play":
                PlayYoutube(payload)
                answer = f"Playing {payload}."
            elif intent == "system":
                System(payload)
                answer = f"Done: {payload}."
            elif intent == "content":
                content(payload)
                answer = f"I created content about {payload} in the Data folder."
            elif intent == "google search":
                GoogleSearchAuto(payload)
                answer = f"I searched Google for {payload}."
            elif intent == "youtube search":
                YouTubeSearch(payload)
                answer = f"I searched YouTube for {payload}."
        elif intent == "exit":
            append_to_chatlogs("user", query)
            user_logged = True
            answer = "Goodbye. The microphone is off; click it again whenever you need me."
            MicButtonClosed()
        elif intent == "realtime":
            search_query = _intent_payload(decision, "realtime") or query
            SetAssistantStatus("Searching...")
            answer = RealtimeSearchEngine(QueryModifier(search_query))
        else:
            answer = ChatBot(QueryModifier(_intent_payload(decision, "general") or query))

        if not answer:
            raise RuntimeError(f"{intent} completed without returning a response.")
        if not handled_by_chat_service:
            append_to_chatlogs("assistant", str(answer))
            assistant_logged = True
        UpdateConversationOrbCategory(active_chat, query, intent)
        ActivateConversation(active_chat)
        print(f"[DEBUG] Assistant response: {answer}")
        SetAssistantStatus("Answering...")
        try:
            with _speech_lock:
                TextToSpeech(
                    _speech_response(str(answer)),
                    level_callback=SetSpeechLevel,
                )
        except Exception as speech_error:
            print(f"[ERROR] Could not speak the response: {speech_error}", flush=True)
            SetAssistantStatus(f"Speech unavailable: {speech_error}")
    except Exception as error:
        print(f"[ERROR] Exception in MainExecution: {error}")
        error_message = f"I couldn't complete that request: {error}"
        try:
            history = ReadChatLogJson()
            last_entry = history[-1] if history else {}
            if not user_logged and not (
                last_entry.get("role") == "user" and last_entry.get("content") == query
            ):
                append_to_chatlogs("user", query)
            if not assistant_logged and (
                not history or history[-1].get("role") != "assistant"
            ):
                append_to_chatlogs("assistant", error_message)
            ActivateConversation(GetActiveChatLogPath())
        except Exception as history_error:
            print(f"[ERROR] Could not update chat history: {history_error}")
            ShowTextToScreen(f"{Username}: {query}\n{AssistantName}: {error_message}")
        SetAssistantStatus("Answering...")
        try:
            with _speech_lock:
                TextToSpeech(error_message, level_callback=SetSpeechLevel)
        except Exception as speech_error:
            print(f"[ERROR] Could not speak the error response: {speech_error}", flush=True)
            SetAssistantStatus(f"Speech unavailable: {speech_error}")


def AppendToChatLog(role, content):
    """Append a new entry to the ChatLog.json file without truncating existing entries.
    If the file exceeds a certain size or entry limit, create a new chat log file.
    """
    append_to_chatlogs(role, content)
def FirstThread():
    """Listen while enabled, then route each recognized query through its intent handler."""
    try:
        while True:
            if GetMicrophoneStatus().strip() != "True":
                SetAssistantStatus("Available...")
                sleep(0.2)
                continue
            SetAssistantStatus("Opening microphone...")
            try:
                Query = SpeechRecognition()
                if GetAssistantStatus().startswith("Microphone unavailable:"):
                    while GetMicrophoneStatus().strip() == "True":
                        sleep(0.2)
                    continue
                if not Query or not Query.strip():
                    if GetMicrophoneStatus().strip() == "True":
                        SetAssistantStatus("Listening...")
                    continue
                print(f"[DEBUG] Captured Query: {Query}", flush=True)
                MainExecution(Query)
            except Exception as speech_error:
                print(f"[ERROR] Speech recognition failed: {speech_error}")
                if GetMicrophoneStatus().strip() == "True":
                    SetAssistantStatus("Listening...")
    except Exception as error:
        print(f"[ERROR] Exception in FirstThread: {error}")
        SetAssistantStatus("Available...")


def SecondThread():


    GraphicalUserInterface()  # Initialize the GUI


def ReminderThread():
    """Deliver due reminders, including those that became due while AIKO was closed."""
    while True:
        try:
            due_reminders = TakeDueReminders()
        except (OSError, RuntimeError, ValueError) as error:
            print(f"[ERROR] Could not check saved reminders: {error}")
            sleep(5)
            continue

        for reminder in due_reminders:
            title = str(reminder.get("title", "")).strip()
            if not title:
                continue
            listening = GetMicrophoneStatus().strip() == "True"
            try:
                with _speech_lock:
                    SetAssistantStatus("Answering...")
                    TextToSpeech(
                        f"Reminder: {title}.",
                        level_callback=SetSpeechLevel,
                    )
            except Exception as speech_error:
                print(f"[ERROR] Could not speak reminder '{title}': {speech_error}")
            finally:
                SetAssistantStatus("Listening..." if listening else "Available...")
        sleep(2)


def InitializeAIKO():
    """
    Comprehensive initialization function that connects all folders and files.
    Runs at startup to ensure everything is properly configured.
    """
    print("\n" + "="*70)
    print("AIKO INITIALIZATION SEQUENCE")
    print("="*70)
   
    # Step 1: Verify environment and folders
    print("\n[1/7] Verifying environment and folders...")
    try:
        required_dirs = [
            "backend",
            "frontend",
            "Data",
            "Data/Generated_Images",
            "frontend/Files",
            "frontend/Graphics"
        ]
       
        for dir_path in required_dirs:
            os.makedirs(dir_path, exist_ok=True)
        print("     ✓ All required directories verified")
    except Exception as e:
        print(f"     ✗ Error creating directories: {e}")
        return False
   
    # Step 2: Load and verify environment variables
    print("\n[2/7] Loading environment variables...")
    try:
        env_vars = dotenv_values(".env")
       
        # Check for API keys (these are critical)
        missing_keys = []
        if not (
            env_vars.get("Account_ID")
            or env_vars.get("CLOUDFLARE_ACCOUNT_ID")
            or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        ):
            missing_keys.append("Account_ID")
        if not (
            env_vars.get("API_Token")
            or env_vars.get("CLOUDFLARE_API_TOKEN")
            or os.environ.get("CLOUDFLARE_API_TOKEN")
        ):
            missing_keys.append("API_Token")
        if not env_vars.get("GroqApiKey"):
            missing_keys.append("GroqApiKey")
       
        if missing_keys:
            print(f"     ⚠ Missing critical keys: {missing_keys}")
        else:
            print("     ✓ All critical API keys present")
       
        # Optional settings
        username = env_vars.get("Username", "User")
        assistant = env_vars.get("AssistantName", "AIKO")
        print(f"     ✓ Username: {username}, Assistant: {assistant}")
       
    except Exception as e:
        print(f"     ✗ Error loading .env: {e}")
        return False
   
    # Step 3: Verify backend modules
    print("\n[3/7] Verifying backend modules...")
    try:
        backend_modules = [
            "Model",
            "RealtimeSearchEngine",
            "Automation",
            "SpeechToText",
            "TextToSpeech",
            "ImageGeneration"
        ]
       
        for module in backend_modules:
            module_path = f"backend/{module}.py"
            if os.path.exists(module_path):
                print(f"     ✓ {module}.py found")
            else:
                print(f"     ✗ {module}.py missing")
       
    except Exception as e:
        print(f"     ✗ Error checking backend modules: {e}")
   
    # Step 4: Verify frontend modules
    print("\n[4/7] Verifying frontend modules...")
    try:
        if os.path.exists("frontend/GUI.py"):
            print("     ✓ GUI.py found")
        else:
            print("     ✗ GUI.py missing")
           
        if os.path.exists("frontend/Files"):
            print("     ✓ Files directory found")
        else:
            print("     ✗ Files directory missing")
           
        if os.path.exists("frontend/Graphics"):
            print("     ✓ Graphics directory found")
        else:
            print("     ✗ Graphics directory missing")
    except Exception as e:
        print(f"     ✗ Error checking frontend: {e}")
   
    # Step 5: Verify data files
    print("\n[5/7] Verifying data files...")
    try:
        data_files = [
            "Data/ChatLog.json",
            "Data/Generated_Images"
        ]
       
        for data_file in data_files:
            if os.path.exists(data_file):
                print(f"     ✓ {data_file} exists")
            else:
                print(f"     ✗ {data_file} missing (will be created)")
       
        # Create ChatLog.json if it doesn't exist
        if not os.path.exists("Data/ChatLog.json"):
            with open("Data/ChatLog.json", "w") as f:
                json.dump([], f)
            print("     ✓ Created Data/ChatLog.json")
           
    except Exception as e:
        print(f"     ✗ Error checking data files: {e}")
   
    # Step 6: Test imports
    print("\n[6/7] Testing module imports...")
    try:
        test_imports = {
            "FirstLayerDMM": FirstLayerDMM,
            "RealtimeSearchEngine": RealtimeSearchEngine,
            "GenerateImage": GenerateImage,
            "OpenApp": OpenApp,
            "SpeechRecognition": SpeechRecognition,
            "TextToSpeech": TextToSpeech,
        }
       
        for name, func in test_imports.items():
            if callable(func):
                print(f"     ✓ {name} imported successfully")
            else:
                print(f"     ✗ {name} import failed")
    except Exception as e:
        print(f"     ✗ Error testing imports: {e}")
        return False
   
    # Step 7: Initialize chat history
    print("\n[7/7] Initializing chat history...")
    try:
        if os.path.exists("Data/ChatLog.json"):
            with open("Data/ChatLog.json", "r") as f:
                chat_data = json.load(f)
            print(f"     ✓ Chat history loaded ({len(chat_data)} entries)")
        else:
            with open("Data/ChatLog.json", "w") as f:
                json.dump([], f)
            print("     ✓ Created new chat history")
    except Exception as e:
        print(f"     ✗ Error initializing chat: {e}")
   
    print("\n" + "="*70)
    print("AIKO INITIALIZATION COMPLETE")
    print("="*70 + "\n")
   
    return True


if __name__ == "__main__":
    # Initialize AIKO first
    if not InitializeAIKO():
        print("[ERROR] Initialization failed. Exiting...")
        sys.exit(1)
   
    print("Starting AIKO Assistant...\n")
    InitalExecution()
   
    # Start the main threads
    reminder_thread = threading.Thread(target=ReminderThread, daemon=True)
    reminder_thread.start()
    thread2 = threading.Thread(target=FirstThread, daemon=True)
    thread2.start()
    SecondThread()
 
