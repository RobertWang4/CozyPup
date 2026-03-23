import SwiftUI

struct EventRow: View {
    let event: CalendarEvent
    let petColor: Color
    var pet: Pet?
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

    // MARK: - Display

    private var displayView: some View {
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
            Button { startEdit() } label: {
                Label(Lang.shared.isZh ? "编辑" : "Edit", systemImage: "pencil")
            }
            Button(role: .destructive) { Haptics.medium(); onDelete() } label: {
                Label(L.delete, systemImage: "trash")
            }
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

    // MARK: - Edit

    private var editView: some View {
        VStack(spacing: 6) {
            TextField(L.title, text: $editTitle)
                .padding(Tokens.spacing.sm).background(Tokens.bg).cornerRadius(Tokens.spacing.sm)
                .overlay(RoundedRectangle(cornerRadius: Tokens.spacing.sm).stroke(Tokens.border))
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.text)
                .submitLabel(.done)

            HStack(spacing: 6) {
                TextField(L.date, text: $editDate)
                    .padding(Tokens.spacing.sm).background(Tokens.bg).cornerRadius(Tokens.spacing.sm)
                    .overlay(RoundedRectangle(cornerRadius: Tokens.spacing.sm).stroke(Tokens.border))
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.text)
                    .submitLabel(.done)
                TextField(L.time, text: $editTime)
                    .padding(Tokens.spacing.sm).background(Tokens.bg).cornerRadius(Tokens.spacing.sm)
                    .overlay(RoundedRectangle(cornerRadius: Tokens.spacing.sm).stroke(Tokens.border))
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.text)
                    .submitLabel(.done)
            }

            Picker(Lang.shared.isZh ? "分类" : "Category", selection: $editCategory) {
                ForEach(EventCategory.allCases, id: \.self) { c in
                    Text(c.label).tag(c)
                }
            }
            .pickerStyle(.menu)

            HStack(spacing: 6) {
                Button {
                    UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                    onUpdate(editTitle, editCategory, editDate, editTime.isEmpty ? nil : editTime)
                    editing = false
                } label: {
                    Label(L.save, systemImage: "checkmark")
                        .font(Tokens.fontCaption.weight(.medium))
                        .foregroundColor(Tokens.white)
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .background(Tokens.accent).cornerRadius(8)
                }
                Button {
                    UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
                    editing = false
                } label: {
                    Text(L.cancel)
                        .font(Tokens.fontCaption.weight(.medium))
                        .foregroundColor(Tokens.textSecondary)
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tokens.border))
                }
            }
        }
        .padding(12)
        .background(Tokens.surface)
        .cornerRadius(14)
        .onTapGesture { } // prevent tap-through to calendar
    }

    private func startEdit() {
        editTitle = event.title
        editCategory = event.category
        editDate = event.eventDate
        editTime = event.eventTime ?? ""
        editing = true
    }
}
