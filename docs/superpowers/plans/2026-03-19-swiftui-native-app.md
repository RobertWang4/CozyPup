# CozyPup SwiftUI Native App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the CozyPup React/Capacitor hybrid app as a pure native SwiftUI iOS app, preserving all existing features and the warm visual design.

**Architecture:** Single-target SwiftUI app using MVVM pattern. ObservableObject stores backed by UserDefaults for persistence. SSE streaming via URLSession for chat. Native Speech/CoreLocation frameworks replace Capacitor plugins.

**Tech Stack:** SwiftUI, Swift 5.9+, iOS 17+, URLSession (SSE), Speech framework, CoreLocation, UserDefaults

**Backend:** Unchanged — Python/FastAPI at `http://<host>:8000/api/v1`

---

## File Structure

```
ios-app/CozyPup/
├── CozyPupApp.swift                  # App entry, auth/disclaimer/onboarding gate
├── Theme/
│   └── Tokens.swift                  # Colors, fonts, spacing constants
├── Models/
│   ├── Pet.swift                     # Pet model + PET_COLORS
│   ├── CalendarEvent.swift           # CalendarEvent model
│   └── ChatMessage.swift             # ChatMessage, CardData, EmergencyData
├── Stores/
│   ├── AuthStore.swift               # Auth state + disclaimer, UserDefaults
│   ├── PetStore.swift                # Pet CRUD, UserDefaults
│   ├── CalendarStore.swift           # Event CRUD + seed data, UserDefaults
│   └── ChatStore.swift               # Message persistence, session management
├── Services/
│   ├── ChatService.swift             # SSE streaming via URLSession
│   ├── SpeechService.swift           # SFSpeechRecognizer wrapper
│   └── LocationService.swift         # CLLocationManager wrapper
├── Views/
│   ├── Auth/
│   │   ├── LoginView.swift           # Apple/Google sign-in buttons
│   │   ├── DisclaimerView.swift      # First-launch disclaimer modal
│   │   └── OnboardingView.swift      # First pet setup
│   ├── Chat/
│   │   ├── ChatView.swift            # Main chat screen (header + stream + input)
│   │   ├── ChatBubble.swift          # Single message bubble
│   │   ├── ChatInputBar.swift        # Text field + mic + send
│   │   └── TypingIndicator.swift     # Animated dots
│   ├── Cards/
│   │   ├── RecordCard.swift          # Calendar record card
│   │   ├── MapCard.swift             # Nearby places card
│   │   └── EmailCard.swift           # Email draft card
│   ├── Calendar/
│   │   ├── CalendarDrawer.swift      # Sheet with month grid + events
│   │   ├── MonthGrid.swift           # 7-col calendar grid
│   │   └── EventRow.swift            # Single event display + edit
│   ├── Settings/
│   │   ├── SettingsDrawer.swift      # Sheet with settings sections
│   │   ├── PetFormView.swift         # Add/edit pet form
│   │   └── LegalPageView.swift       # Privacy, disclaimer, about
│   └── Shared/
│       ├── EmergencyBanner.swift     # Red alert banner
│       └── EmptyStateView.swift      # Icon + title + subtitle
└── Utils/
    ├── HapticsHelper.swift           # UIImpactFeedbackGenerator wrappers
    └── CalendarHelper.swift          # getCalendarDays, month names, weekdays
```

---

### Task 1: Create Xcode Project + Theme

**Files:**
- Create: `ios-app/CozyPup/CozyPupApp.swift`
- Create: `ios-app/CozyPup/Theme/Tokens.swift`

- [ ] **Step 1: Create the Xcode project directory structure**

```bash
mkdir -p /Users/robert/Projects/CozyPup/ios-app/CozyPup.xcodeproj
mkdir -p /Users/robert/Projects/CozyPup/ios-app/CozyPup/{Theme,Models,Stores,Services,Views/{Auth,Chat,Cards,Calendar,Settings,Shared},Utils}
```

- [ ] **Step 2: Create the Xcode project via xcodegen or manually**

Create a `project.yml` for XcodeGen, then generate the `.xcodeproj`:

```yaml
# ios-app/project.yml
name: CozyPup
options:
  bundleIdPrefix: com.cozypup
  deploymentTarget:
    iOS: "17.0"
targets:
  CozyPup:
    type: application
    platform: iOS
    sources: [CozyPup]
    settings:
      INFOPLIST_FILE: CozyPup/Info.plist
      PRODUCT_BUNDLE_IDENTIFIER: com.cozypup.app
      MARKETING_VERSION: "1.0"
      CURRENT_PROJECT_VERSION: "1"
      DEVELOPMENT_TEAM: ""
```

Run: `brew install xcodegen && cd /Users/robert/Projects/CozyPup/ios-app && xcodegen generate`

Alternatively, open Xcode → File → New → Project → App (SwiftUI, Swift) → save to `ios-app/` with product name "CozyPup", then move source files into the generated structure.

- [ ] **Step 3: Write Tokens.swift — all design tokens**

```swift
// ios-app/CozyPup/Theme/Tokens.swift
import SwiftUI

enum Tokens {
    // MARK: - Colors
    static let bg = Color(hex: "FFF8F0")
    static let surface = Color.white
    static let surface2 = Color(hex: "FDF6EF")
    static let text = Color(hex: "3D2C1E")
    static let textSecondary = Color(hex: "8B7355")
    static let textTertiary = Color(hex: "B8A48E")
    static let accent = Color(hex: "E8835C")
    static let accentSoft = Color(hex: "FDEEE8")
    static let green = Color(hex: "7BAE7F")
    static let blue = Color(hex: "6BA3BE")
    static let red = Color(hex: "D35F5F")
    static let redSoft = Color(hex: "FFF0EC")
    static let orange = Color(hex: "E8A33C")
    static let purple = Color(hex: "9B7ED8")
    static let border = Color(hex: "F0E4D6")
    static let divider = Color(hex: "F0E4D6")
    static let inputPlaceholder = Color(hex: "C4AE96")
    static let typingDot = Color(hex: "D4C4B0")
    static let drawerOverlay = Color(hex: "3D2C1E").opacity(0.3)
    static let switchBg = Color(hex: "E0D5C8")
    static let switchActive = Color(hex: "7BAE7F")
    static let bubbleUser = Color(hex: "E8835C")
    static let bubbleAi = Color.white

    // MARK: - Fonts
    // Using system fonts as fallback; Fraunces + DM Sans can be added as custom fonts
    static let fontBody = Font.system(.body, design: .default)
    static let fontDisplay = Font.system(.title2, design: .serif)
    static let fontCaption = Font.system(.caption, design: .default)

    // MARK: - Radius
    static let radius: CGFloat = 20
    static let radiusSmall: CGFloat = 12
    static let radiusIcon: CGFloat = 14
}

extension Color {
    init(hex: String) {
        let scanner = Scanner(string: hex.trimmingCharacters(in: .alphanumerics.inverted))
        var rgb: UInt64 = 0
        scanner.scanHexInt64(&rgb)
        self.init(
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255
        )
    }
}
```

- [ ] **Step 4: Write minimal CozyPupApp.swift entry point**

```swift
// ios-app/CozyPup/CozyPupApp.swift
import SwiftUI

@main
struct CozyPupApp: App {
    var body: some Scene {
        WindowGroup {
            Text("CozyPup")
                .foregroundColor(Tokens.accent)
        }
    }
}
```

- [ ] **Step 5: Verify it builds**

Open in Xcode and build (Cmd+B), or: `xcodebuild -scheme CozyPup -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build`

- [ ] **Step 6: Commit**

```bash
git add ios-app/
git commit -m "feat(ios): scaffold SwiftUI project with design tokens"
```

---

### Task 2: Models

**Files:**
- Create: `ios-app/CozyPup/Models/Pet.swift`
- Create: `ios-app/CozyPup/Models/CalendarEvent.swift`
- Create: `ios-app/CozyPup/Models/ChatMessage.swift`

- [ ] **Step 1: Write Pet.swift**

```swift
import SwiftUI

let petColors: [Color] = [
    Color(hex: "E8835C"), Color(hex: "6BA3BE"), Color(hex: "7BAE7F"),
    Color(hex: "9B7ED8"), Color(hex: "E8A33C"),
]

let petColorHexes = ["E8835C", "6BA3BE", "7BAE7F", "9B7ED8", "E8A33C"]

enum Species: String, Codable, CaseIterable {
    case dog, cat, other
}

struct Pet: Identifiable, Codable, Equatable {
    let id: String
    var name: String
    var species: Species
    var breed: String
    var birthday: String?
    var weight: Double?
    var avatarUrl: String
    var colorHex: String
    let createdAt: String

    var color: Color { Color(hex: colorHex) }

    init(name: String, species: Species, breed: String, birthday: String?, weight: Double?, colorIndex: Int) {
        self.id = UUID().uuidString
        self.name = name
        self.species = species
        self.breed = breed
        self.birthday = birthday
        self.weight = weight
        self.avatarUrl = ""
        self.colorHex = petColorHexes[colorIndex % petColorHexes.count]
        self.createdAt = ISO8601DateFormatter().string(from: Date())
    }
}
```

