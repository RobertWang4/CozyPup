import SwiftUI

struct FamilySettingsView: View {
    @State private var familyStatus: FamilyStatus?
    @State private var inviteEmail = ""
    @State private var isLoading = false
    @State private var message: String?

    var body: some View {
        VStack(spacing: Tokens.spacing.lg) {
            Text("Duo Plan")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            if let status = familyStatus {
                if let partner = status.partner_name ?? status.partner_email {
                    VStack(spacing: Tokens.spacing.sm) {
                        Text("Sharing with")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                        Text(partner)
                            .font(Tokens.fontBody.weight(.semibold))
                            .foregroundColor(Tokens.text)

                        Button("Remove Partner") {
                            Task { await revokePartner() }
                        }
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.red)
                        .padding(.top, Tokens.spacing.sm)
                    }
                } else if status.invite_pending {
                    VStack(spacing: Tokens.spacing.xs) {
                        Text("Invite pending")
                            .font(Tokens.fontSubheadline)
                            .foregroundColor(Tokens.textSecondary)
                        Text(status.pending_invite_email ?? "")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                    }
                } else {
                    VStack(spacing: Tokens.spacing.md) {
                        TextField("Partner's email", text: $inviteEmail)
                            .textContentType(.emailAddress)
                            .keyboardType(.emailAddress)
                            .autocapitalization(.none)
                            .padding(Tokens.spacing.sm)
                            .background(Tokens.surface)
                            .cornerRadius(Tokens.radiusSmall)

                        Button {
                            Task { await sendInvite() }
                        } label: {
                            if isLoading {
                                ProgressView().tint(Tokens.white)
                            } else {
                                Text("Send Invite")
                            }
                        }
                        .font(Tokens.fontBody.weight(.semibold))
                        .foregroundColor(Tokens.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(inviteEmail.isEmpty ? Tokens.accent.opacity(0.5) : Tokens.accent)
                        .cornerRadius(Tokens.radiusSmall)
                        .disabled(inviteEmail.isEmpty || isLoading)
                    }
                }
            } else {
                ProgressView()
            }

            if let message {
                Text(message)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.green)
            }

            Spacer()
        }
        .padding(Tokens.spacing.md)
        .task { await loadStatus() }
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
        }
    }

    private func sendInvite() async {
        isLoading = true
        defer { isLoading = false }
        struct Body: Encodable { let email: String }
        struct Resp: Decodable { let invite_id: String; let status: String }
        do {
            let _: Resp = try await APIClient.shared.request(
                "POST", "/family/invite", body: Body(email: inviteEmail)
            )
            message = "Invite sent!"
            await loadStatus()
        } catch {
            message = "Failed to send invite"
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

#Preview {
    FamilySettingsView()
}
