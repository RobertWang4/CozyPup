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
