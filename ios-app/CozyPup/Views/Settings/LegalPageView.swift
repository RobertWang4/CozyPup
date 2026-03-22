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
        .background(Tokens.bg)
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
    }
}
