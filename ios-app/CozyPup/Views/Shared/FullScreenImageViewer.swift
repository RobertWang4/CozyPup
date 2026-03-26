import SwiftUI

struct FullScreenImageViewer: View {
    let image: UIImage
    let onDismiss: () -> Void

    @State private var scale: CGFloat = 1
    @State private var lastScale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero
    @State private var dragToDismissOffset: CGFloat = 0

    private var isZoomed: Bool { scale > 1.05 }
    private var dismissProgress: CGFloat {
        let v: CGFloat = abs(dragToDismissOffset) / 300
        return min(v, 1)
    }

    var body: some View {
        ZStack {
            Color.black.opacity(1.0 - dismissProgress * 0.5)
                .ignoresSafeArea()
                .onTapGesture { if !isZoomed { onDismiss() } }

            Image(uiImage: image)
                .resizable()
                .scaledToFit()
                .scaleEffect(scale)
                .offset(x: isZoomed ? offset.width : 0,
                        y: isZoomed ? offset.height : dragToDismissOffset)
                .gesture(zoomGesture)
                .gesture(isZoomed ? panGesture : nil)
                .gesture(!isZoomed ? dismissDragGesture : nil)
                .onTapGesture(count: 2) {
                    withAnimation(.spring(response: 0.3)) {
                        if isZoomed {
                            scale = 1; lastScale = 1
                            offset = .zero; lastOffset = .zero
                        } else {
                            scale = 2.5; lastScale = 2.5
                        }
                    }
                }
                .onTapGesture {
                    if !isZoomed { onDismiss() }
                }
        }
        .animation(.spring(response: 0.3), value: dragToDismissOffset)
    }

    private var zoomGesture: some Gesture {
        MagnifyGesture()
            .onChanged { value in
                scale = max(lastScale * value.magnification, 0.5)
            }
            .onEnded { value in
                withAnimation(.spring(response: 0.3)) {
                    scale = max(min(scale, 5), 1)
                    lastScale = scale
                    if scale <= 1 {
                        offset = .zero; lastOffset = .zero
                    }
                }
            }
    }

    private var panGesture: some Gesture {
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

    private var dismissDragGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                dragToDismissOffset = value.translation.height
            }
            .onEnded { value in
                if abs(value.translation.height) > 120 ||
                   abs(value.predictedEndTranslation.height) > 300 {
                    onDismiss()
                } else {
                    withAnimation(.spring(response: 0.3)) {
                        dragToDismissOffset = 0
                    }
                }
            }
    }
}
