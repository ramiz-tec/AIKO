from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QStackedWidget, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QLabel, QSizePolicy, QMessageBox, QDialog, QComboBox, QScrollArea
from PyQt5.QtGui import QIcon, QPainter, QMovie, QColor, QTextCharFormat, QFont, QTextBlockFormat, QRadialGradient, QPen, QPixmap
from PyQt5.QtCore import Qt, QSize, QTimer, QObject, pyqtSignal
from backend.Reminders import ListReminders
from dotenv import dotenv_values
import json
import math
import re
import sys
import os
try:
    import pyaudio
    HAS_AUDIO = True
except ImportError:
    pyaudio = None
    HAS_AUDIO = False
    print("PyAudio not available (running in cloud/headless mode)")
from datetime import datetime
from threading import Event
try:
    import pyaudio
    HAS_AUDIO = True
except ImportError:
    pyaudio = None
    HAS_AUDIO = False
    print("PyAudio not available (running in cloud/headless mode)")


env_vars = dotenv_values(".env")
Assistantname = env_vars.get("AssistantName")
currtent_dir = os.getcwd()
old_chat_message = ""
TempDirPath = rf'{currtent_dir}\frontend\Files'
GraphicsDirPath = rf'{currtent_dir}\frontend\Graphics'
ChatLogDirPath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Data")


def _paint_workspace_background(widget):
     painter = QPainter(widget)
     gradient = QRadialGradient(
          widget.width() * 0.5,
          widget.height() * 0.48,
          max(widget.width(), widget.height()) * 0.75,
     )
     gradient.setColorAt(0, QColor(9, 32, 48))
     gradient.setColorAt(1, QColor(2, 5, 14))
     painter.fillRect(widget.rect(), gradient)


def AnswerModifier(answer):
    lines = answer.split('\n')  # Split the answer into lines.
    non_empty_lines = [line for line in lines if line.strip()]  # Remove empty lines.
    modified_answer = '\n'.join(non_empty_lines)  # Join the cleaned lines back together.
    return modified_answer


def QueryModifier(Query):
   
    new_Query = Query.lower().strip()
    query_words = new_Query.split()
    question_words = ["how", "what", "when", "where", "why", "which", "whose", "whom", "can you", "what's", "how's", "when's"]
    # Check if the query is a question and add a question mark if necessary.
    if any(word in new_Query for word in question_words):
        if query_words[-1][-1] in ['.', '?', '!']:
            new_Query = new_Query[:-1] + "?"
        else:
            new_Query += "?"


    else:
        # Add a period if the query is not a question.
        if query_words[-1][-1] in ['.', '?', '!']:
            new_Query = new_Query[:-1] + "."
        else:
            new_Query += "."
    return new_Query.capitalize()


def SetMicrophoneStatus(command):
    with open(rf'{TempDirPath}/Mic.data', "w", encoding='utf-8') as file:
        file.write(str(command))


def GetMicrophoneStatus():
      with open(rf'{TempDirPath}/Mic.data', "r", encoding='utf-8') as file:
          status = file.read()
      return status


def SetAssistantStatus(Status):
    with open(rf'{TempDirPath}/Status.data', "w", encoding='utf-8') as file:
        file.write(Status)


def GetAssistantStatus():
     with open(rf'{TempDirPath}/Status.data', "r", encoding='utf-8') as file:
          status = file.read()
     return status


def SetSpeechLevel(level):
     value = min(1.0, max(0.0, float(level)))
     _image_selection_bridge.speech_level_changed.emit(value)


class ImageSelectionBridge(QObject):
     selection_requested = pyqtSignal(object)
     speech_level_changed = pyqtSignal(float)


_image_selection_bridge = ImageSelectionBridge()
_image_selection_bridge_connected = False


def SelectGeneratedImage(option_number, timeout=8):
     if not _image_selection_bridge_connected:
          raise RuntimeError("There are no generated image options open to choose from.")
     request = {
          "option_number": int(option_number),
          "event": Event(),
          "success": False,
          "message": "",
     }
     _image_selection_bridge.selection_requested.emit(request)
     if not request["event"].wait(timeout):
          raise RuntimeError("AIKO timed out while closing the unselected images.")
     if not request["success"]:
          raise RuntimeError(request["message"] or "AIKO could not select that image.")
     return request["message"]


def MicButtonInitialed():
    SetMicrophoneStatus("True")


def MicButtonClosed():
    SetMicrophoneStatus("False")


def GetMicrophoneDevices():
     audio = pyaudio.PyAudio()
     try:
          devices = []
          for index in range(audio.get_device_count()):
               info = audio.get_device_info_by_index(index)
               if info.get("maxInputChannels", 0) > 0:
                    devices.append((index, info["name"]))
          try:
               default_index = int(audio.get_default_input_device_info()["index"])
          except OSError:
               default_index = devices[0][0] if devices else None
          return devices, default_index
     finally:
          audio.terminate()


def SetMicrophoneDevice(index):
     with open(TempDirectoryPath("MicDevice.data"), "w", encoding="utf-8") as file:
          file.write(str(index))


def GraphicsDirectoryPath(Filename):
     Path =rf'{GraphicsDirPath}/{Filename}'
     return Path


def TempDirectoryPath(Filename):
     Path = rf'{TempDirPath}/{Filename}'
     return Path


def _ensure_runtime_files():
     os.makedirs(TempDirPath, exist_ok=True)
     defaults = {
          "Mic.data": "False",
          "MicDevice.data": "",
          "Status.data": "Available...",
          "Responses.data": "",
          "ImageGeneration.data": "[]",
     }
     for filename, default in defaults.items():
          path = TempDirectoryPath(filename)
          if not os.path.exists(path):
               with open(path, "w", encoding="utf-8") as file:
                    file.write(default)


def QueueImageGallery(prompt, image_paths):
     _ensure_runtime_files()
     if len(image_paths) != 3:
          raise ValueError(f"An image gallery requires exactly three images; received {len(image_paths)}.")
     queue_path = TempDirectoryPath("ImageGeneration.data")
     with open(queue_path, "r", encoding="utf-8") as file:
          queue_text = file.read().strip()
     queue = json.loads(queue_text) if queue_text else []
     if not isinstance(queue, list):
          raise ValueError("ImageGeneration.data must contain a JSON list.")
     queue.append({
          "prompt": str(prompt),
          "paths": [os.path.abspath(path) for path in image_paths],
     })
     temporary_path = f"{queue_path}.tmp"
     with open(temporary_path, "w", encoding="utf-8") as file:
          json.dump(queue, file, indent=2)
     os.replace(temporary_path, queue_path)


def _take_pending_image_galleries():
     queue_path = TempDirectoryPath("ImageGeneration.data")
     with open(queue_path, "r", encoding="utf-8") as file:
          queue_text = file.read().strip()
     queue = json.loads(queue_text) if queue_text else []
     if not isinstance(queue, list):
          raise ValueError("ImageGeneration.data must contain a JSON list.")
     if not queue:
          return []
     temporary_path = f"{queue_path}.tmp"
     with open(temporary_path, "w", encoding="utf-8") as file:
          json.dump([], file)
     os.replace(temporary_path, queue_path)
     return queue