- [ ] **Step 2: Write CalendarEvent.swift**

```swift
import Foundation

enum EventType: String, Codable, CaseIterable {
    case log, appointment, reminder
}

enum EventCategory: String, Codable, CaseIterable {
    case diet, excretion, abnormal, vaccine, deworming, medical, daily

    var label: String {
        switch self {
        case .diet: return "Diet"
        case .excretion: return "Excretion"
        case .abnormal: return "Abnormal"
        case .vaccine: return "Vaccine"
        case .deworming: return "Deworming"
        case .medical: return "Medical"
        case .daily: return "Daily"
        }
    }
}

enum EventSource: String, Codable {
    case chat, manual
}

struct CalendarEvent: Identifiable, Codable, Equatable {
    let id: String
    var petId: String
    var eventDate: String      // YYYY-MM-DD
    var eventTime: String?
    var title: String
    var type: EventType
    var category: EventCategory
    var rawText: String
    var source: EventSource
    var edited: Bool
    let createdAt: String

    init(petId: String, eventDate: String, eventTime: String?, title: String,
         type: EventType, category: EventCategory, rawText: String,
         source: EventSource, edited: Bool = false) {
        self.id = UUID().uuidString
        self.petId = petId
        self.eventDate = eventDate
        self.eventTime = eventTime
        self.title = title
        self.type = type
        self.category = category
        self.rawText = rawText
        self.source = source
        self.edited = edited
        self.createdAt = ISO8601DateFormatter().string(from: Date())
    }
}
```

- [ ] **Step 3: Write ChatMessage.swift**

```swift
import Foundation

enum MessageRole: String, Codable {
    case user, assistant
}

struct RecordCardData: Codable, Equatable {
    let type: String // "record"
    let pet_name: String
    let date: String
    let category: String
}

struct MapItem: Codable, Equatable {
    let name: String
    let description: String
    let distance: String
}

struct MapCardData: Codable, Equatable {
    let type: String // "map"
    let title: String
    let items: [MapItem]
}

struct EmailCardData: Codable, Equatable {
    let type: String // "email"
    let subject: String
    let body: String
}

enum CardData: Codable, Equatable {
    case record(RecordCardData)
    case map(MapCardData)
    case email(EmailCardData)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        // Try each type
        if let r = try? container.decode(RecordCardData.self), r.type == "record" {
            self = .record(r)
        } else if let m = try? container.decode(MapCardData.self), m.type == "map" {
            self = .map(m)
        } else if let e = try? container.decode(EmailCardData.self), e.type == "email" {
            self = .email(e)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unknown card type")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .record(let d): try container.encode(d)
        case .map(let d): try container.encode(d)
        case .email(let d): try container.encode(d)
        }
    }
}

struct ChatMessage: Identifiable, Codable, Equatable {
    let id: String
    let role: MessageRole
    var content: String
    var cards: [CardData]

    init(role: MessageRole, content: String = "", cards: [CardData] = []) {
        self.id = UUID().uuidString
        self.role = role
        self.content = content
        self.cards = cards
    }
}

struct EmergencyData: Equatable {
    let message: String
    let action: String
}
```

- [ ] **Step 4: Commit**

```bash
git add ios-app/CozyPup/Models/
git commit -m "feat(ios): add Pet, CalendarEvent, ChatMessage models"
```

---

### Task 3: Stores (UserDefaults persistence)

**Files:**
- Create: `ios-app/CozyPup/Stores/AuthStore.swift`
- Create: `ios-app/CozyPup/Stores/PetStore.swift`
- Create: `ios-app/CozyPup/Stores/CalendarStore.swift`
- Create: `ios-app/CozyPup/Stores/ChatStore.swift`

- [ ] **Step 1: Write AuthStore.swift**

```swift
import SwiftUI

struct UserInfo: Codable, Equatable {
    let name: String
    let email: String
}

@MainActor
class AuthStore: ObservableObject {
    @Published var isAuthenticated = false
    @Published var user: UserInfo?
    @Published var hasAcknowledgedDisclaimer = false

    private let authKey = "cozypup_auth"
    private let disclaimerKey = "cozypup_disclaimer"

    init() { load() }

    func load() {
        if let data = UserDefaults.standard.data(forKey: authKey),
           let saved = try? JSONDecoder().decode(UserInfo.self, from: data) {
            user = saved
            isAuthenticated = true
        }
        hasAcknowledgedDisclaimer = UserDefaults.standard.bool(forKey: disclaimerKey)
    }

    func login(provider: String) {
        let mockUsers: [String: UserInfo] = [
            "apple": UserInfo(name: "Apple User", email: "user@icloud.com"),
            "google": UserInfo(name: "Google User", email: "user@gmail.com"),
        ]
        user = mockUsers[provider]
        isAuthenticated = true
        if let data = try? JSONEncoder().encode(user) {
            UserDefaults.standard.set(data, forKey: authKey)
        }
    }

    func logout() {
        isAuthenticated = false
        user = nil
        hasAcknowledgedDisclaimer = false
        UserDefaults.standard.removeObject(forKey: authKey)
        UserDefaults.standard.removeObject(forKey: disclaimerKey)
    }

    func acknowledgeDisclaimer() {
        hasAcknowledgedDisclaimer = true
        UserDefaults.standard.set(true, forKey: disclaimerKey)
    }
}
```

- [ ] **Step 2: Write PetStore.swift**

```swift
import SwiftUI

@MainActor
class PetStore: ObservableObject {
    @Published var pets: [Pet] = []

    private let key = "cozypup_pets"

    init() { load() }

    func load() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let saved = try? JSONDecoder().decode([Pet].self, from: data) else { return }
        pets = saved
    }

    private func save() {
        if let data = try? JSONEncoder().encode(pets) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    func add(name: String, species: Species, breed: String, birthday: String?, weight: Double?) {
        let pet = Pet(name: name, species: species, breed: breed,
                      birthday: birthday, weight: weight, colorIndex: pets.count)
        pets.append(pet)
        save()
    }

    func update(_ id: String, name: String, species: Species, breed: String, birthday: String?, weight: Double?) {
        guard let idx = pets.firstIndex(where: { $0.id == id }) else { return }
        pets[idx].name = name
        pets[idx].species = species
        pets[idx].breed = breed
        pets[idx].birthday = birthday
        pets[idx].weight = weight
        save()
    }

    func remove(_ id: String) {
        pets.removeAll { $0.id == id }
        save()
    }

    func getById(_ id: String) -> Pet? {
        pets.first { $0.id == id }
    }
}
```

- [ ] **Step 3: Write CalendarStore.swift**

```swift
import Foundation

@MainActor
class CalendarStore: ObservableObject {
    @Published var events: [CalendarEvent] = []

    private let key = "cozypup_calendar"

    init() { load() }

    func load() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let saved = try? JSONDecoder().decode([CalendarEvent].self, from: data) else { return }
        events = saved
    }

    private func save() {
        if let data = try? JSONEncoder().encode(events) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    func add(_ event: CalendarEvent) {
        events.append(event)
        save()
    }

    func update(_ id: String, title: String? = nil, category: EventCategory? = nil,
                eventDate: String? = nil, eventTime: String? = nil) {
        guard let idx = events.firstIndex(where: { $0.id == id }) else { return }
        if let t = title { events[idx].title = t }
        if let c = category { events[idx].category = c }
        if let d = eventDate { events[idx].eventDate = d }
        if let t = eventTime { events[idx].eventTime = t }
        events[idx].edited = true
        save()
    }

    func remove(_ id: String) {
        events.removeAll { $0.id == id }
        save()
    }

    func eventsForDate(_ date: String) -> [CalendarEvent] {
        events.filter { $0.eventDate == date }
    }

    func eventsForMonth(year: Int, month: Int) -> [CalendarEvent] {
        let prefix = String(format: "%04d-%02d", year, month + 1)
        return events.filter { $0.eventDate.hasPrefix(prefix) }
    }

    func eventsForPet(_ petId: String) -> [CalendarEvent] {
        events.filter { $0.petId == petId }
    }

    func seedDemoData(pets: [Pet]) {
        guard events.isEmpty, let pet = pets.first else { return }
        let cal = Calendar.current
        let now = Date()
        let year = cal.component(.year, from: now)
        let month = cal.component(.month, from: now)
        let day = cal.component(.day, from: now)
        func dateStr(_ d: Int) -> String {
            String(format: "%04d-%02d-%02d", year, month, d)
        }

        let demos: [(String, String?, String, EventType, EventCategory)] = [
            (dateStr(3), "08:30", "Morning walk & breakfast", .log, .daily),
            (dateStr(7), "10:00", "Annual vaccine booster", .appointment, .vaccine),
            (dateStr(12), nil, "Ate well, normal stool", .log, .diet),
            (dateStr(18), "14:00", "Deworming reminder", .reminder, .deworming),
            (dateStr(day), "09:00", "Morning checkup", .log, .daily),
        ]

        for (date, time, title, type, cat) in demos {
            let evt = CalendarEvent(petId: pet.id, eventDate: date, eventTime: time,
                                    title: title, type: type, category: cat,
                                    rawText: title, source: .chat)
            events.append(evt)
        }
        save()
    }
}
```

