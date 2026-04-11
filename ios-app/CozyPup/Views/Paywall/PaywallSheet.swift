import SwiftUI
import StoreKit

struct PaywallSheet: View {
    @EnvironmentObject var subscriptionStore: SubscriptionStore
    let isHard: Bool  // true = expired (no dismiss), false = soft (can dismiss)
    var onDismiss: (() -> Void)? = nil

    @State private var selectedProduct: StoreKit.Product?
    @State private var showPricing = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: Tokens.spacing.lg) {
            // Drag handle
            RoundedRectangle(cornerRadius: 2)
                .fill(Tokens.border)
                .frame(width: 36, height: 4)
                .padding(.top, Tokens.spacing.sm)

            if isHard {
                hardPaywallContent
            } else if showPricing {
                pricingContent
            } else {
                softPaywallContent
            }

            Spacer()
        }
        .padding(.horizontal, Tokens.spacing.md)
        .background(Tokens.bg)
        .task {
            if isHard {
                await subscriptionStore.loadTrialStats()
                await subscriptionStore.loadProducts()
            }
        }
    }

    // MARK: - Soft Paywall

    private var softPaywallContent: some View {
        VStack(spacing: Tokens.spacing.md) {
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
            }

            Text("Enjoying CozyPup?")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            if case .trial(let daysLeft) = subscriptionStore.status {
                Text("\(daysLeft) days left in trial")
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.textSecondary)
            }

            VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                benefitRow("Unlimited AI chat & health advice")
                benefitRow("Smart reminders & calendar")
                benefitRow("Nearby vet clinic search")
            }
            .padding(.vertical, Tokens.spacing.sm)

            Button {
                Task {
                    await subscriptionStore.loadProducts()
                }
                withAnimation { showPricing = true }
            } label: {
                Text("View Plans")
                    .font(Tokens.fontBody.weight(.semibold))
                    .foregroundColor(Tokens.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Tokens.accent)
                    .cornerRadius(Tokens.radiusSmall)
            }

            Button { onDismiss?() } label: {
                Text("Not now")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)
            }
        }
    }

    // MARK: - Hard Paywall (Data Recap)

    private var hardPaywallContent: some View {
        VStack(spacing: Tokens.spacing.md) {
            Text("In 7 days, CozyPup helped you")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            if let stats = subscriptionStore.trialStats {
                HStack(spacing: Tokens.spacing.xl) {
                    statBubble(value: stats.chat_count, label: "chats", color: Tokens.accent)
                    statBubble(value: stats.reminder_count, label: "reminders", color: Tokens.blue)
                    statBubble(value: stats.event_count, label: "records", color: Tokens.green)
                }
                .padding(.vertical, Tokens.spacing.sm)
            }

            Text("Keep CozyPup caring for your furry friend 🐶")
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textSecondary)

            pricingContent
        }
    }

    // MARK: - Pricing

    private func tierLabel(for product: StoreKit.Product) -> String {
        if product.id.contains("weekly") { return "Weekly" }
        if product.id.contains("yearly") { return "Yearly" }
        return "Monthly"
    }

    private func savingsBadge(for product: StoreKit.Product) -> String? {
        if product.id.contains("monthly") { return "Save 19%" }
        if product.id.contains("yearly") { return "Save 29%" }
        return nil
    }

    private var pricingContent: some View {
        VStack(spacing: Tokens.spacing.md) {
            HStack(spacing: Tokens.spacing.sm) {
                ForEach(subscriptionStore.products, id: \.id) { product in
                    let isRecommended = product.id.contains("monthly")
                    Button {
                        selectedProduct = product
                    } label: {
                        VStack(spacing: Tokens.spacing.xs) {
                            if let badge = savingsBadge(for: product) {
                                Text(badge)
                                    .font(Tokens.fontCaption2.weight(.semibold))
                                    .foregroundColor(Tokens.white)
                                    .padding(.horizontal, Tokens.spacing.sm)
                                    .padding(.vertical, 2)
                                    .background(isRecommended ? Tokens.accent : Tokens.green)
                                    .cornerRadius(Tokens.spacing.sm)
                            }
                            Text(tierLabel(for: product))
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                            Text(product.displayPrice)
                                .font(Tokens.fontTitle)
                                .foregroundColor(Tokens.text)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Tokens.spacing.md)
                        .background(
                            selectedProduct?.id == product.id
                                ? Tokens.accentSoft
                                : Tokens.surface
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: Tokens.radiusSmall)
                                .stroke(
                                    selectedProduct?.id == product.id
                                        ? Tokens.accent
                                        : Tokens.border,
                                    lineWidth: 1.5
                                )
                        )
                        .cornerRadius(Tokens.radiusSmall)
                    }
                }
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.red)
            }

            Button {
                guard let product = selectedProduct ?? subscriptionStore.products.first(where: { $0.id.contains("monthly") }) ?? subscriptionStore.products.last else { return }
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

            Button {
                Task { await subscriptionStore.restorePurchases() }
            } label: {
                Text("Restore Purchase")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)
            }
        }
    }

    // MARK: - Components

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
        .presentationDetents([.medium])
}

#Preview("Hard") {
    PaywallSheet(isHard: true)
        .environmentObject(SubscriptionStore())
        .presentationDetents([.medium])
}
