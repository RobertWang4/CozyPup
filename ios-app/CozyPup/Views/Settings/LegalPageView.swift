import SwiftUI

struct LegalPageView: View {
    let title: String
    let content: String

    var body: some View {
        ScrollView {
            Text(content)
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textSecondary)
                .padding(20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Tokens.bg.ignoresSafeArea())
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.light, for: .navigationBar)
        .tint(Tokens.text)
    }
}
