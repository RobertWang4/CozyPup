import SwiftUI
import StoreKit

struct PaywallSheet: View {
    @EnvironmentObject var subscriptionStore: SubscriptionStore
    @ObservedObject private var lang = Lang.shared
    let isHard: Bool
    var initialDuo: Bool = false
    var onDismiss: (() -> Void)? = nil

    @State private var selectedTier: PlanTier = .monthly
    @State private var isDuo = false
    @State private var errorMessage: String?
    @State private var showManageConfirm = false

    enum PlanTier: String, CaseIterable {
        case weekly, monthly, yearly
    }

    private struct FallbackPlan {
        let tier: PlanTier
        let price: String
        let period: String
        let periodLong: String
        let tagline: String
        let badge: String?
        let productId: String
    }

    private var fallbackPlans: [FallbackPlan] {
        if isDuo {
            return [
                FallbackPlan(tier: .weekly, price: "$2.99", period: "/wk", periodLong: L.paywallPerWeek, tagline: L.paywallTaglineWeekly, badge: nil, productId: "com.cozypup.app.weekly.duo"),
                FallbackPlan(tier: .monthly, price: "$9.99", period: "/mo", periodLong: L.paywallPerMonth, tagline: L.paywallTaglineMonthly, badge: L.paywallSave19, productId: "com.cozypup.app.monthly.duo"),
                FallbackPlan(tier: .yearly, price: "$89.99", period: "/yr", periodLong: L.paywallPerYear, tagline: L.paywallTaglineYearly, badge: L.paywallSave29, productId: "com.cozypup.app.yearly.duo"),
            ]
        }
        return [
            FallbackPlan(tier: .weekly, price: "$1.99", period: "/wk", periodLong: L.paywallPerWeek, tagline: L.paywallTaglineWeekly, badge: nil, productId: "com.cozypup.app.weekly"),
            FallbackPlan(tier: .monthly, price: "$6.99", period: "/mo", periodLong: L.paywallPerMonth, tagline: L.paywallTaglineMonthly, badge: L.paywallSave19, productId: "com.cozypup.app.monthly"),
            FallbackPlan(tier: .yearly, price: "$59.99", period: "/yr", periodLong: L.paywallPerYear, tagline: L.paywallTaglineYearly, badge: L.paywallSave29, productId: "com.cozypup.app.yearly"),
        ]
    }

    private func planTitle(_ tier: PlanTier) -> String {
        switch tier {
        case .weekly: return L.paywallPlanWeekly
        case .monthly: return L.paywallPlanMonthly
        case .yearly: return L.paywallPlanYearly
        }
    }

    private func storeProduct(for plan: FallbackPlan) -> Product? {
        subscriptionStore.products.first { $0.id == plan.productId }
    }

