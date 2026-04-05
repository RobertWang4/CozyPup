import SwiftUI
import PencilKit

struct FullScreenImageViewer: View {
    let image: UIImage
    let onDismiss: () -> Void

    @State private var scale: CGFloat = 1
    @State private var lastScale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var lastOffset: CGSize = .zero
    @State private var dragToDismissOffset: CGFloat = 0
    @State private var showToolbar = true
    @State private var showShareSheet = false
    @State private var showCropSheet = false
    @State private var showMarkup = false
    @State private var savedNotice = false

    private var isZoomed: Bool { scale > 1.05 }
    private var dismissProgress: CGFloat {
        let v: CGFloat = abs(dragToDismissOffset) / 300
        return min(v, 1)
    }

    var body: some View {
        ZStack {
            Color.black.opacity(1.0 - dismissProgress * 0.5)
                .ignoresSafeArea()
                .onTapGesture {
                    if !isZoomed {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showToolbar.toggle()
                        }
                    }
                }

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
                    if !isZoomed {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showToolbar.toggle()
                        }
                    }
                }

            // Top bar with close button
            if showToolbar && !isZoomed {
                GeometryReader { geo in
                    VStack {
                        HStack {
                            Button { onDismiss() } label: {
                                Image(systemName: "xmark")
                                    .font(.system(size: 16, weight: .semibold))
                                    .foregroundColor(.white)
                                    .frame(width: 36, height: 36)
                                    .background(.ultraThinMaterial.opacity(0.6))
                                    .clipShape(Circle())
                            }
                            Spacer()
                        }
                        .padding(.horizontal, Tokens.spacing.md)
                        .padding(.top, geo.safeAreaInsets.top + Tokens.spacing.lg)
                        Spacer()
                    }
                }
                .ignoresSafeArea()
                .transition(.opacity)
            }

            // Bottom toolbar
            if showToolbar && !isZoomed {
                VStack {
                    Spacer()
                    HStack(spacing: Tokens.spacing.xl) {
                        toolbarButton(icon: "square.and.arrow.down", label: Lang.shared.isZh ? "保存" : "Save") {
                            saveToPhotos()
                        }
                        toolbarButton(icon: "square.and.arrow.up", label: Lang.shared.isZh ? "分享" : "Share") {
                            showShareSheet = true
                        }
                        toolbarButton(icon: "pencil.tip.crop.circle", label: Lang.shared.isZh ? "标记" : "Markup") {
                            showMarkup = true
                        }
                        toolbarButton(icon: "crop", label: Lang.shared.isZh ? "裁剪" : "Crop") {
                            showCropSheet = true
                        }
                    }
                    .padding(.vertical, Tokens.spacing.md)
                    .padding(.horizontal, Tokens.spacing.xl)
                    .background(.ultraThinMaterial.opacity(0.6))
                    .cornerRadius(Tokens.radius)
                    .padding(.bottom, Tokens.spacing.xl)
                }
                .transition(.opacity)
            }

            // Saved notice
            if savedNotice {
                VStack {
                    Spacer()
                    HStack(spacing: Tokens.spacing.sm) {
                        Image(systemName: "checkmark.circle.fill")
                        Text(Lang.shared.isZh ? "已保存到相册" : "Saved to Photos")
                    }
                    .font(Tokens.fontSubheadline.weight(.medium))
                    .foregroundColor(.white)
                    .padding(.horizontal, Tokens.spacing.md)
                    .padding(.vertical, Tokens.spacing.sm)
                    .background(.black.opacity(0.7))
                    .cornerRadius(Tokens.radiusSmall)
                    .padding(.bottom, 120)
                }
                .transition(.opacity.combined(with: .scale(scale: 0.9)))
            }
        }
        .animation(.spring(response: 0.3), value: dragToDismissOffset)
        .sheet(isPresented: $showShareSheet) {
            ShareSheet(items: [image])
                .presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showCropSheet) {
            PhotoCropSheet(
                image: image,
                onConfirm: { _ in
                    showCropSheet = false
                },
                onCancel: {
                    showCropSheet = false
                }
            )
        }
        .fullScreenCover(isPresented: $showMarkup) {
            ImageMarkupView(image: image) { markedUp in
                showMarkup = false
                if let markedUp {
                    UIImageWriteToSavedPhotosAlbum(markedUp, nil, nil, nil)
                    withAnimation(.spring(response: 0.3)) { savedNotice = true }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                        withAnimation(.easeOut(duration: 0.3)) { savedNotice = false }
                    }
                }
            }
        }
    }

    // MARK: - Actions

    private func saveToPhotos() {
        UIImageWriteToSavedPhotosAlbum(image, nil, nil, nil)
        withAnimation(.spring(response: 0.3)) { savedNotice = true }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            withAnimation(.easeOut(duration: 0.3)) { savedNotice = false }
        }
    }

    // MARK: - Toolbar Button

    private func toolbarButton(icon: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 20))
                Text(label)
                    .font(Tokens.fontCaption2)
            }
            .foregroundColor(.white)
            .frame(width: 60)
        }
    }

    // MARK: - Gestures

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

