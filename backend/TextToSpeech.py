import asyncio
import base64
import math
import os
import random
import re
import subprocess
import tempfile
import time
from pathlib import Path

import edge_tts
import pywhatkit
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
env_vars = dotenv_values(PROJECT_ROOT / ".env")
AssistantVoice = env_vars.get("AssistantVoice")
DATA_DIR = PROJECT_ROOT / "Data"
SPEECH_FILE = DATA_DIR / "speech.mp3"


async def TextToAudioFile(text) -> None:
    if not AssistantVoice:
        raise RuntimeError("AssistantVoice is not configured in .env.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=DATA_DIR, suffix=".mp3", delete=False
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
    try:
        communicate = edge_tts.Communicate(text, AssistantVoice, pitch="+5Hz", rate="+13%")
        await communicate.save(str(temporary_path))
        if temporary_path.stat().st_size == 0:
            raise RuntimeError("Edge TTS produced an empty audio file.")
        os.replace(temporary_path, SPEECH_FILE)
    finally:
        temporary_path.unlink(missing_ok=True)


def _speech_level(text, position_ms, duration_ms):
    if duration_ms <= 0 or position_ms < 0 or position_ms >= duration_ms:
        return 0.0

    segments = []
    for token in re.findall(r"[A-Za-z0-9']+|[,.!?;:]", text.lower()):
        if token[0].isalnum() or token[0] == "'":
            syllables = max(1, len(re.findall(r"[aeiouy]+", token)))
            segments.append((syllables, syllables))
        else:
            segments.append((0.55 if token in ",:;" else 0.9, 0))
    total_weight = sum(weight for weight, _ in segments)
    if not total_weight:
        return 0.0

    target = position_ms / duration_ms * total_weight
    for weight, syllables in segments:
        if target < weight:
            if not syllables:
                return 0.04
            progress = target / weight
            syllable_progress = (progress * syllables) % 1
            return 0.18 + 0.82 * abs(math.sin(math.pi * syllable_progress))
        target -= weight
    return 0.0


def _estimated_speech_duration_ms(text):
    syllables = sum(
        max(1, len(re.findall(r"[aeiouy]+", word.lower())))
        for word in re.findall(r"[A-Za-z0-9']+", text)
    )
    pauses = sum(180 if char in ",:;" else 320 for char in text if char in ".!?;:")
    return max(500, int(syllables / 3.6 * 1000) + pauses)


def _level_reporter(callback):
    warning_logged = False

    def report(level):
        nonlocal warning_logged
        if callback is None:
            return
        try:
            callback(level)
        except Exception as error:
            if not warning_logged:
                print(
                    f"[WARN] Speech-level animation update failed "
                    f"({type(error).__name__}): {error}",
                    flush=True,
                )
                warning_logged = True

    return report


def _speak_with_windows_mark(text, level_callback=None):
    report_level = _level_reporter(level_callback)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=DATA_DIR, suffix=".progress", delete=False
    ) as progress_file:
        progress_path = Path(progress_file.name)
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "$progressPath = $env:AIKO_SPEECH_PROGRESS; "
        "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
        "$synthType = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, "
        "Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]; "
        "$streamType = [Windows.Media.SpeechSynthesis.SpeechSynthesisStream, "
        "Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]; "
        "$sourceType = [Windows.Media.Core.MediaSource, Windows.Media.Core, "
        "ContentType = WindowsRuntime]; "
        "$playerType = [Windows.Media.Playback.MediaPlayer, Windows.Media, "
        "ContentType = WindowsRuntime]; "
        "$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods("
        "[System.Reflection.BindingFlags]'Public,Static') | "
        "Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition "
        "-and $_.GetParameters().Count -eq 1 "
        "-and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } "
        "| Select-Object -First 1).MakeGenericMethod($streamType); "
        "$synth = [Activator]::CreateInstance($synthType); "
        "$stream = $null; $player = $null; "
        "try { "
        "$voice = $synthType::AllVoices | Where-Object { $_.DisplayName -match '\\bMark\\b' } "
        "| Select-Object -First 1; "
        "if (-not $voice) { throw 'Windows voice Microsoft Mark is not installed.' }; "
        "$synth.Voice = $voice; "
        "$encodedText = [Console]::In.ReadToEnd(); "
        "$text = [System.Text.Encoding]::UTF8.GetString("
        "[Convert]::FromBase64String($encodedText)); "
        "$operation = $synth.SynthesizeTextToStreamAsync($text); "
        "$task = $asTask.Invoke($null, @($operation)); $task.Wait(); "
        "$stream = $task.Result; "
        "$player = [Activator]::CreateInstance($playerType); "
        "$player.Source = $sourceType::CreateFromStream($stream, $stream.ContentType); "
        "$player.Volume = 1.0; $player.Play(); "
        "$started = $false; $timer = [Diagnostics.Stopwatch]::StartNew(); "
        "while ($timer.Elapsed.TotalSeconds -lt 120) { "
        "$state = [string]$player.PlaybackSession.PlaybackState; "
        "if ($state -eq 'Playing') { $started = $true }; "
        "if ($started -and $state -in @('None', 'Paused')) { break }; "
        "$positionMs = [long]$player.PlaybackSession.Position.TotalMilliseconds; "
        "$durationMs = 0; "
        "try { $durationMs = [long]$player.PlaybackSession.NaturalDuration.TotalMilliseconds } catch {}; "
        "[System.IO.File]::WriteAllText($progressPath, "
        "($positionMs.ToString() + '|' + $durationMs.ToString())); "
        "Start-Sleep -Milliseconds 50 "
        "}; "
        "if (-not $started) { throw 'Windows Mark voice playback did not start.' } "
        "} finally { "
        "if ($player) { $player.Dispose() }; "
        "if ($stream) { $stream.Dispose() }; "
        "$synth.Dispose() "
        "}"
    )
    environment = os.environ.copy()
    environment["AIKO_SPEECH_PROGRESS"] = str(progress_path)
    process = None
    try:
        process = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
        )
        try:
            process.stdin.write(base64.b64encode(text.encode("utf-8")).decode("ascii"))
            process.stdin.close()
        except OSError:
            process.wait(timeout=120)
            stdout, stderr = process.communicate()
            message = stderr.strip() or stdout.strip() or "Windows speech synthesis failed."
            raise RuntimeError(message)

        deadline = time.monotonic() + 120
        while process.poll() is None:
            if time.monotonic() >= deadline:
                raise RuntimeError("Windows speech synthesis timed out after 120 seconds.")
            try:
                position_text, duration_text = progress_path.read_text(
                    encoding="utf-8"
                ).split("|", 1)
                level = _speech_level(text, int(position_text), int(duration_text))
                report_level(level)
            except (OSError, ValueError):
                report_level(0.0)
            time.sleep(0.05)

        stdout, stderr = process.communicate()
        if process.returncode:
            message = stderr.strip() or stdout.strip() or "Windows speech synthesis failed."
            raise RuntimeError(message)
    finally:
        if process and process.poll() is None:
            process.kill()
            process.wait()
        progress_path.unlink(missing_ok=True)
        report_level(0.0)


