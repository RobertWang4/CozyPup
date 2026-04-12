import SwiftUI

struct FamilySettingsView: View {
    var onDismiss: () -> Void

    @State private var familyStatus: FamilyStatus?
    @State private var inviteEmail = ""
    @State private var isLoading = false
    @State private var message: String?
    @State private var errorMessage: String?
    @State private var cardVisible = false

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
                        Text("Duo Plan")
                            .font(Tokens.fontTitle.weight(.semibold))
                            .foregroundColor(Tokens.text)
                        Text("Share full access with one person")
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

                // Body
                Group {
                    if let status = familyStatus {
                        if let partner = status.partner_name ?? status.partner_email {
                            // Has partner
                            partnerConnectedView(partner: partner)
                        } else if status.invite_pending {
                            pendingInviteView(email: status.pending_invite_email ?? "")
                        } else {
                            inviteForm
                        }
                    } else {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, Tokens.spacing.xl)
                    }
                }
                .padding(Tokens.spacing.lg)
            }
            .background(Tokens.surface)
            .cornerRadius(28)
            .shadow(color: Color.black.opacity(0.25), radius: 30, x: 0, y: 16)
            .padding(.horizontal, Tokens.spacing.xl)
            .scaleEffect(cardVisible ? 1 : 0.92)
            .opacity(cardVisible ? 1 : 0)
        }
        .background(BackgroundClearView())
        .onAppear {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.82)) {
                cardVisible = true
            }
            Task { await loadStatus() }
        }
    }

    // MARK: - States

    private var inviteForm: some View {
        VStack(spacing: Tokens.spacing.md) {
            VStack(alignment: .leading, spacing: Tokens.spacing.xs) {
                Text("Partner's email")
                    .font(Tokens.fontCaption.weight(.medium))
                    .foregroundColor(Tokens.textSecondary)
                TextField("name@example.com", text: $inviteEmail)
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .autocapitalization(.none)
                    .disableAutocorrection(true)
                    .font(Tokens.fontBody)
                    .foregroundColor(Tokens.text)
                    .padding(Tokens.spacing.sm)
                    .background(Tokens.bg)
                    .overlay(
                        RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                            .stroke(Tokens.border, lineWidth: 1)
                    )
                    .cornerRadius(Tokens.radiusSmall)
            }

            if let message {
                Text(message)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.green)
            }
            if let errorMessage {
                Text(errorMessage)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.red)
            }

            Button {
                Task { await sendInvite() }
            } label: {
                ZStack {
                    RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                        .fill(inviteEmail.isEmpty ? Tokens.accent.opacity(0.5) : Tokens.accent)
                    if isLoading {
                        ProgressView().tint(Tokens.white)
                    } else {
                        Text("Send Invite")
                            .font(Tokens.fontBody.weight(.semibold))
                            .foregroundColor(Tokens.white)
                    }
                }
                .frame(height: 48)
            }
            .disabled(inviteEmail.isEmpty || isLoading)
        }
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
                    Text("Sharing with")
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
                Text("Remove Partner")
                    .font(Tokens.fontSubheadline.weight(.medium))
                    .foregroundColor(Tokens.red)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(Tokens.red.opacity(0.08))
                    .cornerRadius(Tokens.radiusSmall)
            }
        }
    }

    private func pendingInviteView(email: String) -> some View {
        VStack(spacing: Tokens.spacing.sm) {
            Image(systemName: "envelope.badge")
                .font(.system(size: 32))
                .foregroundColor(Tokens.accent)
                .padding(.bottom, 4)

            Text("Invite pending")
                .font(Tokens.fontBody.weight(.semibold))
                .foregroundColor(Tokens.text)
            Text(email)
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textSecondary)

            Button {
                Task { await revokePartner() }
            } label: {
                Text("Cancel invite")
                    .font(Tokens.fontCaption.weight(.medium))
                    .foregroundColor(Tokens.red)
            }
            .padding(.top, Tokens.spacing.sm)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Actions

    private func dismiss() {
        withAnimation(.easeInOut(duration: 0.2)) {
            cardVisible = false
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            onDismiss()
        }
    }

    private func loadStatus() async {
        struct Resp: Decodable {
            let role: String?
            let partner_email: String?
            let partner_name: String?
            let invite_pending: Bool
            let pending_invite_email: String?
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
        } catch {
            print("[Family] load status failed: \(error)")
            familyStatus = FamilyStatus(role: nil, partner_email: nil, partner_name: nil, invite_pending: false, pending_invite_email: nil)
        }
    }

    private func sendInvite() async {
        isLoading = true
        defer { isLoading = false }
        message = nil
        errorMessage = nil
        struct Body: Encodable { let email: String }
        struct Resp: Decodable { let invite_id: String; let status: String }
        do {
            let _: Resp = try await APIClient.shared.request(
                "POST", "/family/invite", body: Body(email: inviteEmail)
            )
            message = "Invite sent!"
            await loadStatus()
        } catch {
            errorMessage = "Failed to send invite"
        }
    }

    private func revokePartner() async {
        struct Resp: Decodable { let status: String }
        do {
            let _: Resp = try await APIClient.shared.request("POST", "/family/revoke")
            await loadStatus()
        } catch {
            print("[Family] revoke failed: \(error)")
        }
    }
}

struct FamilyStatus {
    let role: String?
    let partner_email: String?
    let partner_name: String?
    let invite_pending: Bool
    let pending_invite_email: String?
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
