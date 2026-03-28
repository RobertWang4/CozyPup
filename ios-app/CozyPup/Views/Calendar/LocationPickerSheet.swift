import SwiftUI
import MapKit

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

    @State private var searchText = ""
    @State private var places: [PlaceResult] = []
    @State private var isLoading = false
    @State private var selectedId: String?
    @State private var mapSelection: String?
    @State private var cameraPosition: MapCameraPosition = .automatic
    @State private var searchTask: Task<Void, Never>?

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Map
                Map(position: $cameraPosition, selection: $mapSelection) {
                    if let lat = currentLat, let lng = currentLng {
                        Annotation("", coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lng)) {
                            Circle()
                                .fill(Tokens.accent)
                                .frame(width: 16, height: 16)
                                .overlay(Circle().stroke(Tokens.white, lineWidth: 3))
                                .shadow(radius: 2)
                        }
                    }
                    ForEach(places) { place in
                        Marker(place.name, coordinate: place.coordinate)
                            .tint(Tokens.accent)
                            .tag(place.id)
                    }
                }
                .frame(height: 250)
                .onChange(of: mapSelection) { _, newId in
                    guard let newId, let place = places.first(where: { $0.id == newId }) else { return }
                    selectedId = place.id
                    onSelect(place)
                    dismiss()
                }

                // Search bar
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
                                    selectedId = place.id
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
                                        if selectedId == place.id {
                                            Image(systemName: "checkmark")
                                                .foregroundColor(Tokens.accent)
                                                .fontWeight(.semibold)
                                        }
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
            .background(Tokens.bg.ignoresSafeArea())
            .toolbarBackground(Tokens.bg, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .navigationTitle(Lang.shared.isZh ? "选择地点" : "Choose Location")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(Lang.shared.isZh ? "取消" : "Cancel") { dismiss() }
                        .foregroundColor(Tokens.accent)
                }
            }
            .onTapGesture { dismissKeyboard() }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task {
            if let lat = currentLat, let lng = currentLng {
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
    }

    private func dismissKeyboard() {
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
    }

    private func loadNearby() async {
        guard let lat = currentLat, let lng = currentLng else { return }
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
