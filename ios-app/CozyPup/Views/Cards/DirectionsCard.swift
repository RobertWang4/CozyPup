import SwiftUI
import MapKit

struct DirectionsCard: View {
    let data: DirectionsCardData

    var body: some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.md) {
            HStack {
                Image(systemName: "mappin.circle.fill")
                    .foregroundColor(Tokens.accent)
                Text(data.destName)
                    .font(Tokens.fontBody.weight(.semibold))
                    .foregroundColor(Tokens.text)
            }

            HStack(spacing: Tokens.spacing.lg) {
                VStack(spacing: Tokens.spacing.xxs) {
                    Text(data.distance)
                        .font(Tokens.fontTitle)
                        .foregroundColor(Tokens.text)
                    Text("distance")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                }
                VStack(spacing: Tokens.spacing.xxs) {
                    Text(data.duration)
                        .font(Tokens.fontTitle)
                        .foregroundColor(Tokens.text)
                    Text(data.mode == "walking" ? "walking" : "driving")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                }
            }

            HStack(spacing: Tokens.spacing.sm) {
                Button {
                    openAppleMaps()
                } label: {
                    HStack(spacing: Tokens.spacing.xs) {
                        Image(systemName: "apple.logo")
                        Text("Apple Maps")
                    }
                    .font(Tokens.fontCaption.weight(.semibold))
                    .foregroundColor(Tokens.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, Tokens.spacing.sm)
                    .background(Tokens.accent)
                    .clipShape(RoundedRectangle(cornerRadius: Tokens.radiusSmall))
                }

                if canOpenGoogleMaps() {
                    Button {
                        openGoogleMaps()
                    } label: {
                        HStack(spacing: Tokens.spacing.xs) {
                            Image(systemName: "map")
                            Text("Google Maps")
                        }
                        .font(Tokens.fontCaption.weight(.semibold))
                        .foregroundColor(Tokens.accent)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Tokens.spacing.sm)
                        .background(Tokens.accentSoft)
                        .clipShape(RoundedRectangle(cornerRadius: Tokens.radiusSmall))
                    }
                }
            }
        }
        .padding(Tokens.spacing.md)
        .background(Tokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: Tokens.radius))
    }

    private func openAppleMaps() {
        let coordinate = CLLocationCoordinate2D(latitude: data.destLat, longitude: data.destLng)
        let placemark = MKPlacemark(coordinate: coordinate)
        let mapItem = MKMapItem(placemark: placemark)
        mapItem.name = data.destName
        let mode = data.mode == "walking" ? MKLaunchOptionsDirectionsModeWalking : MKLaunchOptionsDirectionsModeDriving
        mapItem.openInMaps(launchOptions: [MKLaunchOptionsDirectionsModeKey: mode])
    }

    private func canOpenGoogleMaps() -> Bool {
        guard let url = URL(string: "comgooglemaps://") else { return false }
        return UIApplication.shared.canOpenURL(url)
    }

    private func openGoogleMaps() {
        let mode = data.mode == "walking" ? "walking" : "driving"
        let urlString = "comgooglemaps://?daddr=\(data.destLat),\(data.destLng)&directionsmode=\(mode)"
        if let url = URL(string: urlString) {
            UIApplication.shared.open(url)
        }
    }
}

#Preview {
    DirectionsCard(data: DirectionsCardData(
        type: "directions",
        destName: "Happy Paws Vet Clinic",
        destLat: 45.42,
        destLng: -75.69,
        distance: "2.3 km",
        duration: "8 mins",
        mode: "driving"
    ))
    .padding()
}
