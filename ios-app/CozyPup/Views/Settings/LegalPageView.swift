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