def TTS(Text, func=lambda r=None: True, level_callback=None):
    report_level = _level_reporter(level_callback)
    try:
        if os.name == "nt":
            try:
                _speak_with_windows_mark(str(Text), report_level)
                return True
            except Exception as windows_error:
                print(
                    f"[WARN] Windows Mark voice failed ({type(windows_error).__name__}); "
                    "trying Edge TTS.",
                    flush=True,
                )

        try:
            asyncio.run(TextToAudioFile(Text))
        except Exception as edge_error:
            raise RuntimeError(
                f"Edge TTS failed ({type(edge_error).__name__}): {edge_error}"
            ) from edge_error

        pygame.mixer.init()
        pygame.mixer.music.load(str(SPEECH_FILE))
        pygame.mixer.music.set_volume(1.0)
        pygame.mixer.music.play()
        if not pygame.mixer.music.get_busy():
            raise RuntimeError("Audio playback did not start.")

        estimated_duration = _estimated_speech_duration_ms(str(Text))
        playback_started = time.monotonic()
        while pygame.mixer.music.get_busy():
            if func() is False:
                break
            position = pygame.mixer.music.get_pos()
            if position < 0:
                position = int((time.monotonic() - playback_started) * 1000)
            report_level(_speech_level(str(Text), position, estimated_duration))
            pygame.time.Clock().tick(10)

        return True
    finally:
        try:
            report_level(0.0)
            func(False)
        finally:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
                pygame.mixer.quit()


def TextToSpeech(Text, func=lambda r=None: True, level_callback=None):
    text = str(Text)
    sentences = text.split(".")
    responses = [
        "The rest of the result has been printed to the chat screen, kindly check it out sir.",
        "The rest of the text is now on the chat screen, sir, please check it.",
        "You can see the rest of the text on the chat screen, sir.",
        "The remaining part of the text is now on the chat screen, sir.",
        "sir, you'll find more text on the chat screen for you to see.",
        "The rest of the answer is now on the chat screen, sir.",
        "Sir, please look at the chat screen, the rest of the answer is there.",
        "You'll find the complete answer on the chat screen, sir.",
        "The next part of the text is on the chat screen, sir.",
        "Sir, please check the chat screen for more information.",
        "There's more text on the chat screen for you sir.",
        "Sir, take a look at the chat screen for additional information.",
        "You'll find more to read on the chat screen, sir.",
        "Sir, check the chat screen for the rest of the text.",
        "The chat screen has the rest of the text, sir.",
        "There's more to see on the chat screen sir, take a look.",
        "You'll find the complete answer on the chat screen, check it out sir.",
        "Sir, look at the chat screen for the complete answer.",
    ]
    if len(sentences) > 4 and len(text) > 18000:
        spoken_text = ". ".join(sentences[:2]) + ". " + random.choice(responses)
        TTS(spoken_text, func, level_callback)
    else:
        TTS(text, func, level_callback)


if __name__ == "__main__":
    while True:
        TTS(input("Enter the Text:"))
