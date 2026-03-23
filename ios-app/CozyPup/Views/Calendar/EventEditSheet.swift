import SwiftUI

struct EventEditSheet: View {
    let event: CalendarEvent
    var onSave: (String, EventCategory, String, String?) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var title: String
    @State private var category: EventCategory
    @State private var date: String
    @State private var time: String

    init(event: CalendarEvent, onSave: @escaping (String, EventCategory, String, String?) -> Void) {
        self.event = event
        self.onSave = onSave
        _title = State(initialValue: event.title)
        _category = State(initialValue: event.category)
        _date = State(initialValue: event.eventDate)
        _time = State(initialValue: event.eventTime ?? "")
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Tokens.spacing.md) {
                    field(label: L.title) {
                        TextField(L.title, text: $title)
                            .textFieldStyle(.plain)
                            .foregroundColor(Tokens.text)
                    }

                    HStack(spacing: 12) {
                        field(label: L.date) {
                            TextField("YYYY-MM-DD", text: $date)
                                .textFieldStyle(.plain)
                                .foregroundColor(Tokens.text)
                        }
                        field(label: L.time) {
                            TextField("HH:MM", text: $time)
                                .textFieldStyle(.plain)
                                .foregroundColor(Tokens.text)
                        }
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text(Lang.shared.isZh ? "分类" : "Category")
                            .font(Tokens.fontSubheadline.weight(.medium))
                            .foregroundColor(Tokens.textSecondary)
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(EventCategory.allCases, id: \.self) { c in
                                    Button {
                                        category = c
                                    } label: {
                                        Text(c.label)
                                            .font(Tokens.fontCaption.weight(.medium))
                                            .padding(.horizontal, 12)
                                            .padding(.vertical, 6)
                                            .background(category == c ? Tokens.accent : Tokens.surface)
                                            .foregroundColor(category == c ? Tokens.white : Tokens.text)
                                            .cornerRadius(16)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 16)
                                                    .stroke(category == c ? Color.clear : Tokens.border)
                                            )
                                    }
                                }
                            }
                        }
                    }
                }
                .padding(Tokens.spacing.md)
            }
            .background(Tokens.bg)
            .navigationTitle(Lang.shared.isZh ? "编辑事件" : "Edit Event")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(L.cancel) { dismiss() }
                        .foregroundColor(Tokens.textSecondary)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L.save) {
                        onSave(title, category, date, time.isEmpty ? nil : time)
                        dismiss()
                    }
                    .fontWeight(.semibold)
                    .foregroundColor(Tokens.accent)
                    .disabled(title.isEmpty)
                }
            }
        }
        .presentationDetents([.medium])
        .presentationDragIndicator(.visible)
    }

    @ViewBuilder
    private func field(label: String, @ViewBuilder content: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(Tokens.fontSubheadline.weight(.medium))
                .foregroundColor(Tokens.textSecondary)
            content()
                .padding(12)
                .background(Tokens.surface)
                .cornerRadius(12)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Tokens.border))
        }
    }
}