def _chat_log_files():
     if not os.path.isdir(ChatLogDirPath):
          return []
     files = []
     for filename in os.listdir(ChatLogDirPath):
          match = re.fullmatch(r"ChatLog(?:_(\d+))?\.json", filename, re.IGNORECASE)
          if match:
               index = int(match.group(1)) if match.group(1) else 0
               files.append((index, os.path.join(ChatLogDirPath, filename)))
     return [path for _, path in sorted(files)]


def GetActiveChatLogPath():
     files = _chat_log_files()
     marker_path = TempDirectoryPath("ActiveChat.data")
     if os.path.exists(marker_path):
          with open(marker_path, "r", encoding="utf-8") as file:
               active_path = os.path.abspath(file.read().strip())
          if active_path in {os.path.abspath(path) for path in files}:
               return active_path
     if files:
          return os.path.abspath(files[-1])
     os.makedirs(ChatLogDirPath, exist_ok=True)
     base_path = os.path.join(ChatLogDirPath, "ChatLog.json")
     with open(base_path, "w", encoding="utf-8") as file:
          json.dump([], file, indent=4)
     return os.path.abspath(base_path)


def ActivateConversation(conversation_path):
     _ensure_runtime_files()
     valid_paths = {os.path.abspath(path) for path in _chat_log_files()}
     active_path = os.path.abspath(conversation_path)
     if active_path not in valid_paths:
          raise ValueError(f"Unknown conversation history: {conversation_path}")
     with open(TempDirectoryPath("ActiveChat.data"), "w", encoding="utf-8") as file:
          file.write(active_path)
     os.environ["AIKO_CHAT_LOG"] = active_path
     with open(active_path, "r", encoding="utf-8") as file:
          messages = json.load(file)
     if not isinstance(messages, list):
          raise ValueError(f"Chat history must contain a list: {active_path}")
     transcript = "\n".join(
          f"{'You' if entry.get('role') == 'user' else Assistantname}: {entry.get('content', '')}"
          for entry in messages
          if isinstance(entry, dict) and entry.get("role") in {"user", "assistant"}
     )
     ShowTextToScreen(transcript)
     return active_path


def CreateConversationOrb():
     os.makedirs(ChatLogDirPath, exist_ok=True)
     indices = []
     for path in _chat_log_files():
          match = re.fullmatch(r"ChatLog(?:_(\d+))?\.json", os.path.basename(path), re.IGNORECASE)
          indices.append(int(match.group(1)) if match and match.group(1) else 0)
     new_index = max(indices, default=-1) + 1
     filename = "ChatLog.json" if new_index == 0 else f"ChatLog_{new_index}.json"
     path = os.path.join(ChatLogDirPath, filename)
     with open(path, "w", encoding="utf-8") as file:
          json.dump([], file, indent=4)
     ActivateConversation(path)
     return path


def DeleteConversationOrb(conversation_path):
     path = os.path.abspath(conversation_path)
     expected_directory = os.path.abspath(ChatLogDirPath)
     if os.path.dirname(path) != expected_directory or not re.fullmatch(
          r"ChatLog(?:_\d+)?\.json", os.path.basename(path), re.IGNORECASE
     ):
          raise ValueError(f"Not a conversation chatlog: {conversation_path}")

     known_paths = {os.path.normcase(os.path.abspath(item)) for item in _chat_log_files()}
     if os.path.normcase(path) not in known_paths:
          raise ValueError(f"Unknown conversation chatlog: {conversation_path}")

     active_path = os.path.abspath(GetActiveChatLogPath())
     category_path = f"{path}.category"
     if os.path.exists(category_path):
          os.remove(category_path)
     os.remove(path)

     if os.path.normcase(path) == os.path.normcase(active_path):
          remaining_paths = _chat_log_files()
          if remaining_paths:
               ActivateConversation(remaining_paths[-1])
          else:
               CreateConversationOrb()
     return path


ORB_CATEGORIES = {
     "conversation": {"label": "General conversation", "color": QColor(36, 211, 220)},
     "search": {"label": "Google searches", "color": QColor(255, 153, 45)},
     "design": {"label": "Design plans", "color": QColor(240, 65, 65)},
     "schedule": {"label": "Schedules and events", "color": QColor(65, 205, 115)},
     "relationship": {"label": "Relationships", "color": QColor(245, 105, 180)},
}


_IMAGE_TOPIC_PATTERN = re.compile(
     r"\b(?:images?|pictures?|photos?|photographs?|illustrations?|artworks?|"
     r"drawings?|sketches?|graphics?|logos?|icons?|avatars?|wallpapers?|"
     r"portraits?|paintings?|diagrams?|infographics?|memes?|screenshots?|"
     r"thumbnails?|vectors?|visuals?|renderings?)\b",
     re.IGNORECASE,
)

_BLUEPRINT_REQUEST_PATTERN = re.compile(
     r"^\s*(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
     r"(?:create|make|generate|draw|design)\s+"
     r"(?:(?:me)\s+)?(?:an?\s+)?blueprint\b",
     re.IGNORECASE,
)


def _is_image_related_query(query):
     return bool(
          _IMAGE_TOPIC_PATTERN.search(str(query))
          or _BLUEPRINT_REQUEST_PATTERN.search(str(query))
          or re.fullmatch(r"\s*(?:please\s+)?generate[.!?]*\s*", str(query), re.IGNORECASE)
     )


def _classify_query_category(query, intent=None):
     if intent in {"generate image", "choose image"} or _is_image_related_query(query):
          return "design"
     if intent == "reminder":
          return "schedule"
     if intent in {"realtime", "google search"}:
          return "search"

     query = str(query).lower()
     is_image_request = bool(re.search(
          r"\b(?:generate|create|make|draw|design|render|paint)\s+"
          r"(?:(?:me)\s+)?(?:(?:an?|the)\s+)?"
          r"(?:image|iamge|picture|photo|photograph|illustration|artwork|art)\b"
          r"|\b(?:create|make|generate|draw|design)\s+(?:me\s+)?(?:an?\s+)?blueprint\b"
          r"|\bmake\s+(?:me\s+)?a\s+",
          query,
     ))
     if is_image_request:
          return "design"
     scores = {
          "relationship": int(bool(re.search(
               r"\b(relationship|dating|date|partner|girlfriend|boyfriend|spouse|marriage|married|breakup|break up|love life|couple)\b",
               query,
          ))),
          "design": int(bool(re.search(
               r"\b(design|wireframe|prototype|mockup|mock-up|ui|ux|layout|visual identity|brand identity|design plan|image generation|generated image)\b",
               query,
          ))),
          "schedule": int(bool(re.search(
               r"\b(schedule|calendar|appointment|meeting|reminder|event|itinerary|agenda|time slot|plan my (?:day|week|month)|plan (?:an? )?(?:event|trip|weekend))\b",
               query,
          ))),
          "search": int(bool(re.search(
               r"\b(google search|search google|google for|search for|look up|google)\b",
               query,
          ))),
     }
     return max(scores, key=scores.get) if any(scores.values()) else "conversation"


def UpdateConversationOrbCategory(conversation_path, query, intent=None):
     category = _classify_query_category(query, intent)
     if category not in ORB_CATEGORIES:
          raise ValueError(f"Unknown conversation orb category: {category}")

     category_path = f"{conversation_path}.category"
     temporary_path = f"{category_path}.tmp"
     with open(temporary_path, "w", encoding="utf-8") as file:
          file.write(category)
     os.replace(temporary_path, category_path)
     return category


