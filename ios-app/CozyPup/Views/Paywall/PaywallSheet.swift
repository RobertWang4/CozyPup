import SwiftUI
import StoreKit

struct PaywallSheet: View {
    @EnvironmentObject var subscriptionStore: SubscriptionStore
    let isHard: Bool
    var onDismiss: (() -> Void)? = nil

    @State private var selectedTier: PlanTier = .monthly
    @State private var isDuo = false
    @State private var errorMessage: String?

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
                FallbackPlan(tier: .weekly, price: "$2.99", period: "/wk", periodLong: "per week", tagline: "Start small, try it out", badge: nil, productId: "com.cozypup.app.weekly.duo"),
                FallbackPlan(tier: .monthly, price: "$9.99", period: "/mo", periodLong: "per month", tagline: "Our most chosen plan", badge: "SAVE 19%", productId: "com.cozypup.app.monthly.duo"),
                FallbackPlan(tier: .yearly, price: "$89.99", period: "/yr", periodLong: "per year", tagline: "Best long-term value", badge: "SAVE 29%", productId: "com.cozypup.app.yearly.duo"),
            ]
        }
        return [
            FallbackPlan(tier: .weekly, price: "$1.99", period: "/wk", periodLong: "per week", tagline: "Start small, try it out", badge: nil, productId: "com.cozypup.app.weekly"),
            FallbackPlan(tier: .monthly, price: "$6.99", period: "/mo", periodLong: "per month", tagline: "Our most chosen plan", badge: "SAVE 19%", productId: "com.cozypup.app.monthly"),
            FallbackPlan(tier: .yearly, price: "$59.99", period: "/yr", periodLong: "per year", tagline: "Best long-term value", badge: "SAVE 29%", productId: "com.cozypup.app.yearly"),
        ]
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
                        Text("👑")
                            .font(.system(size: 32))
                            .padding(.bottom, Tokens.spacing.xs)

                        (
                            Text("For the love of\n").foregroundColor(Tokens.text) +
                            Text("your best friend.").foregroundColor(Tokens.accent).italic()
                        )
                        .font(Tokens.fontTitle.weight(.medium))
                        .lineSpacing(2)

                        Text("Every meal, every vet visit, every worry — handled by a pet-care companion that actually listens.")
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
                            statBubble(value: stats.chat_count, label: "chats", color: Tokens.accent)
                            statBubble(value: stats.reminder_count, label: "reminders", color: Tokens.blue)
                            statBubble(value: stats.event_count, label: "records", color: Tokens.green)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.bottom, Tokens.spacing.lg)
                    }

                    // ───── Benefits (2x2 grid) ─────
                    VStack(spacing: Tokens.spacing.sm) {
                        HStack(spacing: Tokens.spacing.md) {
                            benefit("Unlimited AI")
                            benefit("Smart reminders")
                        }
                        HStack(spacing: Tokens.spacing.md) {
                            benefit("Vet search")
                            benefit("First-aid help")
                        }
                    }
                    .padding(.bottom, Tokens.spacing.lg)

                    // ───── Individual/Duo segmented toggle ─────
                    HStack(spacing: 0) {
                        tabButton("Individual", icon: "person.fill", isActive: !isDuo) {
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) { isDuo = false }
                        }
                        tabButton("Duo", icon: "person.2.fill", isActive: isDuo) {
                            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) { isDuo = true }
                        }
                    }
                    .padding(3)
                    .background(Tokens.surface2)
                    .cornerRadius(100)
                    .padding(.bottom, Tokens.spacing.md)

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
                        let targetId = fallbackPlans.first { $0.tier == selectedTier }?.productId ?? ""
                        guard let product = subscriptionStore.products.first(where: { $0.id == targetId }) else {
                            errorMessage = "Product not available yet. Please try again."
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
                                .fill(Tokens.accent)
                                .shadow(color: Tokens.accent.opacity(0.35), radius: 16, x: 0, y: 8)

                            if subscriptionStore.isPurchasing {
                                ProgressView().tint(Tokens.white)
                            } else {
                                Text("Start Subscription")
                                    .font(Tokens.fontBody.weight(.semibold))
                                    .foregroundColor(Tokens.white)
                            }
                        }
                        .frame(height: 54)
                    }
                    .buttonStyle(.plain)
                    .disabled(subscriptionStore.isPurchasing)
                    .padding(.bottom, Tokens.spacing.sm)

                    // ───── Footer links ─────
                    HStack(spacing: Tokens.spacing.md) {
                        Button {
                            Task { await subscriptionStore.restorePurchases() }
                        } label: {
                            Text("Restore Purchase")
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textTertiary)
                        }
                    }

                    Text("Auto-renewable · Cancel anytime in Settings")
                        .font(Tokens.fontCaption2)
                        .foregroundColor(Tokens.textTertiary)
                        .padding(.top, Tokens.spacing.xs)

                    if !isHard {
                        Button { onDismiss?() } label: {
                            Text("Not now")
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
            await subscriptionStore.loadProducts()
            if isHard {
                await subscriptionStore.loadTrialStats()
            }
        }
    }

    // MARK: - Plan Card

    private func planCard(plan: FallbackPlan, isSelected: Bool, isRecommended: Bool, displayPrice: String) -> some View {
        ZStack(alignment: .topLeading) {
            // Card body
            HStack(spacing: Tokens.spacing.md) {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: Tokens.spacing.xs) {
                        Text(plan.tier.rawValue.capitalized)
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

            // "MOST POPULAR" ribbon
            if isRecommended {
                Text("MOST POPULAR")
                    .font(Tokens.fontCaption2.weight(.bold))
                    .foregroundColor(Tokens.white)
                    .tracking(0.8)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Tokens.text)
                    .cornerRadius(10)
                    .offset(x: 16, y: -8)
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