// MARK: - Image Markup View (Instagram-style)

struct TextAnnotation: Identifiable {
    let id = UUID()
    var text: String
    var position: CGPoint
    var color: Color = .white
    var fontSize: CGFloat = 32
    var scale: CGFloat = 1
    var lastScale: CGFloat = 1
    var rotation: Angle = .zero
    var lastRotation: Angle = .zero
    var hasBg: Bool = false
}

struct ImageMarkupView: View {
    let image: UIImage
    let onDone: (UIImage?) -> Void

    enum Mode { case draw, text }
    enum PenStyle: Int, CaseIterable {
        case pen, marker, neon, eraser
        var icon: String {
            switch self {
            case .pen: "pencil.tip"
            case .marker: "highlighter"
            case .neon: "sparkles"
            case .eraser: "eraser"
            }
        }
    }

    @State private var canvasView = PKCanvasView()
    @State private var mode: Mode = .draw
    @State private var penStyle: PenStyle = .pen
    @State private var brushSize: CGFloat = 5
    @State private var selectedColor: Color = .white
    @State private var showBrushSlider = false

    @State private var textAnnotations: [TextAnnotation] = []
    @State private var activeAnnotationId: UUID?
    @State private var editingAnnotationId: UUID?
    @State private var editingText = ""
    @State private var canvasSize: CGSize = .zero
    @FocusState private var textFieldFocused: Bool

