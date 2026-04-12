import SwiftUI

/// Section of the Profile sheet showing Duo Plan state.
///
/// Three states:
/// 1. Active (current user has isDuo=true) — shows section header "DUO PLAN · Active"
///    plus a friend row that pushes into FamilySettingsView. Friend row subtitle is
///    "Member" (if I am payer) or "Paid by" (if I am member).
/// 2. Pending invite (payer has sent invite, not yet accepted) — shows section header
///    and a muted "Invite pending..." row that also opens FamilySettingsView.
/// 3. Inactive — section header "DUO PLAN · Inactive" plus an "Upgrade to Duo Plan"
///    row that opens the Duo paywall.
struct DuoPlanSection: View {
    @EnvironmentObject var subscriptionStore: SubscriptionStore
    @ObservedObject private var lang = Lang.shared

    @Binding var showFamilySettings: Bool
    @Binding var showDuoPaywall: Bool

    @State private var familyState: FamilyState = .loading

    private enum FamilyState {
        case loading
        case active(partnerName: String, partnerEmail: String, iAmPayer: Bool)
        case pending(email: String)
        case none
    }

    var body: some View {
        Section(header: Text(headerText).font(Tokens.fontCaption).foregroundColor(Tokens.textSecondary)) {
            switch familyState {
            case .loading:
                HStack {
                    ProgressView().controlSize(.small)
                    Spacer()
                }
                .listRowBackground(Tokens.surface)

            case .active(let name, _, let iAmPayer):
                Button { showFamilySettings = true } label: {
                    HStack(spacing: Tokens.spacing.sm) {
                        Circle()
                            .fill(Tokens.accentSoft)
                            .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
                            .overlay(
                                Text(String(name.prefix(1)))
                                    .foregroundColor(Tokens.accent)
                                    .font(Tokens.fontSubheadline.weight(.semibold))
                            )
                        VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                            Text(name)
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.text)
                            Text(iAmPayer
                                 ? (lang.isZh ? "成员" : "Member")
                                 : (lang.isZh ? "由对方付费" : "Paid by"))
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
                .listRowBackground(Tokens.surface)

            case .pending(let email):
                Button { showFamilySettings = true } label: {
                    HStack(spacing: Tokens.spacing.sm) {
                        Circle()
                            .fill(Tokens.surface2)
                            .frame(width: Tokens.size.avatarSmall, height: Tokens.size.avatarSmall)
                            .overlay(
                                Image(systemName: "hourglass")
                                    .foregroundColor(Tokens.textTertiary)
                                    .font(Tokens.fontSubheadline)
                            )
                        VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                            Text(lang.isZh ? "邀请已发送" : "Invite pending")
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.text)
                            Text(email)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
                .listRowBackground(Tokens.surface)

            case .none:
                Button { showDuoPaywall = true } label: {
                    HStack(spacing: Tokens.spacing.sm) {
                        Image(systemName: "person.2.fill")
                            .foregroundColor(Tokens.accent)
                            .frame(width: Tokens.size.avatarSmall)
                        Text(lang.isZh ? "升级至双人计划" : "Upgrade to Duo Plan")
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                        Spacer()
                        Text(lang.isZh ? "升级" : "Upgrade")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.accent)
                        Image(systemName: "chevron.right")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }
                }
                .listRowBackground(Tokens.surface)
            }
        }
        .task { await loadFamilyState() }
        .onChange(of: subscriptionStore.isDuo) { _, _ in
            Task { await loadFamilyState() }
        }
    }

    private var headerText: String {
        let base = lang.isZh ? "双人计划" : "DUO PLAN"
        switch familyState {
        case .active: return "\(base) · \(lang.isZh ? "已激活" : "ACTIVE")"
        case .pending: return "\(base) · \(lang.isZh ? "邀请中" : "PENDING")"
        default: return "\(base) · \(lang.isZh ? "未开通" : "INACTIVE")"
        }
    }

    private func loadFamilyState() async {
        struct Resp: Decodable {
            let role: String?
            let partner_email: String?
            let partner_name: String?
            let invite_pending: Bool
            let pending_invite_email: String?
        }
        do {
            let resp: Resp = try await APIClient.shared.request("GET", "/family/status")
            if let partnerName = resp.partner_name, let partnerEmail = resp.partner_email {
                familyState = .active(
                    partnerName: partnerName,
                    partnerEmail: partnerEmail,
                    iAmPayer: resp.role == "payer"
                )
            } else if resp.invite_pending {
                familyState = .pending(email: resp.pending_invite_email ?? "")
            } else {
                familyState = .none
            }
        } catch {
            familyState = .none
        }
    }
}
