import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
     sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QStackedWidget, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QLabel, QSizePolicy, QMessageBox, QDialog, QComboBox, QScrollArea, QFileDialog, QInputDialog, QListWidget, QListWidgetItem, QListView, QAbstractItemView, QStyle
from PyQt5.QtGui import QIcon, QPainter, QMovie, QColor, QTextCharFormat, QFont, QTextBlockFormat, QRadialGradient, QPen, QPixmap, QMouseEvent, QPainterPath
from PyQt5.QtCore import Qt, QSize, QTimer, QObject, pyqtSignal, QPoint, QPointF, QEvent, QUrl, QRunnable, QThreadPool
from backend.HandTracking import (
     HandTrackingWorker,
     adjust_system_volume,
     volume_action_for_motion,
     zoom_openness_for_hand,
     zoom_openness_for_two_hands,
)
from backend.SoundTrigger import DoubleSoundTriggerWorker
from backend.Reminders import ListReminders
from backend import Workspace as WorkspaceFiles
from PyQt5.QtGui import QDesktopServices
from dotenv import dotenv_values
import json
import ctypes
import math
import re
import os
import time
try:
    import pyaudio
    HAS_AUDIO = True
except ImportError:
    pyaudio = None
    HAS_AUDIO = False
    print("PyAudio not available (running in cloud/headless mode)")
from datetime import datetime
from threading import Event, Lock


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


def _paint_aiko_core(painter, center_x, center_y, core_radius, is_responding, speech_level):
     core_glow = QRadialGradient(
          center_x - core_radius * 0.31,
          center_y - core_radius * 0.37,
          core_radius * 1.8,
     )
     core_glow.setColorAt(0, QColor(232, 255, 255))
     core_glow.setColorAt(0.25, QColor(37, 235, 220))
     core_glow.setColorAt(0.7, QColor(6, 90, 130))
     core_glow.setColorAt(1, QColor(2, 18, 38, 235))
     painter.setBrush(core_glow)
     painter.setPen(QPen(QColor(115, 249, 255), 2))
     painter.drawEllipse(
          int(center_x - core_radius),
          int(center_y - core_radius),
          core_radius * 2,
          core_radius * 2,
     )
     if is_responding:
          pulse = max(0.08, speech_level)
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
     painter.drawText(
          int(center_x - core_radius),
          int(center_y + core_radius + 9),
          core_radius * 2,
          24,
          Qt.AlignCenter,
          "AIKO",
     )


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


def ShowReminderNotification(reminder):
     global _pending_reminder_notification
     with _notification_state_lock:
          if _notification_bridge_ready:
               _image_selection_bridge.reminder_notification_requested.emit(reminder)
          else:
               _pending_reminder_notification = reminder


def AcknowledgeReminderNotification(reminder_id):
     global _pending_reminder_notification
     with _notification_state_lock:
          if (
               _pending_reminder_notification is not None
               and str(_pending_reminder_notification.get("id")) == reminder_id
          ):
               _pending_reminder_notification = None
          if _notification_bridge_ready:
               _image_selection_bridge.reminder_acknowledged.emit(reminder_id)


def UpdateBreakingNews(stories, error=""):
     global _pending_news_update
     with _notification_state_lock:
          _pending_news_update = (stories, error)
     _image_selection_bridge.breaking_news_updated.emit((stories, error))


class ImageSelectionBridge(QObject):
     selection_requested = pyqtSignal(object)
     image_description_requested = pyqtSignal(object)
     speech_level_changed = pyqtSignal(float)
     workspace_open_requested = pyqtSignal()
     workspace_refresh_requested = pyqtSignal()
     workspace_command_requested = pyqtSignal(object)
     reminder_notification_requested = pyqtSignal(object)
     reminder_acknowledged = pyqtSignal(str)
     breaking_news_updated = pyqtSignal(object)


_image_selection_bridge = ImageSelectionBridge()
_image_selection_bridge_connected = False
_workspace_bridge_connected = False
_notification_state_lock = Lock()
_notification_bridge_ready = False
_pending_reminder_notification = None
_pending_news_update = ([], "")
_HAND_PINCH_THRESHOLD = 0.18
_HAND_PINCH_RELEASE_THRESHOLD = 0.25
_HAND_CLICK_MAX_MOVEMENT = 12
_HAND_ZOOM_IN_THRESHOLD = 0.55
_HAND_DOUBLE_PINCH_WINDOW = 0.55
_HAND_DOUBLE_PINCH_MAX_DISTANCE = 48
_HAND_GRAB_HOLD_SECONDS = 0.28


def OpenWorkspace():
     if not _workspace_bridge_connected:
          raise RuntimeError("The AIKO workspace window is not available.")
     _image_selection_bridge.workspace_refresh_requested.emit()
     _image_selection_bridge.workspace_open_requested.emit()


def ControlWorkspace(action, payload=""):
     if not _workspace_bridge_connected:
          raise RuntimeError("The AIKO workspace window is not available.")
     request = {
          "action": action,
          "payload": payload,
          "completed": Event(),
     }
     _image_selection_bridge.workspace_command_requested.emit(request)
     if not request["completed"].wait(30):
          raise TimeoutError("The workspace did not respond to the voice command.")
     if "error" in request:
          raise RuntimeError(request["error"])
     return request.get("result")


def GetWorkspaceContext():
     if not _workspace_bridge_connected:
          return None
     return ControlWorkspace("describe")


def _hand_click_is_valid(moved, fist_seen):
     return not moved and not fist_seen


def _send_hand_mouse_event(widget, event_type, position, button, buttons):
     local_position = QPointF(position)
     window_position = QPointF(widget.mapTo(widget.window(), position))
     screen_position = QPointF(widget.mapToGlobal(position))
     event = QMouseEvent(
          event_type,
          local_position,
          window_position,
          screen_position,
          button,
          buttons,
          Qt.NoModifier,
     )
     QApplication.sendEvent(widget, event)


def _send_global_hand_mouse_event(event_type, position):
     if os.name != "nt":
          raise RuntimeError("Hand control outside AIKO is available only on Windows.")

     user32 = ctypes.WinDLL("user32", use_last_error=True)
     user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
     user32.SetCursorPos.restype = ctypes.c_int
     if not user32.SetCursorPos(position.x(), position.y()):
          error = ctypes.get_last_error()
          raise OSError(error, "Windows could not move the hand pointer.")
     user32.mouse_event.argtypes = [
          ctypes.c_ulong,
          ctypes.c_ulong,
          ctypes.c_ulong,
          ctypes.c_ulong,
          ctypes.c_size_t,
     ]
     user32.mouse_event.restype = None

     mouse_flags = {
          QEvent.MouseButtonPress: 0x0002,
          QEvent.MouseButtonRelease: 0x0004,
     }
     flags = mouse_flags.get(event_type)
     if flags is not None:
          user32.mouse_event(flags, 0, 0, 0, 0)


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


def GetSelectedGeneratedImage(timeout=8):
     if not _image_selection_bridge_connected:
          raise RuntimeError(
               "Choose an image option first. Choosing it keeps that image and deletes the other two."
          )
     request = {
          "event": Event(),
          "success": False,
          "message": "",
          "image_path": "",
          "image_prompt": "",
     }
     _image_selection_bridge.image_description_requested.emit(request)
     if not request["event"].wait(timeout):
          raise RuntimeError("AIKO timed out while checking the selected image.")
     if not request["success"]:
          raise RuntimeError(
               request["message"]
               or "Choose an image option before asking me to describe it."
          )
     return request["image_path"], request["image_prompt"]


def MicButtonInitialed():
    SetMicrophoneStatus("True")


def MicButtonClosed():
    SetMicrophoneStatus("False")