- [ ] **Step 4: Write ChatStore.swift**

```swift
import Foundation

@MainActor
class ChatStore: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var sessionId: String?

    private let messagesKey = "cozypup_chat_messages"
    private let sessionKey = "cozypup_chat_session"

    init() { load() }

    func load() {
        // Load messages
        if let data = UserDefaults.standard.data(forKey: messagesKey),
           let saved = try? JSONDecoder().decode([ChatMessage].self, from: data) {
            messages = saved
        }
        // Load session (reset daily)
        if let data = UserDefaults.standard.data(forKey: sessionKey),
           let session = try? JSONDecoder().decode(SessionData.self, from: data) {
            let today = Self.todayStr()
            if session.date == today {
                sessionId = session.id
            } else {
                clear()
            }
        }
    }

    func save() {
        if let data = try? JSONEncoder().encode(messages) {
            UserDefaults.standard.set(data, forKey: messagesKey)
        }
    }

    func saveSession(_ id: String) {
        sessionId = id
        let session = SessionData(id: id, date: Self.todayStr())
        if let data = try? JSONEncoder().encode(session) {
            UserDefaults.standard.set(data, forKey: sessionKey)
        }
    }

    func clear() {
        messages = []
        sessionId = nil
        UserDefaults.standard.removeObject(forKey: messagesKey)
        UserDefaults.standard.removeObject(forKey: sessionKey)
    }

    private static func todayStr() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: Date())
    }

    private struct SessionData: Codable {
        let id: String
        let date: String
    }
}
```

- [ ] **Step 5: Commit**

```bash
git add ios-app/CozyPup/Stores/
git commit -m "feat(ios): add AuthStore, PetStore, CalendarStore, ChatStore"
```

---

### Task 4: Services (Chat SSE, Speech, Location)

**Files:**
- Create: `ios-app/CozyPup/Services/ChatService.swift`
- Create: `ios-app/CozyPup/Services/SpeechService.swift`
- Create: `ios-app/CozyPup/Services/LocationService.swift`

- [ ] **Step 1: Write ChatService.swift — SSE streaming**

```swift
import Foundation

struct ChatRequest: Encodable {
    let message: String
    let session_id: String?
    let location: LocationCoord?

    struct LocationCoord: Encodable {
        let lat: Double
        let lng: Double
    }
}

enum SSEEvent {
    case token(String)
    case card(CardData)
    case emergency(EmergencyData)
    case done(intent: String, sessionId: String)
}

class ChatService {
    // Update this to match your development machine's IP
    static let baseURL = "http://localhost:8000/api/v1"

    static func streamChat(message: String, sessionId: String?,
                           location: (lat: Double, lng: Double)?) -> AsyncThrowingStream<SSEEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                let url = URL(string: "\(baseURL)/chat")!
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")

                let body = ChatRequest(
                    message: message,
                    session_id: sessionId,
                    location: location.map { .init(lat: $0.lat, lng: $0.lng) }
                )
                request.httpBody = try? JSONEncoder().encode(body)

                do {
                    let (bytes, response) = try await URLSession.shared.bytes(for: request)
                    guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                        continuation.finish(throwing: URLError(.badServerResponse))
                        return
                    }

                    var currentEvent = ""
                    for try await line in bytes.lines {
                        if line.hasPrefix("event: ") {
                            currentEvent = String(line.dropFirst(7))
                        } else if line.hasPrefix("data: "), !currentEvent.isEmpty {
                            let json = Data(line.dropFirst(6).utf8)
                            switch currentEvent {
                            case "token":
                                if let obj = try? JSONDecoder().decode([String: String].self, from: json),
                                   let text = obj["text"] {
                                    continuation.yield(.token(text))
                                }
                            case "card":
                                if let card = try? JSONDecoder().decode(CardData.self, from: json) {
                                    continuation.yield(.card(card))
                                }
                            case "emergency":
                                if let obj = try? JSONDecoder().decode([String: String].self, from: json),
                                   let msg = obj["message"], let action = obj["action"] {
                                    continuation.yield(.emergency(EmergencyData(message: msg, action: action)))
                                }
                            case "done":
                                if let obj = try? JSONDecoder().decode([String: String].self, from: json) {
                                    continuation.yield(.done(
                                        intent: obj["intent"] ?? "chat",
                                        sessionId: obj["session_id"] ?? ""
                                    ))
                                }
                            default: break
                            }
                            currentEvent = ""
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
}
```

- [ ] **Step 2: Write SpeechService.swift**

```swift
import Speech
import AVFoundation

@MainActor
class SpeechService: ObservableObject {
    @Published var isListening = false
    @Published var transcript = ""

    private var recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var recognitionTask: SFSpeechRecognitionTask?
    private var audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?

    func requestPermission() async -> Bool {
        await withCheckedContinuation { cont in
            SFSpeechRecognizer.requestAuthorization { status in
                cont.resume(returning: status == .authorized)
            }
        }
    }

    func startListening() {
        guard !isListening else { return }

        let audioSession = AVAudioSession.sharedInstance()
        try? audioSession.setCategory(.record, mode: .measurement, options: .duckOthers)
        try? audioSession.setActive(true, options: .notifyOthersOnDeactivation)

        recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
        guard let request = recognitionRequest else { return }
        request.shouldReportPartialResults = true

        let node = audioEngine.inputNode
        let format = node.outputFormat(forBus: 0)
        node.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
        }

        audioEngine.prepare()
        try? audioEngine.start()

        recognitionTask = recognizer?.recognitionTask(with: request) { [weak self] result, error in
            guard let self else { return }
            if let result {
                Task { @MainActor in
                    self.transcript = result.bestTranscription.formattedString
                }
            }
            if error != nil || result?.isFinal == true {
                Task { @MainActor in
                    self.stopListening()
                }
            }
        }

        transcript = ""
        isListening = true
    }

    func stopListening() {
        audioEngine.stop()
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()
        recognitionTask?.cancel()
        recognitionRequest = nil
        recognitionTask = nil
        isListening = false
    }
}
```

- [ ] **Step 3: Write LocationService.swift**

```swift
import CoreLocation

@MainActor
class LocationService: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published var lastLocation: CLLocationCoordinate2D?

    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<CLLocationCoordinate2D?, Never>?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func requestLocation() async -> CLLocationCoordinate2D? {
        manager.requestWhenInUseAuthorization()
        return await withCheckedContinuation { cont in
            continuation = cont
            manager.requestLocation()
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        let coord = locations.first?.coordinate
        Task { @MainActor in
            self.lastLocation = coord
            self.continuation?.resume(returning: coord)
            self.continuation = nil
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in
            self.continuation?.resume(returning: nil)
            self.continuation = nil
        }
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add ios-app/CozyPup/Services/
git commit -m "feat(ios): add ChatService (SSE), SpeechService, LocationService"
```

---

### Task 5: Utils (Haptics + Calendar)

**Files:**
- Create: `ios-app/CozyPup/Utils/HapticsHelper.swift`
- Create: `ios-app/CozyPup/Utils/CalendarHelper.swift`

- [ ] **Step 1: Write HapticsHelper.swift**

```swift
import UIKit

enum Haptics {
    static func light() {
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
    }
    static func medium() {
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
    }
}
```

- [ ] **Step 2: Write CalendarHelper.swift**

```swift
import Foundation

struct CalendarDay: Identifiable {
    let id = UUID()
    let date: Int
    let month: Int   // 0-11
    let year: Int
    let isCurrentMonth: Bool
    let isToday: Bool
}

enum CalendarHelper {
    static let monthNames = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    static let weekdays = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]

    static func getCalendarDays(year: Int, month: Int) -> [CalendarDay] {
        let cal = Calendar.current
        let today = Date()
        let todayComps = cal.dateComponents([.year, .month, .day], from: today)

        var comps = DateComponents(year: year, month: month + 1, day: 1)
        guard let first = cal.date(from: comps) else { return [] }
        let startPad = cal.component(.weekday, from: first) - 1 // 0=Sun

        comps.month = month + 2; comps.day = 0
        guard let last = cal.date(from: comps) else { return [] }
        let daysInMonth = cal.component(.day, from: last)

        // Previous month
        comps = DateComponents(year: year, month: month + 1, day: 0)
        let prevLast = cal.date(from: comps).map { cal.component(.day, from: $0) } ?? 28
        let prevMonth = month - 1 < 0 ? 11 : month - 1
        let prevYear = month - 1 < 0 ? year - 1 : year

        var days: [CalendarDay] = []

        for i in stride(from: startPad - 1, through: 0, by: -1) {
            days.append(CalendarDay(date: prevLast - i, month: prevMonth, year: prevYear,
                                    isCurrentMonth: false, isToday: false))
        }

        for d in 1...daysInMonth {
            let isToday = d == todayComps.day && month == (todayComps.month ?? 0) - 1 && year == todayComps.year
            days.append(CalendarDay(date: d, month: month, year: year,
                                    isCurrentMonth: true, isToday: isToday))
        }

        let remaining = 7 - (days.count % 7)
        if remaining < 7 {
            let nextMonth = month + 1 > 11 ? 0 : month + 1
            let nextYear = month + 1 > 11 ? year + 1 : year
            for i in 1...remaining {
                days.append(CalendarDay(date: i, month: nextMonth, year: nextYear,
                                        isCurrentMonth: false, isToday: false))
            }
        }

        return days
    }

    static func dateString(year: Int, month: Int, day: Int) -> String {
        String(format: "%04d-%02d-%02d", year, month + 1, day)
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add ios-app/CozyPup/Utils/
git commit -m "feat(ios): add HapticsHelper and CalendarHelper utils"
```

