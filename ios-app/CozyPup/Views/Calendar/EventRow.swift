import SwiftUI

struct EventRow: View {
    let event: CalendarEvent
    let petColor: Color
    var pet: Pet?
    var onUpdate: (String, EventCategory, String, String?) -> Void
    var onDelete: () -> Void

    @State private var showEditSheet = false

    var body: some View {
        HStack(spacing: 0) {
            // Left color bar
            Capsule()
                .fill(petColor)
                .frame(width: 5, height: Tokens.size.avatarMedium)

            // Event text with pet name in parentheses
            Text(eventLabel)
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.text)
                .lineLimit(2)
                .padding(.leading, 12)

            Spacer(minLength: Tokens.spacing.sm)

            // Paw icon
            Image(systemName: "pawprint.fill")
                .font(Tokens.fontCallout)
                .foregroundColor(Tokens.accent.opacity(0.5))
        }
        .padding(.horizontal, Tokens.spacing.md)
        .padding(.vertical, 14)
        .background(Tokens.surface)
        .cornerRadius(12)
        .contextMenu {
            Button { showEditSheet = true } label: {
                Label(Lang.shared.isZh ? "编辑" : "Edit", systemImage: "pencil")
            }
            Button(role: .destructive) { Haptics.medium(); onDelete() } label: {
                Label(L.delete, systemImage: "trash")
            }
        }
        .sheet(isPresented: $showEditSheet) {
            EventEditSheet(event: event, onSave: onUpdate)
        }
    }

    private var eventLabel: String {
        var text = ""
        if let time = event.eventTime, !time.isEmpty {
            text = "\(time) - \(event.title)"
        } else {
            text = event.title
        }
        if let name = pet?.name {
            text += "\n(\(name))"
        }
        return text
    }
}
