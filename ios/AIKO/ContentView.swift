import SwiftUI
import UserNotifications
import UIKit

struct AIKOMessage: Identifiable {
    let id = UUID()
    let text: String
    let isUser: Bool
}

struct ContentView: View {
    @AppStorage("aikoServerURL") private var serverURL = ""
    @AppStorage("aikoSessionID") private var sessionID = UUID().uuidString
    @State private var apiKey = APIKeychain.load()
    @State private var showingSettings = false
    @StateObject private var voice = VoiceController()

    private var client: AIKOAPIClient? {
        AIKOAPIClient(baseURLString: serverURL, apiKey: apiKey)
    }

    var body: some View {
        NavigationStack {
            TabView {
                ChatTab(client: client, voice: voice, sessionID: sessionID)
                    .tabItem { Label("Chat", systemImage: "bubble.left.and.bubble.right") }
                ImagesTab(client: client)
                    .tabItem { Label("Images", systemImage: "photo") }
                RemindersTab(client: client)
                    .tabItem { Label("Reminders", systemImage: "bell") }
            }
            .tint(Color(red: 0.65, green: 0.89, blue: 0.18))
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showingSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                    .accessibilityLabel("Server settings")
                }
            }
            .sheet(isPresented: $showingSettings) {
                APISettingsView(serverURL: $serverURL, apiKey: $apiKey)
            }
        }
    }
}

private struct APISettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var serverURL: String
    @Binding var apiKey: String
    @State private var enteredKey = ""
    @State private var errorMessage: String?
    @State private var saved = false

    var body: some View {
        NavigationStack {
            Form {
                Section("AIKO server") {
                    TextField("https://your-server.example", text: $serverURL)
                        .textInputAutocapitalization(.never)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                    SecureField("Server API key", text: $enteredKey)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Text("The API key is stored in iPhone Keychain. Use an HTTPS server URL.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                if let errorMessage {
                    Section {
                        Text(errorMessage).foregroundStyle(.red)
                    }
                }
                if saved {
                    Section {
                        Text("Settings saved.")
                    }
                }
            }
            .navigationTitle("Connection")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }
                }
            }
        }
    }

    private func save() {
        errorMessage = nil
        saved = false
        let trimmedURL = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmedURL),
              url.scheme?.lowercased() == "https",
              url.host != nil else {
            errorMessage = "Enter a valid HTTPS server URL."
            return
        }
        do {
            if !enteredKey.isEmpty {
                try APIKeychain.save(enteredKey)
                apiKey = enteredKey
            } else if apiKey.isEmpty {
                errorMessage = "Enter the server API key."
                return
            }
            serverURL = trimmedURL
            saved = true
            dismiss()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct ChatTab: View {
    let client: AIKOAPIClient?
    @ObservedObject var voice: VoiceController
    let sessionID: String
    @State private var messages: [AIKOMessage] = []
    @State private var draft = ""
    @State private var isSending = false
    @State private var speakReplies = true
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        if messages.isEmpty {
                            Text("Talk to AIKO. Use the microphone to dictate a message.")
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding()
                        }
                        ForEach(messages) { message in
                            Text(message.text)
                                .padding(12)
                                .foregroundStyle(message.isUser ? .white : Color.primary)
                                .background(
                                    message.isUser ? Color.blue.opacity(0.82) : Color.gray.opacity(0.16)
                                )
                                .clipShape(RoundedRectangle(cornerRadius: 14))
                                .frame(
                                    maxWidth: .infinity,
                                    alignment: message.isUser ? .trailing : .leading
                                )
                                .id(message.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: messages.count) { _, _ in
                    if let last = messages.last {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .padding(.horizontal)
            }
            if let voiceError = voice.errorMessage {
                Text(voiceError)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .padding(.horizontal)
            }

            HStack(spacing: 10) {
                Button {
                    voice.toggleListening()
                } label: {
                    Image(systemName: voice.isListening ? "stop.circle.fill" : "mic.circle.fill")
                        .font(.system(size: 32))
                }
                .accessibilityLabel(voice.isListening ? "Stop voice input" : "Start voice input")

                TextField("Message AIKO", text: $draft, axis: .vertical)
                    .lineLimit(1...4)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { send() }

                Button(action: send) {
                    if isSending {
                        ProgressView()
                    } else {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 30))
                    }
                }
                .disabled(isSending || client == nil || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding()
        }
        .navigationTitle("AIKO")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Toggle("Speak replies", isOn: $speakReplies)
                    .labelsHidden()
            }
        }
        .onReceive(voice.$transcript.dropFirst()) { transcript in
            guard !transcript.isEmpty else { return }
            draft = transcript
            send()
        }
        .onAppear {
            if client == nil {
                errorMessage = "Set the AIKO server URL and API key in Settings."
            }
        }
    }

    private func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let client, !isSending else { return }
        draft = ""
        errorMessage = nil
        messages.append(AIKOMessage(text: text, isUser: true))
        isSending = true
        Task {
            defer { isSending = false }
            do {
                let reply = try await client.sendChat(text, sessionID: sessionID)
                messages.append(AIKOMessage(text: reply, isUser: false))
                if speakReplies {
                    voice.speak(reply)
                }
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }
}

