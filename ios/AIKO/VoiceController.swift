import AVFoundation
import Combine
import Foundation
import Speech

@MainActor
final class VoiceController: NSObject, ObservableObject {
    @Published private(set) var transcript = ""
    @Published private(set) var isListening = false
    @Published private(set) var errorMessage: String?

    private let audioEngine = AVAudioEngine()
    private let synthesizer = AVSpeechSynthesizer()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private var hasInputTap = false

    func toggleListening() {
        if isListening {
            stopListening()
            return
        }
        errorMessage = nil
        SFSpeechRecognizer.requestAuthorization { [weak self] status in
            guard status == .authorized else {
                Task { @MainActor in
                    self?.errorMessage = "Enable Speech Recognition in iPhone Settings to use voice input."
                }
                return
            }
            AVAudioSession.sharedInstance().requestRecordPermission { granted in
                DispatchQueue.main.async {
                    guard let self else { return }
                    guard granted else {
                        self.errorMessage = "Enable microphone access in iPhone Settings to use voice input."
                        return
                    }
                    self.beginRecording()
                }
            }
        }
    }

    func speak(_ text: String) {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio, options: .duckOthers)
            try session.setActive(true)
        } catch {
            errorMessage = "Could not start spoken audio: \(error.localizedDescription)"
            return
        }
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate
        synthesizer.speak(utterance)
    }

    private func beginRecording() {
        guard let recognizer, recognizer.isAvailable else {
            errorMessage = "Speech recognition is currently unavailable."
            return
        }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement, options: .duckOthers)
            try session.setActive(true, options: .notifyOthersOnDeactivation)

            let request = SFSpeechAudioBufferRecognitionRequest()
            request.shouldReportPartialResults = true
            recognitionRequest = request
            transcript = ""

            let input = audioEngine.inputNode
            input.installTap(
                onBus: 0,
                bufferSize: 1024,
                format: input.outputFormat(forBus: 0)
            ) { [weak request] buffer, _ in
                request?.append(buffer)
            }
            hasInputTap = true
            audioEngine.prepare()
            try audioEngine.start()
            isListening = true

            recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
                if let result, result.isFinal {
                    Task { @MainActor in
                        self?.transcript = result.bestTranscription.formattedString
                        self?.stopListening(cancelRecognition: false)
                    }
                } else if let error {
                    Task { @MainActor in
                        self?.errorMessage = error.localizedDescription
                        self?.stopListening()
                    }
                }
            }
        } catch {
            errorMessage = "Could not start voice input: \(error.localizedDescription)"
            stopListening()
        }
    }

    private func stopListening(cancelRecognition: Bool = true) {
        if audioEngine.isRunning {
            audioEngine.stop()
        }
        if hasInputTap {
            audioEngine.inputNode.removeTap(onBus: 0)
            hasInputTap = false
        }
        recognitionRequest?.endAudio()
        recognitionRequest = nil
        if cancelRecognition {
            recognitionTask?.cancel()
        }
        recognitionTask = nil
        isListening = false
        do {
            try AVAudioSession.sharedInstance().setActive(
                false,
                options: .notifyOthersOnDeactivation
            )
        } catch {
            errorMessage = "Could not release microphone access: \(error.localizedDescription)"
        }
    }
}