    var body: some View {
        ZStack(alignment: .topTrailing) {
            // Background + decorative radial
            Tokens.bg.ignoresSafeArea()

            Circle()
                .fill(
                    RadialGradient(
                        colors: [Tokens.accentSoft, .clear],
                        center: .center,
                        startRadius: 10,
                        endRadius: 180
                    )
                )
                .frame(width: 280, height: 280)
                .offset(x: 80, y: -60)
                .allowsHitTesting(false)

            ScrollView(showsIndicators: false) {
                VStack(spacing: 0) {
                    // Drag handle
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Tokens.border)
                        .frame(width: 36, height: 4)
                        .padding(.top, Tokens.spacing.sm)
                        .padding(.bottom, Tokens.spacing.md)

                    // ───── Headline ─────
                    VStack(alignment: .leading, spacing: Tokens.spacing.xs) {
                        Image("logo")
                            .resizable()
                            .scaledToFit()
                            .frame(width: 48, height: 48)
                            .padding(.bottom, Tokens.spacing.xs)

                        (
                            Text(L.paywallHeadline1).foregroundColor(Tokens.text) +
                            Text(L.paywallHeadline2).foregroundColor(Tokens.accent).italic()
                        )
                        .font(Tokens.fontTitle.weight(.medium))
                        .lineSpacing(2)

                        Text(L.paywallSubtitle)
                            .font(Tokens.fontSubheadline)
                            .foregroundColor(Tokens.textSecondary)
                            .lineSpacing(2)
                            .padding(.top, Tokens.spacing.xs)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.bottom, Tokens.spacing.lg)

                    // Hard paywall stats
                    if isHard, let stats = subscriptionStore.trialStats {
                        HStack(spacing: Tokens.spacing.xl) {
                            statBubble(value: stats.chat_count, label: L.paywallStatChats, color: Tokens.accent)
                            statBubble(value: stats.reminder_count, label: L.paywallStatReminders, color: Tokens.blue)
                            statBubble(value: stats.event_count, label: L.paywallStatRecords, color: Tokens.green)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.bottom, Tokens.spacing.lg)
                    }

                    // ───── Benefits (2x2 grid) ─────
                    VStack(spacing: Tokens.spacing.sm) {
                        HStack(spacing: Tokens.spacing.md) {
                            benefit(L.paywallBenefitUnlimited)
                            benefit(L.paywallBenefitReminders)
                        }
                        HStack(spacing: Tokens.spacing.md) {
                            benefit(L.paywallBenefitVetSearch)
                            benefit(L.paywallBenefitFirstAid)
                        }
                    }
                    .padding(.bottom, Tokens.spacing.lg)

                    // ───── Individual/Duo segmented toggle ─────
                    HStack(spacing: 0) {
                        tabButton(L.paywallTabIndividual, icon: "person.fill", isActive: !isDuo) {
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) { isDuo = false }
                        }
                        tabButton(L.paywallTabDuo, icon: "person.2.fill", isActive: isDuo) {
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) { isDuo = true }
                        }
                    }
                    .padding(3)
                    .background(Tokens.surface2)
                    .cornerRadius(100)
                    .padding(.bottom, Tokens.spacing.sm)

                    // Plan mode hint (single line under toggle)
                    HStack(spacing: 6) {
                        Image(systemName: isDuo ? "heart.fill" : "sparkles")
                            .font(.system(size: 11))
                            .foregroundColor(Tokens.accent)
                        Text(isDuo ? L.paywallDuoHint : L.paywallIndividualHint)
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.bottom, Tokens.spacing.md)
                    .transition(.opacity)
                    .id(isDuo)

                    // ───── Price cards ─────
                    VStack(spacing: Tokens.spacing.sm) {
                        ForEach(fallbackPlans, id: \.tier) { plan in
                            let isSelected = selectedTier == plan.tier
                            let product = storeProduct(for: plan)
                            let displayPrice = product?.displayPrice ?? plan.price
                            let isRecommended = plan.tier == .monthly

                            planCard(plan: plan, isSelected: isSelected, isRecommended: isRecommended, displayPrice: displayPrice)
                                .contentShape(Rectangle())
                                .onTapGesture {
                                    withAnimation(.spring(response: 0.3, dampingFraction: 0.85)) {
                                        selectedTier = plan.tier
                                    }
                                }
                        }
                    }
                    .padding(.bottom, Tokens.spacing.md)

                    // Error
                    if let errorMessage {
                        Text(errorMessage)
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.red)
                            .padding(.bottom, Tokens.spacing.sm)
                    }

                    // ───── Subscribe button ─────
                    Button {
                        guard buttonEnabled else { return }
                        let targetId = selectedProductId
                        guard let product = subscriptionStore.products.first(where: { $0.id == targetId }) else {
                            errorMessage = L.paywallProductUnavailable
                            return
                        }
                        Task {
                            do {
                                try await subscriptionStore.purchase(product)
                                onDismiss?()
                            } catch {
                                errorMessage = error.localizedDescription
                            }
                        }
                    } label: {
                        ZStack {
                            RoundedRectangle(cornerRadius: 18)
                                .fill(buttonEnabled ? Tokens.accent : Tokens.textTertiary.opacity(0.35))
                                .shadow(
                                    color: buttonEnabled ? Tokens.accent.opacity(0.35) : .clear,
                                    radius: 16, x: 0, y: 8
                                )

                            if subscriptionStore.isPurchasing {
                                ProgressView().tint(Tokens.white)
                            } else {
                                Text(buttonLabel)
                                    .font(Tokens.fontBody.weight(.semibold))
                                    .foregroundColor(Tokens.white)
                            }
                        }
                        .frame(height: 54)
                    }
                    .buttonStyle(.plain)
                    .disabled(subscriptionStore.isPurchasing || !buttonEnabled)
                    .padding(.bottom, Tokens.spacing.sm)

                    // ───── Footer links ─────
                    HStack(spacing: Tokens.spacing.md) {
                        Button {
                            Task { await subscriptionStore.restorePurchases() }
                        } label: {
                            Text(L.paywallRestore)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary)
                        }