---

### Task 6: Auth Views (Login, Disclaimer, Onboarding)

**Files:**
- Create: `ios-app/CozyPup/Views/Auth/LoginView.swift`
- Create: `ios-app/CozyPup/Views/Auth/DisclaimerView.swift`
- Create: `ios-app/CozyPup/Views/Auth/OnboardingView.swift`
- Create: `ios-app/CozyPup/Views/Settings/PetFormView.swift`

- [ ] **Step 1: Write LoginView.swift**

```swift
import SwiftUI

struct LoginView: View {
    @EnvironmentObject var auth: AuthStore

    var body: some View {
        VStack(spacing: 40) {
            Spacer()
            VStack(spacing: 12) {
                Image("logo")
                    .resizable()
                    .frame(width: 80, height: 80)
                    .cornerRadius(20)
                Text("Cozy Pup")
                    .font(.system(.largeTitle, design: .serif))
                    .fontWeight(.semibold)
                    .foregroundColor(Tokens.accent)
                Text("Your pet's personal butler")
                    .font(Tokens.fontBody)
                    .foregroundColor(Tokens.textSecondary)
            }

            VStack(spacing: 14) {
                Button {
                    Haptics.light()
                    auth.login(provider: "apple")
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "apple.logo")
                        Text("Sign in with Apple")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Tokens.text)
                    .foregroundColor(.white)
                    .cornerRadius(16)
                    .font(.system(size: 16, weight: .semibold))
                }

                Button {
                    Haptics.light()
                    auth.login(provider: "google")
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "g.circle.fill")
                        Text("Sign in with Google")
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Tokens.surface)
                    .foregroundColor(Tokens.text)
                    .overlay(RoundedRectangle(cornerRadius: 16).stroke(Tokens.border, lineWidth: 1))
                    .cornerRadius(16)
                    .font(.system(size: 16, weight: .semibold))
                }
            }
            .padding(.horizontal, 32)

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Tokens.bg.ignoresSafeArea())
    }
}
```

- [ ] **Step 2: Write DisclaimerView.swift**

```swift
import SwiftUI

struct DisclaimerView: View {
    @EnvironmentObject var auth: AuthStore

    var body: some View {
        ZStack {
            Tokens.drawerOverlay.ignoresSafeArea()

            VStack(spacing: 20) {
                Text("Before We Begin")
                    .font(.system(.title2, design: .serif))
                    .fontWeight(.semibold)
                    .foregroundColor(Tokens.text)

                Text("AI suggestions are for reference only and do not constitute veterinary advice. In emergencies, please contact a veterinarian immediately. By continuing, you acknowledge these limitations.")
                    .font(.system(size: 15))
                    .foregroundColor(Tokens.textSecondary)
                    .multilineTextAlignment(.center)

                Button {
                    Haptics.light()
                    auth.acknowledgeDisclaimer()
                } label: {
                    Text("I Understand")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Tokens.accent)
                        .foregroundColor(.white)
                        .cornerRadius(14)
                        .font(.system(size: 16, weight: .semibold))
                }
            }
            .padding(28)
            .background(Tokens.surface)
            .cornerRadius(24)
            .shadow(color: .black.opacity(0.1), radius: 20)
            .padding(.horizontal, 32)
        }
        .background(Tokens.bg.ignoresSafeArea())
    }
}
```

- [ ] **Step 3: Write PetFormView.swift** (shared by onboarding + settings)

```swift
import SwiftUI

struct PetFormView: View {
    var editingPet: Pet?
    var onSave: (String, Species, String, String?, Double?) -> Void
    var onCancel: (() -> Void)?

    @State private var name = ""
    @State private var species: Species = .dog
    @State private var breed = ""
    @State private var birthday = ""
    @State private var weight = ""

    var body: some View {
        VStack(spacing: 16) {
            // Name
            VStack(alignment: .leading, spacing: 6) {
                Text("Name").font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                TextField("e.g. Buddy", text: $name)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(Tokens.surface)
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
            }

            // Species
            VStack(alignment: .leading, spacing: 6) {
                Text("Species").font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                HStack(spacing: 10) {
                    ForEach(Species.allCases, id: \.self) { s in
                        Button {
                            species = s
                        } label: {
                            Text(s.rawValue.capitalized)
                                .font(.system(size: 14, weight: .medium))
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                                .background(species == s ? Tokens.accent : Tokens.surface)
                                .foregroundColor(species == s ? .white : Tokens.text)
                                .cornerRadius(20)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 20)
                                        .stroke(species == s ? Color.clear : Tokens.border)
                                )
                        }
                    }
                }
            }

            // Breed
            VStack(alignment: .leading, spacing: 6) {
                Text("Breed").font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                TextField("e.g. Golden Retriever", text: $breed)
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(Tokens.surface)
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
            }

            // Birthday + Weight
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Birthday").font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                    TextField("YYYY-MM-DD", text: $birthday)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(Tokens.surface)
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("Weight (kg)").font(.system(size: 13, weight: .medium)).foregroundColor(Tokens.textSecondary)
                    TextField("0.0", text: $weight)
                        .keyboardType(.decimalPad)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(Tokens.surface)
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
                }
            }

            // Save button
            Button {
                Haptics.light()
                let bday = birthday.isEmpty ? nil : birthday
                let w = Double(weight)
                onSave(name, species, breed, bday, w)
            } label: {
                Text(editingPet != nil ? "Save Changes" : "Add Pet")
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(name.isEmpty ? Tokens.border : Tokens.accent)
                    .foregroundColor(.white)
                    .cornerRadius(14)
                    .font(.system(size: 16, weight: .semibold))
            }
            .disabled(name.isEmpty)

            if let onCancel {
                Button("Cancel") { onCancel() }
                    .foregroundColor(Tokens.textSecondary)
            }
        }
        .onAppear {
            if let pet = editingPet {
                name = pet.name
                species = pet.species
                breed = pet.breed
                birthday = pet.birthday ?? ""
                weight = pet.weight.map { String($0) } ?? ""
            }
        }
    }
}
```

- [ ] **Step 4: Write OnboardingView.swift**

```swift
import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var petStore: PetStore

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                VStack(spacing: 8) {
                    Text("Welcome to Cozy Pup!")
                        .font(.system(.title, design: .serif))
                        .fontWeight(.semibold)
                        .foregroundColor(Tokens.text)
                    Text("Let's set up your first pet")
                        .font(Tokens.fontBody)
                        .foregroundColor(Tokens.textSecondary)
                }
                .padding(.top, 60)

                PetFormView { name, species, breed, birthday, weight in
                    petStore.add(name: name, species: species, breed: breed,
                                 birthday: birthday, weight: weight)
                }
                .padding(.horizontal, 24)
            }
        }
        .background(Tokens.bg.ignoresSafeArea())
    }
}
```

- [ ] **Step 5: Commit**

```bash
git add ios-app/CozyPup/Views/Auth/ ios-app/CozyPup/Views/Settings/PetFormView.swift
git commit -m "feat(ios): add Login, Disclaimer, Onboarding, PetForm views"
```

---

### Task 7: Chat Views (Main screen)

**Files:**
- Create: `ios-app/CozyPup/Views/Chat/ChatView.swift`
- Create: `ios-app/CozyPup/Views/Chat/ChatBubble.swift`
- Create: `ios-app/CozyPup/Views/Chat/ChatInputBar.swift`
- Create: `ios-app/CozyPup/Views/Chat/TypingIndicator.swift`
- Create: `ios-app/CozyPup/Views/Shared/EmergencyBanner.swift`
- Create: `ios-app/CozyPup/Views/Shared/EmptyStateView.swift`

- [ ] **Step 1: Write ChatBubble.swift**

```swift
import SwiftUI

struct ChatBubble: View {
    let role: MessageRole
    let content: String

    private var isUser: Bool { role == .user }

    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 60) }
            Text(content)
                .font(.system(size: 15))
                .foregroundColor(isUser ? .white : Tokens.text)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(isUser ? Tokens.bubbleUser : Tokens.bubbleAi)
                .cornerRadius(Tokens.radius)
                .shadow(color: isUser ? .clear : .black.opacity(0.06), radius: 8, y: 2)
            if !isUser { Spacer(minLength: 60) }
        }
    }
}
```

