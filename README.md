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

## Windows desktop screen and control features

The main Windows app can describe the desktop on request and perform a small
set of explicitly requested controls. Install the desktop requirements and
Ollama, then download a local vision model:

```powershell
pip install -r requirements.txt
ollama pull moondream
```

Keep Ollama running while AIKO is open. The model can be changed with the
`AIKO_LOCAL_VISION_MODEL` environment variable. AIKO defaults to the smaller
`moondream` model for CPU responsiveness. Try commands such as:

- “What's on my screen?”
- “Open a new tab” or “Close this tab”
- “Click the Sign in button”
- “Tell me about the image you generated” (after choosing an image option)

Screen capture happens only after a direct screen-description request. AIKO
temporarily hides its own window to capture the desktop behind it, sends the
image only to Ollama at `127.0.0.1`, and does not save the screenshot. The
description is stored in AIKO's local chat history and is not sent to cloud
text-to-speech. AIKO clicks only a single visible, enabled control whose
accessible name exactly matches the requested label. Send, submit, purchase,
delete, and similar high-impact controls are blocked. Enter passwords and
approve multi-factor sign-ins yourself.

Screen and selected-image descriptions use one local Ollama request with a
bounded wait. The first request can take longer while the local model loads.
Image analysis requires choosing an option first, which keeps that image and
deletes the other two.

This feature requires Windows, Pillow, and `pywinauto`. It cannot interact with
secure Windows screens, and some apps do not expose accessible control names.

### Map reminders, news, and voice controls

Due reminders appear in a centered, theme-matched, draggable notification.
With the microphone enabled, say “OK,” “thank you,” “will do,” or “thanks” to
dismiss it immediately. If it remains open for two seconds, AIKO dismisses
and clears it automatically. Reminders that have not yet become due remain
saved across restarts.

The map includes a small dark-blue breaking-news panel. AIKO checks the public Google
News RSS feed at startup and periodically for recent headlines about major
events; newly found stories are announced once. This requires an internet
connection, and headlines may be delayed or filtered by the feed.

AIKO greets you at startup and when the local time changes to morning,
afternoon, or evening. With the microphone enabled, “stop,” “wait,” “shut up,”
“hold on,” and “pause” interrupt AIKO's current speech. Other recognized
phrases do not stop speech; AIKO keeps checking for those pause commands while
speaking, even if it hears unrelated sound.

Reminder requests that say “later” without a more exact time are scheduled for
one hour from now. For example, “remind me to update that part of the code
later” is saved as “update code.”

“Open Google” opens Google and asks what to search for; AIKO uses your next
spoken phrase as the search query. Combined requests such as “open Google, let
me see what the weather looks like” go straight to a Google search for
“weather,” without including the conversational filler.

### Optional hand tracking

Click **Start Hands** on the conversation map to start local webcam tracking;
click **Stop Hands** there to stop it. Tracking is off by default.
It stays on as you switch between the map, chat, and generated-image windows,
and stops when you turn it off or close AIKO. While enabled, the hand pointers
remain visible across the desktop and can interact with AIKO or other apps.
AIKO processes hand landmarks locally and does not save or upload camera
frames.

AIKO automatically listens through the selected microphone for two sharp sounds
(claps or snaps) within 0.8 seconds to start hand tracking. The listener is
active while AIKO is running, even when hand tracking is off. Audio is analyzed
locally and is not recorded or uploaded.

- With one hand, double-pinch to click. A single pinch held briefly and moved
  grabs/drags instead, so it is distinct from a click. This works over visible
  controls across the desktop while hand tracking is enabled.
- Spread your thumb and index finger over the map to zoom in;
  deliberate spreading is required to zoom in, and closing your fist zooms
  out. Pinch and drag over the map to rotate or tilt.
- With two hands, move them apart to zoom in and bring them together to zoom
  out. Both hand cursors remain visible across the desktop. Pinch with both
  hands over the map to grab and rotate/tilt it. You can also use one hand to
  hold/drag while the other double-pinches to click a different control.
- AIKO switches between one- and two-hand gestures automatically.
- Zoom updates continuously with smooth interpolation.
- Raise an open, palm-up hand to increase Windows master volume. Lower an
  open, palm-down hand to decrease it.
- The tracker uses all 21 landmarks and ignores incomplete hands; keep your
  whole hand in the camera view.

Hand tracking requires a working camera, the `mediapipe` package included in
`requirements.txt`, and the bundled local model at
`backend/models/hand_landmarker.task`. Camera access begins only after clicking
**Start Hands** or after the sound trigger detects two sharp sounds. The model
is from Google's MediaPipe hand-landmarker release under the Apache 2.0
license.

## Local 3D workspace

