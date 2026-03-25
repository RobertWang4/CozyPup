import SwiftUI
import UIKit

/// UIKit-based pinch gesture that works inside ScrollView.
/// Only intercepts two-finger pinch — single finger passes through to ScrollView.
struct PinchGestureView: UIViewRepresentable {
    var onPinch: (CGFloat, Bool) -> Void

    func makeUIView(context: Context) -> PassthroughView {
        let view = PassthroughView()
        let pinch = UIPinchGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.handlePinch(_:)))
        pinch.delegate = context.coordinator
        view.addGestureRecognizer(pinch)
        return view
    }

    func updateUIView(_ uiView: PassthroughView, context: Context) {
        context.coordinator.onPinch = onPinch
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(onPinch: onPinch)
    }

    /// A UIView that passes through all touches except active pinch gestures.
    class PassthroughView: UIView {
        override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
            // Only claim the hit if there are 2+ touches (pinch).
            // Otherwise return nil so ScrollView underneath gets the touch.
            if let touches = event?.allTouches, touches.count >= 2 {
                return super.hitTest(point, with: event)
            }
            return nil
        }
    }

    class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var onPinch: (CGFloat, Bool) -> Void

        init(onPinch: @escaping (CGFloat, Bool) -> Void) {
            self.onPinch = onPinch
        }

        @objc func handlePinch(_ gesture: UIPinchGestureRecognizer) {
            switch gesture.state {
            case .changed:
                onPinch(gesture.scale, false)
            case .ended, .cancelled:
                onPinch(gesture.scale, true)
            default:
                break
            }
        }

        func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer,
                               shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool {
            true
        }
    }
}
