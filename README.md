# AIKO

## Use AIKO on iPhone without a Mac

AIKO has a mobile web app (PWA) in `web/`, served from the Python API. It
provides chat, voice dictation and spoken replies, image generation, and
reminders. It works in iPhone Safari and can be added to the Home Screen.
Voice recognition availability depends on the iOS and Safari version.

### Deploy to Render

1. In Render, create a **Blueprint** from this GitHub repository. The
   `render.yaml` file creates a Python web service and persistent disk.
2. In the service's **Environment** settings, add the secret values for
   `AIKO_API_TOKEN`, `GroqApiKey`, `Account_ID`, and `API_Token`.
   `AIKO_API_TOKEN` is a new random password for the AIKO app. `GroqApiKey`
   belongs to Groq; `Account_ID` and `API_Token` are Cloudflare Workers AI
   credentials. These are not Render account credentials.
3. Deploy and wait for the service health check to pass.
4. Open the Render service's HTTPS URL in iPhone Safari. Enter that URL and
   `AIKO_API_TOKEN` when AIKO asks to connect.
5. In Safari, use **Share → Add to Home Screen** to install the PWA.

Keep the provider keys on the server. Do not commit credentials or paste them
into source files. The app keeps its API token in the current browser session;
disconnect or close the session to clear it.

### Run the API locally

Use Python 3.11 or newer. Install the server-only dependencies:

```powershell
pip install -r requirements-api.txt
```

Set `AIKO_API_TOKEN`, `GroqApiKey`, `Account_ID`, and `API_Token` in the
server environment, then run:

```powershell
uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

For microphone access from iPhone Safari, use a publicly reachable HTTPS
deployment; plain HTTP on another device's local network is not a secure
browser context.

### Current limitations

- Chat history is held in the API process memory and resets when it restarts.
- Reminder and generated-image files use the Render persistent disk.
- Browser notifications are best-effort while AIKO is open. Reliable alerts
  while iOS suspends the app require a push-notification service.
- This API is designed for a private, single-owner deployment, not public
  multi-user use.

The SwiftUI source in `ios/AIKO` is an optional native-app prototype. Building
that version still requires macOS and Xcode.
