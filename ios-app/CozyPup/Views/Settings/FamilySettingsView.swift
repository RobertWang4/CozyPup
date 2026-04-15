import SwiftUI
import CoreImage.CIFilterBuiltins
import UIKit

struct FamilySettingsView: View {
    var onDismiss: () -> Void

    private var isZh: Bool { Lang.shared.isZh }

    @State private var familyStatus: FamilyStatus?
    @State private var pendingInvite: PendingInvite?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var showCopiedToast = false

    var body: some View {
        ZStack {
            Color.clear
                .contentShape(Rectangle())
                .ignoresSafeArea()
                .onTapGesture { dismiss() }

            VStack(spacing: 0) {
                // Header
                HStack(spacing: Tokens.spacing.sm) {
                    ZStack {
                        Circle()
                            .fill(Tokens.accentSoft)
                            .frame(width: 52, height: 52)
                        Image(systemName: "person.2.fill")
                            .font(.system(size: 22))
                            .foregroundColor(Tokens.accent)
                    }

                    VStack(alignment: .leading, spacing: 2) {
                        Text(isZh ? "双人计划" : "Duo Plan")
                            .font(Tokens.fontTitle.weight(.semibold))
                            .foregroundColor(Tokens.text)
                        Text(isZh ? "与一位伙伴共享完整访问权限" : "Share full access with one person")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                    }

                    Spacer()
                }
                .padding(.horizontal, Tokens.spacing.lg)
                .padding(.top, Tokens.spacing.lg)
                .padding(.bottom, Tokens.spacing.md)

                Rectangle()
                    .fill(Tokens.border)
                    .frame(height: 1)
                    .padding(.horizontal, Tokens.spacing.lg)

                Group {
                    if let status = familyStatus,
                       let partner = status.partner_name ?? status.partner_email {
                        partnerConnectedView(partner: partner)
                    } else if let invite = pendingInvite {
                        shareView(invite: invite)
                    } else {
                        generateView
                    }
                }
                .padding(Tokens.spacing.lg)
            }
            .background(Tokens.surface)
            .cornerRadius(28)
            .shadow(color: Color.black.opacity(0.25), radius: 30, x: 0, y: 16)
            .padding(.horizontal, Tokens.spacing.xl)

            if showCopiedToast {
                VStack {
                    Spacer()
                    Text(isZh ? "链接已复制" : "Link copied")
                        .font(Tokens.fontSubheadline.weight(.medium))
                        .foregroundColor(Tokens.white)
                        .padding(.horizontal, 18)
                        .padding(.vertical, 10)
                        .background(Tokens.text.opacity(0.85))
                        .cornerRadius(100)
                        .padding(.bottom, 80)
                }
                .transition(.opacity.combined(with: .move(edge: .bottom)))
            }
        }
        .background(BackgroundClearView())
        .task { await loadStatus() }
    }

    // MARK: - States

    /// Initial state: no pending invite. Show a "Generate Invite" CTA.
    private var generateView: some View {
        VStack(spacing: Tokens.spacing.md) {
            Image(systemName: "qrcode")
                .font(.system(size: 42))
                .foregroundColor(Tokens.accent)
                .padding(.top, Tokens.spacing.xs)

            Text(isZh ? "生成邀请码" : "Generate invite")
                .font(Tokens.fontBody.weight(.semibold))
                .foregroundColor(Tokens.text)

            Text(isZh
                 ? "让伙伴扫码或点击链接加入你的双人计划"
                 : "Your partner can scan the QR or open the link to join.")
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textSecondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)

            if let errorMessage {
                Text(errorMessage)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.red)
                    .padding(.top, Tokens.spacing.xs)
            }