def GetMicrophoneDevices():
     if not HAS_AUDIO:
          return [], None
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
            self.latest_selected_image_path = None
            self.latest_selected_image_prompt = ""
            global _image_selection_bridge_connected
            _image_selection_bridge.selection_requested.connect(
                self.select_generated_image_by_option
            )
            _image_selection_bridge.image_description_requested.connect(
                self.get_selected_image_for_description
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
               self.latest_selected_image_path = None
               self.latest_selected_image_prompt = ""
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
                           lambda selected_path, options=gallery_paths, source_prompt=prompt: (
                               self.choose_generated_image(
                                   selected_path,
                                   options,
                                   image_prompt=source_prompt,
                               )
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
                       "prompt": prompt,
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
                   selected_path,
                   gallery["paths"],
                   show_errors=False,
                   image_prompt=gallery.get("prompt", ""),
               )
               request["success"] = success
               request["message"] = message
           except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
               request["success"] = False
               request["message"] = str(error)
           finally:
               request["event"].set()

       def get_selected_image_for_description(self, request):
           try:
               image_path = self.latest_selected_image_path
               if not image_path:
                   raise RuntimeError(
                       "Choose one of the generated image options first. "
                       "Choosing it keeps that image and deletes the other two."
                   )
               if not os.path.isfile(image_path):
                   self.latest_selected_image_path = None
                   raise RuntimeError(
                       "The selected generated image is no longer available. "
                       "Generate another image and choose an option first."
                   )
               request["image_path"] = image_path
               request["image_prompt"] = self.latest_selected_image_prompt
               request["success"] = True
           except (KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
               request["success"] = False
               request["message"] = str(error)
           finally:
               request["event"].set()

       def choose_generated_image(
           self,
           image_path,
           gallery_paths,
           show_errors=True,
           image_prompt="",
       ):
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
           self.latest_selected_image_path = selected_path
           self.latest_selected_image_prompt = str(image_prompt)
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
          self.hand_cursor = None
          self.hand_cursors = []
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

     def set_hand_zoom(self, zoom_openness):
          target_zoom = 0.65 + min(1.0, max(0.0, zoom_openness)) * 1.05
          self.zoom += (target_zoom - self.zoom) * 0.05625
          self.update()

     def apply_hand_drag(self, delta_x, delta_y):
          self.rotation += delta_x * self.width() * 0.004
          self.vertical_rotation += delta_y * self.height() * 0.004
          self.update()

     def set_hand_cursor(self, position):
          self.hand_cursor = position
          self.hand_cursors = [] if position is None else [position]
          self.update()

     def set_hand_cursors(self, positions):
          self.hand_cursors = list(positions)
          self.hand_cursor = self.hand_cursors[0] if self.hand_cursors else None
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

          _paint_aiko_core(
               painter,
               center_x,
               center_y,
               core_radius,
               self.is_responding,
               self.speech_level,
          )

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
               self.rotation += delta.x() * 0.004
               self.vertical_rotation += delta.y() * 0.004
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


class HandCursorOverlay(QWidget):
     def __init__(self, parent=None):
          super().__init__(parent)
          self.positions = []
          self.setWindowFlags(
               Qt.Tool
               | Qt.FramelessWindowHint
               | Qt.WindowStaysOnTopHint
               | Qt.WindowDoesNotAcceptFocus
          )
          self.setAttribute(Qt.WA_TransparentForMouseEvents)
          self.setAttribute(Qt.WA_ShowWithoutActivating)
          self.setAttribute(Qt.WA_TranslucentBackground)
          self.setGeometry(QApplication.desktop().screenGeometry())

     def set_positions(self, positions):
          self.positions = list(positions)
          self.update()

     def paintEvent(self, event):
          painter = QPainter(self)
          painter.setRenderHint(QPainter.Antialiasing)
          for index, position in enumerate(self.positions):
               local_position = self.mapFromGlobal(position)
               painter.setBrush(QColor(100, 243, 255, 75))
               color = QColor(155, 250, 255) if index == 0 else QColor(255, 220, 100)
               painter.setPen(QPen(color, 2))
               painter.drawEllipse(local_position, 11, 11)


class ReminderBullet(QWidget):
     def __init__(self, parent=None):
          super().__init__(parent)
          self.rotation = 0
          self.setFixedSize(22, 22)
          self.rotation_timer = QTimer(self)
          self.rotation_timer.timeout.connect(self.rotate_flare)
          self.rotation_timer.setInterval(80)

     def showEvent(self, event):
          super().showEvent(event)
          self.rotation_timer.start()

     def hideEvent(self, event):
          self.rotation_timer.stop()
          super().hideEvent(event)

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
          self.refresh_timer.setInterval(5000)
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


class BreakingNewsPanel(QFrame):
     def __init__(self, parent=None):
          super().__init__(parent)
          self.setObjectName("breakingNewsPanel")
          self.setMaximumHeight(116)
          layout = QVBoxLayout(self)
          layout.setContentsMargins(12, 8, 12, 8)
          layout.setSpacing(5)
          heading = QLabel("MAJOR BREAKING NEWS")
          heading.setStyleSheet(
               "color: #ff657a; font-size: 11px; font-weight: bold; "
               "letter-spacing: 1px; border: none;"
          )
          layout.addWidget(heading)
          self.headlines = QLabel("Checking for major breaking news...")
          self.headlines.setWordWrap(True)
          self.headlines.setStyleSheet(
               "color: #e8f4ff; font-size: 12px; border: none;"
          )
          layout.addWidget(self.headlines)
          with _notification_state_lock:
               cached_news = _pending_news_update
          self.set_stories(*cached_news)
          self.setStyleSheet("""
               QFrame#breakingNewsPanel {
                    background-color: #101827;
                    border: 1px solid #526b91;
                    border-radius: 12px;
               }
          """)

     def set_stories(self, stories, error=""):
          if error:
               self.headlines.setText("Breaking news feed is temporarily unavailable.")
          elif not stories:
               self.headlines.setText("No major breaking headlines right now.")
          else:
               self.headlines.setText(
                    "\n".join(f"• {story['title']}" for story in stories[:3])
               )


class ReminderNotification(QDialog):
     def __init__(self, reminder, parent=None):
          super().__init__(parent)
          self.reminder_id = str(reminder["id"])
          self.setWindowTitle("AIKO Reminder")
          self.setWindowFlags(
               Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
          )
          self.setModal(False)
          self.setFixedWidth(460)
          self._drag_offset = None
          self.setMouseTracking(True)
          layout = QVBoxLayout(self)
          layout.setContentsMargins(24, 20, 24, 20)
          layout.setSpacing(12)
          heading = QLabel("REMINDER")
          heading.setAlignment(Qt.AlignCenter)
          heading.setAttribute(Qt.WA_TransparentForMouseEvents)
          heading.setStyleSheet(
               "color: #c6ff4d; font-size: 15px; font-weight: bold; "
               "letter-spacing: 2px; border: none;"
          )
          title = QLabel(str(reminder.get("title", "Reminder")))
          title.setAlignment(Qt.AlignCenter)
          title.setAttribute(Qt.WA_TransparentForMouseEvents)
          title.setWordWrap(True)
          title.setStyleSheet(
               "color: #e6fbff; font-size: 22px; font-weight: bold; "
               "border: none;"
          )
          instruction = QLabel(
               "Say “OK”, “thank you”, “will do”, or “thanks” to acknowledge "
               "and clear this reminder."
          )
          instruction.setAlignment(Qt.AlignCenter)
          instruction.setAttribute(Qt.WA_TransparentForMouseEvents)
          instruction.setWordWrap(True)
          instruction.setStyleSheet("color: #b6c8aa; font-size: 13px; border: none;")
          layout.addWidget(heading)
          layout.addWidget(title)
          layout.addWidget(instruction)
          self.setStyleSheet("""
               QDialog {
                    background-color: #000000;
                    border: 2px solid #a6e22e;
                    border-radius: 16px;
               }
          """)

     def mousePressEvent(self, event):
          if event.button() == Qt.LeftButton:
               self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
               event.accept()
               return
          super().mousePressEvent(event)

     def mouseMoveEvent(self, event):
          if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
               self.move(event.globalPos() - self._drag_offset)
               event.accept()
               return
          super().mouseMoveEvent(event)

     def mouseReleaseEvent(self, event):
          if event.button() == Qt.LeftButton:
               self._drag_offset = None
               event.accept()
               return
          super().mouseReleaseEvent(event)

     def show_centered(self):
          self.show()
          screen = QApplication.desktop().screenGeometry(self.parentWidget())
          self.move(
               screen.center().x() - self.width() // 2,
               screen.center().y() - self.height() // 2,
          )
          self.raise_()
          self.activateWindow()


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
          map_column = QWidget(map_area)
          map_column_layout = QVBoxLayout(map_column)
          map_column_layout.setContentsMargins(0, 0, 0, 0)
          map_column_layout.setSpacing(10)
          self.news_panel = BreakingNewsPanel(map_column)
          _image_selection_bridge.breaking_news_updated.connect(
               lambda update: self.news_panel.set_stories(*update)
          )
          map_column_layout.addWidget(canvas_area, 1)
          map_column_layout.addWidget(self.news_panel)
          map_layout.addWidget(map_column, 1)
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
               "Double-pinch to click; pinch and hold/drag to grab. One hand: "
               "spread thumb/index to zoom in or close fist to zoom out. "
               "Two hands: move apart to zoom in and together to zoom out."
          )
          self.details.setWordWrap(True)
          self.details.setStyleSheet("color: #d1e8f2; font-size: 14px; padding: 8px;")
          footer.addWidget(self.details, 1)
          self.selected_conversation_path = None
          controls = QVBoxLayout()
          controls.setContentsMargins(0, 0, 0, 28)
          controls.setSpacing(8)
          self.hand_tracking_worker = None
          self.double_sound_trigger_worker = None
          self._hand_gesture_states = {}
          self._pending_hand_clicks = {}
          self.hand_cursor_overlay = None
          self._two_hand_drag_position = None
          self._volume_hand_y = None
          self._volume_palm_facing = None
          self._volume_motion = 0.0
          self._two_hand_depth_position = None
          self._next_volume_step = 0.0
          self._volume_error_reported = False
          self.hand_tracking_button = QPushButton("Start Hands")
          self.hand_tracking_button.setFixedSize(112, 42)
          self.hand_tracking_button.setCursor(Qt.PointingHandCursor)
          self.hand_tracking_button.setToolTip(
               "Start local hand tracking. Camera frames are not saved or uploaded."
          )
          self.hand_tracking_button.setStyleSheet("""
               QPushButton {
                    color: #e6fbff; font-size: 13px;
                    background-color: #123647; border: 1px solid #43b9c9;
                    border-radius: 10px; padding: 8px;
               }
               QPushButton:hover { background-color: #1a5265; }
          """)
          self.hand_tracking_button.clicked.connect(self.toggle_hand_tracking)
          controls.addWidget(self.hand_tracking_button)
          self.hand_tracking_status = QLabel("Hand tracking is off.")
          self.hand_tracking_status.setWordWrap(True)
          self.hand_tracking_status.setStyleSheet(
               "color: #89d9e8; font-size: 11px; max-width: 220px;"
          )
          controls.addWidget(self.hand_tracking_status)
          self.double_sound_trigger_status = QLabel(
               "Starting local clap/snap listening..."
          )
          self.double_sound_trigger_status.setWordWrap(True)
          self.double_sound_trigger_status.setStyleSheet(
               "color: #89d9e8; font-size: 11px; max-width: 220px;"
          )
          controls.addWidget(self.double_sound_trigger_status)
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
          self.refresh_timer.setInterval(5000)
          self.rotation_timer = QTimer(self)
          self.rotation_timer.timeout.connect(self.rotate_map)
          self.rotation_timer.setInterval(80)
          self.status_timer = QTimer(self)
          self.status_timer.timeout.connect(self.refresh_status)
          self.status_timer.setInterval(250)
          self.refresh_conversations()
          self.refresh_status()
          self.setAttribute(Qt.WA_StyledBackground, False)

     def showEvent(self, event):
          super().showEvent(event)
          self.refresh_timer.start()
          self.rotation_timer.start()
          self.status_timer.start()
          self.reminder_panel.refresh_timer.start()

     def hideEvent(self, event):
          self.refresh_timer.stop()
          self.rotation_timer.stop()
          self.status_timer.stop()
          self.reminder_panel.refresh_timer.stop()
          super().hideEvent(event)

     def start_double_sound_trigger(self):
          worker = self.double_sound_trigger_worker
          if worker is not None and worker.isRunning():
               worker.requestInterruption()
               if worker.wait(2500):
                    self._double_sound_trigger_finished(worker)
               else:
                    self.double_sound_trigger_status.setText(
                         "The previous microphone stream is still closing; "
                         "sound listening could not restart."
                    )
               return

          device_index = None
          try:
               with open(
                    TempDirectoryPath("MicDevice.data"),
                    "r",
                    encoding="utf-8",
               ) as device_file:
                    selected_device = device_file.read().strip()
               if selected_device:
                    device_index = int(selected_device)
          except FileNotFoundError:
               pass
          except ValueError:
               self.double_sound_trigger_status.setText(
                    "The selected microphone is invalid. Choose it again in settings."
               )
               return

          worker = DoubleSoundTriggerWorker(device_index, self)
          self.double_sound_trigger_worker = worker
          worker.double_sound_detected.connect(self._on_double_sound_detected)
          worker.listening_error.connect(self._on_double_sound_trigger_error)
          worker.finished.connect(
               lambda current_worker=worker: self._double_sound_trigger_finished(
                    current_worker
               )
          )
          self.double_sound_trigger_status.setText(
               "Always listening locally for two sharp sounds to start hand tracking."
          )
          worker.start()

     def _on_double_sound_detected(self):
          worker = self.hand_tracking_worker
          if worker is None or not worker.isRunning():
               self.double_sound_trigger_status.setText(
                    "Double sound detected; starting hand tracking..."
               )
               self.toggle_hand_tracking()

     def _on_double_sound_trigger_error(self, message):
          self.double_sound_trigger_status.setText(message)

     def _double_sound_trigger_finished(self, worker):
          if self.double_sound_trigger_worker is not worker:
               return
          self.double_sound_trigger_worker = None
          if not self.double_sound_trigger_status.text().startswith(
               "Sound trigger stopped:"
          ) and not self.double_sound_trigger_status.text().startswith(
               "The selected microphone is invalid."
          ):
               self.double_sound_trigger_status.setText(
                    "Sound trigger stopped. Restart AIKO to resume listening."
               )

     def toggle_hand_tracking(self):
          worker = self.hand_tracking_worker
          if worker is not None and worker.isRunning():
               self.hand_tracking_status.setText("Stopping hand tracking...")
               self._cancel_hand_gesture()
               worker.requestInterruption()
               self._set_hand_tracking_button_text("Stopping Hands")
               if worker.wait(2500):
                    self._hand_tracking_finished(worker)
               else:
                    self.hand_tracking_status.setText(
                         "The camera is still closing. Please wait before restarting."
                    )
               return

          worker = HandTrackingWorker(self)
          self.hand_tracking_worker = worker
          worker.hand_detected.connect(self._on_hand_detected)
          worker.hand_lost.connect(self._on_hand_lost)
          worker.camera_ready.connect(self._on_camera_ready)
          worker.tracking_error.connect(self._on_hand_tracking_error)
          worker.finished.connect(
               lambda current_worker=worker: self._hand_tracking_finished(current_worker)
          )
          self._two_hand_drag_position = None
          self._volume_hand_y = None
          self._volume_palm_facing = None
          self._volume_motion = 0.0
          self._volume_error_reported = False
          self._set_hand_tracking_button_text("Stop Hands")
          self.hand_tracking_status.setText("Starting the local camera...")
          worker.start()

     def _set_hand_tracking_button_text(self, text):
          self.hand_tracking_button.setText(text)

     def _hand_tracking_finished(self, worker):
          if self.hand_tracking_worker is not worker:
               return
          self._cancel_hand_gesture()
          self._two_hand_drag_position = None
          if self.hand_cursor_overlay is not None:
               self.hand_cursor_overlay.hide()
          self.hand_tracking_worker = None
          self._set_hand_tracking_button_text("Start Hands")
          if self.hand_tracking_status.text() not in {
               "Hand tracking is off.",
               "The camera is still closing. Please wait before restarting.",
          } and not self.hand_tracking_status.text().startswith("Hand tracking error:"):
               self.hand_tracking_status.setText("Hand tracking is off.")

     def _on_hand_tracking_error(self, message):
          self._cancel_hand_gesture()
          if self.hand_cursor_overlay is not None:
               self.hand_cursor_overlay.hide()
          self.hand_tracking_status.setText(f"Hand tracking error: {message}")

     def _on_hand_lost(self):
          self._cancel_hand_gesture()
          self._two_hand_depth_position = None
          workspace = getattr(self.window(), "workspace_screen", None)
          if workspace is not None:
               workspace.viewer.end_two_hand_item_manipulation()
          if self.hand_cursor_overlay is not None:
               self.hand_cursor_overlay.set_positions([])
          self._two_hand_drag_position = None
          self._volume_hand_y = None
          self._volume_palm_facing = None
          self._volume_motion = 0.0
          if self.hand_tracking_worker is not None:
               self.hand_tracking_status.setText("Camera active; no hand detected.")

     def _on_camera_ready(self):
          if self.hand_cursor_overlay is None:
               self.hand_cursor_overlay = HandCursorOverlay(self.window())
          self.hand_cursor_overlay.setGeometry(QApplication.desktop().screenGeometry())
          self.hand_cursor_overlay.show()
          self.hand_cursor_overlay.raise_()
          self.hand_tracking_status.setText(
               "Camera active. Double-pinch to click; pinch and hold/drag to grab. "
               "Hand control works across the desktop while enabled."
          )

     def _on_hand_detected(self, hands):
          if len(hands) == 2:
               self._on_two_hands_detected(hands)
               return
          self._two_hand_depth_position = None
          workspace = getattr(self.window(), "workspace_screen", None)
          if workspace is not None:
               workspace.viewer.end_two_hand_item_manipulation()
          self._two_hand_drag_position = None
          if not hands:
               self._cancel_hand_gesture()
               return
          metrics = hands[0]
          (
               x,
               y,
               pinch_distance,
               fist_openness,
               open_palm,
               palm_facing,
               _,
               hand_center_y,
               _,
          ) = metrics
          window = self.window()
          stacked_widget = window.centralWidget()
          workspace = getattr(window, "workspace_screen", None)
          workspace_active = (
               stacked_widget is not None
               and workspace is not None
               and stacked_widget.currentWidget() is workspace
          )

          origin = window.mapToGlobal(QPoint(0, 0))
          screen_x = origin.x() + round(min(1.0, max(0.0, x)) * (window.width() - 1))
          screen_y = origin.y() + round(min(1.0, max(0.0, y)) * (window.height() - 1))
          global_position = QPoint(screen_x, screen_y)

          self._adopt_single_hand_state(global_position)
          self._set_hand_cursor_positions([global_position])

          canvas_position = self.canvas.mapFromGlobal(global_position)
          if workspace_active:
               viewer_position = workspace.viewer.mapFromGlobal(global_position)
               if workspace.viewer.rect().contains(viewer_position):
                    if (
                         not self._hand_is_pinched(
                              "single", pinch_distance, fist_openness
                         )
                         and (
                              fist_openness < 0.15
                              or pinch_distance >= _HAND_ZOOM_IN_THRESHOLD
                         )
                    ):
                         workspace.viewer.set_hand_zoom(
                              zoom_openness_for_hand(pinch_distance, fist_openness)
                         )
          elif self.canvas.rect().contains(canvas_position):
               self.canvas.set_hand_cursor(canvas_position)
               if (
                    not self._hand_is_pinched("single", pinch_distance, fist_openness)
                    and (
                         fist_openness < 0.15
                         or pinch_distance >= _HAND_ZOOM_IN_THRESHOLD
                    )
               ):
                    self.canvas.set_hand_zoom(
                         zoom_openness_for_hand(pinch_distance, fist_openness)
                    )
          else:
               self.canvas.set_hand_cursor(None)

          self._update_hand_volume(hand_center_y, open_palm, palm_facing)
          try:
               self._update_hand_interaction("single", metrics, global_position)
          except (OSError, RuntimeError) as error:
               self._report_hand_control_error(error)
               return
          self._update_single_hand_workbench_depth(metrics, workspace_active)

          click_guidance = (
               "Pinch once to focus a hologram or open a workspace item."
               if workspace_active
               else "Double-pinch to click."
          )
          status = (
               f"One hand: {click_guidance} Pinch and drag a hologram to "
               "move it. Enable Rotate Selected to turn it in place; "
               "rotation locks to your dominant hand direction. Move "
               "toward/away from the camera to adjust depth. Spread thumb "
               "and index to zoom in; close fist to zoom out."
               if workspace_active
               else (
                    f"One hand: {click_guidance} Pinch and hold/drag to grab. "
                    "Spread thumb and index to zoom in; close fist to zoom out. "
                    "Raise palm-up / lower palm-down to adjust volume."
               )
          )
          if self.hand_tracking_status.text() != status:
               self.hand_tracking_status.setText(status)

     def _update_single_hand_workbench_depth(self, metrics, workspace_active):
          state = self._hand_gesture_states.get("single")
          if state is None or len(metrics) < 9:
               return
          hand_size = metrics[8]
          previous_size = state.get("depth_hand_size")
          state["depth_hand_size"] = hand_size
          if (
               not workspace_active
               or state.get("mode") != "grab"
               or previous_size is None
               or previous_size <= 0
               or hand_size <= 0
          ):
               return
          workspace = getattr(self.window(), "workspace_screen", None)
          if workspace is None:
               return
          viewer = workspace.viewer
          target = state.get("target")
          if not (
               target is viewer
               or target is not None and viewer.isAncestorOf(target)
          ):
               return
          item_index = viewer.dragged_workbench_item
          if item_index is None:
               return
          relative_size_change = math.log(hand_size / previous_size)
          viewer.apply_single_hand_depth_delta(
               item_index, relative_size_change
          )

     def _on_two_hands_detected(self, hands):
          window = self.window()
          stacked_widget = window.centralWidget()
          workspace = getattr(window, "workspace_screen", None)
          map_is_active = (
               stacked_widget is not None
               and stacked_widget.currentWidget() is self
          )
          workspace_is_active = (
               stacked_widget is not None
               and workspace is not None
               and stacked_widget.currentWidget() is workspace
          )
          active_canvas = (
               self.canvas
               if map_is_active
               else workspace.viewer if workspace_is_active else None
          )

          left_to_right = sorted(hands, key=lambda metrics: metrics[6])
          first, second = left_to_right
          first_center = (first[6], first[7])
          second_center = (second[6], second[7])
          origin = window.mapToGlobal(QPoint(0, 0))
          hand_positions = []
          for metrics in (first, second):
               x, y = metrics[:2]
               global_position = QPoint(
                    origin.x() + round(min(1.0, max(0.0, x)) * (window.width() - 1)),
                    origin.y() + round(min(1.0, max(0.0, y)) * (window.height() - 1)),
               )
               hand_positions.append(global_position)

          self._adopt_two_hand_state(hand_positions)
          self._set_hand_cursor_positions(hand_positions)
          left_pinched = self._hand_is_pinched("left", first[2], first[3])
          right_pinched = self._hand_is_pinched("right", second[2], second[3])
          depth_position = (
               (first[8] + second[8]) / 2
               if len(first) > 8 and len(second) > 8
               else None
          )
          canvas_positions = (
               [active_canvas.mapFromGlobal(position) for position in hand_positions]
               if active_canvas is not None else []
          )
          both_over_canvas = (
               active_canvas is not None
               and all(
                    active_canvas.rect().contains(position)
                    for position in canvas_positions
               )
          )

          if map_is_active:
               self.canvas.set_hand_cursors([
                    position for position in canvas_positions
                    if self.canvas.rect().contains(position)
               ])
          self._update_hand_volume(0, False, 0)
          if (
               active_canvas is not None
               and both_over_canvas
               and left_pinched
               and right_pinched
          ):
               self._cancel_hand_gesture()
               self._set_hand_cursor_positions(hand_positions)
               depth_delta = (
                    depth_position - self._two_hand_depth_position
                    if depth_position is not None
                    and self._two_hand_depth_position is not None
                    else 0.0
               )
               if (
                    workspace_is_active
                    and active_canvas.update_two_hand_item_manipulation(
                         canvas_positions, depth_delta
                    )
               ):
                    self._two_hand_depth_position = depth_position
                    self._two_hand_drag_position = None
                    status = (
                         "Both hands on hologram: move apart to enlarge, "
                         "together to shrink, move both to reposition, and "
                         "move toward/away from the camera to pull/push depth."
                    )
                    if self.hand_tracking_status.text() != status:
                         self.hand_tracking_status.setText(status)
                    return
               self._two_hand_depth_position = None
               current_position = (first_center, second_center)
               if self._two_hand_drag_position is not None:
                    previous_first, previous_second = self._two_hand_drag_position
                    delta_x = (
                         first_center[0] - previous_first[0]
                         + second_center[0] - previous_second[0]
                    ) / 2
                    delta_y = (
                         first_center[1] - previous_first[1]
                         + second_center[1] - previous_second[1]
                    ) / 2
                    active_canvas.apply_hand_drag(delta_x, delta_y)
               self._two_hand_drag_position = current_position
               return

          if workspace_is_active:
               active_canvas.end_two_hand_item_manipulation()
          self._two_hand_depth_position = None
          self._two_hand_drag_position = None
          try:
               self._update_hand_interaction(
                    "left", first, hand_positions[0], left_pinched
               )
               self._update_hand_interaction(
                    "right", second, hand_positions[1], right_pinched
               )
          except (OSError, RuntimeError) as error:
               self._report_hand_control_error(error)
               return

          if (
               active_canvas is not None
               and both_over_canvas
               and not left_pinched
               and not right_pinched
          ):
               distance = math.hypot(
                    second_center[0] - first_center[0],
                    second_center[1] - first_center[1],
               )
               active_canvas.set_hand_zoom(zoom_openness_for_two_hands(distance))

          click_guidance = (
               "Pinch once to open workspace items."
               if workspace_is_active
               else "Double-pinch to click."
          )
          status = (
               "Two hands: move apart to zoom in; bring together to zoom out. "
               f"{click_guidance} Pinch and drag to grab."
          )
          if self.hand_tracking_status.text() != status:
               self.hand_tracking_status.setText(status)

     def _hand_is_pinched(self, hand_id, pinch_distance, fist_openness):
          if fist_openness < 0.15:
               return False
          state = self._hand_gesture_states.get(hand_id)
          threshold = (
               _HAND_PINCH_RELEASE_THRESHOLD
               if state is not None and state["target"] is not None
               else _HAND_PINCH_THRESHOLD
          )
          return pinch_distance < threshold

     def _set_hand_cursor_positions(self, positions):
          if self.hand_cursor_overlay is not None:
               self.hand_cursor_overlay.set_positions(positions)

     def _adopt_single_hand_state(self, global_position):
          state = self._hand_gesture_states.pop("single", None)
          if state is None:
               active_ids = [
                    hand_id
                    for hand_id in ("left", "right")
                    if hand_id in self._hand_gesture_states
               ]
               if active_ids:
                    hand_id = min(
                         active_ids,
                         key=lambda item: (
                              global_position
                              - self._hand_gesture_states[item]["start_position"]
                         ).manhattanLength(),
                    )
                    state = self._hand_gesture_states.pop(hand_id)
          if state is None:
               self._release_other_hand_states({"single"})
               self._adopt_pending_click("single", global_position)
               return
          self._hand_gesture_states["single"] = state
          self._release_other_hand_states({"single"})
          self._adopt_pending_click("single", global_position)

     def _adopt_two_hand_state(self, hand_positions):
          state = self._hand_gesture_states.pop("single", None)
          if state is not None:
               nearest_index = min(
                    range(2),
                    key=lambda index: (
                         hand_positions[index] - state["start_position"]
                    ).manhattanLength(),
               )
               hand_id = ("left", "right")[nearest_index]
               self._hand_gesture_states[hand_id] = state
          self._release_other_hand_states({"left", "right"})
          pending = self._pending_hand_clicks.pop("single", None)
          if pending is not None:
               self._pending_hand_clicks.pop("left", None)
               self._pending_hand_clicks.pop("right", None)
               nearest_index = min(
                    range(2),
                    key=lambda index: (
                         hand_positions[index] - pending["position"]
                    ).manhattanLength(),
               )
               self._pending_hand_clicks[("left", "right")[nearest_index]] = pending

     def _adopt_pending_click(self, hand_id, global_position):
          if hand_id in self._pending_hand_clicks:
               for candidate_id in ("left", "right"):
                    if candidate_id != hand_id:
                         self._pending_hand_clicks.pop(candidate_id, None)
               return
          candidates = [
               candidate_id
               for candidate_id in ("left", "right")
               if candidate_id in self._pending_hand_clicks
          ]
          if candidates:
               candidate_id = min(
                    candidates,
                    key=lambda item: (
                         global_position
                         - self._pending_hand_clicks[item]["position"]
                    ).manhattanLength(),
               )
               self._pending_hand_clicks[hand_id] = self._pending_hand_clicks.pop(
                    candidate_id
               )
               for other_id in candidates:
                    if other_id != candidate_id:
                         self._pending_hand_clicks.pop(other_id, None)

     def _release_other_hand_states(self, active_hand_ids):
          for hand_id in tuple(self._hand_gesture_states):
               if hand_id in active_hand_ids:
                    continue
               state = self._hand_gesture_states.pop(hand_id)
               self._release_hand_gesture(state, allow_click=False)

     def _update_hand_interaction(self, hand_id, metrics, global_position, pinched=None):
          if pinched is None:
               pinched = self._hand_is_pinched(
                    hand_id, metrics[2], metrics[3]
               )
          state = self._hand_gesture_states.get(hand_id)
          if state is not None:
               state["fist_seen"] |= metrics[3] < 0.15
          if pinched and state is None:
               target = self._hand_target_at(global_position)
               now = time.monotonic()
               pending = self._pending_hand_clicks.get(hand_id)
               if pending is not None:
                    same_target = target is pending["target"]
                    close_enough = (
                         global_position - pending["position"]
                    ).manhattanLength() <= _HAND_DOUBLE_PINCH_MAX_DISTANCE
                    if (
                         same_target
                         and close_enough
                         and now - pending["released_at"] <= _HAND_DOUBLE_PINCH_WINDOW
                    ):
                         self._send_hand_pointer_click(target, global_position)
                         self._pending_hand_clicks.pop(hand_id, None)
                         self._hand_gesture_states[hand_id] = {
                              "target": target,
                              "position": global_position,
                              "start_position": global_position,
                              "moved": False,
                              "fist_seen": False,
                              "mode": "click",
                              "pressed": False,
                              "depth_hand_size": (
                                   metrics[8] if len(metrics) > 8 else None
                              ),
                         }
                         return
                    self._pending_hand_clicks.pop(hand_id, None)
               state = {
                    "target": target,
                    "position": global_position,
                    "start_position": global_position,
                    "pinch_started_at": now,
                    "moved": False,
                    "fist_seen": False,
                    "mode": "candidate",
                    "pressed": False,
                    "depth_hand_size": (
                         metrics[8] if len(metrics) > 8 else None
                    ),
               }
               self._hand_gesture_states[hand_id] = state
          elif pinched and state is not None:
               if state["mode"] == "click":
                    return
               displacement = (
                    global_position - state["start_position"]
               ).manhattanLength()
               if displacement > _HAND_CLICK_MAX_MOVEMENT:
                    state["moved"] = True
               if state["mode"] == "candidate" and (
                    state["moved"]
                    or time.monotonic() - state["pinch_started_at"]
                    >= _HAND_GRAB_HOLD_SECONDS
               ):
                    state["mode"] = "grab"
                    state["pressed"] = True
                    set_hand_drag_active = getattr(
                         state["target"], "set_hand_drag_active", None
                    )
                    if callable(set_hand_drag_active):
                         set_hand_drag_active(True)
                    self._send_hand_pointer_event(
                         state["target"],
                         QEvent.MouseButtonPress,
                         state["start_position"],
                         Qt.LeftButton,
                         Qt.LeftButton,
                    )
               if state["mode"] == "grab":
                    self._send_hand_pointer_event(
                         state["target"],
                         QEvent.MouseMove,
                         global_position,
                         Qt.NoButton,
                         Qt.LeftButton,
                    )
               state["position"] = global_position
          elif not pinched and state is not None:
               if state["mode"] == "candidate":
                    elapsed = time.monotonic() - state["pinch_started_at"]
                    if (
                         not state["moved"]
                         and elapsed < _HAND_GRAB_HOLD_SECONDS
                    ):
                         if self._workspace_click_target(state["target"]):
                              self._send_hand_pointer_click(
                                   state["target"], global_position
                              )
                         else:
                              self._pending_hand_clicks[hand_id] = {
                                   "target": state["target"],
                                   "position": state["start_position"],
                                   "released_at": time.monotonic(),
                              }
               else:
                    self._release_hand_gesture(
                         state,
                         global_position,
                         _hand_click_is_valid(
                              state["moved"],
                              state["fist_seen"],
                         ),
                    )
               self._hand_gesture_states.pop(hand_id, None)

     def _workspace_click_target(self, target):
          window = self.window()
          stacked_widget = window.centralWidget()
          workspace = getattr(window, "workspace_screen", None)
          if (
               target is None
               or stacked_widget is None
               or workspace is None
               or stacked_widget.currentWidget() is not workspace
          ):
               return False
          return any(
               target is widget
               or widget.isAncestorOf(target)
               for widget in (
                    workspace.project_list,
                    workspace.category_list,
                    workspace.viewer,
               )
          )

     def _hand_target_at(self, global_position):
          target = QApplication.widgetAt(global_position)
          if target is None:
               return None
          overlay = getattr(self, "hand_cursor_overlay", None)
          if overlay is not None and (
               target is overlay or overlay.isAncestorOf(target)
          ):
               return None
          window = self.window()
          ancestor = target
          while ancestor is not None and ancestor is not window:
               ancestor = ancestor.parentWidget()
          if ancestor is not window:
               return None
          while target is not None and target is not window:
               if (
                    target.isVisible()
                    and target.isEnabled()
                    and not target.testAttribute(Qt.WA_TransparentForMouseEvents)
               ):
                    return target
               target = target.parentWidget()
          return None

     def _send_hand_pointer_event(self, target, event_type, global_position, button, buttons):
          if target is None:
               _send_global_hand_mouse_event(event_type, global_position)
               return
          local_position = target.mapFromGlobal(global_position)
          self._send_hand_mouse_event(
               target, event_type, local_position, button, buttons
          )

     def _send_hand_mouse_event(self, target, event_type, position, button, buttons):
          _send_hand_mouse_event(target, event_type, position, button, buttons)

     def _send_hand_pointer_click(self, target, global_position):
          try:
               self._send_hand_pointer_event(
                    target,
                    QEvent.MouseButtonPress,
                    global_position,
                    Qt.LeftButton,
                    Qt.LeftButton,
               )
          finally:
               self._send_hand_pointer_event(
                    target,
                    QEvent.MouseButtonRelease,
                    global_position,
                    Qt.LeftButton,
                    Qt.NoButton,
               )

     def _release_hand_gesture(self, state, global_position=None, allow_click=True):
          if not state.get("pressed", True):
               return
          target = state["target"]
          position = state["position"]
          if global_position is not None:
               position = (
                    global_position
                    if target is None
                    else target.mapFromGlobal(global_position)
               )
          is_map_drag = target is self.canvas and state["moved"]
          if not allow_click and not is_map_drag:
               if target is not None:
                    position = QPoint(-10, -10)
          if target is None:
               _send_global_hand_mouse_event(QEvent.MouseButtonRelease, position)
          else:
               try:
                    _send_hand_mouse_event(
                         target,
                         QEvent.MouseButtonRelease,
                         position,
                         Qt.LeftButton,
                         Qt.NoButton,
                    )
               finally:
                    set_hand_drag_active = getattr(
                         target, "set_hand_drag_active", None
                    )
                    if callable(set_hand_drag_active):
                         set_hand_drag_active(False)

     def _cancel_hand_gesture(self):
          for state in self._hand_gesture_states.values():
               self._release_hand_gesture(state, allow_click=False)
          self._hand_gesture_states.clear()
          self._pending_hand_clicks.clear()
          self.canvas.set_hand_cursor(None)
          overlay = getattr(self, "hand_cursor_overlay", None)
          if overlay is not None:
               overlay.set_positions([])

     def _report_hand_control_error(self, error):
          for state in self._hand_gesture_states.values():
               try:
                    self._release_hand_gesture(state, allow_click=False)
               except (OSError, RuntimeError) as release_error:
                    error = release_error
          self._hand_gesture_states.clear()
          self._pending_hand_clicks.clear()
          self._two_hand_drag_position = None
          overlay = getattr(self, "hand_cursor_overlay", None)
          if overlay is not None:
               overlay.set_positions([])
          self.hand_tracking_status.setText(f"Hand control error: {error}")

     def _update_hand_volume(self, y, open_palm, palm_facing):
          if not open_palm or palm_facing == 0:
               self._volume_hand_y = None
               self._volume_palm_facing = None
               self._volume_motion = 0.0
               return
          if (
               self._volume_hand_y is None
               or self._volume_palm_facing != palm_facing
          ):
               self._volume_hand_y = y
               self._volume_palm_facing = palm_facing
               return

          self._volume_motion += self._volume_hand_y - y
          self._volume_hand_y = y
          now = time.monotonic()
          threshold = 0.035
          if abs(self._volume_motion) < threshold or now < self._next_volume_step:
               return
          volume_action = volume_action_for_motion(
               self._volume_motion,
               palm_facing,
          )
          if volume_action is None:
               self._volume_motion = 0.0
               return
          try:
               adjust_system_volume(volume_action)
          except (OSError, RuntimeError) as error:
               if not self._volume_error_reported:
                    self.hand_tracking_status.setText(
                         f"Could not adjust Windows volume: {error}"
                    )
                    self._volume_error_reported = True
               return
          self._volume_motion -= math.copysign(threshold, self._volume_motion)
          self._next_volume_step = now + 0.12

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
               self.start_double_sound_trigger()

     def create_conversation_orb(self):
          self.selected_conversation_path = CreateConversationOrb()
          self.delete_orb_button.setEnabled(True)
          self.refresh_conversations()
          self.details.setText("New conversation orb created. It has its own chatlog.")


class HologramCanvas(QWidget):
     workbench_item_dragged = pyqtSignal(int, float, float, float)
     workbench_item_scaled = pyqtSignal(int, float)
     workbench_item_rotated = pyqtSignal(int, float, float, float)
     workbench_item_selected = pyqtSignal(object)
     workbench_item_edit_finished = pyqtSignal()
     MAX_RENDERED_TRIANGLES = 3000
     MAX_AUTO_ROTATE_TRIANGLES = 1200

     def __init__(self, parent=None):
          super().__init__(parent)
          self.triangles = []
          self._mesh_vertices = []
          self._mesh_triangles = []
          self._mesh_vertex_owners = None
          self.triangle_materials = None
          self._render_triangle_indices = []
          self._workbench_items = None
          self._workbench_centers = ()
          self._workbench_base_centers = ()
          self._workbench_unit_scale = 1.0
          self._background_pixmap = QPixmap()
          self.circuit_mode = False
          self.auto_fit_zoom = 1.0
          self.workbench_item_count = 0
          self.workbench_triangle_owners = None
          self.scene_center = (0.0, 0.0, 0.0)
          self.workbench_scene_center = (0.0, 0.0, 0.0)
          self.workbench_fit_zoom = 1.0
          self.focused_workbench_item = None
          self.dragged_workbench_item = None
          self.selected_workbench_item = None
          self.item_interaction_mode = "move"
          self._dragged_item_mode = None
          self._two_hand_item_index = None
          self._two_hand_item_center = None
          self._two_hand_item_distance = None
          self._two_hand_item_angle = None
          self._hand_drag_active = False
          self._hand_drag_mode = None
          self._hand_rotation_screen_width = 1.0
          self._hand_rotation_screen_height = 1.0
          self._hand_rotation_axis = None
          self._hand_rotation_total_x = 0
          self._hand_rotation_total_y = 0
          self.rotation = 0.0
          self.vertical_rotation = -0.35
          self.zoom = 1.0
          self.drag_position = None
          self.setMouseTracking(True)
          self.setMinimumSize(420, 320)
          self.rotation_timer = QTimer(self)
          self.rotation_timer.timeout.connect(self.rotate_model)
          self.rotation_timer.setInterval(67)

     @staticmethod
     def prepare_mesh(triangles):
          triangles = list(triangles)
          vertex_indices = {}
          vertices = []
          indexed_triangles = []
          for triangle in triangles:
               indices = []
               for vertex in triangle:
                    vertex_key = tuple(vertex)
                    index = vertex_indices.get(vertex_key)
                    if index is None:
                         index = len(vertices)
                         vertex_indices[vertex_key] = index
                         vertices.append(vertex_key)
                    indices.append(index)
               indexed_triangles.append(tuple(indices))
          return triangles, vertices, indexed_triangles

     def set_mesh(self, triangles, prepared_mesh=None):
          if prepared_mesh is None:
               prepared_mesh = self.prepare_mesh(triangles)
          self.triangles, self._mesh_vertices, self._mesh_triangles = (
               prepared_mesh[:3]
          )
          self._mesh_vertex_owners = None
          self._workbench_items = None
          self.triangle_materials = (
               prepared_mesh[3] if len(prepared_mesh) > 3 else None
          )
          self._set_render_triangle_indices()
          if (
               self.isVisible()
               and self.triangles
               and len(self._render_triangle_indices)
               <= self.MAX_AUTO_ROTATE_TRIANGLES
          ):
               self.rotation_timer.start()
          else:
               self.rotation_timer.stop()
          self.update()

     def set_workbench_mesh(
          self, items, centers, base_centers, unit_scale, reset_zoom=False
     ):
          vertices = []
          indexed_triangles = []
          vertex_owners = []
          triangle_owners = []
          materials = []
          source_triangles = []
          for item_index, item in enumerate(items):
               prepared_mesh = item.get("prepared_mesh")
               if prepared_mesh is None:
                    prepared_mesh = self.prepare_mesh(item["triangles"])
               item_vertices = prepared_mesh[1]
               item_triangles = prepared_mesh[2]
               vertex_offset = len(vertices)
               vertices.extend(item_vertices)
               vertex_owners.extend([item_index] * len(item_vertices))
               indexed_triangles.extend(
                    tuple(vertex_offset + vertex for vertex in triangle)
                    for triangle in item_triangles
               )
               triangle_count = len(item_triangles)
               triangle_owners.extend([item_index] * triangle_count)
               item_materials = item.get("materials")
               materials.extend(
                    item_materials
                    if item_materials is not None
                    else ["model"] * triangle_count
               )
               source_triangles.extend(item["triangles"])

          self.triangles = source_triangles
          self._mesh_vertices = vertices
          self._mesh_triangles = indexed_triangles
          self._mesh_vertex_owners = vertex_owners
          self.triangle_materials = materials
          self.workbench_triangle_owners = triangle_owners
          self.workbench_item_count = len(items)
          self._workbench_items = items
          self._workbench_centers = centers
          self._workbench_base_centers = base_centers
          self._workbench_unit_scale = unit_scale
          self.circuit_mode = any(item["is_circuit"] for item in items)
          self._set_render_triangle_indices()

          world_vertices = self._workbench_world_vertices()
          if world_vertices:
               mins = tuple(
                    min(vertex[axis] for vertex in world_vertices)
                    for axis in range(3)
               )
               maxs = tuple(
                    max(vertex[axis] for vertex in world_vertices)
                    for axis in range(3)
               )
               scene_span = max(
                    maxs[axis] - mins[axis] for axis in range(3)
               ) or 1.0
               self.scene_center = tuple(
                    (mins[axis] + maxs[axis]) / 2 for axis in range(3)
               )
               self.workbench_scene_center = self.scene_center
               self.workbench_fit_zoom = min(1.0, 1.35 / scene_span)
               self.auto_fit_zoom = self.workbench_fit_zoom
               if reset_zoom:
                    self.zoom = 1.0
          if (
               self.focused_workbench_item is not None
               and self.focused_workbench_item < len(items)
          ):
               self._apply_workbench_focus()
          if (
               self.isVisible()
               and self.triangles
               and len(self._render_triangle_indices)
               <= self.MAX_AUTO_ROTATE_TRIANGLES
          ):
               self.rotation_timer.start()
          else:
               self.rotation_timer.stop()
          self.update()

     def set_workbench_transforms(self, items):
          self._workbench_items = items
          self.update()

     def set_workbench_focus(self, item_index):
          if item_index is not None and not (
               0 <= item_index < self.workbench_item_count
          ):
               item_index = None
          self.focused_workbench_item = item_index
          self.selected_workbench_item = item_index
          if item_index is None:
               self.scene_center = self.workbench_scene_center
               self.auto_fit_zoom = self.workbench_fit_zoom
          else:
               self._apply_workbench_focus()
          self.update()

     def _apply_workbench_focus(self):
          item_index = self.focused_workbench_item
          if (
               item_index is None
               or self._mesh_vertex_owners is None
               or item_index >= self.workbench_item_count
          ):
               return
          vertex_indices = {
               index
               for index, owner in enumerate(self._mesh_vertex_owners)
               if owner == item_index
          }
          vertices = self._workbench_world_vertices(vertex_indices).values()
          if not vertices:
               return
          mins = tuple(
               min(vertex[axis] for vertex in vertices) for axis in range(3)
          )
          maxs = tuple(
               max(vertex[axis] for vertex in vertices) for axis in range(3)
          )
          span = max(maxs[axis] - mins[axis] for axis in range(3)) or 1.0
          self.scene_center = tuple(
               (mins[axis] + maxs[axis]) / 2 for axis in range(3)
          )
          self.auto_fit_zoom = min(1.0, 1.35 / span)

     def _set_render_triangle_indices(self):
          triangle_count = len(self._mesh_triangles)
          if (
               self.workbench_triangle_owners is None
               or len(self.workbench_triangle_owners) != triangle_count
          ):
               stride = max(
                    1,
                    math.ceil(triangle_count / self.MAX_RENDERED_TRIANGLES),
               )
               self._render_triangle_indices = range(0, triangle_count, stride)
               return

          triangles_by_owner = {}
          for triangle_index, owner in enumerate(
               self.workbench_triangle_owners
          ):
               triangles_by_owner.setdefault(owner, []).append(triangle_index)

          remaining = self.MAX_RENDERED_TRIANGLES
          selected = []
          owners = sorted(
               triangles_by_owner,
               key=lambda owner: len(triangles_by_owner[owner]),
          )
          pending = []
          for owner in owners:
               owner_triangles = triangles_by_owner[owner]
               if len(owner_triangles) <= remaining:
                    selected.extend(owner_triangles)
                    remaining -= len(owner_triangles)
               else:
                    pending.append(owner_triangles)

          for index, owner_triangles in enumerate(pending):
               if remaining <= 0:
                    break
               quota = max(
                    1,
                    remaining // (len(pending) - index),
               )
               stride = max(1, math.ceil(len(owner_triangles) / quota))
               owner_selection = owner_triangles[::stride]
               selected.extend(owner_selection)
               remaining -= len(owner_selection)

          self._render_triangle_indices = sorted(selected)

     def _workbench_world_vertices(self, vertex_indices=None):
          if self._workbench_items is None or self._mesh_vertex_owners is None:
               if vertex_indices is None:
                    return self._mesh_vertices
               return {
                    index: self._mesh_vertices[index]
                    for index in vertex_indices
               }

          group_centers = {}
          group_counts = {}
          for index, item in enumerate(self._workbench_items):
               group_id = item["group_id"]
               position = tuple(
                    self._workbench_base_centers[index][axis]
                    + item["offset"][axis]
                    for axis in range(3)
               )
               center = group_centers.setdefault(group_id, [0.0, 0.0, 0.0])
               for axis in range(3):
                    center[axis] += position[axis]
               group_counts[group_id] = group_counts.get(group_id, 0) + 1
          for group_id, center in group_centers.items():
               group_centers[group_id] = tuple(
                    value / group_counts[group_id] for value in center
               )

          transforms = []
          for owner, item in enumerate(self._workbench_items):
               rotation_x, rotation_y, rotation_z = item.get(
                    "rotation", (0.0, 0.0, 0.0)
               )
               transforms.append((
                    self._workbench_centers[owner],
                    self._workbench_base_centers[owner],
                    item["offset"],
                    (
                         item.get("fit_scale", 1.0)
                         * item.get("scale", 1.0)
                         / self._workbench_unit_scale
                    ),
                    group_centers[item["group_id"]],
                    math.cos(rotation_x),
                    math.sin(rotation_x),
                    math.cos(rotation_y),
                    math.sin(rotation_y),
                    math.cos(rotation_z),
                    math.sin(rotation_z),
               ))

          indices = (
               range(len(self._mesh_vertices))
               if vertex_indices is None
               else vertex_indices
          )
          world_vertices = {}
          for index in indices:
               owner = self._mesh_vertex_owners[index]
               vertex = self._mesh_vertices[index]
               (
                    center,
                    base_center,
                    offset,
                    scale,
                    group_center,
                    cos_x,
                    sin_x,
                    cos_y,
                    sin_y,
                    cos_z,
                    sin_z,
               ) = transforms[owner]
               positioned = tuple(
                    (vertex[axis] - center[axis])
                    * scale
                    + base_center[axis]
                    + offset[axis]
                    for axis in range(3)
               )
               world_vertices[index] = WorkspaceScreen._rotate_group_vertex(
                    positioned,
                    group_center,
                    cos_x,
                    sin_x,
                    cos_y,
                    sin_y,
                    cos_z,
                    sin_z,
               )
          if vertex_indices is None:
               return [
                    world_vertices[index]
                    for index in range(len(self._mesh_vertices))
               ]
          return world_vertices

     def set_circuit_mode(self, enabled):
          self.circuit_mode = enabled
          self.update()

     def set_triangle_materials(self, materials):
          self.triangle_materials = materials
          self.update()

     def set_auto_fit_zoom(self, zoom, reset_zoom=False):
          self.auto_fit_zoom = zoom
          if reset_zoom:
               self.zoom = 1.0
          self.update()

     def set_scene_center(self, center):
          self.scene_center = tuple(center)
          self.update()

     def set_workbench_triangle_owners(self, owners):
          self.workbench_triangle_owners = owners
          self.update()

     def set_workbench_item_count(self, count):
          self.workbench_item_count = count
          self.update()

     def set_hand_zoom(self, openness):
          target_zoom = 0.65 + min(1.0, max(0.0, openness)) * 1.05
          self.zoom += (target_zoom - self.zoom) * 0.05625
          self.update()

     def apply_hand_drag(self, delta_x, delta_y):
          self.rotation -= delta_x * self.width() * 0.0016
          self.vertical_rotation += delta_y * self.height() * 0.0016
          self.update()

     def rotate_model(self):
          if (
               self.triangles
               and self.isVisible()
               and len(self._render_triangle_indices)
               <= self.MAX_AUTO_ROTATE_TRIANGLES
          ):
               self.rotation += 0.0032
               self.update()

     def showEvent(self, event):
          super().showEvent(event)
          if (
               self.triangles
               and len(self._render_triangle_indices)
               <= self.MAX_AUTO_ROTATE_TRIANGLES
          ):
               self.rotation_timer.start()
          else:
               self.rotation_timer.stop()

     def hideEvent(self, event):
          self.rotation_timer.stop()
          super().hideEvent(event)

     def _project_vertex(
          self, vertex, yaw_cos, yaw_sin, pitch_cos, pitch_sin, scale,
          center_x, center_y
     ):
          x, y, z = (
               vertex[axis] - self.scene_center[axis]
               for axis in range(3)
          )
          x, z = x * yaw_cos - z * yaw_sin, x * yaw_sin + z * yaw_cos
          y, z = y * pitch_cos - z * pitch_sin, y * pitch_sin + z * pitch_cos
          return (
               QPointF(
                    center_x + x * scale,
                    center_y - y * scale,
               ),
               z,
          )

     def _project_current_mesh(self, vertex_indices=None):
          yaw_cos = math.cos(self.rotation)
          yaw_sin = math.sin(self.rotation)
          pitch_cos = math.cos(self.vertical_rotation)
          pitch_sin = math.sin(self.vertical_rotation)
          scale = (
               min(self.width(), self.height())
               * 0.62
               * self.zoom
               * self.auto_fit_zoom
          )
          vertices = self._workbench_world_vertices(vertex_indices)
          if vertex_indices is None:
               return [
                    self._project_vertex(
                         vertex,
                         yaw_cos,
                         yaw_sin,
                         pitch_cos,
                         pitch_sin,
                         scale,
                         self.width() / 2,
                         self.height() / 2,
                    )
                    for vertex in vertices
               ]
          return {
               index: self._project_vertex(
                    vertices[index],
                    yaw_cos,
                    yaw_sin,
                    pitch_cos,
                    pitch_sin,
                    scale,
                    self.width() / 2,
                    self.height() / 2,
               )
               for index in vertex_indices
          }

     @staticmethod
     def _point_in_triangle(point, first, second, third):
          return HologramCanvas._triangle_barycentric_weights(
               point, first, second, third
          ) is not None

     @staticmethod
     def _triangle_barycentric_weights(point, first, second, third):
          denominator = (
               (second.y() - third.y()) * (first.x() - third.x())
               + (third.x() - second.x()) * (first.y() - third.y())
          )
          if abs(denominator) < 1e-8:
               return None
          alpha = (
               (second.y() - third.y()) * (point.x() - third.x())
               + (third.x() - second.x()) * (point.y() - third.y())
          ) / denominator
          beta = (
               (third.y() - first.y()) * (point.x() - third.x())
               + (first.x() - third.x()) * (point.y() - third.y())
          ) / denominator
          gamma = 1 - alpha - beta
          if alpha < 0 or beta < 0 or gamma < 0:
               return None
          return alpha, beta, gamma

     def set_hand_drag_active(self, active):
          self._hand_drag_active = bool(active)

     def _rotate_held_item(self, delta_x, delta_y):
          angle_x = delta_y * math.pi / self._hand_rotation_screen_height
          angle_y = -delta_x * math.pi / self._hand_rotation_screen_width
          if angle_x or angle_y:
               self.workbench_item_rotated.emit(
                    self.dragged_workbench_item, angle_x, angle_y, 0.0
               )
          self.update()

     def _rotate_held_item_on_drag_axis(self, delta_x, delta_y):
          self._hand_rotation_total_x += delta_x
          self._hand_rotation_total_y += delta_y
          if self._hand_rotation_axis is None:
               if max(
                    abs(self._hand_rotation_total_x),
                    abs(self._hand_rotation_total_y),
               ) < 6:
                    return
               self._hand_rotation_axis = (
                    "horizontal"
                    if abs(self._hand_rotation_total_x)
                    >= abs(self._hand_rotation_total_y)
                    else "vertical"
               )
               delta_x = self._hand_rotation_total_x
               delta_y = self._hand_rotation_total_y
          if self._hand_rotation_axis == "horizontal":
               self._rotate_held_item(delta_x, 0)
          else:
               self._rotate_held_item(0, delta_y)

     def _workbench_item_at(self, position):
          if (
               self.workbench_triangle_owners is None
               or self.workbench_item_count < 1
          ):
               return None
          projected = self._project_current_mesh()
          nearest_depth = -math.inf
          selected_item = None
          point = QPointF(position)
          for index, triangle in enumerate(self._mesh_triangles):
               if index >= len(self.workbench_triangle_owners):
                    break
               first_index, second_index, third_index = triangle
               first = projected[first_index][0]
               second = projected[second_index][0]
               third = projected[third_index][0]
               if not self._point_in_triangle(point, first, second, third):
                    continue
               depth = (
                    projected[first_index][1]
                    + projected[second_index][1]
                    + projected[third_index][1]
               ) / 3
               if depth > nearest_depth:
                    nearest_depth = depth
                    selected_item = self.workbench_triangle_owners[index]
          return selected_item

     def _screen_drag_to_world(self, delta):
          scale = (
               min(self.width(), self.height())
               * 0.62
               * self.zoom
               * self.auto_fit_zoom
          ) or 1.0
          camera_x = delta.x() / scale
          camera_y = -delta.y() / scale
          pitch_cos = math.cos(self.vertical_rotation)
          pitch_sin = math.sin(self.vertical_rotation)
          camera_z = 0.0
          world_y = camera_y * pitch_cos + camera_z * pitch_sin
          world_z_after_pitch = -camera_y * pitch_sin + camera_z * pitch_cos
          yaw_cos = math.cos(self.rotation)
          yaw_sin = math.sin(self.rotation)
          world_x = camera_x * yaw_cos + world_z_after_pitch * yaw_sin
          world_z = -camera_x * yaw_sin + world_z_after_pitch * yaw_cos
          return world_x, world_y, world_z

     def begin_two_hand_item_manipulation(self, positions):
          if len(positions) != 2:
               return False
          first, second = positions
          center = QPointF(
               (first.x() + second.x()) / 2,
               (first.y() + second.y()) / 2,
          )
          candidates = (center, first, second)
          item_index = next(
               (
                    hit
                    for point in candidates
                    if (hit := self._workbench_item_at(point)) is not None
               ),
               None,
          )
          if item_index is None:
               return False
          self.selected_workbench_item = item_index
          self._two_hand_item_index = item_index
          self._two_hand_item_center = center
          self._two_hand_item_distance = max(
               math.hypot(first.x() - second.x(), first.y() - second.y()),
               1.0,
          )
          self._two_hand_item_angle = math.atan2(
               second.y() - first.y(),
               second.x() - first.x(),
          )
          return True

     def update_two_hand_item_manipulation(self, positions, depth_delta=0.0):
          if self._two_hand_item_index is None:
               if not self.begin_two_hand_item_manipulation(positions):
                    return False
               return True
          first, second = positions
          center = QPointF(
               (first.x() + second.x()) / 2,
               (first.y() + second.y()) / 2,
          )
          world_delta = self._screen_drag_to_world(
               QPoint(
                    round(center.x() - self._two_hand_item_center.x()),
                    round(center.y() - self._two_hand_item_center.y()),
               )
          )
          if any(world_delta):
               self.workbench_item_dragged.emit(
                    self._two_hand_item_index, *world_delta
               )
          camera_depth_delta = depth_delta * 5.0
          if abs(camera_depth_delta) > 0.0075:
               depth_vector = self._camera_depth_to_world(camera_depth_delta)
               self.workbench_item_dragged.emit(
                    self._two_hand_item_index, *depth_vector
               )
          distance = max(
               math.hypot(first.x() - second.x(), first.y() - second.y()),
               1.0,
          )
          scale_factor = distance / self._two_hand_item_distance
          if not math.isclose(scale_factor, 1.0, rel_tol=1e-3):
               self.workbench_item_scaled.emit(
                    self._two_hand_item_index, scale_factor
               )
          angle = math.atan2(
               second.y() - first.y(),
               second.x() - first.x(),
          )
          angle_delta = math.atan2(
               math.sin(angle - self._two_hand_item_angle),
               math.cos(angle - self._two_hand_item_angle),
          )
          if abs(angle_delta) > 1e-3:
               self.workbench_item_rotated.emit(
                    self._two_hand_item_index, 0.0, 0.0, angle_delta
               )
          self._two_hand_item_center = center
          self._two_hand_item_distance = distance
          self._two_hand_item_angle = angle
          return True

     def _camera_depth_to_world(self, depth_delta):
          pitch_cos = math.cos(self.vertical_rotation)
          pitch_sin = math.sin(self.vertical_rotation)
          yaw_cos = math.cos(self.rotation)
          yaw_sin = math.sin(self.rotation)
          return (
               depth_delta * pitch_cos * yaw_sin,
               depth_delta * pitch_sin,
               depth_delta * pitch_cos * yaw_cos,
          )

     def apply_single_hand_depth_delta(self, item_index, relative_size_change):
          if (
               item_index is None
               or not math.isfinite(relative_size_change)
          ):
               return
          depth_delta = relative_size_change * 1.5
          if abs(depth_delta) <= 0.0075:
               return
          self.workbench_item_dragged.emit(
               item_index, *self._camera_depth_to_world(depth_delta)
          )

     def end_two_hand_item_manipulation(self):
          self._two_hand_item_index = None
          self._two_hand_item_center = None
          self._two_hand_item_distance = None
          self._two_hand_item_angle = None

     def set_item_interaction_mode(self, mode):
          if mode not in {"move", "rotate"}:
               raise ValueError(f"Unknown workbench interaction mode: {mode}")
          self.item_interaction_mode = mode

     def _paint_circuit_mesh(self, painter, projected_vertices):
          bucket_count = 96
          palette = {
               "model": QColor(38, 190, 218),
               "board": QColor(34, 132, 67),
               "arduino": QColor(25, 99, 183),
               "lcd_body": QColor(35, 38, 40),
               "lcd_screen": QColor(107, 162, 65),
               "pot_body": QColor(42, 48, 54),
               "pot_knob": QColor(27, 31, 35),
               "battery": QColor(35, 42, 53),
               "generic": QColor(174, 93, 46),
               "pads": QColor(216, 164, 54),
               "copper": QColor(191, 102, 39),
               "unrouted": QColor(238, 128, 40),
          }
          material_names = tuple(palette)
          triangles_by_item = {}
          depths = []
          material_indices = {
               name: index for index, name in enumerate(material_names)
          }
          for triangle_index in self._render_triangle_indices:
               triangle = self._mesh_triangles[triangle_index]
               points = [projected_vertices[index][0] for index in triangle]
               first, second, third = points
               area = (
                    first.x() * second.y() - second.x() * first.y()
                    + second.x() * third.y() - third.x() * second.y()
                    + third.x() * first.y() - first.x() * third.y()
               )
               if area >= 0:
                    continue
               depth = sum(projected_vertices[index][1] for index in triangle) / 3
               material = (
                    self.triangle_materials[triangle_index]
                    if self.triangle_materials is not None
                    else "board"
               )
               owner = (
                    self.workbench_triangle_owners[triangle_index]
                    if self.workbench_triangle_owners is not None
                    else 0
               )
               depths.append((
                    depth,
                    material_indices.get(material, 0),
                    points,
                    owner,
               ))
          if not depths:
               return

          minimum_depth = min(depth for depth, _, _, _ in depths)
          depth_range = (
               max(depth for depth, _, _, _ in depths) - minimum_depth or 1
          )
          for depth, material_index, points, owner in depths:
               bucket = min(
                    bucket_count - 1,
                    int((depth - minimum_depth) / depth_range * bucket_count),
               )
               triangles_by_bucket = triangles_by_item.setdefault(
                    owner, [[] for _ in range(bucket_count)]
               )
               path = triangles_by_bucket[bucket]
               first, second, third = points
               path.append((material_index, (first, second, third)))

          painter.setPen(Qt.NoPen)
          focus_active = (
               self.focused_workbench_item is not None
               and self.workbench_item_count > 1
          )
          for owner, buckets in triangles_by_item.items():
               is_focused = (
                    not focus_active or owner == self.focused_workbench_item
               )
               painter.save()
               painter.setOpacity(1.0 if is_focused else 0.16)
               for bucket in buckets:
                    grouped_triangles = {}
                    for material_index, triangle in bucket:
                         grouped_triangles.setdefault(material_index, []).append(
                              triangle
                         )
                    for material_index, triangles in grouped_triangles.items():
                         path = QPainterPath()
                         path.setFillRule(Qt.WindingFill)
                         for first, second, third in triangles:
                              path.moveTo(first)
                              path.lineTo(second)
                              path.lineTo(third)
                              path.closeSubpath()
                         painter.setBrush(
                              palette[material_names[material_index]]
                         )
                         painter.drawPath(path)
               painter.restore()

     def paintEvent(self, event):
          if self._background_pixmap.size() != self.size():
               self._background_pixmap = QPixmap(self.size())
               background_painter = QPainter(self._background_pixmap)
               gradient = QRadialGradient(
                    self.width() * 0.5,
                    self.height() * 0.48,
                    max(self.width(), self.height()) * 0.75,
               )
               gradient.setColorAt(0, QColor(9, 32, 48))
               gradient.setColorAt(1, QColor(2, 5, 14))
               background_painter.fillRect(self.rect(), gradient)
               background_painter.end()
          painter = QPainter(self)
          painter.drawPixmap(self.rect(), self._background_pixmap)
          painter.setRenderHint(
               QPainter.Antialiasing, len(self._mesh_triangles) <= 300
          )
          if not self.triangles:
               painter.setPen(QColor(190, 216, 230))
               painter.drawText(self.rect(), Qt.AlignCenter, "Import or create a 3D design to preview it.")
               return

          render_vertex_indices = {
               vertex_index
               for triangle_index in self._render_triangle_indices
               for vertex_index in self._mesh_triangles[triangle_index]
          }
          projected_vertices = self._project_current_mesh(
               render_vertex_indices
          )

          if self.circuit_mode:
               self._paint_circuit_mesh(painter, projected_vertices)
               painter.setPen(QColor(200, 252, 255, 190))
               title = (
                    f"AIKO WORKBENCH  |  {self.workbench_item_count} PROJECTS"
                    if self.workbench_item_count > 1
                    else "PCB HOLOGRAM"
               )
               painter.drawText(14, 24, title)
               return

          shade_count = 6
          mesh_paths = [
               [QPainterPath() for _ in range(shade_count)]
               for _ in range(2)
          ]
          for owner_paths in mesh_paths:
               for path in owner_paths:
                    path.setFillRule(Qt.WindingFill)
          focus_active = (
               self.focused_workbench_item is not None
               and self.workbench_item_count > 1
          )
          for triangle_index in self._render_triangle_indices:
               triangle = self._mesh_triangles[triangle_index]
               points = [
                    projected_vertices[index][0]
                    for index in triangle
               ]
               depth = sum(projected_vertices[index][1] for index in triangle) / 3
               glow = max(80, min(210, 150 + int(depth * 55)))
               shade = min(shade_count - 1, (glow - 80) * shade_count // 131)
               owner = (
                    self.workbench_triangle_owners[triangle_index]
                    if self.workbench_triangle_owners is not None
                    else self.focused_workbench_item
               )
               emphasis = int(
                    focus_active and owner == self.focused_workbench_item
               )
               first, second, third = points
               area = (
                    first.x() * second.y() - second.x() * first.y()
                    + second.x() * third.y() - third.x() * second.y()
                    + third.x() * first.y() - first.x() * third.y()
               )
               if area < 0:
                    points[1], points[2] = points[2], points[1]
               path = mesh_paths[emphasis][shade]
               path.moveTo(points[0])
               path.lineTo(points[1])
               path.lineTo(points[2])
               path.closeSubpath()

          for emphasis, owner_paths in enumerate(mesh_paths):
               painter.save()
               if focus_active and not emphasis:
                    painter.setOpacity(0.16)
               for shade, path in enumerate(owner_paths):
                    if path.isEmpty():
                         continue
                    glow = 135 + round(shade * 115 / (shade_count - 1))
                    painter.setBrush(QColor(15, 196, 220, glow))
                    painter.setPen(
                         QPen(QColor(126, 250, 255, min(255, glow + 35)), 1)
                    )
                    painter.drawPath(path)
               painter.restore()

          painter.setPen(QColor(200, 252, 255, 190))
          title = (
               f"AIKO WORKBENCH  |  {self.workbench_item_count} PROJECTS"
               if self.workbench_item_count > 1
               else "AIKO 3D HOLOGRAM"
          )
          painter.drawText(14, 24, title)

     def mousePressEvent(self, event):
          if event.button() in (Qt.LeftButton, Qt.RightButton):
               self.drag_position = event.pos()
               self._drag_moved = False
               self._hand_rotation_axis = None
               self._hand_rotation_total_x = 0
               self._hand_rotation_total_y = 0
               hit_item = self._workbench_item_at(event.pos())
               if hit_item is not None:
                    self.selected_workbench_item = hit_item
                    self.workbench_item_selected.emit(hit_item)
               self.dragged_workbench_item = hit_item
               if hit_item is not None:
                    self._dragged_item_mode = (
                         "rotate"
                         if event.button() == Qt.RightButton
                         or self.item_interaction_mode == "rotate"
                         else "move"
                    )
                    if self._hand_drag_active:
                         projected_item = self._project_current_mesh({
                              index
                              for index, owner
                              in enumerate(self._mesh_vertex_owners or ())
                              if owner == hit_item
                         })
                         x_positions = [
                              point.x()
                              for point, _depth in projected_item.values()
                         ]
                         y_positions = [
                              point.y()
                              for point, _depth in projected_item.values()
                         ]
                         self._hand_rotation_screen_width = max(
                              1.0,
                              max(x_positions) - min(x_positions)
                              if x_positions
                              else float(self.width()),
                         )
                         self._hand_rotation_screen_height = max(
                              1.0,
                              max(y_positions) - min(y_positions)
                              if y_positions
                              else float(self.height()),
                         )
               else:
                    self._dragged_item_mode = None

     def mouseMoveEvent(self, event):
          if self.drag_position is None:
               return
          delta = event.pos() - self.drag_position
          self._drag_moved |= bool(delta.x() or delta.y())
          if self.dragged_workbench_item is not None:
               if (
                    self._hand_drag_active
                    and self.item_interaction_mode == "rotate"
               ):
                    self._rotate_held_item_on_drag_axis(
                         delta.x(), delta.y()
                    )
               elif self._dragged_item_mode == "rotate":
                    self.workbench_item_rotated.emit(
                         self.dragged_workbench_item,
                         delta.y() * 0.01,
                         delta.x() * 0.01,
                         0.0,
                    )
               else:
                    world_delta = self._screen_drag_to_world(delta)
                    self.workbench_item_dragged.emit(
                         self.dragged_workbench_item, *world_delta
                    )
          else:
               self.rotation -= delta.x() * 0.0032
               self.vertical_rotation += delta.y() * 0.0032
          self.drag_position = event.pos()
          self.update()

     def mouseReleaseEvent(self, event):
          if event.button() in (Qt.LeftButton, Qt.RightButton):
               if self.dragged_workbench_item is None and not self._drag_moved:
                    self.workbench_item_selected.emit(None)
               self.workbench_item_edit_finished.emit()
               self.drag_position = None
               self.dragged_workbench_item = None
               self._dragged_item_mode = None
               self._drag_moved = False
               self._hand_rotation_axis = None
               self._hand_rotation_total_x = 0
               self._hand_rotation_total_y = 0

     def wheelEvent(self, event):
          if self.item_interaction_mode == "rotate":
               item_index = self._workbench_item_at(event.pos())
               angle_delta = event.angleDelta().y()
               if item_index is not None and angle_delta:
                    self.selected_workbench_item = item_index
                    self.workbench_item_rotated.emit(
                         item_index,
                         0.0,
                         0.0,
                         angle_delta / 120 * 0.12,
                    )
                    event.accept()
                    return
          direction = 1.1 if event.angleDelta().y() > 0 else 0.9
          self.zoom = min(1.7, max(0.55, self.zoom * direction))
          self.update()
          event.accept()


class WorkspaceMeshLoadSignals(QObject):
     finished = pyqtSignal(int, str, object, object)


class WorkspaceMeshLoadTask(QRunnable):
     def __init__(self, request_id, path):
          super().__init__()
          self.request_id = request_id
          self.path = str(path)
          self.signals = WorkspaceMeshLoadSignals()

     def run(self):
          try:
               triangles, materials = (
                    WorkspaceFiles.load_mesh_for_workbench(self.path)
               )
               prepared_mesh = HologramCanvas.prepare_mesh(triangles)
               if materials is not None:
                    prepared_mesh = (*prepared_mesh, materials)
          except (OSError, ValueError) as error:
               self.signals.finished.emit(
                    self.request_id, self.path, None, error
               )
               return
          self.signals.finished.emit(
               self.request_id, self.path, prepared_mesh, None
          )


class AikoCoreWidget(QWidget):
     def __init__(self, parent=None):
          super().__init__(parent)
          self.is_responding = False
          self.speech_level = 0.0
          self.setFixedSize(104, 112)

     def set_responding(self, is_responding):
          if self.is_responding != is_responding:
               self.is_responding = is_responding
               self.update()

     def set_speech_level(self, level):
          level = min(1.0, max(0.0, float(level)))
          if abs(self.speech_level - level) >= 0.04:
               self.speech_level = level
               self.update()

     def paintEvent(self, event):
          painter = QPainter(self)
          painter.setRenderHint(QPainter.Antialiasing)
          painter.setRenderHint(QPainter.TextAntialiasing)
          _paint_aiko_core(
               painter,
               self.width() / 2,
               44,
               30,
               self.is_responding,
               self.speech_level,
          )


class WorkspaceAssistantStatus(QFrame):
     def __init__(self, parent=None):
          super().__init__(parent)
          self.setObjectName("workspaceAssistantStatus")
          self.setStyleSheet(
               "QFrame#workspaceAssistantStatus { "
               "background: rgba(3, 18, 30, 220); border: 1px solid #28758a; "
               "border-radius: 12px; }"
          )
          layout = QHBoxLayout(self)
          layout.setContentsMargins(8, 6, 12, 6)
          layout.setSpacing(8)
          self.aiko_core = AikoCoreWidget(self)
          layout.addWidget(self.aiko_core, 0, Qt.AlignVCenter)
          text_layout = QVBoxLayout()
          text_layout.setContentsMargins(0, 0, 0, 0)
          text_layout.setSpacing(1)
          self.name_label = QLabel("AIKO")
          self.name_label.setStyleSheet(
               "color: #c9fbff; font-size: 12px; font-weight: bold; "
               "border: none; background: transparent;"
          )
          self.assistant_status_label = QLabel("Available...")
          self.assistant_status_label.setStyleSheet(
               "color: #b6dce7; font-size: 11px; border: none; "
               "background: transparent;"
          )
          text_layout.addWidget(self.name_label)
          text_layout.addWidget(self.assistant_status_label)
          layout.addLayout(text_layout)
          self.microphone_status_label = QLabel("MIC OFF")
          self.microphone_status_label.setAlignment(Qt.AlignCenter)
          self.microphone_status_label.setStyleSheet(
               "color: #d7e5e9; background: #39464b; border: none; "
               "border-radius: 8px; padding: 4px 7px; font-size: 9px; "
               "font-weight: bold;"
          )
          layout.addWidget(self.microphone_status_label)
          self.setFixedSize(310, 128)


class WorkspaceScreen(QWidget):
     def __init__(self, parent=None):
          super().__init__(parent)
          WorkspaceFiles.ensure_workspace()
          self.project_type = "3D"
          self.current_folder = WorkspaceFiles.WORKSPACE_ROOT / "3D"
          self.selected_project = None
          self._last_synced_active_project = None
          self._mesh_load_generation = 0
          self._next_mesh_load_id = 0
          self._pending_mesh_generations = {}
          self._pending_mesh_projects = {}
          self._mesh_load_tasks = []
          self._workbench_items = []

          layout = QVBoxLayout(self)
          layout.setContentsMargins(28, 16, 28, 24)
          header = QHBoxLayout()
          title = QLabel("AIKO WORKSPACE")
          title.setStyleSheet("color: #c9fbff; font-size: 22px; font-weight: bold;")
          header.addWidget(title)
          header.addStretch(1)
          self.status_label = QLabel(
               "Click 3D designs or .brd boards to add them to the workbench."
          )
          self.status_label.setStyleSheet("color: #89d9e8;")
          header.addWidget(self.status_label)
          layout.addLayout(header)

          toolbar = QHBoxLayout()
          for label, callback in (
               ("Back", self._go_back),
               ("New Folder", self._create_folder),
               ("Import File", self._import_file),
               ("Add Tinkercad Link", self._add_tinkercad_link),
               ("New 3D Design", self._create_design),
               ("Add Part", self._add_part),
               ("Remove Part", self._remove_part),
               ("Move Part", self._move_part),
               ("Remove File", self._remove_file),
               ("Export STL", self._export_stl),
          ):
               button = QPushButton(label)
               button.clicked.connect(callback)
               toolbar.addWidget(button)
          layout.addLayout(toolbar)

          content_layout = QHBoxLayout()
          content_layout.setSpacing(18)
          self.folder_label = QLabel()
          self.folder_label.setStyleSheet("color: #b6dce7;")
          item_panel = QWidget()
          item_panel.setMinimumWidth(220)
          item_panel.setMaximumWidth(280)
          item_layout = QVBoxLayout(item_panel)
          item_layout.setContentsMargins(0, 0, 0, 0)
          item_layout.setSpacing(8)
          self.category_list = QListWidget()
          self.category_list.setViewMode(QListView.ListMode)
          self.category_list.setIconSize(QSize(28, 28))
          self.category_list.setMaximumHeight(104)
          self.category_list.setStyleSheet(
               "QListWidget { color: #e2f3f8; background: rgba(5,18,28,180); "
               "border: 1px solid #28758a; } "
               "QListWidget::item { padding: 6px; } "
               "QListWidget::item:selected { background: #13536a; }"
          )
          for project_type, label in (
               ("3D", "3D Designs"),
               ("Circuits", "Circuits"),
          ):
               category = QListWidgetItem(
                    self.style().standardIcon(QStyle.SP_DirIcon), label
               )
               category.setData(Qt.UserRole, project_type)
               self.category_list.addItem(category)
          self.category_list.itemClicked.connect(self._select_category)
          self.category_list.setCurrentRow(0)
          item_layout.addWidget(self.category_list)
          item_layout.addWidget(self.folder_label)
          self.project_list = QListWidget(self)
          self.project_list.setViewMode(QListView.ListMode)
          self.project_list.setFlow(QListView.TopToBottom)
          self.project_list.setWrapping(False)
          self.project_list.setMovement(QListView.Static)
          self.project_list.setDragDropMode(QAbstractItemView.NoDragDrop)
          self.project_list.setDragEnabled(False)
          self.project_list.setAcceptDrops(False)
          self.project_list.setIconSize(QSize(24, 24))
          self.project_list.setGridSize(QSize(220, 48))
          self.project_list.setWordWrap(False)
          self.project_list.setStyleSheet(
               "QListWidget { color: #e2f3f8; background: rgba(5,18,28,180); "
               "border: 1px solid #28758a; } "
               "QListWidget::item { padding: 6px; } "
               "QListWidget::item:selected { background: #13536a; }"
          )
          self.project_list.itemClicked.connect(self._open_project)
          item_layout.addWidget(self.project_list, 1)
          content_layout.addWidget(item_panel)

          self.viewer = HologramCanvas()
          content_layout.addWidget(self.viewer, 1)
          self.workbench_actions = QWidget()
          self.workbench_actions.setFixedWidth(210)
          actions_layout = QVBoxLayout(self.workbench_actions)
          actions_layout.setContentsMargins(0, 0, 0, 0)
          actions_layout.setSpacing(7)
          self.exit_focus_button = QPushButton("Exit Focus")
          self.exit_focus_button.clicked.connect(
               lambda: self._on_workbench_item_selected(None)
          )
          self.shrink_item_button = QPushButton("Shrink")
          self.shrink_item_button.clicked.connect(
               lambda: self._scale_selected_workbench_item(0.9)
          )
          self.enlarge_item_button = QPushButton("Enlarge")
          self.enlarge_item_button.clicked.connect(
               lambda: self._scale_selected_workbench_item(1.1)
          )
          self.rotate_axis_buttons = []
          for axis, axis_name in enumerate(("X", "Y", "Z")):
               row = QHBoxLayout()
               for direction, symbol in ((-1, "-"), (1, "+")):
                    button = QPushButton(f"{axis_name}{symbol}15")
                    button.setToolTip(
                         f"Rotate the focused hologram {symbol}15 degrees "
                         f"around the {axis_name} axis."
                    )
                    button.clicked.connect(
                         lambda _checked=False, axis=axis, direction=direction:
                         self._rotate_selected_workbench_axis(
                              axis, math.radians(15) * direction
                         )
                    )
                    self.rotate_axis_buttons.append(button)
                    row.addWidget(button)
               actions_layout.addLayout(row)
          self.add_selected_part_button = QPushButton("Add Part")
          self.add_selected_part_button.clicked.connect(self._add_part)
          self.remove_selected_part_button = QPushButton("Remove Part")
          self.remove_selected_part_button.clicked.connect(self._remove_part)
          self.remove_selected_hologram_button = QPushButton(
               "Remove Selected\nHologram"
          )
          self.remove_selected_hologram_button.clicked.connect(
               self._remove_selected_hologram
          )
          self.remove_last_button = QPushButton("Remove Last\nHologram")
          self.remove_last_button.clicked.connect(self._remove_last_hologram)
          self.combine_button = QPushButton("Snap && Combine")
          self.combine_button.clicked.connect(self._combine_holograms)
          self.clear_workbench_button = QPushButton("Clear\nWorkbench")
          self.clear_workbench_button.clicked.connect(self._clear_workbench)
          self.rotate_items_button = QPushButton("Rotate Selected")
          self.rotate_items_button.setCheckable(True)
          self.rotate_items_button.setToolTip(
               "Drag a hologram to move it. Enable Rotate Selected to rotate "
               "a hologram in place; right-drag also rotates."
          )
          self.rotate_items_button.toggled.connect(
               self._set_workbench_rotation_mode
          )
          for button in (
               self.exit_focus_button,
               self.shrink_item_button,
               self.enlarge_item_button,
               *self.rotate_axis_buttons,
               self.add_selected_part_button,
               self.remove_selected_part_button,
               self.remove_selected_hologram_button,
               self.rotate_items_button,
               self.remove_last_button,
               self.combine_button,
               self.clear_workbench_button,
          ):
               button.setMinimumHeight(36)
               button.setStyleSheet(
                    "QPushButton { color: #dffaff; background: #12485a; "
                    "border: 1px solid #2b98aa; border-radius: 6px; "
                    "font-weight: bold; } "
                    "QPushButton:hover { background: #1b6878; }"
               )
          for button in (
               self.exit_focus_button,
               self.shrink_item_button,
               self.enlarge_item_button,
               self.add_selected_part_button,
               self.remove_selected_part_button,
               self.remove_selected_hologram_button,
               self.rotate_items_button,
               self.remove_last_button,
               self.combine_button,
               self.clear_workbench_button,
          ):
               actions_layout.addWidget(button)
          actions_layout.addStretch(1)
          self.workbench_actions.hide()
          content_layout.addWidget(self.workbench_actions)
          layout.addLayout(content_layout, 1)
          self.assistant_status_panel = WorkspaceAssistantStatus(self)
          _image_selection_bridge.speech_level_changed.connect(
               self.assistant_status_panel.aiko_core.set_speech_level
          )
          self.assistant_status_panel.raise_()
          self.assistant_status_panel.show()
          self.viewer.workbench_item_dragged.connect(
               self._move_workbench_item
          )
          self.viewer.workbench_item_scaled.connect(
               self._scale_workbench_item
          )
          self.viewer.workbench_item_rotated.connect(
               self._rotate_workbench_item
          )
          self.viewer.workbench_item_selected.connect(
               self._on_workbench_item_selected
          )
          self.viewer.workbench_item_edit_finished.connect(
               self._save_workbench_transforms
          )
          self._refresh_projects()
          self.refresh_timer = QTimer(self)
          self.refresh_timer.timeout.connect(self._sync_active_project)
          self.refresh_timer.setInterval(3000)
          self.assistant_status_timer = QTimer(self)
          self.assistant_status_timer.timeout.connect(
               self._refresh_assistant_status
          )
          self.assistant_status_timer.setInterval(250)
          self._refresh_assistant_status()

     def showEvent(self, event):
          super().showEvent(event)
          self._position_assistant_status()
          self.refresh_timer.start()
          self.assistant_status_timer.start()
          self._sync_active_project()

     def hideEvent(self, event):
          self.refresh_timer.stop()
          self.assistant_status_timer.stop()
          super().hideEvent(event)

     def _refresh_assistant_status(self):
          assistant_status = GetAssistantStatus().strip() or "Available..."
          microphone_enabled = GetMicrophoneStatus().strip() == "True"
          self.assistant_status_panel.aiko_core.set_responding(
               assistant_status == "Answering..."
          )
          self.assistant_status_panel.assistant_status_label.setText(
               assistant_status
          )
          self.assistant_status_panel.microphone_status_label.setText(
               "MIC ON" if microphone_enabled else "MIC OFF"
          )
          microphone_color = "#15584d" if microphone_enabled else "#39464b"
          self.assistant_status_panel.microphone_status_label.setStyleSheet(
               "color: #d7e5e9; "
               f"background: {microphone_color}; "
               "border: none; border-radius: 8px; padding: 4px 7px; "
               "font-size: 9px; font-weight: bold;"
          )

     def _position_assistant_status(self):
          self.assistant_status_panel.move(
               28,
               max(
                    16,
                    self.height() - self.assistant_status_panel.height() - 112,
               ),
          )
          self.assistant_status_panel.raise_()

     def resizeEvent(self, event):
          super().resizeEvent(event)
          self._position_assistant_status()

     def _change_project_type(self, project_type):
          self.project_type = project_type
          self.current_folder = WorkspaceFiles.WORKSPACE_ROOT / project_type
          self.selected_project = None
          category_row = 0 if project_type == "3D" else 1
          self.category_list.setCurrentRow(category_row)
          self._refresh_projects()

     def _select_category(self, item):
          self._change_project_type(item.data(Qt.UserRole))

     def _refresh_projects(self):
          selected_path = (
               str(Path(self.selected_project["path"]).resolve())
               if self.selected_project is not None
               else None
          )
          self.project_list.clear()
          category_name = "3D Designs" if self.project_type == "3D" else "Circuits"
          relative_folder = self.current_folder.resolve().relative_to(
               (WorkspaceFiles.WORKSPACE_ROOT / self.project_type).resolve()
          )
          folder_path = (
               category_name
               if relative_folder == Path(".")
               else f"{category_name} / {relative_folder}"
          )
          self.folder_label.setText(folder_path)
          try:
               projects = WorkspaceFiles.list_projects(
                    self.project_type, self.current_folder
               )
          except (OSError, ValueError) as error:
               self.status_label.setText(f"Could not load workspace: {error}")
               return
          for project in projects:
               icon = {
                    "folder": "[Folder]",
                    "link": "[Tinkercad]",
                    "circuit": "[Circuit]",
                    "model": "[3D]",
               }.get(project["kind"], "[File]")
               item = QListWidgetItem(f"{icon}  {project['name']}")
               item.setData(Qt.UserRole, project)
               item.setFlags(
                    item.flags() & ~Qt.ItemIsDragEnabled & ~Qt.ItemIsDropEnabled
               )
               self.project_list.addItem(item)
          available_paths = {
               str(Path(self.project_list.item(index).data(Qt.UserRole)["path"]).resolve())
               for index in range(self.project_list.count())
          }
          if selected_path is not None and selected_path not in available_paths:
               self.selected_project = None
               self.viewer.set_mesh([])

     def _open_project(self, item):
          project = item.data(Qt.UserRole)
          self.selected_project = project
          if project["kind"] == "folder":
               self.current_folder = Path(project["path"])
               self._refresh_projects()
          elif project["kind"] == "link":
               if not QDesktopServices.openUrl(QUrl(project["url"])):
                    self.status_label.setText("Could not open the Tinkercad URL.")
               else:
                    self.status_label.setText(
                         "Opened Tinkercad link in your browser; cloud sync is unavailable."
                    )
          elif project["kind"] == "circuit":
               if Path(project["path"]).suffix.lower() == ".brd":
                    self._start_mesh_preview(project)
               elif not QDesktopServices.openUrl(QUrl.fromLocalFile(project["path"])):
                    self.status_label.setText("Could not open the circuit file.")
               else:
                    self.status_label.setText(f"Opened {project['name']}.")
          else:
               try:
                    WorkspaceFiles.set_active_project(project["path"])
               except (OSError, ValueError) as error:
                    self.viewer.set_mesh([])
                    self.status_label.setText(f"Could not open design: {error}")
                    return
               self._start_mesh_preview(project)

     def _start_mesh_preview(self, project):
          project_path = Path(project["path"]).resolve()
          if any(
               Path(entry["path"]).resolve() == project_path
               for entry in self._workbench_items
          ) or any(
               Path(pending["path"]).resolve() == project_path
               for pending in self._pending_mesh_projects.values()
          ):
               self.status_label.setText(
                    f"{project['name']} is already on the workbench."
               )
               return
          self._next_mesh_load_id += 1
          request_id = self._next_mesh_load_id
          self._pending_mesh_generations[request_id] = self._mesh_load_generation
          self._pending_mesh_projects[request_id] = project
          task = WorkspaceMeshLoadTask(request_id, project["path"])
          task.signals.finished.connect(self._on_mesh_loaded)
          self._mesh_load_tasks.append(task)
          if self._workbench_items:
               self.status_label.setText(
                    f"Adding {project['name']} to the workbench..."
               )
          else:
               self.status_label.setText(f"Opening {project['name']}...")
          QThreadPool.globalInstance().start(task)

     def _on_mesh_loaded(self, request_id, path, prepared_mesh, error):
          self._mesh_load_tasks = [
               task for task in self._mesh_load_tasks
               if task.request_id != request_id
          ]
          generation = self._pending_mesh_generations.pop(request_id, None)
          project = self._pending_mesh_projects.pop(request_id, None)
          if generation != self._mesh_load_generation or project is None:
               return
          if error is not None:
               self.status_label.setText(f"Could not add project: {error}")
               return
          triangles, vertices, indexed_triangles = prepared_mesh[:3]
          materials = prepared_mesh[3] if len(prepared_mesh) > 3 else None
          path = Path(path).resolve()
          try:
               saved_transform = WorkspaceFiles.load_workbench_transform(path)
          except (OSError, ValueError) as error:
               self.status_label.setText(
                    f"Could not restore hologram edits: {error}"
               )
               return
          dimensions = tuple(
               max(vertex[axis] for vertex in vertices)
               - min(vertex[axis] for vertex in vertices)
               for axis in range(3)
          ) if vertices else (0.0, 0.0, 0.0)
          reference_size = (
               self._workbench_items[0].get("reference_size")
               if self._workbench_items
               else saved_transform.get("reference_size")
               if saved_transform is not None
               else max(dimensions) or 1.0
          )
          item = {
               "path": str(Path(path).resolve()),
               "name": project["name"],
               "triangles": triangles,
               "prepared_mesh": prepared_mesh,
               "vertices": vertices,
               "materials": materials,
               "is_circuit": Path(path).suffix.lower() == ".brd",
               "offset": [0.0, 0.0, 0.0],
               "scale": 1.0,
               "rotation": [0.0, 0.0, 0.0],
               "reference_size": reference_size,
               "fit_scale": reference_size / (max(dimensions) or reference_size),
               "group_id": request_id,
          }
          if saved_transform is not None:
               item.update(saved_transform)
               item["reference_size"] = reference_size
               item["fit_scale"] = reference_size / (max(dimensions) or reference_size)
          elif self._workbench_items:
               self._place_new_workbench_item(item)
          self._workbench_items.append(item)
          self.viewer.selected_workbench_item = len(self._workbench_items) - 1
          self._refresh_workbench(reset_zoom=True, update_camera=True)
          self.status_label.setText(
               f"Workbench: {len(self._workbench_items)} project(s). "
               f"Added {project['name']}."
          )

     def _place_new_workbench_item(self, item):
          items = [*self._workbench_items, item]
          dimensions, _centers, base_centers, unit_scale = (
               self._workbench_layout(items)
          )
          if self._workbench_items:
               _selected_bounds, existing_bounds = self._workbench_item_bounds(0)
          else:
               existing_bounds = []
          rightmost_index = max(
               range(len(self._workbench_items)),
               key=lambda index: (
                    existing_bounds[index][0][0]
                    + existing_bounds[index][1][0]
               ),
          )
          right_edge = (
               existing_bounds[rightmost_index][0][0]
               + existing_bounds[rightmost_index][1][0]
          )
          new_index = len(self._workbench_items)
          item_center = base_centers[new_index]
          item["offset"] = [
               right_edge - item_center[0]
               + self._workbench_item_half_extents(
                    dimensions[new_index], unit_scale, item
               )[0],
               (
                    existing_bounds[rightmost_index][0][1]
                    - item_center[1]
               ),
               (
                    existing_bounds[rightmost_index][0][2]
                    - item_center[2]
               ),
          ]

     @staticmethod
     def _workbench_layout(items):
          dimensions = []
          centers = []
          for item in items:
               vertices = item.get("vertices")
               if vertices is None:
                    vertices = {
                         tuple(vertex)
                         for triangle in item["triangles"]
                         for vertex in triangle
                    }
               if not vertices:
                    dimensions.append((0.0, 0.0, 0.0))
                    centers.append((0.0, 0.0, 0.0))
                    continue
               mins = tuple(
                    min(vertex[axis] for vertex in vertices)
                    for axis in range(3)
               )
               maxs = tuple(
                    max(vertex[axis] for vertex in vertices)
                    for axis in range(3)
               )
               dimensions.append(tuple(
                    maxs[axis] - mins[axis] for axis in range(3)
               ))
               centers.append(tuple(
                    (mins[axis] + maxs[axis]) / 2 for axis in range(3)
               ))

          if not items:
               return dimensions, centers, [], 1.0
          unit_scale = (
               items[0].get("reference_size")
               or next((max(size) for size in dimensions if max(size) > 0), 1.0)
          )
          base_centers = []
          next_x = 0.0
          for index, item in enumerate(items):
               half_width = (
                    dimensions[index][0]
                    / unit_scale
                    * item.get("fit_scale", 1.0)
                    / 2
               )
               base_centers.append((next_x + half_width, 0.0, 0.0))
               next_x += half_width * 2
          return dimensions, centers, base_centers, unit_scale

     @staticmethod
     def _workbench_item_half_extents(dimensions, unit_scale, item):
          item_scale = (
               item.get("fit_scale", 1.0)
               * item.get("scale", 1.0)
               / unit_scale
          )
          half_dimensions = tuple(
               dimension * item_scale / 2 for dimension in dimensions
          )
          rotation_x, rotation_y, rotation_z = item.get(
               "rotation", (0.0, 0.0, 0.0)
          )
          cos_x, sin_x = math.cos(rotation_x), math.sin(rotation_x)
          cos_y, sin_y = math.cos(rotation_y), math.sin(rotation_y)
          cos_z, sin_z = math.cos(rotation_z), math.sin(rotation_z)
          rotated_corners = []
          for x in (-half_dimensions[0], half_dimensions[0]):
               for y in (-half_dimensions[1], half_dimensions[1]):
                    for z in (-half_dimensions[2], half_dimensions[2]):
                         rotated_corners.append(
                              WorkspaceScreen._rotate_group_vertex(
                                   (x, y, z),
                                   (0.0, 0.0, 0.0),
                                   cos_x,
                                   sin_x,
                                   cos_y,
                                   sin_y,
                                   cos_z,
                                   sin_z,
                              )
                         )
          return tuple(
               max(abs(vertex[axis]) for vertex in rotated_corners)
               for axis in range(3)
          )

     @staticmethod
     def _compose_workbench_mesh(items):
          if not items:
               return [], [], [], 1.0, (0.0, 0.0, 0.0), False
          _dimensions, centers, base_centers, unit_scale = (
               WorkspaceScreen._workbench_layout(items)
          )
          group_centers = {}
          group_counts = {}
          for index, item in enumerate(items):
               group_id = item["group_id"]
               position = tuple(
                    base_centers[index][axis] + item["offset"][axis]
                    for axis in range(3)
               )
               if group_id not in group_centers:
                    group_centers[group_id] = [0.0, 0.0, 0.0]
                    group_counts[group_id] = 0
               for axis in range(3):
                    group_centers[group_id][axis] += position[axis]
               group_counts[group_id] += 1
          for group_id, center in group_centers.items():
               group_centers[group_id] = tuple(
                    value / group_counts[group_id] for value in center
               )
          composed_triangles = []
          composed_materials = []
          triangle_owners = []
          for index, item in enumerate(items):
               base_center = base_centers[index]
               item_scale = (
                    item.get("fit_scale", 1.0) * item.get("scale", 1.0)
               )
               rotation_x, rotation_y, rotation_z = item.get(
                    "rotation", (0.0, 0.0, 0.0)
               )
               cos_x, sin_x = math.cos(rotation_x), math.sin(rotation_x)
               cos_y, sin_y = math.cos(rotation_y), math.sin(rotation_y)
               cos_z, sin_z = math.cos(rotation_z), math.sin(rotation_z)
               group_center = group_centers[item["group_id"]]
               for triangle_index, triangle in enumerate(item["triangles"]):
                    composed_triangles.append(tuple(
                         WorkspaceScreen._rotate_group_vertex(
                              tuple(
                                   (vertex[axis] - centers[index][axis])
                                   / unit_scale
                                   * item_scale
                                   + base_center[axis]
                                   + item["offset"][axis]
                                   for axis in range(3)
                              ),
                              group_center,
                              cos_x,
                              sin_x,
                              cos_y,
                              sin_y,
                              cos_z,
                              sin_z,
                         )
                         for vertex in triangle
                    ))
                    materials = item["materials"]
                    composed_materials.append(
                         materials[triangle_index]
                         if materials is not None
                         else "model"
                    )
                    triangle_owners.append(index)

          if not composed_triangles:
               return [], [], [], 1.0, (0.0, 0.0, 0.0), False
          scene_vertices = [
               vertex for triangle in composed_triangles for vertex in triangle
          ]
          scene_span = max(
               max(vertex[axis] for vertex in scene_vertices)
               - min(vertex[axis] for vertex in scene_vertices)
               for axis in range(3)
          ) or 1.0
          scene_center = tuple(
               (
                    min(vertex[axis] for vertex in scene_vertices)
                    + max(vertex[axis] for vertex in scene_vertices)
               ) / 2
               for axis in range(3)
          )
          fit_zoom = min(1.0, 1.35 / scene_span)
          return (
               composed_triangles,
               composed_materials,
               triangle_owners,
               fit_zoom,
               scene_center,
               any(item["is_circuit"] for item in items),
          )

     @staticmethod
     def _rotate_group_vertex(
          vertex,
          group_center,
          cos_x,
          sin_x,
          cos_y,
          sin_y,
          cos_z,
          sin_z,
     ):
          x, y, z = (
               vertex[axis] - group_center[axis]
               for axis in range(3)
          )
          y, z = y * cos_x - z * sin_x, y * sin_x + z * cos_x
          x, z = x * cos_y + z * sin_y, -x * sin_y + z * cos_y
          x, y = x * cos_z - y * sin_z, x * sin_z + y * cos_z
          return (
               x + group_center[0],
               y + group_center[1],
               z + group_center[2],
          )

     def _refresh_workbench(self, reset_zoom=False, update_camera=False):
          if update_camera or self.viewer._workbench_items is None:
               if self._workbench_items:
                    _dimensions, centers, base_centers, unit_scale = (
                         self._workbench_layout(self._workbench_items)
                    )
                    self.viewer.set_workbench_mesh(
                         self._workbench_items,
                         centers,
                         base_centers,
                         unit_scale,
                         reset_zoom,
                    )
               else:
                    self.viewer.set_mesh([])
                    self.viewer.set_triangle_materials(None)
                    self.viewer.set_workbench_triangle_owners(None)
                    self.viewer.set_circuit_mode(False)
                    self.viewer.set_auto_fit_zoom(1.0, reset_zoom=True)
                    self.viewer.set_scene_center((0.0, 0.0, 0.0))
                    self.viewer.set_workbench_item_count(0)
          else:
               self.viewer.set_workbench_transforms(self._workbench_items)
          self.workbench_actions.setVisible(bool(self._workbench_items))
          self._update_workbench_controls()

     def _update_workbench_controls(self):
          focused_index = self.viewer.focused_workbench_item
          focused_item = (
               self._workbench_items[focused_index]
               if focused_index is not None
               and 0 <= focused_index < len(self._workbench_items)
               else None
          )
          has_focus = focused_item is not None
          editable = (
               has_focus
               and Path(focused_item["path"]).suffix.lower() == ".aiko3d"
          )
          for button in (
               self.shrink_item_button,
               self.enlarge_item_button,
               *self.rotate_axis_buttons,
          ):
               button.setEnabled(has_focus)
          self.exit_focus_button.setEnabled(has_focus)
          self.add_selected_part_button.setEnabled(editable)
          self.remove_selected_part_button.setEnabled(editable)
          self.remove_selected_hologram_button.setEnabled(
               self.viewer.selected_workbench_item is not None
          )
          self.rotate_items_button.setEnabled(bool(self._workbench_items))
          self.remove_last_button.setEnabled(bool(self._workbench_items))
          self.combine_button.setEnabled(len(self._workbench_items) > 1)
          self.clear_workbench_button.setEnabled(bool(self._workbench_items))

     def _on_workbench_item_selected(self, item_index):
          if item_index == self.viewer.focused_workbench_item:
               return
          if self.viewer.focused_workbench_item is not None:
               self._save_workbench_transforms()
          self.viewer.set_workbench_focus(item_index)
          self._update_workbench_controls()
          if item_index is None:
               self.status_label.setText(
                    "Workbench view restored. Hologram edits were saved."
               )
          else:
               item = self._workbench_items[item_index]
               self.status_label.setText(
                    f"Focused {item['name']}. Other holograms remain in the workbench."
               )

     def _save_workbench_transforms(self):
          if not self._workbench_items:
               return
          transforms = {
               item["path"]: {
                    "offset": item["offset"],
                    "scale": item.get("scale", 1.0),
                    "rotation": item.get("rotation", [0.0, 0.0, 0.0]),
                    "reference_size": item.get("reference_size", 1.0),
                    "fit_scale": item.get("fit_scale", 1.0),
               }
               for item in self._workbench_items
          }
          try:
               WorkspaceFiles.save_workbench_transforms(transforms)
          except (OSError, ValueError) as error:
               self.status_label.setText(f"Could not save hologram edits: {error}")
               return

     def _scale_selected_workbench_item(self, scale_factor):
          item_index = self.viewer.focused_workbench_item
          if item_index is None:
               return
          self._scale_workbench_item(item_index, scale_factor)
          self._save_workbench_transforms()

     def _rotate_selected_workbench_axis(self, axis, angle):
          item_index = self.viewer.focused_workbench_item
          if item_index is None:
               return
          delta = [0.0, 0.0, 0.0]
          delta[axis] = angle
          self._rotate_workbench_item(item_index, *delta)
          self._save_workbench_transforms()

     def _workbench_item_bounds(self, item_index):
          items = self._workbench_items
          dimensions, _centers, base_centers, unit_scale = (
               self._workbench_layout(items)
          )
          bounds = [None] * len(items)
          if (
               self.viewer._mesh_vertex_owners is not None
               and self.viewer._workbench_items is items
          ):
               vertices_by_owner = [[] for _ in items]
               for owner, vertex in zip(
                    self.viewer._mesh_vertex_owners,
                    self.viewer._workbench_world_vertices(),
               ):
                    vertices_by_owner[owner].append(vertex)
               for index, vertices in enumerate(vertices_by_owner):
                    if vertices:
                         mins = tuple(
                              min(vertex[axis] for vertex in vertices)
                              for axis in range(3)
                         )
                         maxs = tuple(
                              max(vertex[axis] for vertex in vertices)
                              for axis in range(3)
                         )
                         bounds[index] = (
                              tuple(
                                   (mins[axis] + maxs[axis]) / 2
                                   for axis in range(3)
                              ),
                              tuple(
                                   (maxs[axis] - mins[axis]) / 2
                                   for axis in range(3)
                              ),
                         )
          for index, entry in enumerate(items):
               if bounds[index] is not None:
                    continue
               center = tuple(
                    base_centers[index][axis] + entry["offset"][axis]
                    for axis in range(3)
               )
               half = self._workbench_item_half_extents(
                    dimensions[index], unit_scale, entry
               )
               bounds[index] = (center, half)
          return bounds[item_index], bounds

     @staticmethod
     def _combined_bounds(item_indices, bounds):
          mins = tuple(
               min(bounds[index][0][axis] - bounds[index][1][axis]
                   for index in item_indices)
               for axis in range(3)
          )
          maxs = tuple(
               max(bounds[index][0][axis] + bounds[index][1][axis]
                   for index in item_indices)
               for axis in range(3)
          )
          return (
               tuple((mins[axis] + maxs[axis]) / 2 for axis in range(3)),
               tuple((maxs[axis] - mins[axis]) / 2 for axis in range(3)),
          )

     def _move_workbench_item(self, item_index, delta_x, delta_y, delta_z):
          if item_index < 0 or item_index >= len(self._workbench_items):
               return
          item = self._workbench_items[item_index]
          group_id = item["group_id"]
          for entry in self._workbench_items:
               if entry["group_id"] == group_id:
                    entry["offset"][0] += delta_x
                    entry["offset"][1] += delta_y
                    entry["offset"][2] += delta_z
          self._refresh_workbench()

     def _scale_workbench_item(self, item_index, scale_factor):
          if item_index < 0 or item_index >= len(self._workbench_items):
               return
          item = self._workbench_items[item_index]
          group_id = item["group_id"]
          for entry in self._workbench_items:
               if entry["group_id"] == group_id:
                    entry["scale"] = min(
                         10.0,
                         max(0.1, entry.get("scale", 1.0) * scale_factor),
                    )
          self._refresh_workbench()

     def _rotate_workbench_item(
          self, item_index, delta_x, delta_y, delta_z
     ):
          if item_index < 0 or item_index >= len(self._workbench_items):
               return
          item = self._workbench_items[item_index]
          group_id = item["group_id"]
          for entry in self._workbench_items:
               if entry["group_id"] == group_id:
                    rotation = entry.setdefault(
                         "rotation", [0.0, 0.0, 0.0]
                    )
                    rotation[0] += delta_x
                    rotation[1] += delta_y
                    rotation[2] += delta_z
          self._refresh_workbench()

     def _set_workbench_rotation_mode(self, enabled):
          mode = "rotate" if enabled else "move"
          self.viewer.set_item_interaction_mode(mode)
          self.rotate_items_button.setText(
               "Move Selected" if enabled else "Rotate Selected"
          )
          self.status_label.setText(
               "Rotate mode: drag a hologram to rotate it in place; drag "
               "empty space to orbit. Use the mouse wheel to roll."
               if enabled
               else "Move mode: drag a hologram to reposition it; drag "
               "empty space to orbit."
          )

     def _remove_last_hologram(self):
          if not self._workbench_items:
               return
          removed_index = len(self._workbench_items) - 1
          removed = self._workbench_items.pop()
          if self.viewer.focused_workbench_item == removed_index:
               self.viewer.focused_workbench_item = None
          if self.viewer.focused_workbench_item is not None and (
               self.viewer.focused_workbench_item >= len(self._workbench_items)
          ):
               self.viewer.focused_workbench_item = None
          if self.viewer.selected_workbench_item is not None and (
               self.viewer.selected_workbench_item >= len(self._workbench_items)
          ):
               self.viewer.selected_workbench_item = (
                    len(self._workbench_items) - 1
                    if self._workbench_items
                    else None
               )
          self._refresh_workbench(reset_zoom=True, update_camera=True)
          self.status_label.setText(
               f"Removed the most recent hologram: {removed['name']}."
          )

     def _combine_holograms(self):
          if len(self._workbench_items) < 2:
               return
          moving_index = self.viewer.selected_workbench_item
          if moving_index is None or moving_index >= len(self._workbench_items):
               moving_index = len(self._workbench_items) - 1
          moving_item = self._workbench_items[moving_index]
          moving_group = moving_item["group_id"]
          _moving_item_bounds, all_bounds = self._workbench_item_bounds(
               moving_index
          )
          moving_indices = [
               index
               for index, entry in enumerate(self._workbench_items)
               if entry["group_id"] == moving_group
          ]
          moving_bounds = self._combined_bounds(moving_indices, all_bounds)
          moving_center, moving_half = moving_bounds
          target_groups = {}
          for index, entry in enumerate(self._workbench_items):
               if entry["group_id"] != moving_group:
                    target_groups.setdefault(entry["group_id"], []).append(index)
          if not target_groups:
               self.status_label.setText("These holograms are already combined.")
               return
          target_group = min(
               target_groups,
               key=lambda group_id: sum(
                    (
                         moving_center[axis]
                         - self._combined_bounds(
                              target_groups[group_id], all_bounds
                         )[0][axis]
                    ) ** 2
                    for axis in range(3)
               ),
          )
          target_center, target_half = self._combined_bounds(
               target_groups[target_group], all_bounds
          )
          axis_options = []
          for axis in range(3):
               separation = moving_center[axis] - target_center[axis]
               direction = 1.0 if separation >= 0 else -1.0
               half_span = target_half[axis] + moving_half[axis]
               touching_center = (
                    target_center[axis]
                    + direction * half_span
               )
               axis_options.append((
                    abs(separation) / max(half_span, 1e-6),
                    axis,
                    touching_center - moving_center[axis],
               ))
          _, snap_axis, snap_delta = max(axis_options)
          delta = [0.0, 0.0, 0.0]
          delta[snap_axis] = snap_delta
          for entry in self._workbench_items:
               if entry["group_id"] == moving_group:
                    for axis in range(3):
                         entry["offset"][axis] += delta[axis]
                         entry["group_id"] = target_group
          self._refresh_workbench(reset_zoom=True, update_camera=True)
          self._save_workbench_transforms()
          self.status_label.setText(
               "Snapped the holograms together as one movable assembly."
          )

     def _remove_selected_hologram(self):
          item_index = self.viewer.focused_workbench_item
          if item_index is None:
               item_index = self.viewer.selected_workbench_item
          if item_index is None or not 0 <= item_index < len(self._workbench_items):
               return
          removed = self._workbench_items[item_index]
          self._save_workbench_transforms()
          self.viewer.focused_workbench_item = None
          self.viewer.selected_workbench_item = None
          self._workbench_items.pop(item_index)
          self._refresh_workbench(reset_zoom=True, update_camera=True)
          self.status_label.setText(
               f"Removed {removed['name']} from the workbench; its file was kept."
          )

     def _clear_workbench(self):
          self._mesh_load_generation += 1
          self._workbench_items.clear()
          self._pending_mesh_generations.clear()
          self._pending_mesh_projects.clear()
          self.viewer.set_circuit_mode(False)
          self.viewer.set_mesh([])
          self.viewer.set_triangle_materials(None)
          self.viewer.set_auto_fit_zoom(1.0, reset_zoom=True)
          self.viewer.set_workbench_item_count(0)
          self.viewer.set_workbench_triangle_owners(None)
          self.viewer.set_scene_center((0.0, 0.0, 0.0))
          self.viewer.selected_workbench_item = None
          self.viewer.focused_workbench_item = None
          self.workbench_actions.hide()
          self._update_workbench_controls()
          self.status_label.setText("Workbench cleared.")

     def _go_back(self):
          root = WorkspaceFiles.WORKSPACE_ROOT / self.project_type
          if self.current_folder.resolve() != root.resolve():
               self.selected_project = None
               self.current_folder = self.current_folder.parent
               self._refresh_projects()

     def _create_folder(self):
          name, accepted = QInputDialog.getText(self, "New folder", "Folder name:")
          if not accepted or not name.strip():
               return
          try:
               WorkspaceFiles.create_folder(
                    name, self.project_type, self.current_folder
               )
          except (FileExistsError, OSError, ValueError) as error:
               self.status_label.setText(f"Could not create folder: {error}")
               return
          self._refresh_projects()

     def _import_file(self):
          if self.project_type == "3D":
               file_filter = "3D designs (*.obj *.stl)"
          else:
               file_filter = "Circuit files (*.aikocircuit *.brd *.circ *.ino *.json *.txt)"
          file_path, _ = QFileDialog.getOpenFileName(
               self, "Import workspace file", "", file_filter
          )
          if not file_path:
               return
          try:
               imported_path = WorkspaceFiles.import_project(
                    file_path, self.project_type, self.current_folder
               )
          except (OSError, ValueError) as error:
               self.status_label.setText(f"Could not import file: {error}")
               return
          self._refresh_projects()
          if imported_path.suffix.lower() in {".obj", ".stl"}:
               self._select_path(imported_path)
          self.status_label.setText(f"Imported {imported_path.name}")

     def _add_tinkercad_link(self):
          name, accepted = QInputDialog.getText(
               self, "Tinkercad link", "Project name:"
          )
          if not accepted or not name.strip():
               return
          url, accepted = QInputDialog.getText(
               self, "Tinkercad link", "Public design URL:"
          )
          if not accepted:
               return
          try:
               WorkspaceFiles.add_external_project(
                    name, url.strip(), self.project_type, self.current_folder
               )
          except (FileExistsError, OSError, ValueError) as error:
               self.status_label.setText(f"Could not add link: {error}")
               return
          self._refresh_projects()

     def _create_design(self):
          prompt, accepted = QInputDialog.getText(
               self,
               "New 3D design",
               "Describe any 3D object or scene for AI generation:",
          )
          if not accepted or not prompt.strip():
               return
          try:
               self._create_design_from_prompt(prompt)
          except (OSError, RuntimeError, ValueError) as error:
               self.status_label.setText(f"Could not create design: {error}")

     def _create_design_from_prompt(self, prompt):
          if self.project_type != "3D":
               self._change_project_type("3D")
          path = WorkspaceFiles.create_design(prompt, self.current_folder)
          self._refresh_projects()
          self._select_path(path)
          self.status_label.setText(
               "Created an editable AI-generated AIKO design."
          )
          return path

     def _select_path(self, path):
          normalized_path = str(Path(path).resolve())
          for index in range(self.project_list.count()):
               item = self.project_list.item(index)
               project = item.data(Qt.UserRole)
               if str(Path(project["path"]).resolve()) == normalized_path:
                    self.project_list.setCurrentItem(item)
                    self._open_project(item)
                    return

     def _add_part(self):
          design = self._selected_parametric_design()
          if design is None:
               return
          shape, accepted = QInputDialog.getItem(
               self, "Add part", "Primitive:", ("box", "sphere", "cylinder"), 0, False
          )
          if not accepted:
               return
          path = self._selected_parametric_path()
          try:
               WorkspaceFiles.add_part(path, shape)
               if not self._reload_workbench_design(path):
                    self._select_project_path()
          except (OSError, ValueError) as error:
               self.status_label.setText(f"Could not add part: {error}")

     def _remove_part(self):
          design = self._selected_parametric_design()
          if design is None:
               return
          parts = design["parts"]
          labels = [str(part.get("name", f"Part {index + 1}")) for index, part in enumerate(parts)]
          choice, accepted = QInputDialog.getItem(
               self, "Remove part", "Choose part:", labels, len(labels) - 1, False
          )
          if not accepted:
               return
          path = self._selected_parametric_path()
          try:
               WorkspaceFiles.remove_part(
                    path, labels.index(choice)
               )
               if not self._reload_workbench_design(path):
                    self._select_project_path()
          except (IndexError, OSError, ValueError) as error:
               self.status_label.setText(f"Could not remove part: {error}")

     def _move_part(self):
          design = self._selected_parametric_design()
          if design is None:
               return
          labels = [str(part.get("name", f"Part {index + 1}")) for index, part in enumerate(design["parts"])]
          choice, accepted = QInputDialog.getItem(
               self, "Move part", "Choose part:", labels, 0, False
          )
          if not accepted:
               return
          axis, accepted = QInputDialog.getItem(
               self, "Move part", "Axis:", ("x", "y", "z"), 0, False
          )
          if not accepted:
               return
          distance, accepted = QInputDialog.getDouble(
               self, "Move part", f"New {axis} position:", decimals=2
          )
          if not accepted:
               return
          index = labels.index(choice)
          design["parts"][index]["position"]["xyz".index(axis)] = distance
          path = self._selected_parametric_path()
          try:
               WorkspaceFiles.save_design(path, design)
               if not self._reload_workbench_design(path):
                    self._select_project_path()
          except (OSError, ValueError) as error:
               self.status_label.setText(f"Could not move part: {error}")

     def _remove_file(self):
          item = self.project_list.currentItem()
          if item is None:
               self.status_label.setText("Select a workspace file to remove.")
               return
          project = item.data(Qt.UserRole)
          if project["kind"] == "folder":
               self.status_label.setText("Select a file, not a folder.")
               return
          confirmation = QMessageBox.question(
               self,
               "Remove workspace file?",
               f"Move {project['name']} to the recoverable workspace trash?",
               QMessageBox.Yes | QMessageBox.No,
               QMessageBox.No,
          )
          if confirmation != QMessageBox.Yes:
               return
          try:
               WorkspaceFiles.remove_project(project["path"])
          except (OSError, ValueError) as error:
               self.status_label.setText(f"Could not remove file: {error}")
               return
          self.selected_project = None
          self.viewer.set_mesh([])
          self._refresh_projects()
          self.status_label.setText(f"Moved {project['name']} into workspace trash.")

     def _export_stl(self):
          if not self._selected_parametric_design():
               return
          default_name = f"{Path(self.selected_project['path']).stem}.stl"
          output_path, _ = QFileDialog.getSaveFileName(
               self, "Export STL", default_name, "STL mesh (*.stl)"
          )
          if not output_path:
               return
          try:
               WorkspaceFiles.export_design_to_stl(
                    self.selected_project["path"], output_path
               )
          except (OSError, ValueError) as error:
               self.status_label.setText(f"Could not export STL: {error}")
               return
          self.status_label.setText("Exported STL. Import it into Tinkercad manually.")

     def _selected_parametric_design(self):
          path = self._selected_parametric_path()
          if path is None:
               self.status_label.setText("Select an editable AIKO .aiko3d project first.")
               return None
          try:
               return WorkspaceFiles.load_design(path)
          except (OSError, ValueError) as error:
               self.status_label.setText(f"Could not load project parts: {error}")
               return None

     def _selected_parametric_path(self):
          focused_index = self.viewer.focused_workbench_item
          item_index = (
               focused_index
               if focused_index is not None
               else self.viewer.selected_workbench_item
          )
          if item_index is not None:
               if not 0 <= item_index < len(self._workbench_items):
                    return None
               path = self._workbench_items[item_index]["path"]
               return path if Path(path).suffix.lower() == ".aiko3d" else None
          if (
               self.selected_project is None
               or self.selected_project["kind"] != "model"
               or Path(self.selected_project["path"]).suffix.lower() != ".aiko3d"
          ):
               return None
          return self.selected_project["path"]

     def _reload_workbench_design(self, path):
          target = Path(path).resolve()
          item_index = next(
               (
                    index for index, item in enumerate(self._workbench_items)
                    if Path(item["path"]).resolve() == target
               ),
               None,
          )
          if item_index is None:
               return False
          triangles, materials = WorkspaceFiles.load_mesh_for_workbench(target)
          prepared_mesh = HologramCanvas.prepare_mesh(triangles)
          if materials is not None:
               prepared_mesh = (*prepared_mesh, materials)
          _triangles, vertices, _indexed_triangles = prepared_mesh[:3]
          item = self._workbench_items[item_index]
          dimensions = tuple(
               max(vertex[axis] for vertex in vertices)
               - min(vertex[axis] for vertex in vertices)
               for axis in range(3)
          ) if vertices else (0.0, 0.0, 0.0)
          reference_size = item.get("reference_size", max(dimensions) or 1.0)
          item.update({
               "triangles": triangles,
               "prepared_mesh": prepared_mesh,
               "vertices": vertices,
               "materials": materials,
               "reference_size": reference_size,
               "fit_scale": reference_size / (max(dimensions) or reference_size),
          })
          self._refresh_workbench(update_camera=True)
          self._save_workbench_transforms()
          self.status_label.setText(f"Updated {item['name']} in the workbench.")
          return True

     def _select_project_path(self):
          self._refresh_projects()
          if self.selected_project is not None:
               self._select_path(self.selected_project["path"])

     def refresh_workspace(self):
          self._refresh_projects()
          self._sync_active_project()

     def handle_voice_command(self, request):
          try:
               request["result"] = self._execute_voice_command(
                    request["action"], request.get("payload", "")
               )
          except Exception as error:
               request["error"] = str(error)
               print(
                    f"[ERROR] Workspace voice command failed "
                    f"({type(error).__name__}): {error}",
                    flush=True,
               )
          finally:
               request["completed"].set()

     def _execute_voice_command(self, action, payload):
          if action not in {"current_folder", "close_workspace", "describe"}:
                self.show_workspace()
          if action == "current_folder":
               return str(self.current_folder)
          if action == "describe":
               return self._describe_workspace()
          if action == "create":
               if not payload:
                    return "What would you like me to create as a 3D design?"
               path = self._create_design_from_prompt(payload)
               return (
                    f"Created {path.name} and added it to the workbench."
               )
          if action == "open":
               self.show_workspace()
               return "Opened the workspace."
          if action == "close_workspace":
               self.window().centralWidget().setCurrentWidget(
                    self.window().conversation_map_screen
               )
               return "Closed the workspace view. Your project files are unchanged."
          if action == "switch_type":
               self._change_project_type(payload)
               return f"Switched to the {payload} workspace."
          if action == "back":
               self._go_back()
               return "Moved to the parent workspace folder."
          if action == "create_folder":
               if not payload:
                    return "What should I name the new folder?"
               path = WorkspaceFiles.create_folder(
                    payload, self.project_type, self.current_folder
               )
               self._refresh_projects()
               return f"Created the folder {path.name}."
          if action == "open_project":
               if not payload:
                    return "Which project or folder should I open?"
               path = self._find_workspace_entry(payload)
               if path.is_dir():
                    project_type = self._project_type_for_path(path)
                    self._change_project_type(project_type)
                    self.current_folder = path
                    self._refresh_projects()
                    return f"Opened the folder {path.name}."
               project_type = self._project_type_for_path(path)
               self._change_project_type(project_type)
               self.current_folder = path.parent
               self._refresh_projects()
               self._select_path(path)
               return f"Opened {path.name} in the workspace."
          if action == "close_project":
               if (
                    not payload
                    and self.viewer.focused_workbench_item is None
                    and self.viewer.selected_workbench_item is None
                    and self.selected_project is None
               ):
                    return "Which project should I close from the workbench?"
               self._close_workspace_project(payload)
               return "Closed the project in the workbench. Its file was kept."
          if action == "remove_file":
               if not payload:
                    return "Which workspace file should I move to the recoverable trash?"
               path = WorkspaceFiles.find_project(payload)
               self._close_workspace_project(str(path))
               removed_path = WorkspaceFiles.remove_project(path)
               self._refresh_projects()
               return (
                    f"Moved {path.name} to the recoverable workspace trash "
                    f"({removed_path.parent.name})."
               )
          if action == "focus_project":
               index = self._find_workbench_item(payload)
               self._on_workbench_item_selected(index)
               return f"Focused {self._workbench_items[index]['name']}."
          if action in {"shrink", "enlarge", "rotate"}:
               index = self._selected_or_focused_workbench_item()
               if action == "shrink":
                    self._scale_selected_workbench_item(0.9)
               elif action == "enlarge":
                    self._scale_selected_workbench_item(1.1)
               else:
                    axis, degrees = payload.split()
                    self._rotate_selected_workbench_axis(
                         "xyz".index(axis), math.radians(float(degrees))
                    )
               return f"Updated {self._workbench_items[index]['name']}."
          if action == "exit_focus":
               self._on_workbench_item_selected(None)
               return "Exited hologram focus."
          if action == "toggle_rotation":
               self.rotate_items_button.setChecked(
                    not self.rotate_items_button.isChecked()
               )
               return "Toggled hologram rotation mode."
          if action == "combine":
               if len(self._workbench_items) < 2:
                    raise ValueError("Add at least two holograms before combining them.")
               self._combine_holograms()
               return "Snapped the holograms together."
          if action == "clear_workbench":
               self._clear_workbench()
               return "Cleared the workbench. Project files were not deleted."
          if action == "remove_last_hologram":
               if not self._workbench_items:
                    raise ValueError("There are no holograms on the workbench.")
               self._remove_last_hologram()
               return "Removed the last hologram from the workbench."
          if action == "remove_selected_hologram":
               index = self.viewer.focused_workbench_item
               if index is None:
                    index = self.viewer.selected_workbench_item
               if index is None:
                    raise ValueError("Select or focus a hologram first.")
               self._remove_selected_hologram()
               return "Removed the selected hologram from the workbench."
          if action == "add_part":
               path = self._selected_parametric_path()
               if path is None:
                    raise ValueError("Select or focus an editable AIKO 3D project first.")
               if not payload:
                    return "What part should I add: a box, sphere, or cylinder?"
               if payload not in WorkspaceFiles.PRIMITIVES:
                    raise ValueError(
                         "Say add a box, add a sphere, or add a cylinder."
                    )
               WorkspaceFiles.add_part(path, payload)
               if not self._reload_workbench_design(path):
                    self._select_project_path()
               return f"Added a {payload} part."
          if action == "remove_part":
               path = self._selected_parametric_path()
               if path is None:
                    raise ValueError("Select or focus an editable AIKO 3D project first.")
               design = WorkspaceFiles.load_design(path)
               removed = WorkspaceFiles.remove_part(
                    path, len(design["parts"]) - 1
               )
               if not self._reload_workbench_design(path):
                    self._select_project_path()
               return f"Removed {removed['name']}."
          if action == "move_part":
               if not payload:
                    return (
                         "Which part should I move, along which X, Y, or Z axis, "
                         "and to what position?"
                    )
               path = self._selected_parametric_path()
               if path is None:
                    raise ValueError("Select or focus an editable AIKO 3D project first.")
               name, axis, distance = payload.split("|")
               design = WorkspaceFiles.load_design(path)
               matching_parts = [
                    part for part in design["parts"]
                    if str(part.get("name", "")).casefold() == name.casefold()
               ]
               if len(matching_parts) != 1:
                    raise ValueError(f"Could not identify one part named {name!r}.")
               matching_parts[0]["position"]["xyz".index(axis)] = float(distance)
               WorkspaceFiles.save_design(path, design)
               if not self._reload_workbench_design(path):
                    self._select_project_path()
               return f"Moved {name} along the {axis.upper()} axis."
          if action == "import_file":
               if not payload:
                    return "What is the full path of the file to import?"
               path = WorkspaceFiles.import_project(
                    payload, self.project_type, self.current_folder
               )
               self._refresh_projects()
               self._select_path(path)
               return f"Imported {path.name}."
          if action == "add_link":
               if not payload:
                    return "What is the Tinkercad project name and URL?"
               name, url = payload.split("|", 1)
               path = WorkspaceFiles.add_external_project(
                    name, url, self.project_type, self.current_folder
               )
               self._refresh_projects()
               return f"Added the Tinkercad link {path.name}."
          if action == "export_stl":
               path = self._selected_parametric_path()
               if path is None:
                    raise ValueError("Select or focus an editable AIKO 3D project first.")
               output_path = Path(path).with_suffix(".stl")
               suffix = 2
               while output_path.exists():
                    output_path = Path(path).with_name(
                         f"{Path(path).stem}_{suffix}.stl"
                    )
                    suffix += 1
               WorkspaceFiles.export_design_to_stl(path, output_path)
               return f"Exported {output_path.name}."
          raise ValueError(f"Unsupported workspace voice command: {action}.")

     def _describe_workspace(self):
          WorkspaceFiles.ensure_workspace()
          lines = [
               "AIKO Workspace status:",
               f"Current view: {self.project_type} / "
               f"{self.current_folder.resolve().relative_to((WorkspaceFiles.WORKSPACE_ROOT / self.project_type).resolve())}",
          ]
          for project_type, label in (("3D", "3D Designs"), ("Circuits", "Circuits")):
               root = (WorkspaceFiles.WORKSPACE_ROOT / project_type).resolve()
               lines.append(f"{label}:")
               entries = sorted(
                    (
                         path for path in root.rglob("*")
                         if not any(
                              part.startswith(".")
                              for part in path.relative_to(root).parts
                         )
                         and (path.is_dir() or path.is_file())
                    ),
                    key=lambda path: (
                         len(path.relative_to(root).parts),
                         str(path.relative_to(root)).casefold(),
                    ),
               )
               if not entries:
                    lines.append("- empty")
               else:
                    lines.extend(
                         f"- {path.relative_to(root)}"
                         f"{' (folder)' if path.is_dir() else ''}"
                         for path in entries
                    )

          if self._workbench_items:
               lines.append("Workbench holograms:")
               focused_index = self.viewer.focused_workbench_item
               selected_index = self.viewer.selected_workbench_item
               for index, item in enumerate(self._workbench_items):
                    state = (
                         " (focused)"
                         if index == focused_index
                         else " (selected)"
                         if index == selected_index
                         else ""
                    )
                    item_path = Path(item["path"]).resolve()
                    offset = item.get("offset", [0.0, 0.0, 0.0])
                    rotation = [
                         round(math.degrees(float(value)), 1)
                         for value in item.get("rotation", [0.0, 0.0, 0.0])
                    ]
                    detail = (
                         f"- {item['name']}{state}; "
                         f"source: {item_path.relative_to(WorkspaceFiles.WORKSPACE_ROOT.resolve())}; "
                         f"offset: {offset}; scale: {item.get('scale', 1.0):.2f}; "
                         f"rotation XYZ: {rotation} degrees"
                    )
                    if item_path.suffix.lower() == ".aiko3d":
                         design = WorkspaceFiles.load_design(item_path)
                         part_names = [
                              str(part.get("name", f"Part {part_index + 1}"))
                              for part_index, part in enumerate(design["parts"])
                         ]
                         detail += f"; parts: {', '.join(part_names)}"
                    else:
                         detail += (
                              f"; mesh triangles: "
                              f"{len(item.get('triangles', []))}"
                         )
                    lines.append(detail)
          else:
               lines.append("Workbench: empty")

          if self.selected_project is not None:
               lines.append(f"Open project: {self.selected_project['name']}")
          return "\n".join(lines)

     def _project_type_for_path(self, path):
          resolved = Path(path).resolve()
          for project_type in WorkspaceFiles.PROJECT_TYPES:
               if resolved.is_relative_to(
                    (WorkspaceFiles.WORKSPACE_ROOT / project_type).resolve()
               ):
                    if resolved.is_file():
                         suffix = resolved.suffix.lower()
                         if (
                              suffix not in WorkspaceFiles.PROJECT_TYPES[project_type]
                              and not (
                                   project_type == "3D"
                                   and resolved.name.lower().endswith(".tinkercad.json")
                              )
                         ):
                              raise ValueError(
                                   f"{resolved.name} is not a supported workspace project."
                              )
                    return project_type
          raise ValueError("Projects can only be opened from an AIKO workspace folder.")

     def _find_workspace_entry(self, name):
          if not name.strip():
               raise ValueError("Tell me the exact project or folder name to open.")
          candidate = Path(name).expanduser()
          if candidate.is_absolute() or len(candidate.parts) > 1:
               try:
                    resolved = candidate.resolve(strict=True)
               except OSError as error:
                    raise FileNotFoundError(f"No workspace item named {name!r} exists.") from error
               self._project_type_for_path(resolved)
               return resolved
          root = WorkspaceFiles.WORKSPACE_ROOT.resolve()
          matches = [
               path
               for project_type in WorkspaceFiles.PROJECT_TYPES
               for path in (root / project_type).rglob("*")
               if not path.name.startswith(".")
               and (
                    path.is_dir()
                    or path.suffix.lower() in WorkspaceFiles.PROJECT_TYPES[project_type]
                    or (
                         project_type == "3D"
                         and path.name.lower().endswith(".tinkercad.json")
                    )
               )
               and (
                    path.name.casefold() == name.casefold()
                    or (path.is_file() and path.stem.casefold() == name.casefold())
               )
          ]
          if not matches:
               raise FileNotFoundError(f"No workspace project or folder named {name!r} was found.")
          if len(matches) > 1:
               raise ValueError(
                    f"More than one workspace item is named {name!r}; use its full path."
               )
          self._project_type_for_path(matches[0])
          return matches[0]

     def _find_workbench_item(self, name):
          if name:
               matches = [
                    index
                    for index, item in enumerate(self._workbench_items)
                    if item["name"].casefold() == name.casefold()
                    or Path(item["path"]).stem.casefold() == name.casefold()
               ]
               if len(matches) != 1:
                    raise ValueError(
                         f"Could not identify one hologram named {name!r}."
                    )
               return matches[0]
          index = self.viewer.selected_workbench_item
          if index is None:
               index = self.viewer.focused_workbench_item
          if index is None:
               raise ValueError("Select or name a hologram first.")
          return index

     def _selected_or_focused_workbench_item(self):
          index = self.viewer.focused_workbench_item
          if index is None:
               index = self.viewer.selected_workbench_item
               if index is not None:
                    self._on_workbench_item_selected(index)
          if index is None or not 0 <= index < len(self._workbench_items):
               raise ValueError("Select or focus a hologram first.")
          return index

     def _close_workspace_project(self, name):
          if name:
               path = self._find_workspace_entry(name)
               if path.is_dir():
                    raise ValueError("Name a project file, not a folder, to close it.")
               target = path.resolve()
          elif self.viewer.focused_workbench_item is not None:
               target = Path(
                    self._workbench_items[self.viewer.focused_workbench_item]["path"]
               ).resolve()
          elif self.viewer.selected_workbench_item is not None:
               target = Path(
                    self._workbench_items[self.viewer.selected_workbench_item]["path"]
               ).resolve()
          elif self.selected_project is not None:
               target = Path(self.selected_project["path"]).resolve()
          else:
               raise ValueError("There is no selected project to close.")

          index = next(
               (
                    index
                    for index, item in enumerate(self._workbench_items)
                    if Path(item["path"]).resolve() == target
               ),
               None,
          )
          if index is not None:
               self.viewer.focused_workbench_item = index
               self.viewer.selected_workbench_item = index
               self._remove_selected_hologram()
          if (
               self.selected_project is not None
               and Path(self.selected_project["path"]).resolve() == target
          ):
               self.selected_project = None
          if WorkspaceFiles.get_active_project() == target:
               WorkspaceFiles.clear_active_project()
          self._refresh_projects()
          if self._workbench_items:
               self._refresh_workbench(update_camera=True)

     def show_workspace(self):
          self.window().centralWidget().setCurrentWidget(self)

     def _sync_active_project(self):
          try:
               active_project = WorkspaceFiles.get_active_project()
          except (OSError, ValueError) as error:
               self.status_label.setText(f"Could not read active project: {error}")
               return
          if active_project is None:
               self._last_synced_active_project = None
               return
          if active_project == self._last_synced_active_project:
               return
          self._last_synced_active_project = active_project
          if self.project_type != "3D":
               self._change_project_type("3D")
          if self.current_folder.resolve() != active_project.parent.resolve():
               self.current_folder = active_project.parent
               self._refresh_projects()
          selected_path = (
               Path(self.selected_project["path"]).resolve()
               if self.selected_project is not None
               else None
          )
          if selected_path != active_project:
               self._select_path(active_project)


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
           workspace_button = QPushButton("Workspace")
           workspace_button.setStyleSheet(
                "height:40px; line-height:40px; background-color: white; color: black;"
           )
           workspace_button.clicked.connect(
                lambda: self.stacked_widget.setCurrentIndex(2)
           )
           layout.addWidget(title_label)
           layout.addStretch(1)
           layout.addWidget(map_button)
           layout.addWidget(message_button)
           layout.addWidget(workspace_button)
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
          global _notification_bridge_ready, _pending_reminder_notification
          _ensure_runtime_files()
          desktop = QApplication.desktop()
          screen_width = desktop.screenGeometry().width()
          screen_height = desktop.screenGeometry().height()
          stacked_widget = QStackedWidget(self)
          message_screen = MessageScreen()
          conversation_map_screen = ConversationMapScreen()
          workspace_screen = WorkspaceScreen()
          self.conversation_map_screen = conversation_map_screen
          self.workspace_screen = workspace_screen
          self._reminder_notifications = {}
          stacked_widget.addWidget(conversation_map_screen)
          stacked_widget.addWidget(message_screen)
          stacked_widget.addWidget(workspace_screen)
          conversation_map_screen.on_select_conversation = self.open_conversation
          conversations = _load_conversations()
          if conversations:
               ActivateConversation(GetActiveChatLogPath())
          self.setGeometry(0, 0, screen_width, screen_height)
          self.setStyleSheet("QMainWindow { background: transparent; }")
          top_bar = CustomTopBar(self, stacked_widget)
          self.top_bar = top_bar
          self.setMenuWidget(top_bar)
          self.setCentralWidget(stacked_widget)
          conversation_map_screen.start_double_sound_trigger()
          _image_selection_bridge.workspace_open_requested.connect(
               workspace_screen.show_workspace
          )
          _image_selection_bridge.workspace_refresh_requested.connect(
               workspace_screen.refresh_workspace
          )
          _image_selection_bridge.workspace_command_requested.connect(
               workspace_screen.handle_voice_command
          )
          _image_selection_bridge.reminder_notification_requested.connect(
               self._show_reminder_notification
          )
          _image_selection_bridge.reminder_acknowledged.connect(
               self._close_reminder_notification
          )
          with _notification_state_lock:
               _notification_bridge_ready = True
               pending_reminder = _pending_reminder_notification
               _pending_reminder_notification = None
          global _workspace_bridge_connected
          _workspace_bridge_connected = True
          if pending_reminder is not None:
               self._show_reminder_notification(pending_reminder)

     def _show_reminder_notification(self, reminder):
          reminder_id = str(reminder.get("id", ""))
          if not reminder_id:
               return
          existing = self._reminder_notifications.get(reminder_id)
          if existing is not None:
               existing.close()
          notification = ReminderNotification(reminder, self)
          self._reminder_notifications[reminder_id] = notification
          notification.show_centered()

     def _close_reminder_notification(self, reminder_id):
          notification = self._reminder_notifications.pop(reminder_id, None)
          if notification is not None:
               notification.close()
               notification.deleteLater()
          self.conversation_map_screen.reminder_panel.refresh()

     def open_conversation(self, conversation):
          ActivateConversation(conversation["path"])
          self.centralWidget().setCurrentIndex(1)

     def closeEvent(self, event):
          map_screen = self.conversation_map_screen
          sound_worker = map_screen.double_sound_trigger_worker
          if sound_worker is not None and sound_worker.isRunning():
               sound_worker.requestInterruption()
               if not sound_worker.wait(2500):
                    event.ignore()
                    map_screen.double_sound_trigger_status.setText(
                         "The microphone is still closing. Please wait before closing AIKO."
                    )
                    return
               map_screen._double_sound_trigger_finished(sound_worker)
          worker = map_screen.hand_tracking_worker
          if worker is not None and worker.isRunning():
               map_screen._cancel_hand_gesture()
               worker.requestInterruption()
               if not worker.wait(2500):
                    event.ignore()
                    map_screen.hand_tracking_status.setText(
                         "The camera is still closing. Please wait before closing AIKO."
                    )
                    return
               map_screen._hand_tracking_finished(worker)
          event.accept()


def GraphicalUserInterface():
    _ensure_runtime_files()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
     GraphicalUserInterface()
