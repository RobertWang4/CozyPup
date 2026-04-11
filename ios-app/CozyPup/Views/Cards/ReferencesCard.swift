import SwiftUI

struct ReferencesCard: View {
    let data: ReferencesCardData
    @State private var showDrawer = false

    var body: some View {
        Button {
            showDrawer = true
        } label: {
            HStack(spacing: Tokens.spacing.xs) {
                Text("\u{1F4CE}")
                    .font(Tokens.fontCaption)
                Text("References")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textSecondary)
            }
            .padding(.horizontal, Tokens.spacing.sm)
            .padding(.vertical, Tokens.spacing.xs)
            .background(Tokens.surface)
            .cornerRadius(Tokens.radiusSmall)
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $showDrawer) {
            referencesDrawer
                .presentationDetents([.medium])
                .presentationDragIndicator(.visible)
        }
    }

    private var referencesDrawer: some View {
        NavigationStack {
            List {
                ForEach(data.items) { item in
                    Button {
                        handleTap(item)
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                                Text(item.title)
                                    .font(Tokens.fontSubheadline)
                                    .foregroundColor(Tokens.text)
                                    .lineLimit(2)
                                if item.source == "knowledge" {
                                    Text("\u{77E5}\u{8BC6}\u{5E93}")
                                        .font(Tokens.fontCaption2)
                                        .foregroundColor(Tokens.textTertiary)
                                } else {
                                    Text("\u{5386}\u{53F2}\u{8BB0}\u{5F55}")
                                        .font(Tokens.fontCaption2)
                                        .foregroundColor(Tokens.textTertiary)
                                }
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(Tokens.fontCaption2)
                                .foregroundColor(Tokens.textTertiary)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .listStyle(.plain)
            .navigationTitle("References")
            .navigationBarTitleDisplayMode(.inline)
            .background(Tokens.surface2)
        }
    }

    private func handleTap(_ item: ReferenceItem) {
        if item.source == "knowledge", let urlStr = item.url,
           let url = URL(string: urlStr) {
            UIApplication.shared.open(url)
        }
        // History items: future navigation to calendar event
    }
}

#Preview {
    ReferencesCard(data: ReferencesCardData(
        type: "references",
        items: [
            ReferenceItem(title: "\u{72AC}\u{5455}\u{5410}\u{5E38}\u{89C1}\u{539F}\u{56E0}\u{4E0E}\u{5904}\u{7406}", url: "https://example.com/vomit", eventId: nil, source: "knowledge"),
            ReferenceItem(title: "2026-03-15 \u{7EF4}\u{5C3C}\u{5C31}\u{533B}\u{8BB0}\u{5F55}", url: nil, eventId: "uuid-123", source: "history"),
        ]
    ))
    .padding()
}
