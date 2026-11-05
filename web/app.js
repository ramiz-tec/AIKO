"use strict";

const STORAGE_URL = "aiko.serverURL";
const STORAGE_TOKEN = "aiko.apiToken";
const STORAGE_SESSION = "aiko.sessionID";
const serverURLInput = document.querySelector("#server-url");
const tokenInput = document.querySelector("#api-token");
const connectionCard = document.querySelector("#connection-card");
const chatMessages = document.querySelector("#chat-messages");
const chatInput = document.querySelector("#chat-input");
const toast = document.querySelector("#toast");

let serverURL = sessionStorage.getItem(STORAGE_URL) || "";
let apiToken = sessionStorage.getItem(STORAGE_TOKEN) || "";
let sessionID = sessionStorage.getItem(STORAGE_SESSION);
let recognition = null;
let reminderTimers = new Map();
let toastTimer = null;

if (!sessionID) {
  sessionID = crypto.randomUUID();
  sessionStorage.setItem(STORAGE_SESSION, sessionID);
}

function connected() {
  return Boolean(serverURL && apiToken);
}

function normalizeServerURL(value) {
  const parsed = new URL(value.trim());
  if (parsed.protocol !== "https:" &&
      !(parsed.protocol === "http:" && ["localhost", "127.0.0.1"].includes(parsed.hostname))) {
    throw new Error("Use an HTTPS server URL. HTTP is allowed only for localhost testing.");
  }
  parsed.username = "";
  parsed.password = "";
  parsed.search = "";
  parsed.hash = "";
  return parsed.href.replace(/\/+$/, "");
}

function updateConnectionCard() {
  connectionCard.hidden = connected();
  serverURLInput.value = serverURL;
  if (connected()) {
    loadReminders();
  }
}

function apiURL(path) {
  return `${serverURL}/${path.replace(/^\/+/, "")}`;
}

