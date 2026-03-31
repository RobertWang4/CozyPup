import SwiftUI

/// Drop-in replacement for AsyncImage with memory + disk caching.
/// Usage is identical to AsyncImage:
///   CachedAsyncImage(url: someURL) { image in
///       image.resizable().scaledToFill()
///   } placeholder: {
///       Color.gray.opacity(0.2)
///   }
struct CachedAsyncImage<Content: View, Placeholder: View>: View {
    let url: URL?
    @ViewBuilder let content: (Image) -> Content
    @ViewBuilder let placeholder: () -> Placeholder

    @State private var uiImage: UIImage?
    @State private var isLoading = false

    var body: some View {
        if let uiImage {
            content(Image(uiImage: uiImage))
        } else {
            placeholder()
                .task(id: url) {
                    guard let url, !isLoading else { return }
                    isLoading = true
                    uiImage = await ImageCache.shared.image(for: url)
                    isLoading = false
                }
        }
    }
}

// MARK: - Convenience init (matching AsyncImage API)

extension CachedAsyncImage where Placeholder == Color {
    init(url: URL?, @ViewBuilder content: @escaping (Image) -> Content) {
        self.url = url
        self.content = content
        self.placeholder = { Color.clear }
    }
}

// MARK: - Image Cache (memory + disk)

actor ImageCache {
    static let shared = ImageCache()

    private let memory = NSCache<NSString, UIImage>()
    private let diskURL: URL

    private init() {
        let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
        diskURL = caches.appendingPathComponent("image_cache", isDirectory: true)
        try? FileManager.default.createDirectory(at: diskURL, withIntermediateDirectories: true)
        memory.countLimit = 100
        memory.totalCostLimit = 50 * 1024 * 1024 // 50 MB
    }

    func image(for url: URL) async -> UIImage? {
        let key = cacheKey(for: url)

        // 1. Memory
        if let cached = memory.object(forKey: key as NSString) {
            return cached
        }

        // 2. Disk
        let filePath = diskURL.appendingPathComponent(key)
        if let data = try? Data(contentsOf: filePath),
           let img = UIImage(data: data) {
            memory.setObject(img, forKey: key as NSString, cost: data.count)
            return img
        }

        // 3. Network
        guard let (data, response) = try? await URLSession.shared.data(from: url),
              let http = response as? HTTPURLResponse,
              http.statusCode == 200,
              let img = UIImage(data: data) else {
            return nil
        }

        // Store to memory + disk
        memory.setObject(img, forKey: key as NSString, cost: data.count)
        try? data.write(to: filePath, options: .atomic)

        return img
    }

    /// Remove a specific URL from cache (e.g. after avatar upload)
    func evict(for url: URL) {
        let key = cacheKey(for: url)
        memory.removeObject(forKey: key as NSString)
        let filePath = diskURL.appendingPathComponent(key)
        try? FileManager.default.removeItem(at: filePath)
    }

    private func cacheKey(for url: URL) -> String {
        // Strip query params for cache key so ?v=0 and ?v=1 share the same entry
        // (avatar versioning is handled by evict)
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        components?.query = nil
        let cleaned = components?.url?.absoluteString ?? url.absoluteString
        // SHA256 would be ideal but simple hash is fine for file names
        return cleaned.data(using: .utf8)!
            .map { String(format: "%02x", $0) }
            .joined()
            .suffix(64)
            .description
    }
}
