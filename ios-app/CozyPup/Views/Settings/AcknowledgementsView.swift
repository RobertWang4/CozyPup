import SwiftUI

private struct Dependency: Identifiable {
    let id = UUID()
    let name: String
    let license: String
    let url: String
}

struct AcknowledgementsView: View {
    @ObservedObject private var lang = Lang.shared

    private let dependencies: [Dependency] = [
        Dependency(name: "GoogleSignIn-iOS", license: "Apache 2.0", url: "https://github.com/google/GoogleSignIn-iOS"),
        // Add more as dependencies are introduced.
    ]

    var body: some View {
        List {
            Section {
                ForEach(dependencies) { dep in
                    VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                        Text(dep.name)
                            .font(Tokens.fontBody.weight(.medium))
                            .foregroundColor(Tokens.text)
                        Text(dep.license)
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                        Text(dep.url)
                            .font(Tokens.fontCaption2)
                            .foregroundColor(Tokens.textTertiary)
                    }
                    .padding(.vertical, Tokens.spacing.xxs)
                    .listRowBackground(Tokens.surface)
                }
            } footer: {
                Text(lang.isZh
                    ? "感谢这些开源项目让 CozyPup 成为可能。"
                    : "Thanks to these open-source projects that make CozyPup possible.")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textSecondary)
            }
        }
        .scrollContentBackground(.hidden)
        .background(Tokens.bg)
        .navigationTitle(lang.isZh ? "开源致谢" : "Acknowledgements")
        .navigationBarTitleDisplayMode(.inline)
    }
}

#Preview {
    NavigationStack {
        AcknowledgementsView()
    }
}
