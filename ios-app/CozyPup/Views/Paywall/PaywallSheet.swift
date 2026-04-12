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

    // Fallback prices when StoreKit products haven't loaded
    private struct FallbackPlan {
        let tier: PlanTier
        let price: String
        let period: String
        let badge: String?
        let productId: String
    }

    private var fallbackPlans: [FallbackPlan] {
        if isDuo {
            return [
                FallbackPlan(tier: .weekly, price: "$2.99", period: "/week", badge: nil, productId: "com.cozypup.app.weekly.duo"),
                FallbackPlan(tier: .monthly, price: "$9.99", period: "/month", badge: "Save 19%", productId: "com.cozypup.app.monthly.duo"),
                FallbackPlan(tier: .yearly, price: "$84.99", period: "/year", badge: "Save 29%", productId: "com.cozypup.app.yearly.duo"),
            ]
        }
        return [
            FallbackPlan(tier: .weekly, price: "$1.99", period: "/week", badge: nil, productId: "com.cozypup.app.weekly"),
            FallbackPlan(tier: .monthly, price: "$6.99", period: "/month", badge: "Save 19%", productId: "com.cozypup.app.monthly"),
            FallbackPlan(tier: .yearly, price: "$59.99", period: "/year", badge: "Save 29%", productId: "com.cozypup.app.yearly"),
        ]
    }

    private func storeProduct(for plan: FallbackPlan) -> Product? {
        subscriptionStore.products.first { $0.id == plan.productId }
    }

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(spacing: 0) {
                // Drag handle
                RoundedRectangle(cornerRadius: 2)
                    .fill(Tokens.border)
                    .frame(width: 36, height: 4)
                    .padding(.top, Tokens.spacing.sm)
                    .padding(.bottom, Tokens.spacing.md)

                // Close button
                if !isHard {
                    HStack {
                        Spacer()
                        Button { onDismiss?() } label: {
                            Image(systemName: "xmark")
                                .font(Tokens.fontSubheadline)
                                .foregroundColor(Tokens.textSecondary)
                                .frame(width: 28, height: 28)
                                .background(Tokens.surface)
                                .clipShape(Circle())
                        }
                    }
                    .padding(.bottom, Tokens.spacing.xs)
                }

                // Title
                Text("CozyPup Premium")
                    .font(Tokens.fontTitle)
                    .foregroundColor(Tokens.text)
                    .padding(.bottom, Tokens.spacing.xs)

                // Trial status
                if case .trial(let daysLeft) = subscriptionStore.status {
                    Text("\(daysLeft) days left in trial")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                        .padding(.bottom, Tokens.spacing.sm)
                }

                // Hard paywall stats
                if isHard, let stats = subscriptionStore.trialStats {
                    HStack(spacing: Tokens.spacing.xl) {
                        statBubble(value: stats.chat_count, label: "chats", color: Tokens.accent)
                        statBubble(value: stats.reminder_count, label: "reminders", color: Tokens.blue)
                        statBubble(value: stats.event_count, label: "records", color: Tokens.green)
                    }
                    .padding(.bottom, Tokens.spacing.md)
                }

                // Benefits
                VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                    benefitRow("Unlimited AI chat & health advice")
                    benefitRow("Smart reminders & calendar")
                    benefitRow("Nearby vet clinic search")
                    benefitRow("Emergency first-aid guidance")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.bottom, Tokens.spacing.lg)

                // Individual / Duo toggle
                HStack(spacing: 0) {
                    tabButton("Individual", icon: "person", isActive: !isDuo) {
                        withAnimation(.easeInOut(duration: 0.2)) { isDuo = false }
                    }
                    tabButton("Duo", icon: "person.2", isActive: isDuo) {
                        withAnimation(.easeInOut(duration: 0.2)) { isDuo = true }
                    }
                }
                .background(Tokens.surface2)
                .cornerRadius(Tokens.radiusSmall)
                .padding(.bottom, Tokens.spacing.xs)

                if isDuo {
                    Text("Full access for two people")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                        .padding(.bottom, Tokens.spacing.sm)
                } else {
                    Text("Everything you need")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                        .padding(.bottom, Tokens.spacing.sm)
                }

                // Price cards (vertical)
                VStack(spacing: Tokens.spacing.sm) {
                    ForEach(fallbackPlans, id: \.tier) { plan in
                        let isSelected = selectedTier == plan.tier
                        let product = storeProduct(for: plan)
                        let displayPrice = product?.displayPrice ?? plan.price

                        Button {
                            withAnimation(.easeInOut(duration: 0.15)) { selectedTier = plan.tier }
                        } label: {
                            HStack(spacing: Tokens.spacing.sm) {
                                // Radio indicator
                                Circle()
                                    .strokeBorder(isSelected ? Tokens.accent : Tokens.border, lineWidth: isSelected ? 6 : 1.5)
                                    .frame(width: 22, height: 22)

                                VStack(alignment: .leading, spacing: 2) {
                                    HStack(spacing: Tokens.spacing.xs) {
                                        Text(plan.tier.rawValue.capitalized)
                                            .font(Tokens.fontBody.weight(.semibold))
                                            .foregroundColor(Tokens.text)

                                        if let badge = plan.badge {
                                            Text(badge)
                                                .font(Tokens.fontCaption2.weight(.semibold))
                                                .foregroundColor(Tokens.white)
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(plan.tier == .monthly ? Tokens.accent : Tokens.green)
                                                .cornerRadius(4)
                                        }
                                    }
                                }

                                Spacer()

                                VStack(alignment: .trailing, spacing: 1) {
                                    Text(displayPrice)
                                        .font(Tokens.fontBody.weight(.bold))
                                        .foregroundColor(Tokens.text)
                                    Text(plan.period)
                                        .font(Tokens.fontCaption2)
                                        .foregroundColor(Tokens.textTertiary)
                                }
                            }
                            .padding(.horizontal, Tokens.spacing.md)
                            .padding(.vertical, 14)
                            .background(isSelected ? Tokens.accentSoft : Tokens.surface)
                            .overlay(
                                RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                                    .stroke(isSelected ? Tokens.accent : Tokens.border, lineWidth: isSelected ? 2 : 1)
                            )
                            .cornerRadius(Tokens.radiusSmall)
                        }
                        .buttonStyle(.plain)
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

                // Subscribe button
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
                    if subscriptionStore.isPurchasing {
                        ProgressView()
                            .tint(Tokens.white)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(Tokens.accent.opacity(0.7))
                            .cornerRadius(Tokens.radiusSmall)
                    } else {
                        Text("Subscribe")
                            .font(Tokens.fontBody.weight(.semibold))
                            .foregroundColor(Tokens.white)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 14)
                            .background(Tokens.accent)
                            .cornerRadius(Tokens.radiusSmall)
                    }
                }
                .disabled(subscriptionStore.isPurchasing)
                .padding(.bottom, Tokens.spacing.sm)

                // Restore + cancel anytime
                Button {
                    Task { await subscriptionStore.restorePurchases() }
                } label: {
                    Text("Restore Purchase")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
                .padding(.bottom, Tokens.spacing.xs)

                Text("Auto-renewable. Cancel anytime in Settings.")
                    .font(Tokens.fontCaption2)
                    .foregroundColor(Tokens.textTertiary)

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
        .background(Tokens.bg)
        .task {
            await subscriptionStore.loadProducts()
            if isHard {
                await subscriptionStore.loadTrialStats()
            }
        }
    }

    // MARK: - Components

    private func tabButton(_ label: String, icon: String, isActive: Bool, action: @escaping () -> Void) -> some View {
        HStack(spacing: Tokens.spacing.xs) {
            Image(systemName: icon)
                .font(Tokens.fontCaption)
            Text(label)
                .font(Tokens.fontSubheadline.weight(.medium))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .background(isActive ? Tokens.surface : Color.clear)
        .foregroundColor(isActive ? Tokens.text : Tokens.textTertiary)
        .cornerRadius(Tokens.radiusSmall - 2)
        .contentShape(Rectangle())
        .onTapGesture { action() }
        .padding(3)
    }

    private func benefitRow(_ text: String) -> some View {
        HStack(spacing: Tokens.spacing.sm) {
            Image(systemName: "checkmark")
                .font(Tokens.fontCaption.weight(.bold))
                .foregroundColor(Tokens.accent)
            Text(text)
                .font(Tokens.fontBody)
                .foregroundColor(Tokens.text)
        }
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
