from json import load, dump  # Importing functions to read and write JSON files
import datetime  # Importing datetime module for real-time date and time information
from dotenv import dotenv_values  # Importing dotenv_values to read environment variables from a .env file
import os
import glob
import re
import requests
from groq import Groq
# Try to import the local realtime search engine module and helpers; continue gracefully if unavailable
try:
    from backend import RealtimeSearchEngine as realtime_module
    RealtimeSearchEngine = getattr(realtime_module, "RealtimeSearchEngine", None)
    GoogleSearch = getattr(realtime_module, "GoogleSearch", None)
    GetWeather = getattr(realtime_module, "GetWeather", None)
except Exception:
    RealtimeSearchEngine = None
    GoogleSearch = None
    GetWeather = None


# Load environment variables from .env file
env_vars = dotenv_values(".env")


# Retrieve specific environment variables for username, assistant name, and API key.
username = env_vars.get("Username", "User")
AssistantName = env_vars.get("AssistantName", "Assistant")
GroqAPIKEY= env_vars.get("GroqApiKey")
GROQ_CHAT_MODEL = env_vars.get("GroqModel", "openai/gpt-oss-120b")


client = Groq(api_key=GroqAPIKEY) if GroqAPIKEY else None


# Debug flag: set to True to enable debug prints added for troubleshooting
DEBUG = False


# Initialize an empty list to store chat messages.
messages = []


# Define the original system message
system = f"""
hello, I am {username}, you are a very intelligent AI assistant named {AssistantName} with advanced capabilities.
*** Do not tell time until I ask, Answer in short sentences ***
*** Reply in a sarcastic but friendly and helpful manner ***
*** Do not provide notes in the output, just the answer and never mention training data ***
*** Always refer to yourself as {AssistantName} and never as an AI model or assistant ***
*** never mention being a LLM just say "I can't do that yet" ***
"""


# A list of system instructions for the chatbot.
SystemChatBot = [
    {"role": "system", "content": system},
]


# Attempt to load the chat log from a JSON file.
try:
    # Load all existing chatlog files (preserve history across ChatLog.json, ChatLog_1.json, ...)
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


# Helper functions to append to the latest chatlog and rotate when full
def _list_chatlog_files():
    os.makedirs(r"Data", exist_ok=True)
    pattern = os.path.join(r"Data", "ChatLog*.json")
    files = glob.glob(pattern)
    base = os.path.join(r"Data", "ChatLog.json")
    if base not in files:
        files.append(base)


    def _index_from_name(p):
        name = os.path.basename(p)
        m = re.match(r"ChatLog(?:_(\d+))?\.json$", name, re.IGNORECASE)
        if not m:
            return 0
        return int(m.group(1)) if m.group(1) else 0


    unique_files = {os.path.normcase(os.path.abspath(path)): path for path in files}
    files = sorted(unique_files.values(), key=_index_from_name)
    return files


def _get_latest_chatlog_path():
    active_path = os.environ.get("AIKO_CHAT_LOG")
    if active_path and os.path.isfile(active_path):
        return active_path
    files = _list_chatlog_files()
    # Ensure at least base file exists
    base = os.path.join(r"Data", "ChatLog.json")
    if not files:
        with open(base, "w", encoding="utf-8") as f:
            dump([], f, indent=4)
        return base
    # Return the path with the highest index
    return files[-1]


def append_to_chatlogs(role, content):
    """Append a message to the active conversation's dedicated chatlog."""
    path = _get_latest_chatlog_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            existing = load(f)
            if not isinstance(existing, list):
                existing = []
    except Exception:
        existing = []


    new_entry = {"role": role, "content": content}
    existing.append(new_entry)


    with open(path, "w", encoding="utf-8") as f:
        dump(existing, f, indent=4)


# Function to get real-time date and time information.
def RealTimeInformation():
    current_date_time = datetime.datetime.now()  # Get the current date and time.
    day = current_date_time.strftime("%A")  # Get the current day of the week.
    date = current_date_time.strftime("%d")  # Get the current date.
    month = current_date_time.strftime("%B")  # Get the current month.
    year = current_date_time.strftime("%Y")  # Get the current year.
    hour = current_date_time.strftime("%H")  # Get the current hour in 12-hour format.
    minute = current_date_time.strftime("%M")  # Get the current minute.


    # Format the information into a string.
    data = f"please use this real-time information if needed,\n"
    data += f"Day: {day}\nDate: {date}\nMonth: {month}\nYear: {year}\n"
    data += f"Time: {hour}:{minute}\n"
    return data


