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

            Text("喜欢 CozyPup 吗？")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            if case .trial(let daysLeft) = subscriptionStore.status {
                Text("试用还剩 \(daysLeft) 天")
                    .font(Tokens.fontSubheadline)
                    .foregroundColor(Tokens.textSecondary)
            }

            VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                benefitRow("无限 AI 对话 & 健康咨询")
                benefitRow("智能提醒 & 日历管理")
                benefitRow("附近宠物医院搜索")
            }
            .padding(.vertical, Tokens.spacing.sm)

            Button {
                Task {
                    await subscriptionStore.loadProducts()
                }
                withAnimation { showPricing = true }
            } label: {
                Text("查看方案")
                    .font(Tokens.fontBody.weight(.semibold))
                    .foregroundColor(Tokens.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Tokens.accent)
                    .cornerRadius(Tokens.radiusSmall)
            }

            Button { onDismiss?() } label: {
                Text("暂不需要")
                    .font(Tokens.fontCaption)
                    .foregroundColor(Tokens.textTertiary)
            }
        }
    }

    // MARK: - Hard Paywall (Data Recap)

    private var hardPaywallContent: some View {
        VStack(spacing: Tokens.spacing.md) {
            Text("这 7 天，CozyPup 帮你")
                .font(Tokens.fontTitle)
                .foregroundColor(Tokens.text)

            if let stats = subscriptionStore.trialStats {
                HStack(spacing: Tokens.spacing.xl) {
                    statBubble(value: stats.chat_count, label: "次对话", color: Tokens.accent)
                    statBubble(value: stats.reminder_count, label: "个提醒", color: Tokens.blue)
                    statBubble(value: stats.event_count, label: "条记录", color: Tokens.green)
                }
                .padding(.vertical, Tokens.spacing.sm)
            }

            Text("继续让 CozyPup 照顾你的毛孩子 🐶")
                .font(Tokens.fontSubheadline)
                .foregroundColor(Tokens.textSecondary)

            pricingContent
        }
    }

    // MARK: - Pricing

    private var pricingContent: some View {
        VStack(spacing: Tokens.spacing.md) {
            HStack(spacing: Tokens.spacing.sm) {
                ForEach(subscriptionStore.products, id: \.id) { product in
                    let isYearly = product.id.contains("yearly")
                    Button {
                        selectedProduct = product
                    } label: {
                        VStack(spacing: Tokens.spacing.xs) {
                            if isYearly {
                                Text("推荐")
                                    .font(Tokens.fontCaption2.weight(.semibold))
                                    .foregroundColor(Tokens.white)
                                    .padding(.horizontal, Tokens.spacing.sm)
                                    .padding(.vertical, 2)
                                    .background(Tokens.accent)
                                    .cornerRadius(Tokens.spacing.sm)
                            }
                            Text(isYearly ? "年付" : "月付")
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
                guard let product = selectedProduct ?? subscriptionStore.products.last else { return }
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
                    Text("订阅")
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
                Text("恢复购买")
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
