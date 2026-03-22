import SwiftUI

struct TimelineEventCard: View {
    let event: CalendarEvent
    let petColor: Color
    let petName: String

    var body: some View {
        HStack(spacing: 0) {
            // Left accent bar
            RoundedRectangle(cornerRadius: 1.5)
                .fill(categoryColor)
                .frame(width: 3)
                .padding(.vertical, 12)

            VStack(alignment: .leading, spacing: Tokens.spacing.xs) {
                // Header: category + time
                HStack {
                    Text(event.category.label.uppercased())
                        .font(Tokens.fontCaption2.weight(.medium))
                        .foregroundColor(categoryColor)
                        .tracking(0.5)
                    Spacer()
                    if let time = event.eventTime {
                        Text(time)
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }

                // Title
                Text(event.title)
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.text)
                    .lineLimit(3)

                // Photo grid (if photos exist)
                if !event.photos.isEmpty {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 6) {
                        ForEach(event.photos, id: \.self) { url in
                            AsyncImage(url: URL(string: url)) { image in
                                image.resizable().scaledToFill()
                            } placeholder: {
                                Tokens.placeholderBg
                            }
                            .aspectRatio(4/3, contentMode: .fill)
                            .clipped()
                            .cornerRadius(Tokens.radiusSmall)
                        }
                    }
                }

                // Pet name
                Text(petName)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)
            }
            .padding(.leading, 12)
            .padding(.vertical, 14)
            .padding(.trailing, Tokens.spacing.md)
        }
        .background(Tokens.surface)
        .cornerRadius(14)
    }

    private var categoryColor: Color {
        switch event.category {
        case .diet: return Tokens.green
        case .medical: return Tokens.blue
        case .daily: return Tokens.accent
        case .abnormal: return Tokens.red
        case .vaccine: return Tokens.purple
        case .deworming: return Tokens.orange
        case .excretion: return Tokens.textSecondary
        }
    }
}