    private let palette: [Color] = [
        .white,
        Color(red: 0.17, green: 0.17, blue: 0.18),
        Color(red: 1.0, green: 0.27, blue: 0.23),
        Color(red: 1.0, green: 0.62, blue: 0.04),
        Color(red: 1.0, green: 0.84, blue: 0.04),
        Color(red: 0.19, green: 0.82, blue: 0.35),
        Color(red: 0.39, green: 0.82, blue: 1.0),
        Color(red: 0.04, green: 0.52, blue: 1.0),
        Color(red: 0.75, green: 0.35, blue: 0.95),
        Color(red: 1.0, green: 0.22, blue: 0.37),
    ]

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 0) {
                drawTopBar
                    .opacity(editingAnnotationId == nil ? 1 : 0)

                // Image + canvas area
                imageCanvas

                // Bottom controls
                if editingAnnotationId == nil {
                    bottomControls
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }

            // Brush size slider (left edge, Instagram-style vertical)
            if mode == .draw && showBrushSlider && editingAnnotationId == nil {
                brushSizeSlider
            }

            // Text editing overlay
            if editingAnnotationId != nil {
                textEditOverlay
            }
        }
        .animation(.easeInOut(duration: 0.2), value: mode)
        .animation(.easeInOut(duration: 0.2), value: editingAnnotationId != nil)
    }

    // MARK: - Top Bar

    private var drawTopBar: some View {
        HStack(spacing: 0) {
            // Cancel
            Button { onDone(nil) } label: {
                Text(Lang.shared.isZh ? "取消" : "Cancel")
                    .font(Tokens.fontBody.weight(.medium))
                    .foregroundColor(.white)
            }

            Spacer()

            if mode == .draw {
                // Pen style selector (Instagram-style)
                HStack(spacing: 4) {
                    ForEach(PenStyle.allCases, id: \.rawValue) { style in
                        Button {
                            penStyle = style
                            updateCanvasTool()
                        } label: {
                            Image(systemName: style.icon)
                                .font(.system(size: 18, weight: penStyle == style ? .bold : .regular))
                                .foregroundColor(penStyle == style ? .white : .white.opacity(0.45))
                                .frame(width: 40, height: 36)
                                .background(
                                    penStyle == style
                                        ? Circle()
                                            .fill(.white.opacity(0.15))
                                            .frame(width: 36, height: 36)
                                        : nil
                                )
                        }
                    }
                }
            } else {
                // Text mode indicator
                Image(systemName: "textformat")
                    .font(.system(size: 20, weight: .medium))
                    .foregroundColor(.white)
            }

            Spacer()

            // Done / Save
            Button {
                commitEditing()
                activeAnnotationId = nil
                let result = renderMarkedUpImage()
                onDone(result)
            } label: {
                Text(Lang.shared.isZh ? "完成" : "Done")
                    .font(Tokens.fontBody.weight(.semibold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 7)
                    .background(Tokens.accent)
                    .cornerRadius(20)
            }
        }
        .padding(.horizontal, Tokens.spacing.md)
        .padding(.vertical, Tokens.spacing.sm)
    }

    // MARK: - Image Canvas

    private var imageCanvas: some View {
        GeometryReader { geo in
            let imgSize = imageFitSize(in: geo.size)

            ZStack {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(width: imgSize.width, height: imgSize.height)

                if mode == .draw {
                    CanvasRepresentable(canvasView: $canvasView)
                        .frame(width: imgSize.width, height: imgSize.height)
                }

                // Text annotations
                ForEach(textAnnotations) { ann in
                    if ann.id != editingAnnotationId {
                        textOnCanvas(ann: ann, containerSize: imgSize)
                    }
                }

                // Tap to add text
                if mode == .text && activeAnnotationId == nil && editingAnnotationId == nil {
                    Color.clear
                        .frame(width: imgSize.width, height: imgSize.height)
                        .contentShape(Rectangle())
                        .onTapGesture { loc in
                            addTextAnnotation(at: loc)
                        }
                }
            }
            .frame(width: imgSize.width, height: imgSize.height)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .onAppear { canvasSize = imgSize }
            .onChange(of: geo.size) { _, _ in canvasSize = imgSize }
        }
    }

    // MARK: - Bottom Controls

    private var bottomControls: some View {
        VStack(spacing: Tokens.spacing.sm) {
            if mode == .draw {
                drawBottomBar
            } else {
                textBottomBar
            }

            // Mode switcher
            HStack(spacing: 0) {
                modeTab(label: Lang.shared.isZh ? "画笔" : "Draw", target: .draw)
                modeTab(label: Lang.shared.isZh ? "文字" : "Text", target: .text)
            }
            .padding(.bottom, Tokens.spacing.xs)
        }
    }

    // MARK: - Draw Bottom Bar

    private var drawBottomBar: some View {
        HStack(spacing: Tokens.spacing.md) {
            // Undo
            Button { canvasView.undoManager?.undo() } label: {
                Image(systemName: "arrow.uturn.backward")
                    .font(.system(size: 20, weight: .medium))
                    .foregroundColor(.white.opacity(0.8))
            }

            // Brush size indicator (tap to toggle slider)
            Button { withAnimation(.spring(response: 0.3)) { showBrushSlider.toggle() } } label: {
                Circle()
                    .fill(Color(uiColor: uiColorFromSwiftUI(selectedColor)))
                    .frame(width: brushSize + 10, height: brushSize + 10)
                    .overlay(Circle().stroke(.white.opacity(0.5), lineWidth: 1.5))
            }

            // Color palette
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(Array(palette.enumerated()), id: \.offset) { _, color in
                        colorDot(color: color)
                    }
                }
                .padding(.horizontal, 4)
            }
        }
        .padding(.horizontal, Tokens.spacing.md)
        .padding(.vertical, Tokens.spacing.sm)
    }

    // MARK: - Text Bottom Bar

    private var textBottomBar: some View {
        HStack(spacing: Tokens.spacing.md) {
            // Undo (remove last text)
            Button {
                if let last = textAnnotations.last {
                    if last.id == activeAnnotationId { activeAnnotationId = nil }
                    textAnnotations.removeAll { $0.id == last.id }
                }
            } label: {
                Image(systemName: "arrow.uturn.backward")
                    .font(.system(size: 20, weight: .medium))
                    .foregroundColor(textAnnotations.isEmpty ? .white.opacity(0.3) : .white.opacity(0.8))
            }
            .disabled(textAnnotations.isEmpty)

            Spacer()

            if activeAnnotationId != nil {
                Button {
                    if let id = activeAnnotationId {
                        textAnnotations.removeAll { $0.id == id }
                        activeAnnotationId = nil
                    }
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 18, weight: .medium))
                        .foregroundColor(.white.opacity(0.8))
                        .frame(width: 40, height: 40)
                        .background(.white.opacity(0.1))
                        .clipShape(Circle())
                }
            } else {
                Text(Lang.shared.isZh ? "点击图片添加文字" : "Tap to add text")
                    .font(Tokens.fontCaption)
                    .foregroundColor(.white.opacity(0.4))
            }

            Spacer()

            // Spacer for symmetry
            Color.clear.frame(width: 24, height: 24)
        }
        .padding(.horizontal, Tokens.spacing.md)
        .padding(.vertical, Tokens.spacing.sm)
    }

    // MARK: - Color Dot

    private func colorDot(color: Color) -> some View {
        let isSelected = selectedColor.description == color.description
        return Button {
            selectedColor = color
            updateCanvasTool()
        } label: {
            ZStack {
                if isSelected {
                    Circle()
                        .stroke(.white, lineWidth: 2.5)
                        .frame(width: 30, height: 30)
                }
                Circle()
                    .fill(color)
                    .frame(width: 24, height: 24)
                    .overlay(
                        // Black dot needs a subtle border
                        color == Color(red: 0.17, green: 0.17, blue: 0.18)
                            ? Circle().stroke(.white.opacity(0.3), lineWidth: 0.5)
                            : nil
                    )
            }
            .frame(width: 32, height: 32)
        }
    }

    // MARK: - Mode Tab

    private func modeTab(label: String, target: Mode) -> some View {
        Button {
            commitEditing()
            activeAnnotationId = nil
            withAnimation(.easeInOut(duration: 0.2)) { mode = target }
        } label: {
            VStack(spacing: 4) {
                Text(label)
                    .font(Tokens.fontSubheadline.weight(mode == target ? .semibold : .regular))
                    .foregroundColor(mode == target ? .white : .white.opacity(0.4))
                Rectangle()
                    .fill(mode == target ? .white : .clear)
                    .frame(width: 24, height: 2)
                    .cornerRadius(1)
            }
            .frame(maxWidth: .infinity)
        }
    }

    // MARK: - Brush Size Slider (vertical, left edge)

    private var brushSizeSlider: some View {
        HStack {
            VStack {
                Spacer()
                VStack(spacing: Tokens.spacing.sm) {
                    // Size preview
                    Circle()
                        .fill(.white)
                        .frame(width: brushSize + 4, height: brushSize + 4)

                    // Vertical slider
                    Slider(value: $brushSize, in: 1...30)
                        .rotationEffect(.degrees(-90))
                        .frame(width: 36, height: 180)
                        .tint(.white)
                        .onChange(of: brushSize) { _, _ in updateCanvasTool() }
                }
                .padding(.vertical, Tokens.spacing.md)
                .padding(.horizontal, Tokens.spacing.sm)
                .background(.ultraThinMaterial)
                .cornerRadius(Tokens.radius)
                Spacer()
            }
            .padding(.leading, Tokens.spacing.sm)
            Spacer()
        }
    }

    // MARK: - Text on Canvas

    private func textOnCanvas(ann: TextAnnotation, containerSize: CGSize) -> some View {
        let isActive = ann.id == activeAnnotationId
        let effectiveSize = ann.fontSize * ann.scale

        return Text(ann.text.isEmpty ? " " : ann.text)
            .font(.system(size: effectiveSize, weight: .bold))
            .foregroundColor(ann.hasBg ? .white : ann.color)
            .shadow(color: ann.hasBg ? .clear : .black.opacity(0.6), radius: 2, x: 1, y: 1)
            .padding(.horizontal, ann.hasBg ? 10 : 6)
            .padding(.vertical, ann.hasBg ? 6 : 3)
            .background(
                Group {
                    if ann.hasBg {
                        RoundedRectangle(cornerRadius: 6)
                            .fill(ann.color)
                    } else if isActive {
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(.white.opacity(0.6), lineWidth: 1)
                            .background(RoundedRectangle(cornerRadius: 6).fill(.white.opacity(0.08)))
                    }
                }
            )
            .rotationEffect(ann.rotation)
            .position(ann.position)
            .gesture(
                DragGesture()
                    .onChanged { value in
                        if mode == .text {
                            activeAnnotationId = ann.id
                            let clamped = CGPoint(
                                x: max(0, min(value.location.x, containerSize.width)),
                                y: max(0, min(value.location.y, containerSize.height))
                            )
                            if let idx = textAnnotations.firstIndex(where: { $0.id == ann.id }) {
                                textAnnotations[idx].position = clamped
                            }
                        }
                    }
            )
            .simultaneousGesture(
                MagnifyGesture()
                    .onChanged { value in
                        if mode == .text, let idx = textAnnotations.firstIndex(where: { $0.id == ann.id }) {
                            textAnnotations[idx].scale = max(0.5, min(textAnnotations[idx].lastScale * value.magnification, 4.0))
                        }
                    }
                    .onEnded { _ in
                        if let idx = textAnnotations.firstIndex(where: { $0.id == ann.id }) {
                            textAnnotations[idx].lastScale = textAnnotations[idx].scale
                        }
                    }
            )
            .simultaneousGesture(
                RotationGesture()
                    .onChanged { value in
                        if mode == .text, let idx = textAnnotations.firstIndex(where: { $0.id == ann.id }) {
                            textAnnotations[idx].rotation = textAnnotations[idx].lastRotation + value
                        }
                    }
                    .onEnded { _ in
                        if let idx = textAnnotations.firstIndex(where: { $0.id == ann.id }) {
                            textAnnotations[idx].lastRotation = textAnnotations[idx].rotation
                        }
                    }
            )
            .onTapGesture(count: 2) {
                if mode == .text {
                    activeAnnotationId = ann.id
                    editingAnnotationId = ann.id
                    editingText = ann.text
                    textFieldFocused = true
                }
            }
            .onTapGesture {
                if mode == .text {
                    if activeAnnotationId == ann.id {
                        editingAnnotationId = ann.id
                        editingText = ann.text
                        textFieldFocused = true
                    } else {
                        commitEditing()
                        activeAnnotationId = ann.id
                    }
                }
            }
    }

    // MARK: - Text Edit Overlay (Instagram-style)

    private var textEditOverlay: some View {
        ZStack {
            Color.black.opacity(0.7)
                .ignoresSafeArea()
                .onTapGesture { commitEditing() }

            VStack(spacing: 0) {
                // Top: alignment + bg toggle + done
                HStack {
                    // Toggle text background
                    Button {
                        if let id = editingAnnotationId,
                           let idx = textAnnotations.firstIndex(where: { $0.id == id }) {
                            textAnnotations[idx].hasBg.toggle()
                        }
                    } label: {
                        Image(systemName: "a.square.fill")
                            .font(.system(size: 22, weight: .medium))
                            .foregroundColor(.white.opacity(0.8))
                    }

                    Spacer()

                    Button { commitEditing() } label: {
                        Text(Lang.shared.isZh ? "完成" : "Done")
                            .font(Tokens.fontBody.weight(.semibold))
                            .foregroundColor(Tokens.accent)
                    }
                }
                .padding(.horizontal, Tokens.spacing.md)
                .padding(.vertical, Tokens.spacing.sm)

                Spacer()

                // Centered text input
                TextField(Lang.shared.isZh ? "输入文字" : "Type here", text: $editingText)
                    .font(.system(size: 32, weight: .bold))
                    .foregroundColor(selectedColor)
                    .multilineTextAlignment(.center)
                    .focused($textFieldFocused)
                    .padding(.horizontal, Tokens.spacing.xl)
                    .onChange(of: editingText) { _, newVal in
                        if let id = editingAnnotationId,
                           let idx = textAnnotations.firstIndex(where: { $0.id == id }) {
                            textAnnotations[idx].text = newVal
                        }
                    }
                    .onSubmit { commitEditing() }

                Spacer()

                // Color palette at bottom
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(Array(palette.enumerated()), id: \.offset) { _, color in
                            textColorDot(color: color)
                        }
                    }
                    .padding(.horizontal, Tokens.spacing.md)
                }
                .padding(.bottom, Tokens.spacing.md)
            }
        }
        .transition(.opacity)
    }

    private func textColorDot(color: Color) -> some View {
        let isSelected = selectedColor.description == color.description
        return Button {
            selectedColor = color
            if let id = editingAnnotationId,
               let idx = textAnnotations.firstIndex(where: { $0.id == id }) {
                textAnnotations[idx].color = color
            }
        } label: {
            ZStack {
                if isSelected {
                    Circle()
                        .stroke(.white, lineWidth: 2.5)
                        .frame(width: 32, height: 32)
                }
                Circle()
                    .fill(color)
                    .frame(width: 26, height: 26)
            }
            .frame(width: 34, height: 34)
        }
    }

    // MARK: - Helpers

    private func addTextAnnotation(at point: CGPoint) {
        commitEditing()
        let annotation = TextAnnotation(
            text: "",
            position: point,
            color: selectedColor
        )
        textAnnotations.append(annotation)
        activeAnnotationId = annotation.id
        editingAnnotationId = annotation.id
        editingText = ""
        textFieldFocused = true
    }

    private func commitEditing() {
        guard let id = editingAnnotationId else { return }
        textAnnotations.removeAll { $0.id == id && $0.text.trimmingCharacters(in: .whitespaces).isEmpty }
        editingAnnotationId = nil
        textFieldFocused = false
    }

    private func updateCanvasTool() {
        let uiColor = uiColorFromSwiftUI(selectedColor)
        switch penStyle {
        case .pen:
            canvasView.tool = PKInkingTool(.pen, color: uiColor, width: brushSize)
        case .marker:
            canvasView.tool = PKInkingTool(.marker, color: uiColor.withAlphaComponent(0.4), width: brushSize * 3)
        case .neon:
            canvasView.tool = PKInkingTool(.pen, color: uiColor.withAlphaComponent(0.7), width: brushSize * 1.5)
        case .eraser:
            canvasView.tool = PKEraserTool(.bitmap)
        }
    }

    private func uiColorFromSwiftUI(_ color: Color) -> UIColor {
        UIColor(color)
    }

    private func imageFitSize(in containerSize: CGSize) -> CGSize {
        let ratio = min(containerSize.width / image.size.width,
                        containerSize.height / image.size.height)
        return CGSize(width: image.size.width * ratio,
                      height: image.size.height * ratio)
    }

    private func renderMarkedUpImage() -> UIImage {
        let size = image.size
        let renderer = UIGraphicsImageRenderer(size: size)
        return renderer.image { ctx in
            image.draw(in: CGRect(origin: .zero, size: size))

            let cSize = canvasView.bounds.size
            if cSize.width > 0 && cSize.height > 0 {
                let scaleX = size.width / cSize.width
                let scaleY = size.height / cSize.height
                ctx.cgContext.saveGState()
                ctx.cgContext.scaleBy(x: scaleX, y: scaleY)
                let drawingImage = canvasView.drawing.image(
                    from: canvasView.bounds, scale: UIScreen.main.scale
                )
                drawingImage.draw(in: CGRect(origin: .zero, size: cSize))
                ctx.cgContext.restoreGState()
            }

            guard canvasSize.width > 0 && canvasSize.height > 0 else { return }
            let viewToImageX = size.width / canvasSize.width
            let viewToImageY = size.height / canvasSize.height
            for ann in textAnnotations where !ann.text.isEmpty {
                let effectiveFontSize = ann.fontSize * ann.scale * viewToImageX
                let uiColor = UIColor(ann.color)

                // Draw background if needed
                if ann.hasBg {
                    let font = UIFont.boldSystemFont(ofSize: effectiveFontSize)
                    let str = ann.text as NSString
                    let textSize = str.size(withAttributes: [.font: font])
                    let bgRect = CGRect(
                        x: ann.position.x * viewToImageX - textSize.width / 2 - 10,
                        y: ann.position.y * viewToImageY - textSize.height / 2 - 6,
                        width: textSize.width + 20,
                        height: textSize.height + 12
                    )
                    ctx.cgContext.saveGState()
                    if ann.rotation != .zero {
                        let center = CGPoint(x: bgRect.midX, y: bgRect.midY)
                        ctx.cgContext.translateBy(x: center.x, y: center.y)
                        ctx.cgContext.rotate(by: CGFloat(ann.rotation.radians))
                        ctx.cgContext.translateBy(x: -center.x, y: -center.y)
                    }
                    let path = UIBezierPath(roundedRect: bgRect, cornerRadius: 6)
                    uiColor.setFill()
                    path.fill()
                    // White text on bg
                    let attrs: [NSAttributedString.Key: Any] = [
                        .font: UIFont.boldSystemFont(ofSize: effectiveFontSize),
                        .foregroundColor: UIColor.white
                    ]
                    let x = ann.position.x * viewToImageX - textSize.width / 2
                    let y = ann.position.y * viewToImageY - textSize.height / 2
                    str.draw(at: CGPoint(x: x, y: y), withAttributes: attrs)
                    ctx.cgContext.restoreGState()
                } else {
                    let shadow = NSShadow()
                    shadow.shadowColor = UIColor.black.withAlphaComponent(0.6)
                    shadow.shadowOffset = CGSize(width: 1, height: 1)
                    shadow.shadowBlurRadius = 2
                    let attrs: [NSAttributedString.Key: Any] = [
                        .font: UIFont.boldSystemFont(ofSize: effectiveFontSize),
                        .foregroundColor: uiColor,
                        .shadow: shadow
                    ]
                    let str = ann.text as NSString
                    let textSize = str.size(withAttributes: attrs)

                    ctx.cgContext.saveGState()
                    if ann.rotation != .zero {
                        let center = CGPoint(
                            x: ann.position.x * viewToImageX,
                            y: ann.position.y * viewToImageY
                        )
                        ctx.cgContext.translateBy(x: center.x, y: center.y)
                        ctx.cgContext.rotate(by: CGFloat(ann.rotation.radians))
                        ctx.cgContext.translateBy(x: -center.x, y: -center.y)
                    }
                    let x = ann.position.x * viewToImageX - textSize.width / 2
                    let y = ann.position.y * viewToImageY - textSize.height / 2
                    str.draw(at: CGPoint(x: x, y: y), withAttributes: attrs)
                    ctx.cgContext.restoreGState()
                }
            }
        }
    }
}

// MARK: - PKCanvasView Representable (no system tool picker)

struct CanvasRepresentable: UIViewRepresentable {
    @Binding var canvasView: PKCanvasView

    func makeUIView(context: Context) -> PKCanvasView {
        canvasView.drawingPolicy = .anyInput
        canvasView.backgroundColor = .clear
        canvasView.isOpaque = false
        canvasView.tool = PKInkingTool(.pen, color: .white, width: 5)
        return canvasView
    }

    func updateUIView(_ uiView: PKCanvasView, context: Context) {}
}