- [ ] **Step 2: Write TypingIndicator.swift**

```swift
import SwiftUI

struct TypingIndicator: View {
    @State private var phase = 0.0

    var body: some View {
        HStack {
            HStack(spacing: 5) {
                ForEach(0..<3) { i in
                    Circle()
                        .fill(Tokens.typingDot)
                        .frame(width: 8, height: 8)
                        .offset(y: sin(phase + Double(i) * .pi / 1.5) * 4)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(Tokens.bubbleAi)
            .cornerRadius(Tokens.radius)
            .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
            Spacer()
        }
        .onAppear {
            withAnimation(.linear(duration: 1.0).repeatForever(autoreverses: false)) {
                phase = .pi * 2
            }
        }
    }
}
```

- [ ] **Step 3: Write EmptyStateView.swift**

```swift
import SwiftUI

struct EmptyStateView: View {
    let icon: String   // SF Symbol name
    let title: String
    var subtitle: String?

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: icon)
                .font(.system(size: 48))
                .foregroundColor(Tokens.textTertiary)
            Text(title)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(Tokens.textSecondary)
            if let subtitle {
                Text(subtitle)
                    .font(.system(size: 14))
                    .foregroundColor(Tokens.textTertiary)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }
}
```

- [ ] **Step 4: Write EmergencyBanner.swift**

```swift
import SwiftUI

struct EmergencyBanner: View {
    var onFind: () -> Void
    var onDismiss: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.white)
                .padding(6)
                .background(Tokens.red)
                .cornerRadius(8)

            VStack(alignment: .leading, spacing: 2) {
                Text("Possible emergency detected")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Tokens.text)
                Text("Find a nearby 24h pet ER?")
                    .font(.system(size: 12))
                    .foregroundColor(Tokens.textSecondary)
            }

            Spacer()

            Button("Find") { onFind() }
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Tokens.red)
                .cornerRadius(10)

            Button { onDismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(Tokens.textSecondary)
            }
        }
        .padding(12)
        .background(Tokens.redSoft)
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "F5C4B5")))
        .padding(.horizontal, 12)
    }
}
```

- [ ] **Step 5: Write ChatInputBar.swift**

```swift
import SwiftUI

struct ChatInputBar: View {
    @Binding var text: String
    var isStreaming: Bool
    var isListening: Bool
    var onSend: () -> Void
    var onMicToggle: () -> Void

    private var hasText: Bool { !text.trimmingCharacters(in: .whitespaces).isEmpty }

    var body: some View {
        HStack(spacing: 8) {
            // Plus button
            Button { } label: {
                Image(systemName: "plus")
                    .font(.system(size: 20, weight: .medium))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: 44, height: 44)
                    .overlay(Circle().stroke(Tokens.border))
            }

            // Input field
            HStack(spacing: 4) {
                TextField("Talk to Cozy Pup...", text: $text)
                    .font(.system(size: 16))
                    .foregroundColor(Tokens.text)
                    .disabled(isStreaming)
                    .onSubmit { if hasText { onSend() } }

                if hasText {
                    Button {
                        Haptics.light()
                        onSend()
                    } label: {
                        Image(systemName: "arrow.up")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white)
                            .frame(width: 40, height: 40)
                            .background(Tokens.accent)
                            .clipShape(Circle())
                    }
                    .disabled(isStreaming)
                } else {
                    Button {
                        onMicToggle()
                    } label: {
                        Image(systemName: "mic")
                            .font(.system(size: 18, weight: .medium))
                            .foregroundColor(isListening ? Tokens.red : Tokens.textSecondary)
                            .frame(width: 40, height: 40)
                            .opacity(isListening ? 0.5 : 1)
                            .animation(.easeInOut(duration: 0.75).repeatForever(autoreverses: true), value: isListening)
                    }
                }
            }
            .padding(.leading, 16)
            .padding(.trailing, 4)
            .frame(height: 48)
            .background(Tokens.surface)
            .cornerRadius(24)
            .overlay(RoundedRectangle(cornerRadius: 24).stroke(Tokens.border))
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 4)
        .background(Tokens.bg)
    }
}
```

- [ ] **Step 6: Write ChatView.swift — main chat screen**

```swift
import SwiftUI

struct ChatView: View {
    @EnvironmentObject var chatStore: ChatStore
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @StateObject private var speech = SpeechService()
    @StateObject private var location = LocationService()

    @State private var inputText = ""
    @State private var isStreaming = false
    @State private var emergency: EmergencyData?
    @State private var showCalendar = false
    @State private var showSettings = false

    var body: some View {
        VStack(spacing: 0) {
            // Header
            header

            // Emergency
            if let emergency {
                EmergencyBanner(
                    onFind: { self.emergency = nil },
                    onDismiss: { self.emergency = nil }
                )
            }

            // Chat stream
            ScrollViewReader { proxy in
                ScrollView {
                    if chatStore.messages.isEmpty {
                        EmptyStateView(
                            icon: "bubble.left.and.bubble.right",
                            title: "Ask Cozy Pup anything",
                            subtitle: "Health questions, record keeping, vet recommendations..."
                        )
                        .frame(minHeight: 400)
                    }
                    LazyVStack(spacing: 10) {
                        ForEach(chatStore.messages) { msg in
                            VStack(spacing: 8) {
                                if !msg.content.isEmpty {
                                    ChatBubble(role: msg.role, content: msg.content)
                                }
                                ForEach(Array(msg.cards.enumerated()), id: \.offset) { _, card in
                                    cardView(card)
                                }
                            }
                        }
                        if isStreaming, let last = chatStore.messages.last, last.content.isEmpty {
                            TypingIndicator()
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 12)
                    Color.clear.frame(height: 1).id("bottom")
                }
                .onChange(of: chatStore.messages.count) {
                    withAnimation { proxy.scrollTo("bottom") }
                }
            }

            // Disclaimer
            Text("AI suggestions are for reference only. In emergencies, see a vet.")
                .font(.system(size: 11))
                .foregroundColor(Tokens.textSecondary)
                .padding(.vertical, 6)

            // Input
            ChatInputBar(
                text: $inputText,
                isStreaming: isStreaming,
                isListening: speech.isListening,
                onSend: sendMessage,
                onMicToggle: toggleMic
            )
        }
        .background(Tokens.bg.ignoresSafeArea())
        .sheet(isPresented: $showCalendar) {
            CalendarDrawer()
        }
        .sheet(isPresented: $showSettings) {
            SettingsDrawer()
        }
        .onChange(of: speech.transcript) {
            if speech.isListening { inputText = speech.transcript }
        }
        .onAppear {
            calendarStore.seedDemoData(pets: petStore.pets)
            Task { await location.requestLocation() }
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Button { Haptics.light(); showCalendar = true } label: {
                Image(systemName: "calendar")
                    .font(.system(size: 18))
                    .foregroundColor(Tokens.text)
                    .frame(width: 40, height: 40)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radiusIcon)
                    .overlay(RoundedRectangle(cornerRadius: Tokens.radiusIcon).stroke(Tokens.border))
                    .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
            }

            Spacer()

            HStack(spacing: 8) {
                Image("logo")
                    .resizable()
                    .frame(width: 28, height: 28)
                    .cornerRadius(8)
                Text("Cozy Pup")
                    .font(.system(.title3, design: .serif))
                    .fontWeight(.medium)
                    .foregroundColor(Tokens.accent)
            }

            Spacer()

            Button { Haptics.light(); showSettings = true } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 18))
                    .foregroundColor(Tokens.text)
                    .frame(width: 40, height: 40)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radiusIcon)
                    .overlay(RoundedRectangle(cornerRadius: Tokens.radiusIcon).stroke(Tokens.border))
                    .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
            }
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 12)
    }

    // MARK: - Cards

    @ViewBuilder
    private func cardView(_ card: CardData) -> some View {
        switch card {
        case .record(let data):
            RecordCard(petName: data.pet_name, date: data.date, category: data.category) {
                showCalendar = true
            }
        case .map(let data):
            MapCard(items: data.items)
        case .email(let data):
            EmailCard(subject: data.subject, emailBody: data.body)
        }
    }

    // MARK: - Actions

    private func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty, !isStreaming else { return }
        Haptics.light()

        let userMsg = ChatMessage(role: .user, content: text)
        let assistantMsg = ChatMessage(role: .assistant)
        chatStore.messages.append(userMsg)
        chatStore.messages.append(assistantMsg)
        chatStore.save()

        inputText = ""
        isStreaming = true

        Task {
            let coord = location.lastLocation
            let loc = coord.map { (lat: $0.latitude, lng: $0.longitude) }
            let stream = ChatService.streamChat(
                message: text, sessionId: chatStore.sessionId, location: loc
            )

            do {
                for try await event in stream {
                    guard let idx = chatStore.messages.indices.last else { break }
                    switch event {
                    case .token(let t):
                        chatStore.messages[idx].content += t
                    case .card(let c):
                        chatStore.messages[idx].cards.append(c)
                    case .emergency(let e):
                        emergency = e
                    case .done(_, let sid):
                        chatStore.saveSession(sid)
                    }
                }
            } catch {
                if let idx = chatStore.messages.indices.last,
                   chatStore.messages[idx].content.isEmpty {
                    chatStore.messages[idx].content = "Sorry, something went wrong. Please try again."
                }
            }
            chatStore.save()
            isStreaming = false
        }
    }

    private func toggleMic() {
        if speech.isListening {
            speech.stopListening()
        } else {
            Task {
                let granted = await speech.requestPermission()
                if granted { speech.startListening() }
            }
        }
    }
}
```