private struct ImagesTab: View {
    let client: AIKOAPIClient?
    @State private var prompt = ""
    @State private var images: [Data] = []
    @State private var isGenerating = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                TextField("Describe an image", text: $prompt, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                Button("Create") { generate() }
                    .disabled(isGenerating || client == nil || prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            if isGenerating { ProgressView("Generating images…") }
            if let errorMessage {
                Text(errorMessage).font(.footnote).foregroundStyle(.red)
            }
            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(Array(images.enumerated()), id: \.offset) { _, data in
                        if let image = UIImage(data: data) {
                            Image(uiImage: image)
                                .resizable()
                                .scaledToFit()
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                    }
                }
            }
            Spacer(minLength: 0)
        }
        .padding()
        .navigationTitle("Image studio")
    }

    private func generate() {
        guard let client else {
            errorMessage = "Configure the AIKO server in Settings."
            return
        }
        let text = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        isGenerating = true
        errorMessage = nil
        images = []
        Task {
            defer { isGenerating = false }
            do {
                images = try await client.generateImages(prompt: text)
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }
}

private struct RemindersTab: View {
    let client: AIKOAPIClient?
    @State private var reminders: [Reminder] = []
    @State private var title = ""
    @State private var dueAt = Date().addingTimeInterval(3600)
    @State private var errorMessage: String?
    @State private var isSaving = false

    var body: some View {
        VStack {
            Form {
                Section("New reminder") {
                    TextField("What should AIKO remind you about?", text: $title)
                    DatePicker("Date and time", selection: $dueAt, in: Date()...)
                    Button(isSaving ? "Saving…" : "Save reminder") { save() }
                        .disabled(isSaving || client == nil || title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                Section("Saved reminders") {
                    if reminders.isEmpty {
                        Text("No reminders yet.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(reminders) { reminder in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(reminder.title)
                            Text(reminder.dueAt.formatted(date: .abbreviated, time: .shortened))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if let errorMessage {
                Text(errorMessage).font(.footnote).foregroundStyle(.red).padding()
            }
        }
        .navigationTitle("Reminders")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { await refresh() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .accessibilityLabel("Refresh reminders")
            }
        }
        .task { await refresh() }
    }

    private func refresh() async {
        guard let client else { return }
        do {
            reminders = try await client.getReminders()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func save() {
        guard let client else {
            errorMessage = "Configure the AIKO server in Settings."
            return
        }
        let reminderTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !reminderTitle.isEmpty else { return }
        isSaving = true
        errorMessage = nil
        Task {
            defer { isSaving = false }
            do {
                let reminder = try await client.createReminder(title: reminderTitle, dueAt: dueAt)
                reminders.append(reminder)
                reminders.sort { $0.dueAt < $1.dueAt }
                title = ""
                await scheduleLocalNotification(for: reminder)
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    private func scheduleLocalNotification(for reminder: Reminder) async {
        guard reminder.dueAt > Date() else { return }
        do {
            let center = UNUserNotificationCenter.current()
            let granted = try await center.requestAuthorization(options: [.alert, .sound])
            guard granted else { return }
            let content = UNMutableNotificationContent()
            content.title = "AIKO reminder"
            content.body = reminder.title
            content.sound = .default
            let components = Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute],
                from: reminder.dueAt
            )
            let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: false)
            let request = UNNotificationRequest(
                identifier: reminder.id,
                content: content,
                trigger: trigger
            )
            try await center.add(request)
        } catch {
            errorMessage = "Reminder was saved, but iPhone notification setup failed: \(error.localizedDescription)"
        }
    }
}