# Restore the original AnswerModifier function
def AnswerModifier(answer):
    # Preserve the original answer including blank lines so model formatting is retained.
    try:
        return answer
    except Exception:
        return ""


def _chat_error_message(error):
    status_code = getattr(error, "status_code", None)
    error_type = type(error).__name__

    if status_code == 401:
        return "The AI service rejected its API key. Check GroqApiKey in your .env file."
    if status_code == 403:
        return "The AI service denied access. Check that your Groq account can use the configured model."
    if status_code == 404:
        return f"The configured Groq model ({GROQ_CHAT_MODEL}) is unavailable. Set GroqModel in .env to an active model."
    if status_code == 429:
        return "The AI service rate limit or usage quota was reached. Wait and try again, or check your Groq account limits."
    if "Connection" in error_type or "Timeout" in error_type:
        return "Could not connect to the AI service. Check your internet connection and try again."
    return f"The AI service request failed ({error_type}). Check the terminal for the error details."


# Restore the original ChatBot function with retry limit
def ChatBot(Query, retry_count=0, max_retries=3, user_already_logged=False):
    """ This function sends the user's query to the chatbot and returns the AI's response. """


    try:
        # Load recent context from all chatlogs (we preserve full history on disk)
        # Use just the last few messages for model context to avoid token issues.
        try:
            with open(_get_latest_chatlog_path(), "r", encoding="utf-8") as f:
                data = load(f)
                all_messages = data if isinstance(data, list) else []
        except Exception:
            all_messages = []


        # Append this user query to disk (preserve historic logs). For model context use last N
        if not user_already_logged:
            append_to_chatlogs("user", Query)
        # Use the last N messages from history and include the current Query so the model
        # always sees the user's latest input (prevents replying to the previous message).
        messages = all_messages[-10:]
        if user_already_logged:
            if not messages or messages[-1].get("role") != "user" or messages[-1].get("content") != Query:
                messages.append({"role": "user", "content": Query})
        else:
            messages.append({"role": "user", "content": Query})


        # Helper to synthesize a natural assistant answer from support/search text
        def _synthesize_from_support(support_text, msg_list=None):
            try:
                if not support_text or not support_text.strip():
                    return ""
                extra_sys = [{"role": "system", "content": f"Realtime information:\n{support_text}"}, {"role": "system", "content": RealTimeInformation()}]
                use_messages = SystemChatBot + extra_sys + (msg_list if msg_list is not None else messages)
                # non-streaming for simplicity
                completion2 = client.chat.completions.create(
                    model=GROQ_CHAT_MODEL,
                    messages=use_messages,
                    max_tokens=512,
                    temperature=0.7,
                    top_p=1,
                    stream=False,
                )
                # extract assistant text
                try:
                    choice = completion2.choices[0]
                    if hasattr(choice, "message"):
                        msg = choice.message
                        if isinstance(msg, dict):
                            return msg.get("content", "").strip()
                        return getattr(msg, "content", "").strip()
                    elif hasattr(choice, "delta"):
                        delta = choice.delta
                        if isinstance(delta, dict):
                            return delta.get("content", "").strip()
                        return getattr(delta, "content", "").strip()
                    else:
                        return getattr(choice, "text", "").strip()
                except Exception:
                    return ""
            except Exception:
                return ""


        # If the query likely requires real-time information, call the realtime engine first
        realtime_keywords = [
            "weather",
            "forecast",
            "temperature",
            "time",
            "current",
            "today",
            "now",
            "news",
            "stock",
            "stocks",
            "price",
        ]


        def _is_realtime_query(q: str) -> bool:
            try:
                ql = q.lower()
            except Exception:
                return False
            # explicit search triggers (only when user explicitly asks to search/look up)
            if re.search(r"(?:^search:|^google:|\bsearch for\b|\blook up\b|\bgoogle for\b)", ql):
                return True
            # word-boundary match for realtime keywords
            pattern = r"\b(" + "|".join(realtime_keywords) + r")\b"
            if re.search(pattern, ql):
                return True
            return False


        def _is_factual_query(q: str) -> bool:
            try:
                ql = q.lower().strip()
            except Exception:
                return False
            if not ql:
                return False
            # ignore simple greetings or small talk
            if re.match(r'^(hi|hello|hey|thanks|thank you|yo|sup)\b', ql):
                return False
            # explicit question mark or wh- words indicate factual queries
            if '?' in ql:
                return True
            # start-words often indicating advice/decision requests — include modal verbs and suggestion phrases
            if re.match(r'^(who|what|when|where|how|why|which|whom|whose|define|describe|explain|tell me about|should|could|would|can|may|shall|will|recommend|suggest|advise|lets|let\'s|start|plan|help me)\b', ql):
                return True
            # also detect modal/suggestion terms appearing anywhere in the sentence
            if re.search(r'\b(should|could|would|can|recommend|suggest|advise|help me|let\'s|lets|start|plan)\b', ql):
                return True
            return False


        # lowercase query for local checks
        try:
            qlow = Query.lower()
        except Exception:
            qlow = ""


        # Helper to resolve a location from the query and return formatted local time
        def _get_time_for_location(query):
            try:
                m_loc = re.search(r"time\s+(?:in\s+)?(.+)", query, re.IGNORECASE)
                if m_loc:
                    loc = m_loc.group(1).strip()
                else:
                    parts = query.strip().split()
                    loc = " ".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else "")
                if not loc:
                    return ""
                try:
                    tz_list_resp = requests.get("http://worldtimeapi.org/api/timezone", timeout=5)
                    tz_list = tz_list_resp.json() if tz_list_resp.status_code == 200 else []
                    tokens = [t for t in re.split(r"[\s,\-]+", loc) if t]
                    candidates = [tz for tz in tz_list if all(tok.lower() in tz.lower() for tok in tokens)]
                    if not candidates:
                        candidates = [tz for tz in tz_list if any(tok.lower() in tz.lower() for tok in tokens)]
                    if not candidates:
                        return ""
                    tz = candidates[0]
                    resp = requests.get(f"http://worldtimeapi.org/api/timezone/{tz}", timeout=5)
                    if resp.status_code != 200:
                        return ""
                    data = resp.json()
                    dt = data.get("datetime")
                    if not dt:
                        return ""
                    from datetime import datetime as _dt
                    try:
                        parsed = _dt.fromisoformat(dt)
                        formatted = parsed.strftime("%I:%M %p")
                    except Exception:
                        formatted = dt
                    return f"{loc}: {formatted} ({tz})"
                except Exception:
                    return ""
            except Exception:
                return ""


        if _is_realtime_query(Query):
            # If this is a weather request, prefer a direct weather lookup
            if "weather" in qlow and GetWeather is not None:
                if DEBUG:
                    print(f"[DEBUG_CHATBOT] Detected weather query; calling GetWeather: {Query}")
                try:
                    w = GetWeather(Query)
                    if w and w.strip():
                        append_to_chatlogs("assistant", w)
                        return w
                except Exception as ex:
                    if DEBUG:
                        print(f"[DEBUG_CHATBOT] GetWeather failed: {ex}")


            # If this is a time query, prefer a direct timezone lookup and return city + time
            if "time" in qlow:
                # Prefer direct timezone lookup for a location
                try:
                    tloc = _get_time_for_location(Query)
                    if tloc:
                        append_to_chatlogs("assistant", tloc)
                        return tloc
                except Exception:
                    pass


                # Only call GoogleSearch for explicit searches (ending with '?')
                if GoogleSearch is not None and isinstance(Query, str) and Query.strip().endswith('?'):
                    try:
                        gs = GoogleSearch(Query)
                        if gs and gs.strip():
                            import re as _re
                            m = _re.search(r"(\d{1,2}:\d{2}(?:\s?[AP]M)?)", gs)
                            if m:
                                tstr = m.group(1)
                                m_loc = re.search(r"time\s+(?:in\s+)?(.+)", Query, re.IGNORECASE)
                                if m_loc:
                                    loc = m_loc.group(1).strip()
                                    out = f"{loc}: {tstr}"
                                else:
                                    out = tstr
                                append_to_chatlogs("assistant", out)
                                return out
                            # synthesize a natural assistant response from the search support text
                            synth = _synthesize_from_support(gs)
                            if synth:
                                append_to_chatlogs("assistant", synth)
                                return synth
                            append_to_chatlogs("assistant", gs)
                            return gs
                    except Exception as ex:
                        if DEBUG:
                            print(f"[DEBUG_CHATBOT] GoogleSearch (time) failed: {ex}")
                # fallback to realtime engine for time
                if RealtimeSearchEngine is not None:
                    try:
                        rt = RealtimeSearchEngine(Query, persist=False)
                        if rt and rt.strip():
                            append_to_chatlogs("assistant", rt)
                            return rt
                    except Exception as ex:
                        if DEBUG:
                            print(f"[DEBUG_CHATBOT] RealtimeSearchEngine (time) failed: {ex}")


            # Prefer returning direct GoogleSearch results if available — but only for explicit searches
            if GoogleSearch is not None and isinstance(Query, str) and Query.strip().endswith('?'):
                if DEBUG:
                    print(f"[DEBUG_CHATBOT] Query looks realtime-ish; calling GoogleSearch: {Query}")
                try:
                    gs = GoogleSearch(Query)
                    if gs and gs.strip():
                        synth = _synthesize_from_support(gs)
                        if synth:
                            append_to_chatlogs("assistant", synth)
                            return synth
                        append_to_chatlogs("assistant", gs)
                        return gs
                except Exception as ex:
                    if DEBUG:
                        print(f"[DEBUG_CHATBOT] GoogleSearch failed: {ex}")


            # Fall back to the RealtimeSearchEngine flow if GoogleSearch not available or empty
            if RealtimeSearchEngine is not None:
                if DEBUG:
                    print(f"[DEBUG_CHATBOT] calling RealtimeSearchEngine fallback: {Query}")
                try:
                    realtime_result = RealtimeSearchEngine(Query, persist=False)
                    if realtime_result and realtime_result.strip():
                        append_to_chatlogs("assistant", realtime_result)
                        return realtime_result
                except Exception as ex:
                    if DEBUG:
                        print(f"[DEBUG_CHATBOT] RealtimeSearchEngine failed: {ex}")


        # For general queries, try to augment the model context with realtime search results
        support_text = ""
        try:
            # New rule: only treat queries that end with '?' as explicit searches.
            # Everything else is general conversation and should not be auto-searched.
            if GoogleSearch is not None and isinstance(Query, str) and Query.strip().endswith('?'):
                support_text = GoogleSearch(Query)
        except Exception:
            support_text = ""


        extra_system = [{"role": "system", "content": RealTimeInformation()}]
        if support_text and support_text.strip():
            # inject realtime findings into the model context so the assistant can use them
            extra_system.insert(0, {"role": "system", "content": f"Realtime information:\n{support_text}"})


        # Make a request to the OpenAI API for a response.
        if client is None:
            raise RuntimeError("GroqApiKey is missing from .env.")
        completion = client.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=SystemChatBot + extra_system + messages,
            max_tokens=1024,  # Set the maximum number of tokens for the response.
            temperature=0.7,  # Set the temperature for response variability.
            top_p=1,  # Use nucleus sampling to control diversity.
            stream=True,  # Enable streaming response.
            stop=None
        )


        Answer = ""  # Initialize an empty string to store the response.


        # Process the streamed response chunks robustly (handle dict or object deltas)
        try:
            if DEBUG:
                print("[DEBUG_CHATBOT] starting stream iteration")
            for chunk in completion:
                try:
                    if DEBUG:
                        print(f"[DEBUG_CHATBOT] raw chunk: {repr(chunk)}")
                    delta = chunk.choices[0].delta
                    content = None
                    if isinstance(delta, dict):
                        content = delta.get("content")
                    else:
                        content = getattr(delta, "content", None)
                    if DEBUG:
                        print(f"[DEBUG_CHATBOT] extracted content: {repr(content)}")
                    if content:
                        Answer += content
                except Exception as ex:
                    if DEBUG:
                        print(f"[DEBUG_CHATBOT] chunk processing error: {ex}")
                    continue
        except Exception as ex:
            # If streaming iteration itself fails, we'll attempt a non-stream fallback below
            if DEBUG:
                print(f"[DEBUG_CHATBOT] stream iteration failed: {ex}")
            Answer = ""


        # If the stream produced nothing, fall back to a non-streaming request
        if not Answer.strip():
            try:
                if DEBUG:
                    print("[DEBUG_CHATBOT] attempting non-stream fallback")
                completion2 = client.chat.completions.create(
                    model=GROQ_CHAT_MODEL,
                    messages=SystemChatBot + [{"role": "system", "content": RealTimeInformation()}] + messages,
                    max_tokens=1024,
                    temperature=0.7,
                    top_p=1,
                    stream=False,
                )
                if DEBUG:
                    print(f"[DEBUG_CHATBOT] fallback raw response: {repr(completion2)}")
                # Try multiple ways to extract the assistant text from the non-stream response
                try:
                    choice = completion2.choices[0]
                    if hasattr(choice, "message"):
                        msg = choice.message
                        if DEBUG:
                            print(f"[DEBUG_CHATBOT] fallback message object: {repr(msg)}")
                        if isinstance(msg, dict):
                            Answer = msg.get("content", "") or Answer
                        else:
                            Answer = getattr(msg, "content", "") or Answer
                    elif hasattr(choice, "delta"):
                        delta = choice.delta
                        if DEBUG:
                            print(f"[DEBUG_CHATBOT] fallback delta object: {repr(delta)}")
                        if isinstance(delta, dict):
                            Answer = delta.get("content", "") or Answer
                        else:
                            Answer = getattr(delta, "content", "") or Answer
                    else:
                        Answer = getattr(choice, "text", "") or Answer
                except Exception:
                    # leave Answer as empty if extraction fails
                    if DEBUG:
                        print("[DEBUG_CHATBOT] fallback extraction failed")
                    pass
            except Exception:
                if DEBUG:
                    print("[DEBUG_CHATBOT] non-stream fallback request failed")
                # ignore fallback errors; we'll return whatever we have
                pass


        Answer = Answer.replace("</s>", "").replace("<s>", "")  # Clean up any unwanted tokens in the response.


        # Prepare the formatted response and ensure we always return something
        modified = AnswerModifier(answer=Answer)
        if not modified.strip():
            # attempt to use the realtime search engine if available
            if RealtimeSearchEngine is not None:
                if DEBUG:
                    print("[DEBUG_CHATBOT] model returned empty — calling RealtimeSearchEngine fallback")
                try:
                    r_answer = RealtimeSearchEngine(Query, persist=False)
                    if r_answer and r_answer.strip():
                        # Log and return the realtime engine answer
                        append_to_chatlogs("assistant", r_answer)
                        if DEBUG:
                            print(f"[DEBUG_CHATBOT] RealtimeSearchEngine returned: {repr(r_answer)}")
                        return r_answer
                except Exception as ex:
                    if DEBUG:
                        print(f"[DEBUG_CHATBOT] RealtimeSearchEngine call failed: {ex}")
            # if realtime fallback not available or failed, use visible fallback
            modified = "[No response received — please try again]"


        if DEBUG:
            print(f"[DEBUG_CHATBOT] final modified response: {repr(modified)}")


        # Append the (possibly fallback) chatbot response to disk
        append_to_chatlogs("assistant", modified)


        # Return the formatted (or fallback) response.
        return modified


    except Exception as e:
        # Handle any errors by printing the exception and limiting retries.
        status_code = getattr(e, "status_code", None)
        print(f"[ERROR] Chat request failed ({type(e).__name__}, HTTP {status_code}).")
        if retry_count < max_retries:
            return ChatBot(Query, retry_count + 1, max_retries, True)
        error_message = _chat_error_message(e)
        append_to_chatlogs("assistant", error_message)
        return error_message


# Main program entry point.
if __name__ == "__main__":
    while True:
        user_input = input("Enter your question: ")
        print(ChatBot(user_input))  # Call the ChatBot function with user input and print the response.






