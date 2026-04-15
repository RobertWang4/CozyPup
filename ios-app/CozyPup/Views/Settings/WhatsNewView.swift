import SwiftUI

struct WhatsNewView: View {
    @ObservedObject private var lang = Lang.shared

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Tokens.spacing.lg) {
                ForEach(ReleaseNotes.all) { note in
                    VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                        HStack {
                            Text(note.version)
                                .font(Tokens.fontTitle.weight(.semibold))
                                .foregroundColor(Tokens.text)
                            Spacer()
                            Text(note.date)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                        }
                        VStack(alignment: .leading, spacing: Tokens.spacing.xs) {
                            ForEach(note.highlights, id: \.self) { h in
                                HStack(alignment: .top, spacing: Tokens.spacing.sm) {
                                    Text("•").foregroundColor(Tokens.accent)
                                    Text(h)
                                        .font(Tokens.fontBody)
                                        .foregroundColor(Tokens.text)
                                }
                            }
                        }
                    }
                    .padding(Tokens.spacing.md)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radius)
                }
            }
            .padding(Tokens.spacing.md)
        }
        .background(Tokens.bg)
        .navigationTitle(lang.isZh ? "更新说明" : "What's New")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    NavigationStack {
        WhatsNewView()
    }
}
