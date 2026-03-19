import CoreLocation

@MainActor
class LocationService: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published var lastLocation: CLLocationCoordinate2D?

    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<CLLocationCoordinate2D?, Never>?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func requestLocation() async -> CLLocationCoordinate2D? {
        manager.requestWhenInUseAuthorization()
        return await withCheckedContinuation { cont in
            continuation = cont
            manager.requestLocation()
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        let coord = locations.first?.coordinate
        Task { @MainActor in
            self.lastLocation = coord
            self.continuation?.resume(returning: coord)
            self.continuation = nil
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in
            self.continuation?.resume(returning: nil)
            self.continuation = nil
        }
    }
}
