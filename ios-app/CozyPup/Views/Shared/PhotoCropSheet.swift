import SwiftUI

struct PhotoCropSheet: View {
    let image: UIImage
    let onConfirm: (Data) -> Void
    let onCancel: () -> Void

    @State private var scale: CGFloat = 1
    @State private var lastScale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero

    private let cropSize: CGFloat = 300

    var body: some View {
        ZStack {
            Tokens.bg.ignoresSafeArea()

            VStack(spacing: Tokens.spacing.lg) {
                // Header
                HStack {
                    Button {
                        onCancel()
                    } label: {
                        Text(Lang.shared.isZh ? "取消" : "Cancel")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.textSecondary)
                    }
                    Spacer()
                    Text(Lang.shared.isZh ? "裁剪照片" : "Crop Photo")
                        .font(Tokens.fontHeadline)
                        .foregroundColor(Tokens.text)
                    Spacer()
                    Button {
                        confirmCrop()
                    } label: {
                        Text(Lang.shared.isZh ? "确认" : "Done")
                            .font(Tokens.fontBody.weight(.semibold))
                            .foregroundColor(Tokens.accent)
                    }
                }
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.top, Tokens.spacing.md)

                Spacer()

                // Crop area
                ZStack {
                    Color.black

                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .scaleEffect(scale)
                        .offset(offset)
                        .frame(width: cropSize, height: cropSize)
                        .clipped()
                        .gesture(dragGesture)
                        .gesture(zoomGesture)
                }
                .frame(width: cropSize, height: cropSize)
                .cornerRadius(Tokens.radiusSmall)

                // Hint
                Text(Lang.shared.isZh ? "拖动和缩放来调整" : "Drag and pinch to adjust")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)

                Spacer()
            }
        }
        .interactiveDismissDisabled()
    }

    private var zoomGesture: some Gesture {
        MagnifyGesture()
            .onChanged { value in
                scale = max(lastScale * value.magnification, 0.5)
            }
            .onEnded { _ in
                withAnimation(.spring(response: 0.3)) {
                    scale = max(min(scale, 5), 1)
                    lastScale = scale
                    if scale <= 1 {
                        offset = .zero
                        lastOffset = .zero
                    }
                }
            }
    }

    private var dragGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                offset = CGSize(
                    width: lastOffset.width + value.translation.width,
                    height: lastOffset.height + value.translation.height
                )
            }
            .onEnded { _ in
                lastOffset = offset
            }
    }

    private func confirmCrop() {
        let outputSize = cropSize * UIScreen.main.scale
        let imgSize = image.size

        // Calculate the displayed image size (scaledToFill within cropSize)
        let fillScale: CGFloat = max(cropSize / imgSize.width, cropSize / imgSize.height) * scale
        let drawW = imgSize.width * fillScale
        let drawH = imgSize.height * fillScale

        // Image is centered in the crop area, then offset by user drag
        let drawX = (cropSize - drawW) / 2 + offset.width
        let drawY = (cropSize - drawH) / 2 + offset.height

        let renderer = UIGraphicsImageRenderer(size: CGSize(width: cropSize, height: cropSize))
        let cropped = renderer.image { _ in
            image.draw(in: CGRect(x: drawX, y: drawY, width: drawW, height: drawH))
        }

        if let jpeg = cropped.jpegData(compressionQuality: 0.7) {
            onConfirm(jpeg)
        }
    }
}