            Button {
                Task { await generateInvite() }
            } label: {
                ZStack {
                    RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                        .fill(Tokens.accent)
                    if isLoading {
                        ProgressView().tint(Tokens.white)
                    } else {
                        Text(isZh ? "生成邀请链接" : "Generate Link")
                            .font(Tokens.fontBody.weight(.semibold))
                            .foregroundColor(Tokens.white)
                    }
                }
                .frame(height: 48)
            }
            .disabled(isLoading)
            .padding(.top, Tokens.spacing.xs)
        }
    }

    /// Invite exists — show QR, share button, copy button, countdown.
    @ViewBuilder
    private func shareView(invite: PendingInvite) -> some View {
        VStack(spacing: Tokens.spacing.md) {
            // QR code
            if let qr = Self.qrCode(for: invite.inviteUrl) {
                Image(uiImage: qr)
                    .interpolation(.none)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: 180, height: 180)
                    .padding(Tokens.spacing.sm)
                    .background(Tokens.white)
                    .cornerRadius(Tokens.radiusSmall)
                    .overlay(
                        RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                            .stroke(Tokens.border, lineWidth: 1)
                    )
            }

            // Countdown
            CountdownText(expiresAt: invite.expiresAt, isZh: isZh)
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textSecondary)

            // Buttons row
            HStack(spacing: Tokens.spacing.sm) {
                // Share
                ShareLink(
                    item: URL(string: invite.inviteUrl) ?? URL(string: "https://cozypup.app")!,
                    subject: Text(isZh ? "一起用 CozyPup" : "Join me on CozyPup"),
                    message: Text(shareMessage)
                ) {
                    shareButtonLabel(icon: "square.and.arrow.up", text: isZh ? "分享" : "Share")
                }
                .buttonStyle(.plain)

                // Copy
                Button {
                    UIPasteboard.general.string = invite.inviteUrl
                    Haptics.light()
                    withAnimation { showCopiedToast = true }
                    Task {
                        try? await Task.sleep(for: .seconds(1.5))
                        withAnimation { showCopiedToast = false }
                    }
                } label: {
                    shareButtonLabel(icon: "doc.on.doc", text: isZh ? "复制" : "Copy")
                }
                .buttonStyle(.plain)
            }

            // Regenerate / cancel
            HStack(spacing: Tokens.spacing.md) {
                Button {
                    Task { await generateInvite() }
                } label: {
                    Text(isZh ? "重新生成" : "Regenerate")
                        .font(Tokens.fontCaption.weight(.medium))
                        .foregroundColor(Tokens.textSecondary)
                }
                Text("·")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)
                Button {
                    Task { await revokePartner() }
                } label: {
                    Text(isZh ? "取消邀请" : "Cancel invite")
                        .font(Tokens.fontCaption.weight(.medium))
                        .foregroundColor(Tokens.red)
                }
            }
            .padding(.top, Tokens.spacing.xs)

            if let errorMessage {
                Text(errorMessage)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.red)
            }
        }
    }

    private func shareButtonLabel(icon: String, text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .semibold))
            Text(text)
                .font(Tokens.fontSubheadline.weight(.semibold))
        }
        .foregroundColor(Tokens.white)
        .frame(maxWidth: .infinity)
        .frame(height: 44)
        .background(Tokens.accent)
        .cornerRadius(Tokens.radiusSmall)
    }

    private var shareMessage: String {
        isZh
            ? "点击链接加入我的 CozyPup 双人计划，一起照顾毛孩子 🐾"
            : "Tap to join my CozyPup Duo plan — let's take care of our pets together 🐾"
    }

    private func partnerConnectedView(partner: String) -> some View {
        VStack(spacing: Tokens.spacing.md) {
            HStack(spacing: Tokens.spacing.sm) {
                ZStack {
                    Circle()
                        .fill(Tokens.green.opacity(0.15))
                        .frame(width: 44, height: 44)
                    Image(systemName: "checkmark")
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(Tokens.green)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(isZh ? "正在共享给" : "Sharing with")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                    Text(partner)
                        .font(Tokens.fontBody.weight(.semibold))
                        .foregroundColor(Tokens.text)
                }
                Spacer()
            }

            Button {
                Task { await revokePartner() }
            } label: {
                Text(isZh ? "移除伙伴" : "Remove Partner")
                    .font(Tokens.fontSubheadline.weight(.medium))
                    .foregroundColor(Tokens.red)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(Tokens.red.opacity(0.08))
                    .cornerRadius(Tokens.radiusSmall)
            }
        }
    }

    // MARK: - Actions

    private func dismiss() {
        onDismiss()
    }

    private func loadStatus() async {
        struct Resp: Decodable {
            let role: String?
            let partner_email: String?
            let partner_name: String?
            let invite_pending: Bool
            let pending_invite_email: String?
            let pending_invite_id: String?
            let pending_invite_url: String?
            let pending_invite_expires_at: String?
        }
        do {
            let resp: Resp = try await APIClient.shared.request("GET", "/family/status")
            familyStatus = FamilyStatus(
                role: resp.role,
                partner_email: resp.partner_email,
                partner_name: resp.partner_name,
                invite_pending: resp.invite_pending,
                pending_invite_email: resp.pending_invite_email
            )
            if resp.invite_pending,
               let id = resp.pending_invite_id,
               let url = resp.pending_invite_url {
                pendingInvite = PendingInvite(
                    id: id,
                    inviteUrl: url,
                    expiresAt: resp.pending_invite_expires_at.flatMap(Self.parseISO8601)
                )
            } else {
                pendingInvite = nil
            }
        } catch {
            print("[Family] load status failed: \(error)")
            familyStatus = FamilyStatus(role: nil, partner_email: nil, partner_name: nil, invite_pending: false, pending_invite_email: nil)
        }
    }

    private func generateInvite() async {
        isLoading = true
        defer { isLoading = false }
        errorMessage = nil

        struct Body: Encodable {}
        struct Resp: Decodable {
            let invite_id: String
            let status: String
            let invite_url: String
            let expires_at: String
        }
        do {
            let resp: Resp = try await APIClient.shared.request(
                "POST", "/family/invite", body: Body()
            )
            pendingInvite = PendingInvite(
                id: resp.invite_id,
                inviteUrl: resp.invite_url,
                expiresAt: Self.parseISO8601(resp.expires_at)
            )
            await loadStatus()
        } catch {
            errorMessage = isZh ? "生成失败，请稍后再试" : "Failed to generate invite"
        }
    }

    private func revokePartner() async {
        struct Resp: Decodable { let status: String }
        do {
            let _: Resp = try await APIClient.shared.request("POST", "/family/revoke")
            pendingInvite = nil
            await loadStatus()
        } catch {
            print("[Family] revoke failed: \(error)")
        }
    }

    // MARK: - Helpers

    private static func parseISO8601(_ s: String) -> Date? {
        let fmt = ISO8601DateFormatter()
        fmt.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = fmt.date(from: s) { return d }
        fmt.formatOptions = [.withInternetDateTime]
        return fmt.date(from: s)
    }

    private static func qrCode(for string: String) -> UIImage? {
        let data = Data(string.utf8)
        let filter = CIFilter.qrCodeGenerator()
        filter.message = data
        filter.correctionLevel = "M"
        guard let ciImage = filter.outputImage else { return nil }
        // Scale up for crisp rendering
        let scaled = ciImage.transformed(by: CGAffineTransform(scaleX: 10, y: 10))
        let context = CIContext()
        guard let cgImage = context.createCGImage(scaled, from: scaled.extent) else { return nil }
        return UIImage(cgImage: cgImage)
    }
}