                        Text("·")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)

                        Button {
                            showManageConfirm = true
                        } label: {
                            Text(lang.isZh ? "在 App Store 管理" : "Manage on App Store")
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary)
                        }
                    }

                    Text(L.paywallAutoRenew)
                        .font(Tokens.fontCaption2)
                        .foregroundColor(Tokens.textTertiary)
                        .padding(.top, Tokens.spacing.xs)

                    if !isHard {
                        Button { onDismiss?() } label: {
                            Text(L.paywallNotNow)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary)
                        }
                        .padding(.top, Tokens.spacing.sm)
                    }

                    Spacer().frame(height: Tokens.spacing.lg)
                }
                .padding(.horizontal, Tokens.spacing.md)
            }

            // Close button (floating top-right)
            if !isHard {
                Button { onDismiss?() } label: {
                    Image(systemName: "xmark")
                        .font(Tokens.fontSubheadline.weight(.semibold))
                        .foregroundColor(Tokens.textSecondary)
                        .frame(width: 32, height: 32)
                        .background(Tokens.surface)
                        .clipShape(Circle())
                }
                .padding(.top, Tokens.spacing.md)
                .padding(.trailing, Tokens.spacing.md)
            }
        }
        .task {
            isDuo = initialDuo
            await subscriptionStore.loadProducts()
            if isHard {
                await subscriptionStore.loadTrialStats()
            }
            // If the user already has a subscription, pre-select its tab+tier
            // so the first render shows "Current Plan" on the right row.
            if let currentId = subscriptionStore.currentProductId, !currentId.isEmpty {
                isDuo = currentId.hasSuffix(".duo")
                if currentId.contains("weekly") { selectedTier = .weekly }
                else if currentId.contains("yearly") { selectedTier = .yearly }
                else { selectedTier = .monthly }
            }
        }
        .alert(
            lang.isZh ? "离开 CozyPup？" : "Leave CozyPup?",
            isPresented: $showManageConfirm
        ) {
            Button(lang.isZh ? "取消" : "Cancel", role: .cancel) {}
            Button(lang.isZh ? "继续" : "Continue") {
                if let url = URL(string: "itms-apps://apps.apple.com/account/subscriptions") {
                    UIApplication.shared.open(url)
                }
            }
        } message: {
            Text(lang.isZh
                ? "将跳转到 App Store 的订阅管理页面。"
                : "You'll be taken to the App Store subscription management page.")
        }
    }

    // MARK: - Button state

    private enum SubscribeButtonState {
        case subscribe   // no current sub → normal "Start Subscription"
        case current     // selected plan == current → disabled "Current Plan"
        case upgrade     // selected plan > current → enabled "Upgrade"
        case downgrade   // selected plan < current → disabled "Switch to lower"
    }

    private var selectedProductId: String {
        fallbackPlans.first { $0.tier == selectedTier }?.productId ?? ""
    }

    /// Rank all products by value. Higher rank = "bigger" subscription.
    /// Individual tier < Duo tier; within tier: weekly < monthly < yearly.
    private func planRank(_ productId: String) -> Int {
        switch productId {
        case "com.cozypup.app.weekly":      return 1
        case "com.cozypup.app.monthly":     return 2
        case "com.cozypup.app.yearly":      return 3
        case "com.cozypup.app.weekly.duo":  return 4
        case "com.cozypup.app.monthly.duo": return 5
        case "com.cozypup.app.yearly.duo":  return 6
        default: return 0
        }
    }

    private var buttonState: SubscribeButtonState {
        guard let currentId = subscriptionStore.currentProductId, !currentId.isEmpty else {
            return .subscribe
        }
        let selected = planRank(selectedProductId)
        let current = planRank(currentId)
        if selected == 0 || current == 0 { return .subscribe }
        if selected == current { return .current }
        if selected > current { return .upgrade }
        return .downgrade
    }

    private var buttonLabel: String {
        switch buttonState {
        case .subscribe: return L.paywallStartSubscription
        case .current:   return lang.isZh ? "当前订阅" : "Current Plan"
        case .upgrade:   return lang.isZh ? "升级" : "Upgrade"
        case .downgrade: return lang.isZh ? "降级" : "Downgrade"
        }
    }

    private var buttonEnabled: Bool {
        switch buttonState {
        case .subscribe, .upgrade: return true
        case .current, .downgrade: return false
        }
    }

    // MARK: - Plan Card

    private func planCard(plan: FallbackPlan, isSelected: Bool, isRecommended: Bool, displayPrice: String) -> some View {
        let isCurrent = subscriptionStore.currentProductId == plan.productId
        return ZStack(alignment: .topLeading) {
            // Card body
            HStack(spacing: Tokens.spacing.md) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: Tokens.spacing.xs) {
                        Text(planTitle(plan.tier))
                            .font(Tokens.fontTitle.weight(.semibold))
                            .foregroundColor(Tokens.text)
                        if let badge = plan.badge {
                            Text(badge)
                                .font(Tokens.fontCaption2.weight(.bold))
                                .foregroundColor(Tokens.white)
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(isRecommended ? Tokens.accent : Tokens.green)
                                .cornerRadius(5)
                                .offset(y: -2)
                        }
                    }
                    Text(plan.tagline)
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 0) {
                    Text(displayPrice)
                        .font(Tokens.fontTitle.weight(.bold))
                        .foregroundColor(Tokens.text)
                    Text(plan.periodLong)
                        .font(Tokens.fontCaption2)
                        .foregroundColor(Tokens.textTertiary)
                }
            }
            .padding(.horizontal, Tokens.spacing.md)
            .padding(.vertical, 16)
            .padding(.top, isRecommended ? 4 : 0)
            .background(isSelected ? Tokens.accentSoft : Tokens.surface)
            .overlay(
                RoundedRectangle(cornerRadius: 18)
                    .stroke(isSelected ? Tokens.accent : Tokens.border, lineWidth: isSelected ? 2 : 1)
            )
            .cornerRadius(18)
            .shadow(
                color: isSelected ? Tokens.accent.opacity(0.18) : .clear,
                radius: 16, x: 0, y: 8
            )

            // "MOST POPULAR" ribbon (left)
            if isRecommended && !isCurrent {
                Text(L.paywallMostPopular)
                    .font(Tokens.fontCaption2.weight(.bold))
                    .foregroundColor(Tokens.white)
                    .tracking(0.8)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Tokens.text)
                    .cornerRadius(10)
                    .offset(x: 16, y: -8)
            }

            // "当前订阅" badge (top-right)
            if isCurrent {
                HStack(spacing: 3) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 10, weight: .bold))
                    Text(L.paywallCurrent)
                        .font(Tokens.fontCaption2.weight(.bold))
                        .tracking(0.3)
                }
                .foregroundColor(Tokens.white)
                .padding(.horizontal, 9)
                .padding(.vertical, 4)
                .background(Tokens.green)
                .cornerRadius(10)
                .frame(maxWidth: .infinity, alignment: .trailing)
                .offset(x: -16, y: -8)
            }
        }
    }

    // MARK: - Components

    private func benefit(_ text: String) -> some View {
        HStack(spacing: Tokens.spacing.xs) {
            ZStack {
                Circle()
                    .fill(Tokens.accentSoft)
                    .frame(width: 20, height: 20)
                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(Tokens.accent)
            }
            Text(text)
                .font(Tokens.fontCaption.weight(.medium))
                .foregroundColor(Tokens.text)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            Spacer()
        }
    }

    private func tabButton(_ label: String, icon: String, isActive: Bool, action: @escaping () -> Void) -> some View {
        HStack(spacing: Tokens.spacing.xs) {
            Image(systemName: icon)
                .font(.system(size: 12))
            Text(label)
                .font(Tokens.fontSubheadline.weight(.semibold))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 11)
        .background(
            Group {
                if isActive {
                    Tokens.surface
                        .cornerRadius(100)
                        .shadow(color: .black.opacity(0.06), radius: 6, y: 2)
                } else {
                    Color.clear
                }
            }
        )
        .foregroundColor(isActive ? Tokens.text : Tokens.textSecondary)
        .contentShape(Rectangle())
        .onTapGesture { action() }
    }

    private func statBubble(value: Int, label: String, color: Color) -> some View {
        VStack(spacing: Tokens.spacing.xxs) {
            Text("\(value)")
                .font(Tokens.fontTitle.weight(.bold))
                .foregroundColor(color)
            Text(label)
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textSecondary)
        }
    }
}

#Preview("Soft") {
    PaywallSheet(isHard: false)
        .environmentObject(SubscriptionStore())
        .presentationDetents([.large])
}

#Preview("Hard") {
    PaywallSheet(isHard: true)
        .environmentObject(SubscriptionStore())
        .presentationDetents([.large])
}