def _classify_conversation(messages):
     scores = {category: 0 for category in ORB_CATEGORIES if category != "conversation"}
     for message in messages:
          if not isinstance(message, dict) or message.get("role") != "user":
               continue
          query = str(message.get("content", "")).lower()
          if _is_image_related_query(query):
               scores["design"] += 1
               continue
          if re.search(
               r"\b(?:generate|create|make|draw|design|render|paint)\s+"
               r"(?:(?:me)\s+)?(?:(?:an?|the)\s+)?"
               r"(?:image|iamge|picture|photo|photograph|illustration|artwork|art)\b"
               r"|\bmake\s+(?:me\s+)?a\s+"
               r"|\bimage generation\b",
               query,
          ):
               scores["design"] += 1
               continue
          if re.search(r"\b(relationship|dating|date|partner|girlfriend|boyfriend|spouse|marriage|married|breakup|break up|love life|couple)\b", query):
               scores["relationship"] += 1
          if re.search(r"\b(design|wireframe|prototype|mockup|mock-up|ui|ux|layout|visual identity|brand identity|design plan)\b", query):
               scores["design"] += 1
          if re.search(r"\b(schedule|calendar|appointment|meeting|reminder|event|itinerary|agenda|time slot|plan my (?:day|week|month)|plan (?:an? )?(?:event|trip|weekend))\b", query):
               scores["schedule"] += 1
          if re.search(r"\b(google search|search google|google for|search for|look up|google)\b", query):
               scores["search"] += 1
     return max(scores, key=lambda category: scores[category]) if any(scores.values()) else "conversation"


def _load_conversations():
     conversations = []
     for path in _chat_log_files():
          with open(path, "r", encoding="utf-8") as file:
               entries = json.load(file)
          if not isinstance(entries, list):
               raise ValueError(f"Chat history must contain a list: {path}")
          user_messages = [
               str(entry.get("content", "")).strip()
               for entry in entries
               if isinstance(entry, dict) and entry.get("role") == "user"
          ]
          category = _classify_conversation(entries)
          try:
               with open(f"{path}.category", "r", encoding="utf-8") as file:
                    saved_category = file.read().strip()
               if saved_category in ORB_CATEGORIES:
                    category = saved_category
          except FileNotFoundError:
               pass
          title = next((message for message in user_messages if message), "New conversation")
          words = re.findall(r"[a-zA-Z0-9']{3,}", " ".join(user_messages).lower())
          stop_words = {
               "about", "after", "again", "could", "from", "have", "just",
               "like", "make", "more", "need", "please", "that", "them",
               "there", "this", "want", "what", "when", "where", "which",
               "with", "would", "your",
          }
          keywords = {word for word in words if word not in stop_words}
          conversations.append({
               "path": path,
               "title": title[:52] + ("..." if len(title) > 52 else ""),
               "summary": user_messages[-1] if user_messages else "No messages yet.",
               "message_count": len(entries),
               "keywords": keywords,
               "category": category,
          })
     return conversations


def ShowTextToScreen(Text):
    with open(rf'{TempDirPath}/Responses.data', "w", encoding='utf-8') as file:
            file.write(Text)


class GeneratedImageWindow(QDialog):
     def __init__(self, image_path, index, prompt, on_choose, parent=None):
          super().__init__(parent, Qt.Window)
          self.image_path = image_path
          self.on_choose = on_choose
          self.setWindowTitle(f"AIKO - Image option {index}")
          self.setStyleSheet(
               "QDialog { background: transparent; color: white; } "
               "QLabel { color: white; background: transparent; }"
          )
          layout = QVBoxLayout(self)
          prompt_label = QLabel(
               f"Which image do you like best? Choose this option to keep it; "
               f"the other two will be deleted.\n\nOption {index}\n{prompt}"
          )
          prompt_label.setWordWrap(True)
          layout.addWidget(prompt_label)
          image_label = QLabel()
          image_label.setAlignment(Qt.AlignCenter)
          pixmap = QPixmap(image_path)
          if pixmap.isNull():
               raise ValueError(f"Could not load generated image: {image_path}")
          image_label.setPixmap(pixmap.scaled(
               640, 520, Qt.KeepAspectRatio, Qt.SmoothTransformation
          ))
          layout.addWidget(image_label, 1)
          self.choose_button = QPushButton("Choose this image")
          self.choose_button.clicked.connect(lambda: self.on_choose(self.image_path))
          layout.addWidget(self.choose_button)
          self.resize(500, 500)

     def paintEvent(self, event):
          _paint_workspace_background(self)
          super().paintEvent(event)

     def mark_selected(self):
          self.setWindowTitle("AIKO - Selected image")
          self.choose_button.setText("Selected - keep this image")
          self.choose_button.setEnabled(False)


