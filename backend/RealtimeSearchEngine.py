from googlesearch import search
from groq import Groq  # Import the Groq library to use its API
from json import load, dump  # Importing functions to read and write JSON files
import datetime  # Importing datetime module for real-time date and time information
from dotenv import dotenv_values  # Importing dotenv_values to read environment variables from a .env file
import re
import requests
import os


# Load environment variables from .env file
env_vars = dotenv_values(".env")


# Retrieve specific environment variables for the chatbot configuration.
username = env_vars.get("Username")
AssistantName = env_vars.get("AssistantName")
GroqAPIKEY = env_vars.get("GroqApiKey")
GROQ_CHAT_MODEL = env_vars.get("GroqModel", "openai/gpt-oss-120b")


# Initialize the Groq client using the API key
client = Groq(api_key=GroqAPIKEY)


# Defin the system instructions for the chatbot.
syatem = f""" Hello, You are a very accurate and advanced AI Chatbot named {AssistantName} which has real-time up-to-date information.
*** provide Answers in a sarcastic, witty way, make sure to add full stops, commas, question marks, and use propper grammer ***
*** just answer the question from the provided data in a professional way.***
*** call the user "sir".***
"""


# Try to load the chat log from then JSON file, or create an empty one if it dosn't exist.
try:
    with open(r"Data\ChatLog.json", "r") as f:
        messages = load(f)
except:
    with open(r"Data\ChatLog.json", "w") as f:
        dump([], f)


        # Function to preform a google search and format the results.
def GoogleSearch(query):
    results = list(search(query, advanced=True, num_results=5 ))
    # Build a concise results string without start/end markers and without printing
    parts = [f"Search results for: {query}"]
    for i in results:
        title = getattr(i, "title", str(i))
        desc = getattr(i, "description", "")
        parts.append(f"Title: {title}")
        if desc:
            parts.append(f"Description: {desc}")
        parts.append("")


    Answer = "\n".join(parts).strip()
    return Answer




def GetWeather(prompt):
    """Try to extract a location from the prompt and query wttr.in for a concise weather report.
    Returns a short string or an empty string on failure."""
    # try to extract 'in <location>' first
    m = re.search(r"weather\s+in\s+([\w\s,.-]+)", prompt, re.IGNORECASE)
    if m:
        location = m.group(1).strip()
    else:
        # fallback: take last two words as location
        parts = prompt.strip().split()
        location = " ".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else "")


    if not location:
        return ""


    # Query wttr.in for a brief one-line weather summary
    try:
        url = f"https://wttr.in/{requests.utils.quote(location)}?format=3"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            text = resp.text.strip()
            # wttr.in can return helpful plain strings; return it prefixed by location if not included
            return text
    except Exception:
        return ""


    return ""


# Function to clean up the answer by removing empty lines.
def AnswerModifier(answer):
    lines = answer.split('\n')  # Split the answer into lines.
    non_empty_lines = [line for line in lines if line.strip()]  # Remove empty lines.
    modified_answer = '\n'.join(non_empty_lines)  # Join the cleaned lines back together.
    return modified_answer


# Predefined Chatbot conversation syatem message  and an initial user message.
SystemChatBot = [
    {"role": "system", "content": syatem},
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": f"hello {username}, how can I assist you?"}
]


# Functions to get real-time information like the current date and time.
def Information():
    data = ""
    current_date_time = datetime.datetime.now()
    day = current_date_time.strftime("%A")
    date = current_date_time.strftime("%d")
    month = current_date_time.strftime("%B")
    year = current_date_time.strftime("%Y")
    hour = current_date_time.strftime("%H")
    minute = current_date_time.strftime("%M")
    second = current_date_time.strftime("%S")
    data += f"use this real-time information if needed:\n"
    data += f"Day: {day}\n"
    data += f"Date: {date}\n"
    data += f"Month: {month}\n"
    data += f"Year: {year}\n"
    data += f" Time : {hour} hours, {minute} minutes, {second} seconds.\n"
    return data


# Function to handle real-time search and response generation.
def _chat_log_path():
    return os.environ.get("AIKO_CHAT_LOG", os.path.join("Data", "ChatLog.json"))


def RealtimeSearchEngine(prompt, persist=True):
    with open(_chat_log_path(), "r", encoding="utf-8") as file:
        messages = load(file)
    if not isinstance(messages, list):
        raise ValueError(f"Chat history must contain a list: {_chat_log_path()}")
    if not messages or messages[-1].get("role") != "user" or messages[-1].get("content") != prompt:
        messages.append({"role": "user", "content": prompt})

    SystemChatBot.append({"role": "system", "content": GoogleSearch(prompt)})
    try:
        completion = client.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=SystemChatBot + [{"role": "system", "content": Information()}] + messages,
            temperature=0.7,
            max_tokens=2048,
            top_p=1,
            stream=True,
            stop=None
        )

        answer = ""
        for chunk in completion:
            if chunk.choices[0].delta.content:
                answer += chunk.choices[0].delta.content

        answer = answer.strip().replace("</s>", "")
        if not answer:
            raise RuntimeError("The real-time search service returned an empty response.")
        if persist:
            messages.append({"role": "assistant", "content": answer})
            with open(_chat_log_path(), "w", encoding="utf-8") as file:
                dump(messages, file, indent=4)
        return AnswerModifier(answer=answer)
    finally:
        SystemChatBot.pop()


# Main entry point of the program for interactive querying.
if __name__=="__main__":
    while True:
        prompt = input("enter you query: ")
        print(RealtimeSearchEngine(prompt))