- [ ] **Step 7: Commit**

```bash
git add ios-app/CozyPup/Views/Chat/ ios-app/CozyPup/Views/Shared/
git commit -m "feat(ios): add ChatView, ChatBubble, ChatInputBar, TypingIndicator, EmergencyBanner, EmptyState"
```

---

### Task 8: Card Views

**Files:**
- Create: `ios-app/CozyPup/Views/Cards/RecordCard.swift`
- Create: `ios-app/CozyPup/Views/Cards/MapCard.swift`
- Create: `ios-app/CozyPup/Views/Cards/EmailCard.swift`

- [ ] **Step 1: Write RecordCard.swift**

```swift
import SwiftUI

struct RecordCard: View {
    let petName: String
    let date: String
    let category: String
    var onTap: (() -> Void)?

    var body: some View {
        HStack {
            Button(action: { onTap?() }) {
                HStack(spacing: 12) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Tokens.accent)
                        .frame(width: 4, height: 36)

                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Circle().fill(Tokens.accent).frame(width: 6, height: 6)
                            Text("Recorded to Calendar")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(Tokens.textSecondary)
                        }
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle")
                                .font(.system(size: 14))
                                .foregroundColor(Tokens.green)
                            VStack(alignment: .leading, spacing: 1) {
                                Text("\(petName) · \(category)")
                                    .font(.system(size: 14, weight: .medium))
                                    .foregroundColor(Tokens.text)
                                Text(date)
                                    .font(.system(size: 12))
                                    .foregroundColor(Tokens.textSecondary)
                            }
                        }
                    }

                    Spacer()
                }
                .padding(12)
                .background(Tokens.surface)
                .cornerRadius(Tokens.radiusSmall)
                .overlay(RoundedRectangle(cornerRadius: Tokens.radiusSmall).stroke(Tokens.border))
            }
            .buttonStyle(.plain)
            Spacer()
        }
    }
}
```

- [ ] **Step 2: Write MapCard.swift**

```swift
import SwiftUI

struct MapCard: View {
    let items: [MapItem]

    private let icons = ["tree", "fence", "figure.walk"]

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "mappin.and.ellipse")
                        .font(.system(size: 12))
                        .foregroundColor(Tokens.accent)
                    Text("Nearby Pet-Friendly Places")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(Tokens.textSecondary)
                }

                ForEach(Array(items.enumerated()), id: \.offset) { i, item in
                    HStack(spacing: 12) {
                        Image(systemName: icons[i % icons.count])
                            .font(.system(size: 14))
                            .foregroundColor(Tokens.green)
                            .frame(width: 28, height: 28)
                            .background(Tokens.accentSoft)
                            .cornerRadius(8)

                        VStack(alignment: .leading, spacing: 1) {
                            Text(item.name)
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(Tokens.text)
                            Text(item.description)
                                .font(.system(size: 12))
                                .foregroundColor(Tokens.textSecondary)
                        }

                        Spacer()

                        Text(item.distance)
                            .font(.system(size: 12))
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
            }
            .padding(12)
            .background(Tokens.surface)
            .cornerRadius(Tokens.radiusSmall)
            .overlay(RoundedRectangle(cornerRadius: Tokens.radiusSmall).stroke(Tokens.border))
            Spacer()
        }
    }
}
```

- [ ] **Step 3: Write EmailCard.swift**

```swift
import SwiftUI

struct EmailCard: View {
    let subject: String
    let emailBody: String
    @State private var copied = false

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "envelope")
                        .font(.system(size: 12))
                        .foregroundColor(Tokens.blue)
                    Text("Email Draft")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(Tokens.textSecondary)
                }

                Text(subject)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Tokens.text)

                Text(emailBody)
                    .font(.system(size: 13))
                    .foregroundColor(Tokens.textSecondary)

                HStack(spacing: 8) {
                    Button {
                        UIPasteboard.general.string = "\(subject)\n\n\(emailBody)"
                        copied = true
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { copied = false }
                    } label: {
                        Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(Tokens.textSecondary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
                    }

                    ShareLink(item: "\(subject)\n\n\(emailBody)") {
                        Label("Share", systemImage: "square.and.arrow.up")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(Tokens.textSecondary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
                    }
                }
            }
            .padding(12)
            .background(Tokens.surface)
            .cornerRadius(Tokens.radiusSmall)
            .overlay(RoundedRectangle(cornerRadius: Tokens.radiusSmall).stroke(Tokens.border))
            Spacer()
        }
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add ios-app/CozyPup/Views/Cards/
git commit -m "feat(ios): add RecordCard, MapCard, EmailCard views"
```

---

### Task 9: Calendar Drawer

**Files:**
- Create: `ios-app/CozyPup/Views/Calendar/CalendarDrawer.swift`
- Create: `ios-app/CozyPup/Views/Calendar/MonthGrid.swift`
- Create: `ios-app/CozyPup/Views/Calendar/EventRow.swift`

- [ ] **Step 1: Write MonthGrid.swift**

```swift
import SwiftUI

struct MonthGrid: View {
    let days: [CalendarDay]
    let events: [CalendarEvent]
    let pets: [Pet]
    @Binding var selectedDate: String?
    var filterPetId: String?

    private let columns = Array(repeating: GridItem(.flexible()), count: 7)

    var body: some View {
        VStack(spacing: 0) {
            // Weekday headers
            LazyVGrid(columns: columns) {
                ForEach(CalendarHelper.weekdays, id: \.self) { day in
                    Text(day)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(Tokens.textTertiary)
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 4)

            // Day cells
            LazyVGrid(columns: columns, spacing: 2) {
                ForEach(days) { day in
                    let dateStr = CalendarHelper.dateString(year: day.year, month: day.month, day: day.date)
                    let dayEvents = filteredEvents(for: dateStr)
                    let isSelected = selectedDate == dateStr

                    Button {
                        selectedDate = dateStr
                    } label: {
                        VStack(spacing: 3) {
                            Text("\(day.date)")
                                .font(.system(size: 14, weight: day.isToday ? .bold : .medium))
                                .foregroundColor(
                                    day.isToday ? .white :
                                    day.isCurrentMonth ? Tokens.text : Tokens.textTertiary
                                )
                                .frame(width: 30, height: 30)
                                .background(day.isToday ? Tokens.accent : Color.clear)
                                .clipShape(Circle())

                            HStack(spacing: 3) {
                                ForEach(uniquePetColors(dayEvents).prefix(2), id: \.self) { color in
                                    Circle().fill(color).frame(width: 5, height: 5)
                                }
                            }
                            .frame(height: 5)
                        }
                        .padding(.vertical, 6)
                        .background(isSelected ? Tokens.accentSoft : Color.clear)
                        .cornerRadius(10)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private func filteredEvents(for date: String) -> [CalendarEvent] {
        events.filter { e in
            e.eventDate == date && (filterPetId == nil || e.petId == filterPetId)
        }
    }

    private func uniquePetColors(_ evts: [CalendarEvent]) -> [Color] {
        var seen = Set<String>()
        var colors: [Color] = []
        for e in evts {
            if seen.insert(e.petId).inserted, let pet = pets.first(where: { $0.id == e.petId }) {
                colors.append(pet.color)
            }
        }
        return colors
    }
}
```

- [ ] **Step 2: Write EventRow.swift**

