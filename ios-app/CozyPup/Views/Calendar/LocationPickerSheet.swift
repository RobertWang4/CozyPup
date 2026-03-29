import SwiftUI
import MapKit
import CoreLocation

struct PlaceResult: Identifiable, Equatable {
    let id: String  // place_id
    let name: String
    let address: String
    let lat: Double
    let lng: Double

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: lat, longitude: lng)
    }
}

struct LocationPickerSheet: View {
    let currentLat: Double?
    let currentLng: Double?
    let onSelect: (PlaceResult) -> Void
    @Environment(\.dismiss) private var dismiss
    @StateObject private var locationService = LocationService()

    @State private var activeLat: Double?
    @State private var activeLng: Double?
    @State private var searchText = ""
    @State private var places: [PlaceResult] = []
    @State private var isLoading = false
    @State private var cameraPosition: MapCameraPosition = .automatic
    @State private var searchTask: Task<Void, Never>?
    @State private var pinnedPlace: PlaceResult?
    @State private var isGeocoding = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Map — tap anywhere to drop a pin
                ZStack(alignment: .bottom) {
                    MapReader { proxy in
                        Map(position: $cameraPosition) {
                            // User location dot
                            if let lat = activeLat, let lng = activeLng {
                                Annotation("", coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lng)) {
                                    Circle()
                                        .fill(Color.blue)
                                        .frame(width: 12, height: 12)
                                        .overlay(Circle().stroke(Tokens.white, lineWidth: 2))
                                        .shadow(radius: 2)
                                }
                            }
                            // Dropped pin
                            if let pin = pinnedPlace {
                                Annotation("", coordinate: pin.coordinate) {
                                    VStack(spacing: 0) {
                                        Image(systemName: "mappin.circle.fill")
                                            .font(.system(size: 30))
                                            .foregroundColor(Tokens.accent)
                                        Image(systemName: "arrowtriangle.down.fill")
                                            .font(.system(size: 10))
                                            .foregroundColor(Tokens.accent)
                                            .offset(y: -4)
                                    }
                                }
                            }
                        }
                        .onTapGesture { screenPoint in
                            if let coordinate = proxy.convert(screenPoint, from: .local) {
                                Task { await reverseGeocode(coordinate) }
                            }
                        }
                    }

