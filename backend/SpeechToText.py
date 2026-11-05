from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import dotenv_values
import os
import mtranslate as mt
import speech_recognition as sr
from time import sleep
import traceback


# load enviornment variables from the .env files.
env_vars = dotenv_values(".env")
# Get the input language setting from the enviornment variables.
InputLanguage = env_vars.get("InputLanguage", "en-US")
recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.8
recognizer.phrase_threshold = 0.3
recognizer.non_speaking_duration = 0.5
ambient_noise_calibrated = False


# define the html code for the text to speech recognition interface.
HtmlCode = '''  <!DOCTYPE html>
<html lang="en">
<head>
     <title>Speech Recognition</title>
 </head>
 <body>
     <button id="start" onclick="startRecognition()">Start Recognition</button>
     <button id="end" onclick="stopRecognition()">Stop Recognition</button>
     <p id="output"></p>
     <script>
         const output = document.getElementById('output');
         let recognition;


         function startRecognition() {
             recognition = new webkitSpeechRecognition() || new SpeechRecognition();
             recognition.lang = '';
             recognition.continuous = true;


             recognition.onresult = function(event) {
                 const transcript = event.results[event.results.length - 1][0].transcript;
                 output.textContent += transcript;
             };


            recognition.onend = function() {
                 recognition.start();
            };
            recognition.start();
        }


        function stopRecognition() {
            recognition.stop();
            output.innerHTML="";
        }
    </script>
</body>
</html>
'''


# Replace the language setting in the html code with input language from enviornment varibles.
HtmlCode = str(HtmlCode).replace("recognition.lang = '';", f"recognition.lang = '{InputLanguage}';")




# write the modified HTML code to a file.
with open(r"Data\Voice.html", "w") as f:
    f.write(HtmlCode)


# Get the current working directory.
current_dir = os.getcwd()


# Generate the file path for the html file.
link = f"{current_dir}/Data/Voice.html"


# set chrome options for the webdriver.
chrome_options = Options()
user_agent = "Mozilla/5.0(Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like gecko) chrome/89.0142.86 safa"
chrome_options.add_argument(f'user-agent={user_agent}')
# Removed headless mode to allow real microphone access
# chrome_options.add_argument("--headless=new")


# define the path for temporary files
TempDirPath = rf"{current_dir}/frontend/Files"


# Function to set the assistant's status by writing it to a file
def SetAssistantStatus(Status):
    with open(rf'{TempDirPath}/Status.data', "w", encoding='utf-8') as file:
        file.write(Status)


# Function to modify query to ensure proper punctuation
def QueryModifier(Query):
    new_Query =  Query.lower().strip()
    query_words = new_Query.split()
    question_words = ["how", "what", "when", "where", "why", "which", "whose", "whom","can you", "what's","how's", "when's",]
    # Check if the query is a question and add a question mark if necessary.
    if any(word in new_Query for word in question_words):
        if query_words[-1][-1] in ['.','?','!',]:
            new_Query = new_Query[:-1] + "?"
        else:
            new_Query += "?"
    else:
        # Add a period if the query is not a question.
        if query_words[-1][-1] in ['.','?','!']:
            new_Query = new_Query[:-1]+ "."
        else:
            new_Query += "."
    return new_Query.capitalize()


# Function to translate text into English using the mtranslate library.
def UniversalTranslator(Text):
    english_translation = mt.translate(Text, "en", "auto")
    return english_translation.capitalize()


# Function to perform speech recognition using the WebDriver.
def SpeechRecognition(timeout=2, phrase_time_limit=30):
    """Capture speech from microphone and convert to text using Google Speech Recognition with improved continuous listening."""
    global ambient_noise_calibrated
    microphone_device_path = os.path.join(
        current_dir, "frontend", "Files", "MicDevice.data"
    )
    device_index = None
    try:
        with open(microphone_device_path, "r", encoding="utf-8") as file:
            selected_device = file.read().strip()
        if selected_device:
            device_index = int(selected_device)
    except FileNotFoundError:
        pass
   
    try:
        with sr.Microphone(device_index=device_index) as source:
            print("[DEBUG] Listening for speech...", flush=True)
            SetAssistantStatus("Listening...")
           
            if not ambient_noise_calibrated:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                ambient_noise_calibrated = True
           
            try:
                audio = recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )
                SetAssistantStatus("Processing...")
               
                # Use Google Speech Recognition
                text = recognizer.recognize_google(audio, language=InputLanguage)
                print(f"[DEBUG] Detected speech: {text}", flush=True)
               
                if "en" in InputLanguage.lower():
                    return QueryModifier(text)
                else:
                    SetAssistantStatus("Translating...")
                    return QueryModifier(UniversalTranslator(text))
                   
            except sr.UnknownValueError:
                print("[DEBUG] Audio received, but no speech was recognized.", flush=True)
                SetAssistantStatus("Listening...")
                return ""
            except sr.WaitTimeoutError:
                print("[DEBUG] No speech detected before the listening timeout.", flush=True)
                SetAssistantStatus("Listening...")
                return ""
            except sr.RequestError as e:
                print(f"[DEBUG] Speech recognition service error: {e}", flush=True)
                return ""
               
    except Exception as e:
        print(f"[ERROR] SpeechRecognition error ({type(e).__name__}): {e!r}", flush=True)
        traceback.print_exc()
        SetAssistantStatus(f"Microphone unavailable: {e}")
        return ""




# Main execution block.
if __name__ == "__main__":
    while True:
        Text = SpeechRecognition()
        print(Text)
   
                                   







