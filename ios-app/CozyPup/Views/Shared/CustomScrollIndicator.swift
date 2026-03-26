import SwiftUI

/// Custom scroll indicator: accent-colored, expands when touched, drag to scrub.
struct ScrollIndicatorOverlay: ViewModifier {
    let contentHeight: CGFloat
    let containerHeight: CGFloat
    let scrollOffset: CGFloat
    var onScrub: ((CGFloat) -> Void)? = nil  // progress 0..1

    @State private var isTouching = false
    @State private var isVisible = false
    @State private var hideTask: Task<Void, Never>?
    @State private var isDragging = false
    @State private var dragThumbOffset: CGFloat = 0
    @State private var dragStartOffset: CGFloat = 0

    private let normalWidth: CGFloat = 3.5
    private let expandedWidth: CGFloat = 14
    private let minThumbHeight: CGFloat = 40

    private var scrollable: Bool { contentHeight > containerHeight + 10 && containerHeight > 0 }
    private var maxScroll: CGFloat { max(contentHeight - containerHeight, 1) }
    private var trackLength: CGFloat { containerHeight - thumbHeight }

    private var thumbHeight: CGFloat {
        guard scrollable else { return 0 }
        let ratio = containerHeight / contentHeight
        return max(containerHeight * ratio, minThumbHeight)
    }

    /// Thumb position from scroll state (used when not dragging)
    private var scrollThumbOffset: CGFloat {
        guard scrollable else { return 0 }
        let progress = min(max(-scrollOffset / maxScroll, 0), 1)
        return progress * trackLength
    }

    /// Active thumb position: drag position when dragging, scroll position otherwise
    private var activeThumbOffset: CGFloat {
        isDragging ? dragThumbOffset : scrollThumbOffset
    }

    func body(content: Content) -> some View {
        content
            .overlay(alignment: .topTrailing) {
                if scrollable {
                    thumb.padding(.trailing, 0)
                        .opacity(isVisible ? 1 : 0)
                        .animation(.easeInOut(duration: 0.2), value: isVisible)
                }
            }
            .onChange(of: scrollOffset) {
                if !isDragging {
                    showThenFade()
                }
            }
    }

    private var thumb: some View {
        let w = isTouching ? expandedWidth : normalWidth
        return RoundedRectangle(cornerRadius: w / 2)
            .fill(Tokens.accent.opacity(isTouching ? 0.8 : 0.4))
            .frame(width: w, height: thumbHeight)
            .padding(.leading, 36) // invisible hit area to the left only
            .padding(.trailing, 2)
            .padding(.vertical, 10)
            .contentShape(Rectangle())
            .offset(y: activeThumbOffset)
            .animation(.spring(response: 0.15, dampingFraction: 0.85), value: isTouching)
            .highPriorityGesture(scrubGesture)
    }

    private var scrubGesture: some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                if !isDragging {
                    isTouching = true
                    isDragging = true
                    isVisible = true
                    hideTask?.cancel()
                    dragStartOffset = scrollThumbOffset
                    Haptics.light()
                }

                let newOffset = dragStartOffset + value.translation.height
                let clampedOffset = min(max(newOffset, 0), trackLength)
                dragThumbOffset = clampedOffset

                let progress = trackLength > 0 ? clampedOffset / trackLength : 0
                onScrub?(progress)
            }
            .onEnded { _ in
                isTouching = false
                isDragging = false
                showThenFade()
            }
    }

    private func showThenFade() {
        isVisible = true
        hideTask?.cancel()
        hideTask = Task {
            try? await Task.sleep(for: .seconds(1.5))
            guard !Task.isCancelled else { return }
            isVisible = false
        }
    }
}

struct ScrollOffsetKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

struct ContentHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}