                    // Pinned place preview card
                    if let pin = pinnedPlace {
                        HStack(spacing: Tokens.spacing.sm) {
                            VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                                Text(pin.name.isEmpty ? (Lang.shared.isZh ? "已选位置" : "Selected Location") : pin.name)
                                    .font(Tokens.fontSubheadline.weight(.semibold))
                                    .foregroundColor(Tokens.text)
                                    .lineLimit(1)
                                if !pin.address.isEmpty {
                                    Text(pin.address)
                                        .font(Tokens.fontCaption)
                                        .foregroundColor(Tokens.textSecondary)
                                        .lineLimit(1)
                                }
                            }
                            Spacer()
                            if isGeocoding {
                                ProgressView()
                                    .controlSize(.small)
                            } else {
                                Button {
                                    onSelect(pin)
                                    dismiss()
                                } label: {
                                    Text(Lang.shared.isZh ? "选择" : "Select")
                                        .font(Tokens.fontSubheadline.weight(.semibold))
                                        .foregroundColor(Tokens.white)
                                        .padding(.horizontal, Tokens.spacing.md)
                                        .padding(.vertical, Tokens.spacing.xs + 2)
                                        .background(Tokens.accent)
                                        .cornerRadius(Tokens.radiusSmall)
                                }
                            }
                        }
                        .padding(Tokens.spacing.sm)
                        .background(.ultraThinMaterial)
                        .cornerRadius(Tokens.radiusSmall)
                        .padding(.horizontal, Tokens.spacing.sm)
                        .padding(.bottom, Tokens.spacing.sm)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                }
                .frame(height: 280)

                // Search bar + results
                VStack(spacing: 0) {
                    HStack(spacing: Tokens.spacing.sm) {
                        Image(systemName: "magnifyingglass")
                            .foregroundColor(Tokens.textTertiary)
                        TextField(Lang.shared.isZh ? "搜索地点" : "Search for location", text: $searchText)
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                            .autocorrectionDisabled()
                            .submitLabel(.search)
                            .onSubmit {
                                searchTask?.cancel()
                                if !searchText.isEmpty {
                                    searchTask = Task { await searchPlaces(query: searchText) }
                                }
                            }
                    }
                    .padding(Tokens.spacing.sm)
                    .background(Tokens.surface)
                    .cornerRadius(Tokens.radiusSmall)
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.vertical, Tokens.spacing.sm)

                    // Results list
                    if isLoading {
                        ProgressView()
                            .padding(.top, Tokens.spacing.lg)
                        Spacer()
                    } else if places.isEmpty {
                        VStack(spacing: Tokens.spacing.sm) {
                            Image(systemName: "mappin.slash")
                                .font(.system(size: 32))
                                .foregroundColor(Tokens.textTertiary)
                            Text(Lang.shared.isZh ? "暂无结果" : "No results")
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.textSecondary)
                        }
                        .padding(.top, Tokens.spacing.xl)
                        Spacer()
                    } else {
                        ScrollView {
                            LazyVStack(spacing: 0) {
                                ForEach(places) { place in
                                    Button {
                                        onSelect(place)
                                        dismiss()
                                    } label: {
                                        HStack {
                                            VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                                                Text(place.name)
                                                    .font(Tokens.fontBody)
                                                    .foregroundColor(Tokens.text)
                                                Text(place.address)
                                                    .font(Tokens.fontCaption)
                                                    .foregroundColor(Tokens.textSecondary)
                                                    .lineLimit(2)
                                            }
                                            Spacer()
                                        }
                                        .padding(.horizontal, Tokens.spacing.md)
                                        .padding(.vertical, Tokens.spacing.sm + 2)
                                    }

                                    Divider()
                                        .padding(.leading, Tokens.spacing.md)
                                }
                            }
                        }
                        .scrollDismissesKeyboard(.interactively)
                    }
                }
                .onTapGesture { dismissKeyboard() }
            }
            .background(Tokens.bg.ignoresSafeArea())
            .toolbarBackground(Tokens.bg, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.light, for: .navigationBar)
            .navigationTitle(Lang.shared.isZh ? "选择地点" : "Choose Location")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(Lang.shared.isZh ? "取消" : "Cancel") { dismiss() }
                        .foregroundColor(Tokens.textSecondary)
                }
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task {
            if let lat = currentLat, let lng = currentLng {
                activeLat = lat
                activeLng = lng
            } else {
                let coord = await locationService.requestLocation()
                activeLat = coord?.latitude
                activeLng = coord?.longitude
            }
            if let lat = activeLat, let lng = activeLng {
                cameraPosition = .region(MKCoordinateRegion(
                    center: CLLocationCoordinate2D(latitude: lat, longitude: lng),
                    span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
                ))
            }
            await loadNearby()
        }
        .onChange(of: searchText) { _, newValue in
            searchTask?.cancel()
            searchTask = Task {
                try? await Task.sleep(for: .milliseconds(500))
                if !Task.isCancelled {
                    if newValue.isEmpty {
                        await loadNearby()
                    } else {
                        await searchPlaces(query: newValue)
                    }
                }
            }
        }
        .animation(.easeInOut(duration: 0.2), value: pinnedPlace)
    }

    private func dismissKeyboard() {
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
    }

    private func reverseGeocode(_ coordinate: CLLocationCoordinate2D) async {
        isGeocoding = true
        pinnedPlace = PlaceResult(
            id: "pin-\(coordinate.latitude)-\(coordinate.longitude)",
            name: "",
            address: Lang.shared.isZh ? "获取地址中…" : "Getting address…",
            lat: coordinate.latitude,
            lng: coordinate.longitude
        )

        let geocoder = CLGeocoder()
        let location = CLLocation(latitude: coordinate.latitude, longitude: coordinate.longitude)
        do {
            let placemarks = try await geocoder.reverseGeocodeLocation(location)
            if let pm = placemarks.first {
                let name = pm.name ?? ""
                let parts = [pm.thoroughfare, pm.subLocality, pm.locality, pm.administrativeArea].compactMap { $0 }
                let address = parts.joined(separator: ", ")
                pinnedPlace = PlaceResult(
                    id: "pin-\(coordinate.latitude)-\(coordinate.longitude)",
                    name: name,
                    address: address,
                    lat: coordinate.latitude,
                    lng: coordinate.longitude
                )
            }
        } catch {
            // Keep the coordinate-only pin
            pinnedPlace = PlaceResult(
                id: "pin-\(coordinate.latitude)-\(coordinate.longitude)",
                name: Lang.shared.isZh ? "已选位置" : "Dropped Pin",
                address: String(format: "%.5f, %.5f", coordinate.latitude, coordinate.longitude),
                lat: coordinate.latitude,
                lng: coordinate.longitude
            )
        }
        isGeocoding = false
    }

    private func loadNearby() async {
        guard let lat = activeLat, let lng = activeLng else { return }
        isLoading = true
        defer { isLoading = false }

        struct NearbyResponse: Decodable {
            let places: [PlaceJSON]
        }
        struct PlaceJSON: Decodable {
            let name: String
            let address: String?
            let lat: Double
            let lng: Double
            let place_id: String
        }

        do {
            let resp: NearbyResponse = try await APIClient.shared.request(
                "GET", "/places/nearby",
                query: ["lat": "\(lat)", "lng": "\(lng)", "radius": "1000"]
            )
            places = resp.places.map {
                PlaceResult(id: $0.place_id, name: $0.name, address: $0.address ?? "", lat: $0.lat, lng: $0.lng)
            }
        } catch {
            print("Failed to load nearby places: \(error)")
        }
    }

    private func searchPlaces(query: String) async {
        isLoading = true
        defer { isLoading = false }

        struct SearchResponse: Decodable {
            let places: [PlaceJSON]
        }
        struct PlaceJSON: Decodable {
            let name: String
            let address: String?
            let lat: Double
            let lng: Double
            let place_id: String
        }

        do {
            let resp: SearchResponse = try await APIClient.shared.request(
                "GET", "/places/search",
                query: ["query": query]
            )
            places = resp.places.map {
                PlaceResult(id: $0.place_id, name: $0.name, address: $0.address ?? "", lat: $0.lat, lng: $0.lng)
            }
        } catch {
            print("Failed to search places: \(error)")
        }
    }
}