The Windows desktop app includes a **Workspace** window with separate local
folders for 3D designs and Circuits. Import `.obj` and `.stl` models or supported
circuit files, including EAGLE `.brd` boards, create subfolders, and drag files
onto a folder to organize them. Imported and generated 3D files can be previewed
as holograms. Simpler previews auto-rotate; dense previews show more geometry
and remain still to keep the workbench responsive, and can be rotated by hand.
The Workspace view includes a compact AIKO core and microphone status indicator
slightly above its lower-left edge, without displaying the conversation-map orbs.
Clicking multiple 3D models or EAGLE boards adds
them to the workbench without changing the source files; the view zooms out
only as needed to fit the holograms. Grab or drag empty workbench space to
orbit around the holograms. The workbench starts in move mode: drag a hologram
to reposition it, or enable **Rotate Selected** to turn it in place around the
X and Y axes. Right-drag also rotates a hologram. In rotation mode, use the
mouse wheel or twist two pinched hands to roll a hologram around the Z axis.
New holograms spawn side-by-side, touching edge-to-edge on the same plane;
existing items stay in place as more are added. Move a hologram sideways or
raise it above another before lowering it to arrange a preview; choose
**Snap & Combine** to bring the selected item into touching contact with its
nearest neighbor and move or rotate the connected assembly together. Use
**Remove Last Hologram**,
**Snap & Combine** to snap the selected part to its nearest neighbor and move
them as one assembly, or **Clear Workbench** to start over. Combining affects
only the workbench preview, not the source files. Hand tracking uses the same
zoom and drag/rotate gestures as the map. With both hands pinched over a
hologram, move the hands together or apart to resize it, move their midpoint
to reposition it, and move both hands toward or away from the camera to push
the hologram back or pull it forward in the workbench. You can also pinch and
drag a hologram with one hand to move it; while holding it, move your hand
toward or away from the camera to push or pull it in depth. Enable
**Rotate Selected** to spin the held hologram instead. Empty-space view
rotation follows the direction of your hand. When rotating a hologram by hand,
AIKO locks the gesture to its initial dominant horizontal or vertical
direction so small off-axis drift does not add unwanted tilt. Pinching over
empty workbench space still rotates the view. Removed
files go to the workspace's recoverable
`.Trash` folder.

Click or single-pinch a hologram to focus it; the other holograms remain in the
workbench but are dimmed. Use **Shrink** or **Enlarge**, or the X/Y/Z rotation
buttons, to edit the focused item. **Exit Focus** returns to the full workbench
and saves its position, size, and rotation for the next time that file is
opened. Newly added holograms are normalized to the first model's displayed
size. **Add Part** and **Remove Part** edit primitive components only in
`.aiko3d` designs; imported OBJ/STL meshes remain unchanged. **Remove Selected
Hologram** removes an item from the workbench without deleting its file.

AIKO sends a 3D design prompt to Cohere (using `CohereApiKey` and the
`CohereModel` setting in `.env`, defaulting to `command-a-03-2025`) and builds an
editable `.aiko3d` model from its response. The model assembles objects from
boxes, spheres, and cylinders, so this is AI-assisted primitive geometry rather
than a detailed sculpted CAD mesh; results can still need editing. Generated
parts are validated and limited to 32 components. Prompts are sent to Cohere.
Editable designs support adding, removing, and moving
primitive parts and exporting to STL. OBJ/STL imports are previewable but not
editable part-by-part. EAGLE `.brd` files can
be previewed as colored PCB holograms with footprint pads, package outlines,
and component-type colors and shapes. The `.brd` export does not embed full 3D
component models or screen contents, so those colors and shapes are
approximations, not exact assemblies or circuit simulations. Unrouted nets are
shown as guides rather than copper traces. Other circuit files are stored and
opened locally; AIKO does not simulate or synchronize them.

Tinkercad project links can be stored and opened in a browser, but they do not
sync account contents or edit cloud designs. To use a Tinkercad design in the
local 3D workspace, export it from Tinkercad as `.obj` or `.stl` and import
that file into AIKO.

With the microphone enabled, workspace commands can open or close the workspace
and projects, switch between 3D Designs and Circuits, create folders in the
current folder, create 3D designs in the current 3D folder (switching from
Circuits when needed), import a
file by path, add a Tinkercad link by name and URL, edit parts,
focus/shrink/enlarge/rotate holograms, snap or clear the workbench, remove a
hologram, and export an editable design to STL. Examples:
“open project bridge,” “create folder named Prototype Parts,” “rotate selected
item around X axis by 30 degrees,” and “export as STL.” Ask “what am I working
on?” to hear the current folder, workspace file tree, and loaded workbench
holograms. Voice-created designs switch to the 3D workspace as needed and are
added to the workbench automatically. Removing a workspace file moves it to the
recoverable `.Trash` folder; closing a project only removes its preview from
the workbench.
During an active AIKO conversation, AIKO reads the current workspace state and
includes it with that chat request so relevant help can refer to the open
project and workbench. This is on-demand only: AIKO does not continuously watch
the screen, camera, or workspace, and the workspace snapshot is not added to the
chat transcript.

Chat and voice requests mentioning an **image**/**picture**, or phrased **show
me**, route to image generation. **Generate**, **create**, **make**, and
**blueprint** requests create a 3D workspace item. If either command is given
without a subject, AIKO asks what to make. Image requests open three separate
options to choose from instead of returning an inline image in chat. Music
phrases such as “drop my needle,” “play some toons,”
and “serenade me” start YouTube music playback. “Play my liked songs from
Spotify” opens Spotify Liked Songs in your browser; you may need to sign in.
