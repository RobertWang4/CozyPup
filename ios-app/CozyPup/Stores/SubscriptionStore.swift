import SwiftUI
import StoreKit

enum SubscriptionStatus: Equatable {
    case loading
    case trial(daysLeft: Int)
    case active
    case expired
}

struct TrialStats: Decodable {
    let chat_count: Int
    let reminder_count: Int
    let event_count: Int
}

@MainActor
class SubscriptionStore: ObservableObject {
    @Published var status: SubscriptionStatus = .loading
    @Published var products: [Product] = []
    @Published var trialStats: TrialStats?
    @Published var isPurchasing = false

    static let productIDs = ["com.cozypup.app.monthly", "com.cozypup.app.yearly"]

    private var transactionListener: Task<Void, Never>?

    init() {
        transactionListener = listenForTransactions()
    }

    deinit {
        transactionListener?.cancel()
    }

    // MARK: - Load

    func loadStatus() async {
        struct StatusResp: Decodable {
            let status: String
            let trial_days_left: Int?
            let expires_at: String?
        }
        do {
            let resp: StatusResp = try await APIClient.shared.request("GET", "/subscription/status")
            switch resp.status {
            case "trial":
                status = .trial(daysLeft: resp.trial_days_left ?? 7)
            case "active":
                status = .active
            default:
                status = .expired
            }
        } catch {
            await checkStoreKitEntitlements()
        }
    }

    func loadProducts() async {
        do {
            products = try await Product.products(for: Self.productIDs)
                .sorted { $0.price < $1.price }
        } catch {
            print("[Subscription] Failed to load products: \(error)")
        }
    }

    func loadTrialStats() async {
        do {
            trialStats = try await APIClient.shared.request("GET", "/subscription/trial-stats")
        } catch {
            print("[Subscription] Failed to load trial stats: \(error)")
        }
    }

    // MARK: - Purchase

    func purchase(_ product: Product) async throws {
        isPurchasing = true
        defer { isPurchasing = false }

        let result = try await product.purchase()
        switch result {
        case .success(let verification):
            let transaction = try checkVerified(verification)
            await verifyWithBackend(transactionID: String(transaction.id), productID: product.id)
            await transaction.finish()
            status = .active
        case .userCancelled:
            break
        case .pending:
            break
        @unknown default:
            break
        }
    }

    func restorePurchases() async {
        try? await AppStore.sync()
        await checkStoreKitEntitlements()
    }

    // MARK: - Private

    private func listenForTransactions() -> Task<Void, Never> {
        Task.detached {
            for await result in Transaction.updates {
                if let transaction = try? self.checkVerified(result) {
                    await self.verifyWithBackend(
                        transactionID: String(transaction.id),
                        productID: transaction.productID
                    )
                    await transaction.finish()
                    await MainActor.run { self.status = .active }
                }
            }
        }
    }

    private func checkStoreKitEntitlements() async {
        for await result in Transaction.currentEntitlements {
            if let _ = try? checkVerified(result) {
                status = .active
                return
            }
        }
    }

    nonisolated private func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .unverified:
            throw StoreError.verificationFailed
        case .verified(let value):
            return value
        }
    }

    private func verifyWithBackend(transactionID: String, productID: String) async {
        struct VerifyBody: Encodable {
            let transaction_id: String
            let product_id: String
        }
        struct VerifyResp: Decodable {
            let status: String
            let expires_at: String?
        }
        do {
            let _: VerifyResp = try await APIClient.shared.request(
                "POST", "/subscription/verify",
                body: VerifyBody(transaction_id: transactionID, product_id: productID)
            )
        } catch {
            print("[Subscription] Backend verify failed: \(error)")
        }
    }

    enum StoreError: Error {
        case verificationFailed
    }
}