```swift
import SwiftUI

struct EventRow: View {
    let event: CalendarEvent
    let petColor: Color
    var onUpdate: (String, EventCategory, String, String?) -> Void
    var onDelete: () -> Void

    @State private var editing = false
    @State private var editTitle: String = ""
    @State private var editCategory: EventCategory = .daily
    @State private var editDate: String = ""
    @State private var editTime: String = ""

    var body: some View {
        if editing {
            editView
        } else {
            displayView
        }
    }

    private var displayView: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 2)
                .fill(petColor)
                .frame(width: 4, height: 36)

            VStack(alignment: .leading, spacing: 2) {
                Text(event.title)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(Tokens.text)
                Text([event.eventTime, event.category.label].compactMap { $0 }.joined(separator: " · "))
                    .font(.system(size: 12))
                    .foregroundColor(Tokens.textSecondary)
            }

            Spacer()

            HStack(spacing: 4) {
                Button { startEdit() } label: {
                    Image(systemName: "pencil")
                        .font(.system(size: 12))
                        .foregroundColor(Tokens.textSecondary)
                        .frame(width: 28, height: 28)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
                }
                Button { Haptics.medium(); onDelete() } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 12))
                        .foregroundColor(Tokens.red)
                        .frame(width: 28, height: 28)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
                }
            }
        }
        .padding(12)
        .background(Tokens.surface)
        .cornerRadius(Tokens.radiusSmall)
        .overlay(RoundedRectangle(cornerRadius: Tokens.radiusSmall).stroke(Tokens.border))
    }

    private var editView: some View {
        VStack(spacing: 6) {
            TextField("Title", text: $editTitle)
                .padding(8).background(Tokens.bg).cornerRadius(8)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
                .font(.system(size: 13))

            HStack(spacing: 6) {
                TextField("Date", text: $editDate)
                    .padding(8).background(Tokens.bg).cornerRadius(8)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
                    .font(.system(size: 13))
                TextField("Time", text: $editTime)
                    .padding(8).background(Tokens.bg).cornerRadius(8)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
                    .font(.system(size: 13))
            }

            Picker("Category", selection: $editCategory) {
                ForEach(EventCategory.allCases, id: \.self) { c in
                    Text(c.label).tag(c)
                }
            }
            .pickerStyle(.menu)

            HStack(spacing: 6) {
                Button {
                    onUpdate(editTitle, editCategory, editDate, editTime.isEmpty ? nil : editTime)
                    editing = false
                } label: {
                    Label("Save", systemImage: "checkmark")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white)
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .background(Tokens.accent).cornerRadius(8)
                }
                Button { editing = false } label: {
                    Text("Cancel")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(Tokens.textSecondary)
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
                }
            }
        }
        .padding(12)
        .background(Tokens.surface)
        .cornerRadius(Tokens.radiusSmall)
        .overlay(RoundedRectangle(cornerRadius: Tokens.radiusSmall).stroke(Tokens.border))
    }

    private func startEdit() {
        editTitle = event.title
        editCategory = event.category
        editDate = event.eventDate
        editTime = event.eventTime ?? ""
        editing = true
    }
}
```

- [ ] **Step 3: Write CalendarDrawer.swift**

```swift
import SwiftUI

struct CalendarDrawer: View {
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore
    @Environment(\.dismiss) var dismiss

    @State private var year: Int
    @State private var month: Int
    @State private var selectedDate: String?
    @State private var filterPetId: String?

    init() {
        let cal = Calendar.current
        let now = Date()
        _year = State(initialValue: cal.component(.year, from: now))
        _month = State(initialValue: cal.component(.month, from: now) - 1)
    }

    private var monthEvents: [CalendarEvent] {
        calendarStore.eventsForMonth(year: year, month: month)
    }

    private var selectedEvents: [CalendarEvent] {
        guard let date = selectedDate else { return [] }
        let dayEvts = calendarStore.eventsForDate(date)
        if let pid = filterPetId {
            return dayEvts.filter { $0.petId == pid }
        }
        return dayEvts
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 0) {
                    // Pet filter
                    filterBar

                    // Month navigation
                    monthNav

                    // Grid
                    MonthGrid(
                        days: CalendarHelper.getCalendarDays(year: year, month: month),
                        events: monthEvents,
                        pets: petStore.pets,
                        selectedDate: $selectedDate,
                        filterPetId: filterPetId
                    )

                    // Events for selected date
                    if let _ = selectedDate {
                        eventsList
                    }
                }
            }
            .background(Tokens.bg)
            .navigationTitle("Calendar")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(Tokens.textSecondary)
                            .frame(width: 32, height: 32)
                            .background(Tokens.surface)
                            .cornerRadius(10)
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Tokens.border))
                    }
                }
            }
        }
    }

    // MARK: - Filter

    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Button {
                    filterPetId = nil
                } label: {
                    Text("All")
                        .font(.system(size: 12, weight: .medium))
                        .padding(.horizontal, 14).padding(.vertical, 6)
                        .background(filterPetId == nil ? Tokens.accent : Color.clear)
                        .foregroundColor(filterPetId == nil ? .white : Tokens.textSecondary)
                        .cornerRadius(20)
                        .overlay(RoundedRectangle(cornerRadius: 20)
                            .stroke(filterPetId == nil ? Color.clear : Tokens.border))
                }

                ForEach(petStore.pets) { pet in
                    Button {
                        filterPetId = pet.id
                    } label: {
                        HStack(spacing: 6) {
                            Circle().fill(pet.color).frame(width: 8, height: 8)
                            Text(pet.name)
                        }
                        .font(.system(size: 12, weight: .medium))
                        .padding(.horizontal, 14).padding(.vertical, 6)
                        .background(filterPetId == pet.id ? Tokens.accent : Color.clear)
                        .foregroundColor(filterPetId == pet.id ? .white : Tokens.textSecondary)
                        .cornerRadius(20)
                        .overlay(RoundedRectangle(cornerRadius: 20)
                            .stroke(filterPetId == pet.id ? Color.clear : Tokens.border))
                    }
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
        }
    }

    // MARK: - Month Nav

    private var monthNav: some View {
        HStack {
            Button { prevMonth() } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: 32, height: 32)
                    .background(Tokens.surface)
                    .cornerRadius(8)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
            }
            Spacer()
            Text("\(CalendarHelper.monthNames[month]) \(String(year))")
                .font(.system(.body, design: .serif))
                .fontWeight(.semibold)
                .foregroundColor(Tokens.text)
            Spacer()
            Button { nextMonth() } label: {
                Image(systemName: "chevron.right")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Tokens.textSecondary)
                    .frame(width: 32, height: 32)
                    .background(Tokens.surface)
                    .cornerRadius(8)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 16)
        .padding(.bottom, 8)
    }

    // MARK: - Events

    private var eventsList: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("EVENTS")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Tokens.textSecondary)
                .tracking(1)
                .padding(.top, 12)

            if selectedEvents.isEmpty {
                Text("No events for this date")
                    .font(.system(size: 13))
                    .foregroundColor(Tokens.textTertiary)
                    .padding(.vertical, 12)
            } else {
                ForEach(selectedEvents) { evt in
                    let petColor = petStore.getById(evt.petId)?.color ?? Tokens.accent
                    EventRow(event: evt, petColor: petColor) { title, category, date, time in
                        calendarStore.update(evt.id, title: title, category: category,
                                             eventDate: date, eventTime: time)
                    } onDelete: {
                        calendarStore.remove(evt.id)
                    }
                }
            }
        }
        .padding(.horizontal, 20)
    }

    // MARK: - Helpers

    private func prevMonth() {
        if month == 0 { month = 11; year -= 1 } else { month -= 1 }
    }
    private func nextMonth() {
        if month == 11 { month = 0; year += 1 } else { month += 1 }
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add ios-app/CozyPup/Views/Calendar/
git commit -m "feat(ios): add CalendarDrawer with MonthGrid and EventRow"
```

---

### Task 10: Settings Drawer

**Files:**
- Create: `ios-app/CozyPup/Views/Settings/SettingsDrawer.swift`
- Create: `ios-app/CozyPup/Views/Settings/LegalPageView.swift`

- [ ] **Step 1: Write LegalPageView.swift**

```swift
import SwiftUI

struct LegalPageView: View {
    let title: String
    let content: String

    var body: some View {
        ScrollView {
            Text(content)
                .font(.system(size: 14))
                .foregroundColor(Tokens.textSecondary)
                .padding(20)
        }
        .background(Tokens.bg)
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
    }
}
```

- [ ] **Step 2: Write SettingsDrawer.swift**

