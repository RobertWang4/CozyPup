import UIKit

extension UIImage {
    /// Resize to fit within maxDimension (preserving aspect ratio).
    /// LLM vision models internally resize to ~1024px anyway, so sending
    /// larger images just wastes bandwidth and risks request timeouts.
    func resizedForUpload(maxDimension: CGFloat = 1024) -> UIImage {
        let maxSide = max(size.width, size.height)
        guard maxSide > maxDimension else { return self }
        let scale = maxDimension / maxSide
        let newSize = CGSize(width: size.width * scale, height: size.height * scale)
        let renderer = UIGraphicsImageRenderer(size: newSize)
        return renderer.image { _ in
            draw(in: CGRect(origin: .zero, size: newSize))
        }
    }
}
