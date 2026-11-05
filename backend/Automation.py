# Import required libraries
from AppOpener import close, open as appopen
from webbrowser import open as webopen
from pywhatkit import playonyt, search
from dotenv import dotenv_values
from bs4 import BeautifulSoup
from rich import print
from groq import Groq
import webbrowser
import subprocess
import requests
import keyboard
import asyncio
import os
from urllib.parse import quote_plus


# Load eniornment variables from the .env file.
env_vars = dotenv_values(".env")
GroqApiKey = env_vars.get("GroqApiKey")
Username = env_vars.get("Username", "User")


# Define CSS classes for paring specific elements in HTML content.
classes = ["zCubwf", "hgKELc", "LTKOO sY7ric", "Z0LcW", "gsrt vk_bk FzvWSb YwPhnf", "pclqee",
            "tw-data-text tw-text-small tw-ta",
           "IZ6rdc", "O5uR6d", "webanswers-webanswers_table_webabswers-table",
           "dDoNo ikb4Bb gsrt", "sXLaOe",
           "LWKfKe", "VQF4g", "qv3Wpe", "kno-rdesc", "SPZz6b"]


# Define a user-agent for making web requests.
useragent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36'


# Initialize the Groq client with the API key.
client = Groq(api_key=GroqApiKey)


# predefined professional responses for user interactions
professional_responses = [
    "Your satifacation is my top priority; feel free to reach out if theres anything else I can help you with.",
    "I'm at your service for any additional questions or support you may need-don't hesitate to ask."
]


# List to store chatbots messages
messages =[]


# system message to provide context to the content
SystemChatBot = [{"role": "system", "content": f"Hello, I am {Username}, You're a content writer"}]


# Function to preform google search.
def GoogleSearch(Topic):
    search(Topic)
    return True


# Function to generate content using AI and save it to a file
def content(Topic):
 
    # Nested function to open a file in notepad
 def OpenNotepad(File):
    default_text_editor = 'notepad.exe'
    subprocess.Popen([default_text_editor, File])


        # Nested function to generate content using the AI chatbot
    def ContentWriterAI(prompt):
        messages.append({"role": "user", "content": f"{prompt}"})


        completion = client.chat.completions.create(
            model = "mixtral-8x7b-32768",
            messages =SystemChatBot + messages,
            max_tokens=2048,
            temperature=0.7,
            top_p=1,
            stream=True,
            stop=None
        )
           
        Answer = ""


            # Process streamed response chunks
        for chunk in completion:
            if chunk.choices[0].delta.content:
                Answer += chunk.choices[0].delta.content


        Answer = Answer.replace("</s>", "")
        messages.append({"role": "assistant", "content": Answer})
        return Answer
       
    Topic: str = Topic.replace("Content ", "")
    ContentByAI = ContentWriterAI(Topic)


    # save the generated content to a text file
    with open(rf"Data\{Topic.lower().replace(' ','')}.txt", "w", encoding="utf-8") as file:
        file.write(ContentByAI)
        file.close()


    OpenNotepad(rf"Data\{Topic.lower().replace(' ','')}.txt")
    return True
       
        # Function search the topic on YouTube
def YouTubeSearch(Topic):
    if not Topic or not Topic.strip():
        url4Search = "https://www.youtube.com"
    else:
        url4Search = f"https://www.youtube.com/results?search_query={quote_plus(Topic.strip())}"
    webbrowser.open(url4Search)
    return True
       
        # Function to play video on YouTube
def PlayYoutube(query):
    if not query or not query.strip():
        raise ValueError("A video search query is required.")
    playonyt(query.strip())
    return True
       
        # Function to open an App or relevant webpage
def OpenApp(app, sess=requests.session()):


    try:
        appopen(app, match_closest=True, output=True, throw_error=True)
        return True
           
    except:
            # Nested function to extract links from html content.
        def extract_links(html):
                if html is None:
                    return[]
                soup = BeautifulSoup(html, 'html.parser')
                links = soup.find_all('a', {'jsname': 'UWcKNb'})
                return [link.get('href') for link in links]
               
                # Nested function to preform a google search and retrive HTML.
        def search_google(query):
            url = f"https://www.google.com/search?q={query}"
            headers = {"User-Agent": useragent}
            response = sess.get(url, headers=headers)


            if response.status_code == 200:
                return response.text
            else:
                print("Failed to retrieve search results.")
            return None
               
        html = search_google(app)


        if html:
            link = extract_links(html)[0]
            webopen(link)


        return True


    # Function to close an application
def CloseApp(app):
    close(app, match_closest=True, throw_error=True)
    return True
               
        # Function to execute system-level commands.
def System(command):


            # Nested function to mute system volume.
    def mute():
        keyboard.press_and_release("volume mute")


            # Nested Function to unmute system.
    def unmute():
        keyboard.press_and_release("volume mute")


        #nested function to increase system volume.
    def volume_up():
        keyboard.press_and_release("volume up")


    # Nested function to decrease system volume.
    def volume_down():
        keyboard.press_and_release("volume down")


        # execute appropriate command
    if command == "mute":
            mute()
    elif command == "unmute":
            unmute()


    elif command == "volume up":
            volume_up()
    elif command == "volume down":
            volume_down()
           
    return True
       
        # Asynchronous function to translate and execute user commands
async def  TranslateAndExecute(commands: list[str]):
     
     funcs = []
     
     for command in commands:


         if command.startswith("open "):


             if "open it" in command:
                 pass


             if "open file" == command:
                 pass


             else:
                fun = asyncio.to_thread(OpenApp, command.removeprefix("open "))
                funcs.append(fun)
       
         elif command.startswith("general "):
              pass


         elif command.startswith("realtime "):
              pass


         elif command.startswith("close "):
              fun = asyncio.to_thread(CloseApp, command.removeprefix("close "))
              funcs.append(fun)


         elif command.startswith("play "):
            fun = asyncio.to_thread(PlayYoutube, command.removeprefix("play "))
            funcs.append(fun)


         elif command.startswith("content "):
            fun = asyncio.to_thread(content, command.removeprefix("content "))
            funcs.append(fun)


         elif command.startswith("google search "):
            fun = asyncio.to_thread(content, command.removeprefix("google search"))
            funcs.append(fun)


         elif command.startswith("youtube search "):
            fun = asyncio.to_thread(content, command.removeprefix("youtube search"))
            funcs.append(fun)


         elif command.startswith("system "):
            fun = asyncio.to_thread(content, command.removeprefix("system"))
            funcs.append(fun)


         else:
            print("no function found. For {command}")


     results = await asyncio.gather(+funcs)


     for result in results:
            if isinstance(result, str):
                yield result
            else:
                yield result
       
        # Asynchronous function to automate command execution.
async def Automation(commands: list[str]):


    async for result in TranslateAndExecute(commands):
        pass


        return True


        if __name__=="__main__":
            asyncio.run(Automation(["open google", "open youtube"]))
