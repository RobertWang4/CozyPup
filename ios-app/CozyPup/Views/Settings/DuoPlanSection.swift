import SwiftUI

/// Section of the Profile sheet showing Duo Plan state.
///
/// State machine — derived from `/family/status` plus `subscriptionStore.isDuo`:
/// 1. Active: has partner → friend row (subtitle "Member" if payer, "Paid by" if member)
/// 2. Pending: payer sent invite, not yet accepted → "Invite pending" row
/// 3. NoPartnerYet: isDuo=true but no partner and no pending → "Invite a partner" row
/// 4. Upgrade: no Duo subscription → "Upgrade to Duo Plan" row opening paywall
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
        case noPartnerYet
        case upgrade
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

            case .noPartnerYet:
                Button { showFamilySettings = true } label: {
                    HStack(spacing: Tokens.spacing.sm) {
                        Image(systemName: "person.badge.plus")
                            .foregroundColor(Tokens.accent)
                            .frame(width: Tokens.size.avatarSmall)
                        VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                            Text(lang.isZh ? "邀请伙伴" : "Invite a partner")
                                .font(Tokens.fontBody)
                                .foregroundColor(Tokens.text)
                            Text(lang.isZh ? "把双人计划分享给一个人" : "Share Duo Plan with one person")
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

            case .upgrade:
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
        case .noPartnerYet: return "\(base) · \(lang.isZh ? "已激活" : "ACTIVE")"
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
            } else if subscriptionStore.isDuo {
                familyState = .noPartnerYet
            } else {
                familyState = .upgrade
            }
        } catch {
            familyState = subscriptionStore.isDuo ? .noPartnerYet : .upgrade
        }
    }
}