class ChatSection(QWidget):
   
       def __init__(self):
            super().__init__()
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 40, 40, 100)
            layout.setSpacing(0)
           
            # Chat display area
            self.chat_text_edit = QTextEdit()
            self.chat_text_edit.setReadOnly(True)
            self.chat_text_edit.setTextInteractionFlags(Qt.NoTextInteraction)
            self.chat_text_edit.setFrameStyle(QFrame.NoFrame)
            self.chat_text_edit.setStyleSheet(
                 "background: transparent; color: white; border: none;"
            )
            self.chat_text_edit.viewport().setStyleSheet("background: transparent;")
            layout.addWidget(self.chat_text_edit)
           
            layout.setSizeConstraint(QVBoxLayout.SetDefaultConstraint)
            self.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
            text_color = QColor(Qt.blue)
            text_color_text = QTextCharFormat()
            text_color_text.setForeground(text_color)
            self.gif_label = QLabel()
            self.gif_label.setStyleSheet("border: none;")
            self.gif_movie = QMovie(GraphicsDirectoryPath("AIKO(2).gif"))
            max_gif_size_W = 480
            max_gif_size_H = 270
            self.gif_movie.setScaledSize(QSize(max_gif_size_W, max_gif_size_H))
            self.gif_label.setAlignment(Qt.AlignRight | Qt.AlignBottom)
            self.gif_label.setMovie(self.gif_movie)
            self.gif_movie.start()
            layout.addWidget(self.gif_label)
            self.label = QLabel("")
            self.label.setStyleSheet("color: white; font-size: 16px; margin-right: 195px; border: none; margin-top: -30px;")
            self.label.setAlignment(Qt.AlignRight)
            layout.addWidget(self.label)
            # Removed duplicate layout.addWidget(self.gif_label) and negative spacing
            font = QFont()
            font.setPointSize(13)
            self.chat_text_edit.setFont(font)
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.loadMessages)
            self.timer.timeout.connect(self.SpeechRecogText)
            self.timer.timeout.connect(self.show_pending_image_galleries)
            self.image_windows = []
            self.image_galleries = []
            global _image_selection_bridge_connected
            _image_selection_bridge.selection_requested.connect(
                self.select_generated_image_by_option
            )
            _image_selection_bridge_connected = True
            self.timer.start(100)
            self.chat_text_edit.viewport().installEventFilter(self)
            self.setStyleSheet("""
                QScrollBar:vertical {
                    border: none;
                    background: transparent;
                    width: 10px;
                    margin: 0px 0px 0px 0px;
                }
                QScrollBar::handle:vertical {
                    background: white;
                    min-height: 20px;
                }
                QScrollBar::add-line:vertical{
                    background: black;
                    subcontrol-position: bottom;
                    subcontrol-origin: margin;
                    height: 10px;
                }
                QScrollBar::sub-line:vertical {
                    background: black;
                    subcontrol-position: top;
                    subcontrol-origin: margin;
                    height: 10px;
                }
                QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
                    border: none;
                    background: none;
                    color: none;
                }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                    background: none;
                }
            """)

       def paintEvent(self, event):
           _paint_workspace_background(self)
           super().paintEvent(event)
       
       def loadMessages(self):
           global old_chat_message
           with open(rf'{TempDirPath}/Responses.data', "r", encoding='utf-8') as file:
               messages = file.read()
           if str(old_chat_message) == str(messages):
               return
           self.chat_text_edit.clear()
           if messages:
               self.addMessage(message=messages, color='white')
           old_chat_message = messages


       def SpeechRecogText(self):
           with open(rf'{TempDirPath}/Status.data', "r", encoding='utf-8') as file:
               messages = file.read()
           self.label.setText(messages)


       def show_pending_image_galleries(self):
           try:
               galleries = _take_pending_image_galleries()
           except (OSError, ValueError, json.JSONDecodeError) as error:
               print(f"[ERROR] Could not read generated images: {error}")
               return

           for gallery in galleries:
               if not isinstance(gallery, dict):
                   print("[ERROR] Invalid image gallery entry in ImageGeneration.data.")
                   continue
               prompt = str(gallery.get("prompt", "Generated image"))
               paths = gallery.get("paths")
               if not isinstance(paths, list) or len(paths) != 3:
                   print("[ERROR] Image gallery must contain exactly three image paths.")
                   continue
               screen = QApplication.desktop().screenGeometry()
               window_width = min(500, max(1, screen.width() // 3))
               start_x = max(0, (screen.width() - window_width * 3) // 2)
               gallery_paths = tuple(os.path.abspath(path) for path in paths)
               gallery_windows = []
               for index, image_path in enumerate(paths, start=1):
                   try:
                       window = GeneratedImageWindow(
                           image_path,
                           index,
                           prompt,
                           lambda selected_path, options=gallery_paths: (
                               self.choose_generated_image(selected_path, options)
                           ),
                           self,
                       )
                   except (OSError, ValueError) as error:
                       print(f"[ERROR] Could not display generated image: {error}")
                       continue
                   window.move(
                       start_x + (index - 1) * window_width,
                       max(0, (screen.height() - 500) // 2),
                   )
                   window.resize(window_width, min(500, screen.height()))
                   self.image_windows.append(window)
                   gallery_windows.append(window)
                   window.show()
               if len(gallery_windows) == 3:
                   self.image_galleries.append({
                       "paths": gallery_paths,
                       "windows": gallery_windows,
                   })

       def select_generated_image_by_option(self, request):
           try:
               option_number = request["option_number"]
               gallery = next(
                   (
                       item for item in reversed(self.image_galleries)
                       if len(item["paths"]) == 3
                   ),
                   None,
               )
               if gallery is None or option_number not in (1, 2, 3):
                   raise RuntimeError("No matching image option is open.")
               selected_path = gallery["paths"][option_number - 1]
               success, message = self.choose_generated_image(
                   selected_path, gallery["paths"], show_errors=False
               )
               request["success"] = success
               request["message"] = message
           except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
               request["success"] = False
               request["message"] = str(error)
           finally:
               request["event"].set()

       def choose_generated_image(self, image_path, gallery_paths, show_errors=True):
           selected_path = os.path.abspath(image_path)
           normalized_paths = tuple(os.path.abspath(path) for path in gallery_paths)
           generated_images_dir = os.path.normcase(
               os.path.abspath(os.path.join(ChatLogDirPath, "Generated_Images"))
           )
           try:
               paths_are_generated_images = all(
                   os.path.samefile(os.path.dirname(path), generated_images_dir)
                   for path in normalized_paths
               )
           except OSError:
               paths_are_generated_images = False
           if (
               len(normalized_paths) != 3
               or len(set(map(os.path.normcase, normalized_paths))) != 3
               or os.path.normcase(selected_path) not in {
                   os.path.normcase(path) for path in normalized_paths
               }
               or not paths_are_generated_images
           ):
               message = "The image gallery contains unexpected file paths; no images were deleted."
               if show_errors:
                    QMessageBox.critical(self, "Could not choose image", message)
               return False, message

           if not os.path.isfile(selected_path):
               message = "The selected image is missing; no other images were deleted."
               if show_errors:
                    QMessageBox.warning(self, "Selected image missing", message)
               return False, message

           gallery_set = {os.path.normcase(path) for path in normalized_paths}
           gallery_windows = [
               window for window in self.image_windows
               if os.path.normcase(os.path.abspath(window.image_path)) in gallery_set
           ]
           for window in gallery_windows:
               if os.path.normcase(os.path.abspath(window.image_path)) == os.path.normcase(selected_path):
                   window.mark_selected()
               else:
                   window.hide()
                   window.close()
           QApplication.processEvents()
           still_open = [
               window for window in gallery_windows
               if os.path.normcase(os.path.abspath(window.image_path)) != os.path.normcase(selected_path)
               and window.isVisible()
           ]
           if still_open:
               message = "One or more unselected image windows could not be closed."
               if show_errors:
                    QMessageBox.warning(self, "Could not close image options", message)
               return False, message
           unselected_windows = [
               window for window in gallery_windows
               if os.path.normcase(os.path.abspath(window.image_path)) != os.path.normcase(selected_path)
           ]
           self.image_windows = [
               window for window in self.image_windows
               if window not in gallery_windows
               or os.path.normcase(os.path.abspath(window.image_path)) == os.path.normcase(selected_path)
           ]
           for window in unselected_windows:
               window.deleteLater()

           delete_errors = []
           for path in normalized_paths:
               if os.path.normcase(path) == os.path.normcase(selected_path):
                   continue
               try:
                   os.remove(path)
               except FileNotFoundError:
                   pass
               except OSError as error:
                   delete_errors.append(f"{os.path.basename(path)}: {error}")
           if delete_errors:
               message = (
                   "The selected image was kept, but cleanup was incomplete:\n\n"
                   + "\n".join(delete_errors)
               )
               if show_errors:
                    QMessageBox.warning(self, "Some images could not be deleted", message)
               return False, message

           self.image_galleries = [
               gallery for gallery in self.image_galleries
               if not set(map(os.path.normcase, gallery["paths"])) == gallery_set
           ]
           selected_index = next(
               index for index, path in enumerate(normalized_paths, start=1)
               if os.path.normcase(path) == os.path.normcase(selected_path)
           )
           return True, f"Kept image option {selected_index}; closed and deleted the other two."

       def addMessage(self, message, color):
           cursor = self.chat_text_edit.textCursor()
           format = QTextCharFormat()
           formatm = QTextBlockFormat()
           formatm.setTopMargin(10)
           formatm.setLeftMargin(10)
           format.setForeground(QColor(color))
           cursor.setCharFormat(format)
           cursor.setBlockFormat(formatm)  # Fixed the method call
           cursor.insertText(message + "\n")
           self.chat_text_edit.setTextCursor(cursor)


class MessageScreen(QWidget):
   
    def __init__(self, parent=None):
        super().__init__(parent)
        desktop = QApplication.desktop()
        screen_width = desktop.screenGeometry().width()
        screen_height = desktop.screenGeometry().height()
        layout = QVBoxLayout()
        label = QLabel("")
        layout.addWidget(label)
        chat_section = ChatSection()
        layout.addWidget(chat_section)
        self.setLayout(layout)
        self.setFixedHeight(screen_height)
        self.setFixedWidth(screen_width)

    def paintEvent(self, event):
        _paint_workspace_background(self)
        super().paintEvent(event)


class OrbMapCanvas(QWidget):
     def __init__(self, parent=None):
          super().__init__(parent)
          self.conversations = []
          self.rotation = 0.0
          self.vertical_rotation = 0.0
          self.float_time = 0.0
          self.float_phases = {}
          self.is_responding = False
          self.speech_level = 0.0
          self.zoom = 1.0
          self.drag_start = None
          self.last_drag_pos = None
          self.on_select = None
          self.setMinimumSize(500, 360)
          self.setMouseTracking(True)

     def set_conversations(self, conversations):
          self.conversations = conversations
          for conversation in conversations:
               path = conversation["path"]
               if path not in self.float_phases:
                    self.float_phases[path] = len(self.float_phases) * 2.399963
          self.update()

     def set_responding(self, is_responding):
          if self.is_responding != is_responding:
               self.is_responding = is_responding
               self.update()

     def set_speech_level(self, level):
          level = min(1.0, max(0.0, float(level)))
          if abs(self.speech_level - level) >= 0.04:
               self.speech_level = level
               self.update()

     def _node_positions(self):
          width = self.width()
          height = self.height()
          center_x = width / 2
          center_y = height / 2
          base_radius = min(width * 0.31, height * 0.34) * self.zoom
          positions = []
          count = len(self.conversations)
          for index, conversation in enumerate(self.conversations):
               angle = self.rotation + (2 * math.pi * index / max(count, 1))
               orbit = base_radius * (0.72 + (index % 3) * 0.15)
               phase = self.float_phases.get(conversation["path"], index * 2.399963)
               drift_x = (
                    math.sin(self.float_time * 0.72 + phase) * 24
                    + math.sin(self.float_time * 0.37 + phase * 1.7) * 9
               )
               drift_y = (
                    math.cos(self.float_time * 0.61 + phase * 1.3) * 18
                    + math.cos(self.float_time * 0.29 + phase * 0.6) * 7
               )
               orbit_x = math.cos(angle) * orbit
               orbit_y = math.sin(angle) * orbit * 0.58
               orbit_z = math.cos(angle) * orbit * 0.42
               tilt_cos = math.cos(self.vertical_rotation)
               tilt_sin = math.sin(self.vertical_rotation)
               rotated_y = orbit_y * tilt_cos - orbit_z * tilt_sin
               depth = orbit_z * tilt_cos + orbit_y * tilt_sin
               x = center_x + orbit_x + drift_x
               y = center_y + rotated_y + drift_y
               depth_factor = depth / max(orbit, 1)
               radius = 13 + (depth_factor + 1) * 4
               positions.append((conversation, x, y, depth, radius))
          return center_x, center_y, positions

     def paintEvent(self, event):
          _paint_workspace_background(self)
          painter = QPainter(self)
          painter.setRenderHint(QPainter.Antialiasing)
          painter.setRenderHint(QPainter.TextAntialiasing)

          center_x, center_y, positions = self._node_positions()
          core_radius = 48
          painter.setPen(QPen(QColor(48, 204, 226, 85), 1))
          painter.setBrush(Qt.NoBrush)
          painter.drawEllipse(int(center_x - core_radius * 2.5), int(center_y - core_radius * 1.45),
                              int(core_radius * 5), int(core_radius * 2.9))
          painter.setPen(Qt.NoPen)
          for conversation, x, y, depth, radius in positions:
               painter.setPen(QPen(QColor(68, 182, 207, 100 + int((depth + 1) * 45)), 1))
               painter.drawLine(int(center_x), int(center_y), int(x), int(y))

          for index, first in enumerate(positions):
               first_conversation = first[0]
               for second in positions[index + 1:]:
                    shared_topics = first_conversation["keywords"] & second[0]["keywords"]
                    if len(shared_topics) >= 2:
                         painter.setPen(QPen(QColor(138, 91, 220, 95), 1))
                         painter.drawLine(int(first[1]), int(first[2]), int(second[1]), int(second[2]))

          for conversation, x, y, depth, radius in sorted(positions, key=lambda node: node[3]):
               orb_color = ORB_CATEGORIES[conversation["category"]]["color"]
               glow = QRadialGradient(x - radius * 0.3, y - radius * 0.3, radius * 1.8)
               glow.setColorAt(0, orb_color.lighter(190))
               glow.setColorAt(0.35, orb_color)
               glow.setColorAt(1, orb_color.darker(260))
               painter.setBrush(glow)
               painter.setPen(QPen(orb_color.lighter(150), 1))
               painter.drawEllipse(int(x - radius), int(y - radius), int(radius * 2), int(radius * 2))
               painter.setPen(QColor(230, 244, 255, 210))
               painter.drawText(int(x - 80), int(y + radius + 16), 160, 22,
                                Qt.AlignHCenter | Qt.AlignTop, conversation["title"])

          core_glow = QRadialGradient(center_x - 15, center_y - 18, core_radius * 1.8)
          core_glow.setColorAt(0, QColor(232, 255, 255))
          core_glow.setColorAt(0.25, QColor(37, 235, 220))
          core_glow.setColorAt(0.7, QColor(6, 90, 130))
          core_glow.setColorAt(1, QColor(2, 18, 38, 235))
          painter.setBrush(core_glow)
          painter.setPen(QPen(QColor(115, 249, 255), 2))
          painter.drawEllipse(int(center_x - core_radius), int(center_y - core_radius),
                              core_radius * 2, core_radius * 2)
          if self.is_responding:
               pulse = max(0.08, self.speech_level)
               ring_radius = core_radius + 7 + pulse * 12
               ring_color = QColor(64, 154, 255, 55 + int(pulse * 200))
               painter.setBrush(Qt.NoBrush)
               painter.setPen(QPen(ring_color, 1.5 + pulse * 3))
               painter.drawEllipse(
                    int(center_x - ring_radius),
                    int(center_y - ring_radius),
                    int(ring_radius * 2),
                    int(ring_radius * 2),
               )
          painter.setPen(QColor(230, 255, 255))
          painter.drawText(int(center_x - core_radius), int(center_y + core_radius + 9),
                           core_radius * 2, 24, Qt.AlignCenter, "AIKO")

          if not self.conversations:
               painter.setPen(QColor(190, 216, 230))
               painter.drawText(self.rect(), Qt.AlignCenter, "Start a new chat to create your first conversation orb.")

     def mousePressEvent(self, event):
          if event.button() == Qt.LeftButton:
               self.drag_start = event.pos()
               self.last_drag_pos = event.pos()

     def mouseMoveEvent(self, event):
          if self.drag_start is not None:
               delta = event.pos() - self.last_drag_pos
               self.rotation += delta.x() * 0.008
               self.vertical_rotation = min(
                    1.15,
                    max(-1.15, self.vertical_rotation + delta.y() * 0.008),
               )
               self.last_drag_pos = event.pos()
               self.update()

     def mouseReleaseEvent(self, event):
          if self.drag_start is None:
               return
          dragged = (event.pos() - self.drag_start).manhattanLength()
          self.drag_start = None
          self.last_drag_pos = None
          if dragged > 5:
               return
          _, _, positions = self._node_positions()
          for conversation, x, y, _depth, radius in positions:
               if math.hypot(event.pos().x() - x, event.pos().y() - y) <= radius + 8:
                    if self.on_select:
                         self.on_select(conversation)
                    return

     def wheelEvent(self, event):
          direction = 1.1 if event.angleDelta().y() > 0 else 0.9
          self.zoom = min(1.7, max(0.55, self.zoom * direction))
          self.update()
          event.accept()


class ReminderBullet(QWidget):
     def __init__(self, parent=None):
          super().__init__(parent)
          self.rotation = 0
          self.setFixedSize(22, 22)
          self.rotation_timer = QTimer(self)
          self.rotation_timer.timeout.connect(self.rotate_flare)
          self.rotation_timer.start(45)

     def rotate_flare(self):
          self.rotation = (self.rotation + 3) % 360
          self.update()

     def paintEvent(self, event):
          painter = QPainter(self)
          painter.setRenderHint(QPainter.Antialiasing)
          center = self.rect().center()
          painter.translate(center)
          painter.setBrush(Qt.NoBrush)
          for index, tilt in enumerate((0, 60, 120)):
               painter.save()
               painter.rotate(tilt + self.rotation)
               alpha = 220 if index == 0 else 175
               painter.setPen(QPen(QColor(255, 0, 0, alpha), 1.4))
               painter.drawEllipse(-10, -4, 20, 8)
               painter.restore()
          painter.setBrush(QColor("#a6e22e"))
          painter.setPen(QPen(QColor("#d5ff78"), 1))
          painter.drawEllipse(-6, -6, 12, 12)


class ReminderPanel(QFrame):
     def __init__(self, parent=None):
          super().__init__(parent)
          self.setObjectName("reminderPanel")
          self.setFixedSize(240, 320)
          layout = QVBoxLayout(self)
          layout.setContentsMargins(10, 10, 10, 10)
          layout.setSpacing(7)

          heading = QLabel("REMINDERS & EVENTS")
          heading.setStyleSheet(
               "color: #c6ff4d; font-size: 12px; font-weight: bold; "
               "letter-spacing: 1px; border: none;"
          )
          heading.setAlignment(Qt.AlignCenter)
          layout.addWidget(heading)

          self.scroll_area = QScrollArea()
          self.scroll_area.setWidgetResizable(True)
          self.scroll_area.setFrameShape(QFrame.NoFrame)
          self.scroll_area.setStyleSheet(
               "QScrollArea, QWidget#reminderList { background: transparent; border: none; }"
          )
          self.list_widget = QWidget()
          self.list_widget.setObjectName("reminderList")
          self.list_layout = QVBoxLayout(self.list_widget)
          self.list_layout.setContentsMargins(2, 2, 2, 2)
          self.list_layout.setSpacing(8)
          self.list_layout.addStretch(1)
          self.scroll_area.setWidget(self.list_widget)
          layout.addWidget(self.scroll_area, 1)
          self.setStyleSheet("""
               QFrame#reminderPanel {
                    background-color: #000000;
                    border: 2px solid #a6e22e;
                    border-radius: 16px;
               }
          """)

          self.refresh_timer = QTimer(self)
          self.refresh_timer.timeout.connect(self.refresh)
          self.refresh_timer.start(3000)
          self.refresh()

     def refresh(self):
          try:
               reminders = ListReminders()
          except (OSError, RuntimeError, ValueError) as error:
               print(f"[ERROR] Could not load reminders: {error}")
               self._clear_items()
               self._add_empty_message("Could not load reminders.")
               return

          self._clear_items()
          if not reminders:
               self._add_empty_message("No reminders saved yet.")
               return

          for reminder in reminders:
               try:
                    due_at = datetime.fromisoformat(reminder["due_at"])
                    hour = due_at.strftime("%I").lstrip("0") or "12"
                    minute = f":{due_at.minute:02d}" if due_at.minute else ""
                    due_label = f"{hour}{minute}{due_at.strftime('%p').lower()}"
                    title = str(reminder["title"])
               except (KeyError, TypeError, ValueError):
                    print("[ERROR] Skipping a reminder with invalid display data.")
                    continue
               row = QWidget()
               row.setStyleSheet("background:transparent; border:none;")
               row_layout = QHBoxLayout(row)
               row_layout.setContentsMargins(3, 5, 3, 8)
               row_layout.setSpacing(9)
               bullet = ReminderBullet()
               task_label = QLabel(f"{title}: {due_label}")
               task_label.setWordWrap(True)
               task_label.setStyleSheet("color:#ffffff; font-size:12px;")
               row_layout.addWidget(bullet, 0, Qt.AlignTop)
               row_layout.addWidget(task_label, 1)
               self.list_layout.insertWidget(self.list_layout.count() - 1, row)

     def _clear_items(self):
          while self.list_layout.count() > 1:
               item = self.list_layout.takeAt(0)
               widget = item.widget()
               if widget is not None:
                    widget.deleteLater()

     def _add_empty_message(self, message):
          label = QLabel(message)
          label.setWordWrap(True)
          label.setAlignment(Qt.AlignCenter)
          label.setStyleSheet("color:#b6c8aa; background:transparent; border:none;")
          self.list_layout.insertWidget(0, label)


class ConversationMapScreen(QWidget):
     def __init__(self, parent=None):
          super().__init__(parent)
          _ensure_runtime_files()
          layout = QVBoxLayout(self)
          layout.setContentsMargins(28, 16, 28, 24)
          self.heading = QLabel("CONVERSATION MAP")
          self.heading.setStyleSheet("color: #c9fbff; font-size: 22px; font-weight: bold;")
          layout.addWidget(self.heading)
          map_area = QWidget()
          map_layout = QHBoxLayout(map_area)
          map_layout.setContentsMargins(0, 0, 0, 0)
          map_layout.setSpacing(14)
          canvas_area = QWidget()
          canvas_layout = QGridLayout(canvas_area)
          canvas_layout.setContentsMargins(0, 0, 0, 0)
          self.canvas = OrbMapCanvas()
          _image_selection_bridge.speech_level_changed.connect(
               self.canvas.set_speech_level
          )
          canvas_layout.addWidget(self.canvas, 0, 0)
          self.orb_key = self._create_orb_key(canvas_area)
          canvas_layout.addWidget(self.orb_key, 0, 0, Qt.AlignLeft | Qt.AlignTop)
          map_layout.addWidget(canvas_area, 1)
          reminder_column = QWidget(map_area)
          reminder_column.setFixedWidth(250)
          reminder_column_layout = QVBoxLayout(reminder_column)
          reminder_column_layout.setContentsMargins(0, 0, 0, 0)
          reminder_column_layout.addStretch(1)
          self.reminder_panel = ReminderPanel(reminder_column)
          reminder_column_layout.addWidget(self.reminder_panel, 0, Qt.AlignHCenter)
          reminder_column_layout.addStretch(1)
          map_layout.addWidget(reminder_column)
          layout.addWidget(map_area, 1)
          footer = QHBoxLayout()
          self.status_label = QLabel("Available...")
          self.status_label.setStyleSheet("color: #89d9e8; font-size: 15px; padding: 8px;")
          footer.addWidget(self.status_label)
          self.details = QLabel(
               "Drag left/right and up/down to rotate  |  Scroll to zoom  |  "
               "Click an orb to open its chat"
          )
          self.details.setWordWrap(True)
          self.details.setStyleSheet("color: #d1e8f2; font-size: 14px; padding: 8px;")
          footer.addWidget(self.details, 1)
          self.selected_conversation_path = None
          controls = QVBoxLayout()
          controls.setContentsMargins(0, 0, 0, 28)
          controls.setSpacing(8)
          self.new_orb_button = QPushButton("New Orb")
          self.new_orb_button.setFixedSize(112, 42)
          self.new_orb_button.setCursor(Qt.PointingHandCursor)
          self.new_orb_button.setStyleSheet("""
               QPushButton {
                    color: #e6fbff; font-size: 14px;
                    background-color: #123647; border: 1px solid #43b9c9;
                    border-radius: 10px; padding: 8px 12px;
               }
               QPushButton:hover { background-color: #1a5265; }
          """)
          self.new_orb_button.clicked.connect(self.create_conversation_orb)
          controls.addWidget(self.new_orb_button)
          self.delete_orb_button = QPushButton("Delete Orb")
          self.delete_orb_button.setFixedSize(112, 42)
          self.delete_orb_button.setCursor(Qt.PointingHandCursor)
          self.delete_orb_button.setEnabled(False)
          self.delete_orb_button.setStyleSheet("""
               QPushButton {
                    color: #ffe9e9; font-size: 14px;
                    background-color: #4a2028; border: 1px solid #d45b68;
                    border-radius: 10px; padding: 8px 12px;
               }
               QPushButton:hover { background-color: #71303a; }
               QPushButton:disabled {
                    color: #8c777a; background-color: #241a1c;
                    border-color: #554448;
               }
          """)
          self.delete_orb_button.clicked.connect(self.delete_conversation_orb)
          controls.addWidget(self.delete_orb_button)
          self.mic_button = QPushButton()
          self.mic_button.setFixedSize(112, 64)
          self.mic_button.setCursor(Qt.PointingHandCursor)
          self.mic_movie = QMovie(GraphicsDirectoryPath("Mic_on.gif"))
          self.mic_movie.setScaledSize(QSize(64, 64))
          self.mic_movie.frameChanged.connect(self.update_mic_icon)
          self.mic_button.clicked.connect(self.toggle_microphone)
          controls.addWidget(self.mic_button)
          self.input_device_combo = QComboBox()
          self.input_device_combo.setFixedWidth(220)
          self.input_device_combo.setToolTip("Choose the microphone AIKO will capture audio from.")
          self.input_device_combo.setStyleSheet("""
               QComboBox {
                    color: white; background-color: #101c28;
                    border: 1px solid #43b9c9; border-radius: 6px;
                    padding: 6px;
               }
               QComboBox QAbstractItemView {
                    color: white; background-color: #101c28;
                    selection-background-color: #1a5265;
               }
          """)
          devices, default_device = GetMicrophoneDevices()
          selected_device = None
          device_path = TempDirectoryPath("MicDevice.data")
          if os.path.exists(device_path):
               try:
                    with open(device_path, "r", encoding="utf-8") as file:
                         selected_device = int(file.read().strip())
               except ValueError:
                    selected_device = None
          for index, name in devices:
               self.input_device_combo.addItem(f"{name} (device {index})", index)
          selected_row = self.input_device_combo.findData(
               selected_device if selected_device is not None else default_device
          )
          if selected_row < 0 and self.input_device_combo.count():
               selected_row = 0
          if selected_row >= 0:
               self.input_device_combo.setCurrentIndex(selected_row)
               SetMicrophoneDevice(self.input_device_combo.currentData())
          self.input_device_combo.currentIndexChanged.connect(self.select_microphone_device)
          controls.addWidget(self.input_device_combo)
          footer.addLayout(controls)
          layout.addLayout(footer)
          self.canvas.on_select = self.show_conversation
          self.on_select_conversation = None
          self.refresh_timer = QTimer(self)
          self.refresh_timer.timeout.connect(self.refresh_conversations)
          self.refresh_timer.start(2000)
          self.rotation_timer = QTimer(self)
          self.rotation_timer.timeout.connect(self.rotate_map)
          self.rotation_timer.start(40)
          self.status_timer = QTimer(self)
          self.status_timer.timeout.connect(self.refresh_status)
          self.status_timer.start(50)
          self.refresh_conversations()
          self.refresh_status()
          self.setAttribute(Qt.WA_StyledBackground, False)

     def paintEvent(self, event):
          _paint_workspace_background(self)
          super().paintEvent(event)

     def _create_orb_key(self, parent):
          key = QFrame(parent)
          key.setFixedWidth(226)
          key.setStyleSheet("""
               QFrame#orbKey {
                    background: transparent;
                    border: none;
               }
               QLabel { color: #e2f3f8; border: none; }
          """)
          key.setObjectName("orbKey")
          key_layout = QVBoxLayout(key)
          key_layout.setContentsMargins(12, 9, 12, 9)
          key_layout.setSpacing(5)
          title = QLabel("ORB KEY")
          title.setStyleSheet("font-size: 12px; font-weight: bold; color: #c9fbff;")
          key_layout.addWidget(title)
          for category in ("conversation", "search", "design", "schedule", "relationship"):
               row = QHBoxLayout()
               row.setSpacing(9)
               color = ORB_CATEGORIES[category]["color"]
               orb = QLabel()
               orb.setFixedSize(13, 13)
               orb.setStyleSheet(
                    f"background-color: {color.name()}; border: 1px solid rgba(255,255,255,180); "
                    "border-radius: 6px;"
               )
               label = QLabel(ORB_CATEGORIES[category]["label"])
               label.setStyleSheet("font-size: 12px;")
               row.addWidget(orb)
               row.addWidget(label, 1)
               key_layout.addLayout(row)
          return key

     def refresh_conversations(self):
          try:
               conversations = _load_conversations()
               self.canvas.set_conversations(conversations)
               if self.selected_conversation_path and not any(
                    item["path"] == self.selected_conversation_path for item in conversations
               ):
                    self.selected_conversation_path = None
                    self.delete_orb_button.setEnabled(False)
          except (OSError, ValueError, json.JSONDecodeError) as error:
               print(f"[ERROR] Could not load conversation map: {error}")
               self.details.setText(f"Could not load conversation history: {error}")

     def rotate_map(self):
          self.canvas.rotation += 0.003
          self.canvas.float_time += 0.04
          self.canvas.update()

     def show_conversation(self, conversation):
          self.selected_conversation_path = conversation["path"]
          self.delete_orb_button.setEnabled(True)
          self.details.setText(
               f"{conversation['title']}  |  {ORB_CATEGORIES[conversation['category']]['label']}  |  "
               f"{conversation['message_count']} messages\n"
               f"Latest user message: {conversation['summary']}"
          )
          if self.on_select_conversation:
               self.on_select_conversation(conversation)

     def delete_conversation_orb(self):
          if GetMicrophoneStatus().strip() == "True":
               QMessageBox.warning(
                    self,
                    "Turn off microphone",
                    "Turn off the microphone before deleting a conversation.",
               )
               return
          assistant_status = GetAssistantStatus().strip()
          if assistant_status not in {"Available...", "Listening..."}:
               QMessageBox.warning(
                    self,
                    "Assistant is busy",
                    "Wait for AIKO to finish its current response before deleting a conversation.",
               )
               return
          if not self.selected_conversation_path:
               return
          conversation_path = self.selected_conversation_path
          conversation = next(
               (item for item in self.canvas.conversations if item["path"] == conversation_path),
               None,
          )
          title = conversation["title"] if conversation else os.path.basename(conversation_path)
          confirmation = QMessageBox.question(
               self,
               "Delete conversation?",
               f"Delete '{title}' and its chat history? This cannot be undone.",
               QMessageBox.Yes | QMessageBox.No,
               QMessageBox.No,
          )
          if confirmation != QMessageBox.Yes:
               return
          try:
               DeleteConversationOrb(conversation_path)
          except (OSError, ValueError) as error:
               QMessageBox.critical(self, "Could not delete conversation", str(error))
               return
          self.selected_conversation_path = None
          self.delete_orb_button.setEnabled(False)
          self.refresh_conversations()
          self.details.setText("Conversation orb and its chat history deleted.")

     def refresh_status(self):
          listening = GetMicrophoneStatus().strip() == "True"
          self.input_device_combo.setEnabled(not listening)
          with open(TempDirectoryPath("Status.data"), "r", encoding="utf-8") as file:
               assistant_status = file.read().strip()
          self.status_label.setText(assistant_status)
          self.canvas.set_responding(assistant_status == "Answering...")
          self.mic_button.setText("" if listening else "MIC OFF")
          if listening:
               if self.mic_movie.state() != QMovie.Running:
                    self.mic_movie.start()
               self.update_mic_icon()
               self.mic_button.setStyleSheet("QPushButton { background: transparent; border: none; }")
          else:
               self.mic_movie.stop()
               self.mic_button.setIcon(QIcon())
               self.mic_button.setStyleSheet("""
                    QPushButton {
                         color: white; font-size: 13px;
                         background-color: rgba(0, 0, 0, 180);
                         border: 2px solid #777; border-radius: 12px;
                    }
                    QPushButton:hover { border-color: white; }
               """)

     def update_mic_icon(self, _frame=None):
          if GetMicrophoneStatus().strip() == "True":
               pixmap = self.mic_movie.currentPixmap()
               if not pixmap.isNull():
                    self.mic_button.setIcon(QIcon(pixmap))
                    self.mic_button.setIconSize(QSize(64, 64))

     def toggle_microphone(self):
          if GetMicrophoneStatus().strip() == "True":
               MicButtonClosed()
               SetAssistantStatus("Available...")
          else:
               MicButtonInitialed()
               SetAssistantStatus("Listening...")
          self.refresh_status()

     def select_microphone_device(self, index):
          if GetMicrophoneStatus().strip() == "True":
               return
          device_index = self.input_device_combo.itemData(index)
          if device_index is not None:
               SetMicrophoneDevice(device_index)

     def create_conversation_orb(self):
          self.selected_conversation_path = CreateConversationOrb()
          self.delete_orb_button.setEnabled(True)
          self.refresh_conversations()
          self.details.setText("New conversation orb created. It has its own chatlog.")


class CustomTopBar(QWidget):


     def __init__(self, parent, stacked_widget):
         super().__init__(parent)
         self.initUI()
         self.stacked_widget = stacked_widget


     def initUI(self):
           self.setFixedHeight(50)
           layout = QHBoxLayout(self)
           layout.setAlignment(Qt.AlignRight)
           map_button = QPushButton("Map")
           map_button.setStyleSheet("height:40px; line-height:40px; background-color: white; color: black;")
           message_button = QPushButton()
           message_icon = QIcon(GraphicsDirectoryPath("chats.png"))
           message_button.setIcon(message_icon)
           message_button.setText(" Chat")
           message_button.setStyleSheet("height:40px; line-height:40px ; background-color: white; color: black;")
           minimize_button = QPushButton()
           minimize_icon = QIcon(GraphicsDirectoryPath("minimize.png"))
           minimize_button.setIcon(minimize_icon)
           minimize_button.setStyleSheet("background-color:white;")
           minimize_button.clicked.connect(self.minimizeWindow)
           self.maximize_button = QPushButton()
           self.maximize_icon = QIcon(GraphicsDirectoryPath("maximize.png"))
           self.restore_icon = QIcon(GraphicsDirectoryPath("minimize.png"))
           self.maximize_button.setIcon(self.maximize_icon)
           self.maximize_button.setFlat(True)
           self.maximize_button.setStyleSheet("background-color:white;")
           self.maximize_button.clicked.connect(self.maximizeWindow)
           close_button = QPushButton()
           close_icon = QIcon(GraphicsDirectoryPath("close.png"))
           close_button.setIcon(close_icon)
           close_button.setStyleSheet("background-color:white;")
           close_button.clicked.connect(self.closeWindow)
           title_label = QLabel(f"{str(Assistantname)} AI   ")
           title_label.setStyleSheet("color: black; font-size: 18px; background-color: white;")
           map_button.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
           message_button.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
           layout.addWidget(title_label)
           layout.addStretch(1)
           layout.addWidget(map_button)
           layout.addWidget(message_button)
           layout.addStretch(1)
           layout.addWidget(minimize_button)
           layout.addWidget(self.maximize_button)
           layout.addWidget(close_button)
           self.draggable = True
           self.offset = None

     def paintEvent(self, event):
           painter = QPainter(self)
           painter.fillRect(self.rect(), Qt.white)
           super().paintEvent(event)


     def minimizeWindow(self):
           self.window().showMinimized()


     def maximizeWindow(self):
           if self.window().isMaximized():
               self.window().showNormal()
               self.maximize_button.setIcon(self.maximize_icon)
           else:
               self.window().showMaximized()
               self.maximize_button.setIcon(self.restore_icon)


     def closeWindow(self):
           self.window().close()


     def mousePressEvent(self, event):
          if self.draggable:
               self.offset = event.pos()


     def mouseMoveEvent(self, event):
          if self.draggable and self.offset:
               new_pos = event.globalPos() - self.offset
               self.window().move(new_pos)


class MainWindow(QMainWindow):
     def __init__(self):
          super().__init__()
          self.setWindowFlags(Qt.FramelessWindowHint)
          self.initUI()


     def initUI(self):
          _ensure_runtime_files()
          desktop = QApplication.desktop()
          screen_width = desktop.screenGeometry().width()
          screen_height = desktop.screenGeometry().height()
          stacked_widget = QStackedWidget(self)
          message_screen = MessageScreen()
          conversation_map_screen = ConversationMapScreen()
          stacked_widget.addWidget(conversation_map_screen)
          stacked_widget.addWidget(message_screen)
          conversation_map_screen.on_select_conversation = self.open_conversation
          conversations = _load_conversations()
          if conversations:
               ActivateConversation(GetActiveChatLogPath())
          self.setGeometry(0, 0, screen_width, screen_height)
          self.setStyleSheet("QMainWindow { background: transparent; }")
          top_bar = CustomTopBar(self, stacked_widget)
          self.setMenuWidget(top_bar)
          self.setCentralWidget(stacked_widget)

     def open_conversation(self, conversation):
          ActivateConversation(conversation["path"])
          self.centralWidget().setCurrentIndex(1)


def GraphicalUserInterface():
    _ensure_runtime_files()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
     GraphicalUserInterface()
