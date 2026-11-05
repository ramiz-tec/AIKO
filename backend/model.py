import cohere
from rich import print
from dotenv import dotenv_values




# Load environment variables from .env file
env_vars = dotenv_values(".env")




# retrieve API key


Cohere_ApiKey = env_vars.get("CohereApiKey")
# Check for missing API key
if not Cohere_ApiKey:
    print("[red]Cohere API key not found. Please check your .env file.[/red]")
    exit(1)


# create a Cohere client using the API key
co = cohere.Client(api_key=Cohere_ApiKey)


# define a list of recognized functions for task categorization
funcs  = [
    "exit", "general", "realtime", "open", "close", "play",
    "generate image", "system", "content", "google search",
    "youtube search", "reminder"
]






# Define the preamble that guides the AI model on how to categorize queries
preamble = """
you are a ver accurate decistion-making model, which decides what kind of a query is given to you.
you will decide whether a query is a 'query', 'action', 'general', 'realtime', 'exit' or 'unknown'
***
do not answer the query, just categorize it.
***
respond with 'general (query)' if a can be answered by a LLM model ( conversational AI)
respond with 'realtime (query)' if a query can not be answered by a LLM model, but requires real-time data or actions.
respond with 'open (application name or website name)' if the query requires opening an application or website.
respond with 'exit(application name or websitie name)' if the query requires closing the application.
respond with 'play(song name)' if the query requires playing a song.
respond with 'generate image(image prompt)' if the query requires generating an image.
respond with 'reminder (datetime with message)' if the query requires setting a reminder.
respond with 'system(tasks name)' if query is asking to mute, unmute, volume up, volume down, or any other system related task.
respond with 'content(topic)' if the query is asking to write any type of content like application, website, blog, article, etc.
respond with 'google search(topic)' if the query is asking to search something on google.
respond with 'youtube search(topic)' if the query is asking to search something on youtube.
*** if the query is asking to preform multiple tasks, categorize it as 'query' and return '(query)' in the response.***
*** if the user is saying 'exit' or 'close' or 'quit' or 'stop' or 'shutdown', categorize it as 'exit' and return '(exit)' in the response.***
*** respond with 'general (query)' if the query is not recognized or does not fit any of the above categories.***
"""




# define a chat history with predefined user-chatbot interactions for context
chat_history = [
    {"role": "user", "content": "how are you?"},
    {"role": "assistant", "content": "general im fine, how can I assist you today?"},
    {"role": "user", "content": "do you like pizza?"},
    {"role": "assistant", "content": "general yes, pizza is delicious!"},
    {"role": "user", "content": "open chrome"},
    {"role": "assistant", "content": "action opening chrome browser."},
    {"role": "user", "content": "what is todays date?  "},
    {"role": "assistant", "content": "realtime today's date is 2023-10-01."},
    {"role": "user", "content": "exit"},
    {"role": "assistant", "content": "exit closing the application."},
]


# Define the main function for decision-making on queries


def FirstLayerDMM(prompt: str = "test") -> list[str]:
    """
    Categorize the user's query using Cohere's chat_stream API.
    Returns a list of categorized responses.
    """
    # Format chat history and prompt as a single string
    history_str = "\n".join(f"{msg['role']}: {msg['content']}" for msg in chat_history)
    history_str += f"\nuser: {prompt}\n"


    # Call Cohere chat_stream and collect the response
    response_text = ""
    try:
        stream = co.chat_stream(
            model='command-r-plus',
            message=history_str,
            temperature=0.7,
            prompt_truncation='off',
            connectors=[],
            preamble=preamble,
        )
        for event in stream:
            if hasattr(event, "text"):
                response_text += event.text
    except Exception as e:
        import traceback
        print(f"[red]Cohere API error: {e}[/red]")
        print(traceback.format_exc())
        return ["(error)"]


    # Debug: print the raw model response
    print(f"[yellow]Raw model response: {response_text}[/yellow]")


    # Remove newline characters and split response into individual tasks.
    response = response_text.replace("\n", "").split(".")
    response = [i.strip() for i in response if i.strip()]


    # Filter the tasks based on recognized function keywords.
    temp = []
    for tasks in response:
        for func in funcs:
            if tasks.startswith(func):
                temp.append(tasks)


    # Return only the first matched category or a single message
    if "(query)" in temp:
        return "(query) detected, please clarify your request."
    elif temp:
        return temp[0]
    else:
        return "(unknown)"


# Entry point for the script.
if __name__ == "__main__":
    # Continuously prompt the user for input and process it.
    while True:
        user_input = input(">>> ")
        if user_input.strip().lower() in ["exit", "quit", "close", "stop", "shutdown", "goodbye"]:
            print("Exiting.")
            break
        result = FirstLayerDMM(user_input)
        # Print only the type/category (first word) if result is a string
        if isinstance(result, str):
            print(result.split()[0])
        else:
            print(result)