async function apiRequest(path, options = {}) {
  if (!connected()) {
    throw new Error("Connect to your AIKO server in Settings first.");
  }
  const headers = new Headers(options.headers || {});
  headers.set("X-AIKO-API-Key", apiToken);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(apiURL(path), { ...options, headers });
  if (!response.ok) {
    let detail = `AIKO server error (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // The response may be plain text.
    }
    throw new Error(detail);
  }
  return response;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 2800);
}

function showError(id, error) {
  document.querySelector(id).textContent = error instanceof Error ? error.message : String(error);
}

function addMessage(text, role) {
  chatMessages.querySelector(".empty-state")?.remove();
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = text;
  chatMessages.append(node);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return node;
}

async function sendChat() {
  const message = chatInput.value.trim();
  if (!message) return;
  chatInput.value = "";
  document.querySelector("#chat-error").textContent = "";
  addMessage(message, "user");
  const pending = addMessage("AIKO is thinking…", "assistant");
  document.querySelector("#send-button").disabled = true;
  try {
    const response = await apiRequest("v1/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionID }),
    });
    const result = await response.json();
    pending.textContent = result.reply;
    if (document.querySelector("#speak-replies").checked && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(result.reply));
    }
  } catch (error) {
    pending.remove();
    showError("#chat-error", error);
    addMessage(error.message || "Could not reach AIKO.", "assistant");
  } finally {
    document.querySelector("#send-button").disabled = false;
    chatInput.focus();
  }
}

function startVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showError("#chat-error", new Error("Speech input is not supported here. Try the latest iOS Safari."));
    return;
  }
  if (recognition) {
    recognition.stop();
    recognition = null;
    return;
  }
  recognition = new SpeechRecognition();
  recognition.lang = navigator.language || "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  const button = document.querySelector("#voice-button");
  button.classList.add("listening");
  recognition.onresult = (event) => {
    const transcript = event.results?.[0]?.[0]?.transcript?.trim();
    if (transcript) {
      chatInput.value = transcript;
      sendChat();
    }
  };
  recognition.onerror = (event) => {
    showError("#chat-error", new Error(`Voice input failed: ${event.error}.`));
  };
  recognition.onend = () => {
    button.classList.remove("listening");
    recognition = null;
  };
  try {
    recognition.start();
  } catch (error) {
    button.classList.remove("listening");
    recognition = null;
    showError("#chat-error", error);
  }
}

async function generateImages(event) {
  event.preventDefault();
  const prompt = document.querySelector("#image-prompt").value.trim();
  const results = document.querySelector("#image-results");
  const button = event.currentTarget.querySelector("button");
  if (!prompt) return;
  showError("#image-error", "");
  results.replaceChildren();
  button.disabled = true;
  button.textContent = "Generating…";
  try {
    const response = await apiRequest("v1/images", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    });
    const result = await response.json();
    const images = await Promise.all(result.image_urls.map(async (url) => {
      const imageResponse = await apiRequest(url);
      return URL.createObjectURL(await imageResponse.blob());
    }));
    for (const [index, src] of images.entries()) {
      const card = document.createElement("figure");
      card.className = "image-card";
      const image = document.createElement("img");
      image.src = src;
      image.alt = `AIKO image option ${index + 1}: ${result.prompt}`;
      image.loading = "lazy";
      card.append(image);
      results.append(card);
    }
  } catch (error) {
    showError("#image-error", error);
  } finally {
    button.disabled = false;
    button.textContent = "Generate images";
  }
}

function formatDue(value) {
  return new Date(value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function scheduleForegroundReminder(reminder) {
  const due = new Date(reminder.due_at).getTime();
  const delay = due - Date.now();
  if (!Number.isFinite(due) || delay <= 0 || delay > 2_147_000_000) return;
  clearTimeout(reminderTimers.get(reminder.id));
  const timer = setTimeout(() => {
    showToast(`Reminder: ${reminder.title}`);
    if ("Notification" in window && Notification.permission === "granted") {
      try {
        new Notification("AIKO reminder", { body: reminder.title, icon: "/icon.svg" });
      } catch {
        showToast(`Reminder: ${reminder.title}`);
      }
    }
    reminderTimers.delete(reminder.id);
  }, delay);
  reminderTimers.set(reminder.id, timer);
}

async function loadReminders() {
  if (!connected()) return;
  try {
    const response = await apiRequest("v1/reminders");
    const reminders = await response.json();
    const list = document.querySelector("#reminder-list");
    list.replaceChildren();
    for (const reminder of reminders) {
      const item = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = reminder.title;
      const due = document.createElement("span");
      due.className = "reminder-date";
      due.textContent = formatDue(reminder.due_at);
      item.append(title, due);
      list.append(item);
      if (!reminder.notified) scheduleForegroundReminder(reminder);
    }
    if (!reminders.length) {
      const empty = document.createElement("li");
      empty.className = "empty-state";
      empty.textContent = "No reminders saved yet.";
      list.append(empty);
    }
  } catch (error) {
    showError("#reminder-error", error);
  }
}

async function saveReminder(event) {
  event.preventDefault();
  const title = document.querySelector("#reminder-title").value.trim();
  const localDue = document.querySelector("#reminder-due").value;
  if (!title || !localDue) return;
  const dueAt = new Date(localDue);
  if (!Number.isFinite(dueAt.getTime())) {
    showError("#reminder-error", new Error("Choose a valid date and time."));
    return;
  }
  if ("Notification" in window && Notification.permission === "default") {
    try {
      await Notification.requestPermission();
    } catch {
      showToast("Reminder notifications were not enabled.");
    }
  }
  showError("#reminder-error", "");
  try {
    const response = await apiRequest("v1/reminders", {
      method: "POST",
      body: JSON.stringify({ title, due_at: dueAt.toISOString() }),
    });
    const reminder = await response.json();
    document.querySelector("#reminder-title").value = "";
    scheduleForegroundReminder(reminder);
    await loadReminders();
    showToast("Reminder saved.");
  } catch (error) {
    showError("#reminder-error", error);
  }
}

async function saveConnection(url, token) {
  const candidateURL = normalizeServerURL(url);
  const candidateToken = token.trim();
  if (!candidateToken) throw new Error("Enter your AIKO API token.");
  const response = await fetch(`${candidateURL}/v1/reminders`, {
    headers: { "X-AIKO-API-Key": candidateToken },
  });
  if (!response.ok) {
    throw new Error(response.status === 401
      ? "The server rejected that API token."
      : `Could not connect to AIKO (${response.status}).`);
  }
  serverURL = candidateURL;
  apiToken = candidateToken;
  sessionStorage.setItem(STORAGE_URL, serverURL);
  sessionStorage.setItem(STORAGE_TOKEN, apiToken);
  updateConnectionCard();
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab === button));
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === `${button.dataset.tab}-panel`);
    });
    if (button.dataset.tab === "reminders") loadReminders();
  });
});

document.querySelector("#send-button").addEventListener("click", sendChat);
document.querySelector("#voice-button").addEventListener("click", startVoiceInput);
chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendChat();
  }
});
document.querySelector("#image-form").addEventListener("submit", generateImages);
document.querySelector("#reminder-form").addEventListener("submit", saveReminder);

document.querySelector("#connection-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  try {
    await saveConnection(serverURLInput.value, tokenInput.value);
    tokenInput.value = "";
    showToast("Connected to AIKO.");
  } catch (error) {
    showError("#connection-error", error);
  } finally {
    button.disabled = false;
  }
});

const settingsDialog = document.querySelector("#settings-dialog");
document.querySelector("#settings-button").addEventListener("click", () => {
  document.querySelector("#settings-server-url").value = serverURL;
  document.querySelector("#settings-api-token").value = "";
  showError("#settings-error", "");
  if (typeof settingsDialog.showModal === "function") settingsDialog.showModal();
});
document.querySelector("#close-settings").addEventListener("click", () => settingsDialog.close());
document.querySelector("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    const token = document.querySelector("#settings-api-token").value || apiToken;
    await saveConnection(document.querySelector("#settings-server-url").value, token);
    settingsDialog.close();
    showToast("Connection updated.");
  } catch (error) {
    showError("#settings-error", error);
  } finally {
    button.disabled = false;
  }
});
document.querySelector("#disconnect-button").addEventListener("click", () => {
  sessionStorage.removeItem(STORAGE_URL);
  sessionStorage.removeItem(STORAGE_TOKEN);
  serverURL = "";
  apiToken = "";
  connectionCard.hidden = false;
  settingsDialog.close();
});

const defaultDue = new Date(Date.now() + 60 * 60 * 1000);
const localDue = new Date(defaultDue.getTime() - defaultDue.getTimezoneOffset() * 60_000);
document.querySelector("#reminder-due").value = localDue.toISOString().slice(0, 16);
updateConnectionCard();

if ("serviceWorker" in navigator && location.protocol === "https:") {
  navigator.serviceWorker.register("/service-worker.js").catch((error) => {
    console.error("Could not register the AIKO offline shell:", error);
  });
}
