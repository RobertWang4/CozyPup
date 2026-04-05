import SwiftUI
import MapKit

struct PlaceCard: View {
    let data: PlaceCardData

    var body: some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
            Text(data.query)
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textSecondary)

            TabView {
                ForEach(Array(data.places.enumerated()), id: \.offset) { index, place in
                    placeItem(place)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .automatic))
            .frame(height: 190)
        }
        .padding(Tokens.spacing.md)
        .background(Tokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: Tokens.radius))
    }

    @ViewBuilder
    private func placeItem(_ place: PlaceItem) -> some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
            HStack {
                Text(place.name)
                    .font(Tokens.fontBody.weight(.semibold))
                    .foregroundColor(Tokens.text)
                    .lineLimit(1)
                Spacer()
                if let rating = place.rating {
                    HStack(spacing: 2) {
                        Image(systemName: "star.fill")
                            .font(.caption2)
                            .foregroundColor(.orange)
                        Text(String(format: "%.1f", rating))
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                    }
                }
            }

            Text(place.address)
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textSecondary)
                .lineLimit(2)

            HStack(spacing: Tokens.spacing.sm) {
                if let distance = place.distance, let duration = place.duration {
                    Label(distance, systemImage: "car.fill")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                    Text("·").foregroundColor(Tokens.textTertiary)
                    Text(duration)
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                }
                Spacer()
                if let isOpen = place.isOpen {
                    Text(isOpen ? "Open" : "Closed")
                        .font(Tokens.fontCaption.weight(.medium))
                        .foregroundColor(isOpen ? Tokens.green : Tokens.red)
                }
            }

            Button {
                openInMaps(place)
            } label: {
                HStack(spacing: Tokens.spacing.xs) {
                    Image(systemName: "arrow.triangle.turn.up.right.diamond.fill")
                    Text("Navigate")
                }
                .font(Tokens.fontCaption.weight(.semibold))
                .foregroundColor(Tokens.white)
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.vertical, Tokens.spacing.xs)
                .background(Tokens.accent)
                .clipShape(RoundedRectangle(cornerRadius: Tokens.radiusSmall))
            }
        }
        .padding(Tokens.spacing.sm)
    }

    private func openInMaps(_ place: PlaceItem) {
        let coordinate = CLLocationCoordinate2D(latitude: place.lat, longitude: place.lng)
        let placemark = MKPlacemark(coordinate: coordinate)
        let mapItem = MKMapItem(placemark: placemark)
        mapItem.name = place.name
        mapItem.openInMaps(launchOptions: [MKLaunchOptionsDirectionsModeKey: MKLaunchOptionsDirectionsModeDriving])
    }
}

#Preview {
    PlaceCard(data: PlaceCardData(
        type: "place_card",
        query: "pet hospitals nearby",
        places: [
            PlaceItem(placeId: "1", name: "Happy Paws Vet", address: "123 Main St", rating: 4.5, isOpen: true, lat: 45.42, lng: -75.69, distance: "1.2 km", duration: "5 mins"),
            PlaceItem(placeId: "2", name: "City Animal Hospital", address: "456 Oak Ave", rating: 4.2, isOpen: false, lat: 45.43, lng: -75.70, distance: "2.8 km", duration: "10 mins"),
        ]
    ))
    .padding()
}