// MARK: - Models

struct FamilyStatus {
    let role: String?
    let partner_email: String?
    let partner_name: String?
    let invite_pending: Bool
    let pending_invite_email: String?
}

struct PendingInvite {
    let id: String
    let inviteUrl: String
    let expiresAt: Date?
}

// MARK: - Countdown

private struct CountdownText: View {
    let expiresAt: Date?
    let isZh: Bool

    @State private var now = Date()
    private let timer = Timer.publish(every: 30, on: .main, in: .common).autoconnect()

    var body: some View {
        Text(text)
            .onReceive(timer) { _ in now = Date() }
    }

    private var text: String {
        guard let expiresAt else {
            return isZh ? "60 分钟内有效" : "Valid for 60 minutes"
        }
        let remaining = expiresAt.timeIntervalSince(now)
        if remaining <= 0 {
            return isZh ? "已过期 · 请重新生成" : "Expired · regenerate"
        }
        let minutes = max(1, Int(remaining / 60))
        return isZh ? "剩余 \(minutes) 分钟" : "Expires in \(minutes) min"
    }
}

/// Makes the underlying UIWindow background transparent so fullScreenCover looks like a floating modal.
private struct BackgroundClearView: UIViewRepresentable {
    func makeUIView(context: Context) -> UIView {
        let view = UIView()
        DispatchQueue.main.async {
            view.superview?.superview?.backgroundColor = .clear
        }
        return view
    }
    func updateUIView(_ uiView: UIView, context: Context) {}
}
