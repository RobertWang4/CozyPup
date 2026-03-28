import SwiftUI

struct LocationPickerCard: View {
    let data: LocationPickerCardData
    @EnvironmentObject var calendarStore: CalendarStore
    @State private var selectedId: String?

    var body: some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
            Text("选择地点")
                .font(Tokens.fontSubheadline.weight(.semibold))
                .foregroundColor(Tokens.text)

            ForEach(data.options, id: \.place_id) { option in
                Button {
                    selectedId = option.place_id
                    Task {
                        await calendarStore.updateLocation(
                            eventId: data.event_id,
                            name: option.name,
                            address: option.address,
                            lat: option.lat,
                            lng: option.lng,
                            placeId: option.place_id
                        )
                    }
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                            Text(option.name)
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.text)
                            Text(option.address)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                                .lineLimit(1)
                        }
                        Spacer()
                        if let dist = option.distance_m {
                            Text(dist < 1000 ? "\(dist)m" : String(format: "%.1fkm", Double(dist) / 1000))
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary)
                        }
                        if selectedId == option.place_id {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(Tokens.green)
                        }
                    }
                    .padding(Tokens.spacing.sm)
                    .background(selectedId == option.place_id ? Tokens.accentSoft : Tokens.surface)
                    .cornerRadius(Tokens.radiusSmall)
                }
                .disabled(selectedId != nil)
            }
        }
        .padding(Tokens.spacing.md)
        .background(Tokens.surface)
        .cornerRadius(Tokens.radius)
    }
}