```swift
import SwiftUI

struct SettingsDrawer: View {
    @EnvironmentObject var auth: AuthStore
    @EnvironmentObject var petStore: PetStore
    @Environment(\.dismiss) var dismiss

    @State private var notifications = true
    @State private var medReminders = true
    @State private var weeklyInsights = false
    @State private var editingPet: Pet?
    @State private var showAddPet = false
    @State private var showDeleteConfirm: Pet?

    private let prefsKey = "cozypup_notification_prefs"

    var body: some View {
        NavigationStack {
            List {
                // Account
                Section {
                    HStack(spacing: 12) {
                        Circle()
                            .fill(Tokens.accent)
                            .frame(width: 44, height: 44)
                            .overlay(
                                Text(String(auth.user?.name.prefix(1) ?? "U"))
                                    .foregroundColor(.white)
                                    .font(.system(size: 18, weight: .semibold))
                            )
                        VStack(alignment: .leading, spacing: 2) {
                            Text(auth.user?.name ?? "User")
                                .font(.system(size: 16, weight: .medium))
                                .foregroundColor(Tokens.text)
                            Text(auth.user?.email ?? "")
                                .font(.system(size: 13))
                                .foregroundColor(Tokens.textSecondary)
                        }
                    }
                    .listRowBackground(Tokens.surface)
                }

                // Pets
                Section("My Pets") {
                    ForEach(petStore.pets) { pet in
                        HStack(spacing: 12) {
                            Image(systemName: pet.species == .cat ? "cat" : "dog")
                                .foregroundColor(pet.color)
                            VStack(alignment: .leading) {
                                Text(pet.name).font(.system(size: 15, weight: .medium))
                                Text(pet.breed).font(.system(size: 12)).foregroundColor(Tokens.textSecondary)
                            }
                            Spacer()
                            Button { editingPet = pet } label: {
                                Image(systemName: "pencil")
                                    .font(.system(size: 13))
                                    .foregroundColor(Tokens.textSecondary)
                            }
                            Button { showDeleteConfirm = pet } label: {
                                Image(systemName: "trash")
                                    .font(.system(size: 13))
                                    .foregroundColor(Tokens.red)
                            }
                        }
                        .listRowBackground(Tokens.surface)
                    }
                    Button { showAddPet = true } label: {
                        Label("Add Pet", systemImage: "plus")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(Tokens.accent)
                    }
                    .listRowBackground(Tokens.surface)
                }

                // Notifications
                Section("Notifications") {
                    Toggle("Push Notifications", isOn: $notifications)
                    Toggle("Medication Reminders", isOn: $medReminders)
                    Toggle("Weekly Insights", isOn: $weeklyInsights)
                }
                .tint(Tokens.green)
                .listRowBackground(Tokens.surface)

                // Legal
                Section {
                    NavigationLink { LegalPageView(title: "Privacy Policy", content: privacyText) } label: {
                        Label("Privacy Policy", systemImage: "shield")
                    }
                    NavigationLink { LegalPageView(title: "Disclaimer", content: disclaimerText) } label: {
                        Label("Disclaimer", systemImage: "doc.text")
                    }
                    NavigationLink { LegalPageView(title: "About", content: aboutText) } label: {
                        Label("About", systemImage: "info.circle")
                    }
                }
                .listRowBackground(Tokens.surface)

                // Logout
                Section {
                    Button(role: .destructive) {
                        Haptics.medium()
                        auth.logout()
                        dismiss()
                    } label: {
                        Label("Log Out", systemImage: "rectangle.portrait.and.arrow.right")
                    }
                    .listRowBackground(Tokens.surface)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Tokens.bg)
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(Tokens.textSecondary)
                            .frame(width: 32, height: 32)
                            .background(Tokens.surface)
                            .cornerRadius(10)
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Tokens.border))
                    }
                }
            }
            .sheet(item: $editingPet) { pet in
                NavigationStack {
                    PetFormView(editingPet: pet) { name, species, breed, birthday, weight in
                        petStore.update(pet.id, name: name, species: species, breed: breed,
                                        birthday: birthday, weight: weight)
                        editingPet = nil
                    } onCancel: {
                        editingPet = nil
                    }
                    .padding(20)
                    .navigationTitle("Edit Pet")
                    .navigationBarTitleDisplayMode(.inline)
                }
            }
            .sheet(isPresented: $showAddPet) {
                NavigationStack {
                    PetFormView { name, species, breed, birthday, weight in
                        petStore.add(name: name, species: species, breed: breed,
                                     birthday: birthday, weight: weight)
                        showAddPet = false
                    } onCancel: {
                        showAddPet = false
                    }
                    .padding(20)
                    .navigationTitle("Add Pet")
                    .navigationBarTitleDisplayMode(.inline)
                }
            }
            .alert("Delete Pet?", isPresented: Binding(
                get: { showDeleteConfirm != nil },
                set: { if !$0 { showDeleteConfirm = nil } }
            )) {
                Button("Delete", role: .destructive) {
                    if let pet = showDeleteConfirm {
                        petStore.remove(pet.id)
                    }
                }
                Button("Cancel", role: .cancel) { }
            }
        }
        .onAppear { loadPrefs() }
        .onChange(of: notifications) { savePrefs() }
        .onChange(of: medReminders) { savePrefs() }
        .onChange(of: weeklyInsights) { savePrefs() }
    }

    // MARK: - Prefs persistence

    private func loadPrefs() {
        guard let data = UserDefaults.standard.data(forKey: prefsKey),
              let prefs = try? JSONDecoder().decode([String: Bool].self, from: data) else { return }
        notifications = prefs["notifications"] ?? true
        medReminders = prefs["medReminders"] ?? true
        weeklyInsights = prefs["weeklyInsights"] ?? false
    }

    private func savePrefs() {
        let prefs = ["notifications": notifications, "medReminders": medReminders, "weeklyInsights": weeklyInsights]
        if let data = try? JSONEncoder().encode(prefs) {
            UserDefaults.standard.set(data, forKey: prefsKey)
        }
    }

    // MARK: - Legal text
    private let privacyText = "CozyPup values your privacy. We only collect data necessary to provide personalized pet health suggestions. Your data is stored locally on your device and is not shared with third parties."
    private let disclaimerText = "CozyPup provides AI-generated suggestions for informational purposes only. These suggestions do not constitute professional veterinary advice. Always consult a qualified veterinarian for medical concerns."
    private let aboutText = "CozyPup v1.0\n\nYour pet's personal health butler, powered by AI.\n\nBuilt with love for pet parents everywhere. 🐾"
}
```

- [ ] **Step 3: Commit**

```bash
git add ios-app/CozyPup/Views/Settings/
git commit -m "feat(ios): add SettingsDrawer with pet management, notifications, legal pages"
```

---

### Task 11: Wire Up App Entry + Assets

**Files:**
- Modify: `ios-app/CozyPup/CozyPupApp.swift`

- [ ] **Step 1: Update CozyPupApp.swift with auth gates and environment objects**

```swift
import SwiftUI

@main
struct CozyPupApp: App {
    @StateObject private var auth = AuthStore()
    @StateObject private var petStore = PetStore()
    @StateObject private var calendarStore = CalendarStore()
    @StateObject private var chatStore = ChatStore()

    var body: some Scene {
        WindowGroup {
            Group {
                if !auth.isAuthenticated {
                    LoginView()
                } else if !auth.hasAcknowledgedDisclaimer {
                    DisclaimerView()
                } else if petStore.pets.isEmpty {
                    OnboardingView()
                } else {
                    ChatView()
                }
            }
            .environmentObject(auth)
            .environmentObject(petStore)
            .environmentObject(calendarStore)
            .environmentObject(chatStore)
        }
    }
}
```

- [ ] **Step 2: Copy logo.png to asset catalog**

```bash
mkdir -p /Users/robert/Projects/CozyPup/ios-app/CozyPup/Assets.xcassets/logo.imageset
cp /Users/robert/Projects/CozyPup/logo.png /Users/robert/Projects/CozyPup/ios-app/CozyPup/Assets.xcassets/logo.imageset/logo.png
```

Create `Assets.xcassets/logo.imageset/Contents.json`:
```json
{
  "images": [
    { "filename": "logo.png", "idiom": "universal", "scale": "1x" },
    { "idiom": "universal", "scale": "2x" },
    { "idiom": "universal", "scale": "3x" }
  ],
  "info": { "author": "xcode", "version": 1 }
}
```

Also create `Assets.xcassets/Contents.json`:
```json
{ "info": { "author": "xcode", "version": 1 } }
```

- [ ] **Step 3: Add NSMicrophoneUsageDescription and NSLocationWhenInUseUsageDescription to Info.plist**

Add to the Xcode project's Info.plist:
- `NSMicrophoneUsageDescription`: "CozyPup needs microphone access for voice input"
- `NSSpeechRecognitionUsageDescription`: "CozyPup uses speech recognition for voice input"
- `NSLocationWhenInUseUsageDescription`: "CozyPup uses your location to find nearby pet services"

- [ ] **Step 4: Build and run on simulator**

Run: `xcodebuild -scheme CozyPup -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build`

Fix any compilation errors.

- [ ] **Step 5: Commit**

```bash
git add ios-app/
git commit -m "feat(ios): wire up app entry with auth gates and environment objects"
```

---

### Task 12: End-to-End Smoke Test

- [ ] **Step 1: Run the app on simulator, verify login flow**

Test: Tap "Sign in with Apple" → see disclaimer → tap "I Understand" → see onboarding

- [ ] **Step 2: Add a pet via onboarding**

Test: Fill name, select species, add breed → tap "Add Pet" → see chat screen

- [ ] **Step 3: Send a chat message**

Start backend: `cd /Users/robert/Projects/CozyPup/backend && uvicorn app.main:app --host 0.0.0.0 --port 8000`

Update `ChatService.baseURL` to your machine's IP.

Test: Type "hi" → see streaming response with greeting

- [ ] **Step 4: Open calendar sheet**

Test: Tap calendar icon → sheet slides up → see month grid with demo events → select a day → see events

- [ ] **Step 5: Open settings sheet**

Test: Tap gear icon → sheet slides up → see pets, notifications, legal pages → test edit/delete pet

- [ ] **Step 6: Commit final state**

```bash
git add -A
git commit -m "feat(ios): complete SwiftUI native app — all screens functional"
```
