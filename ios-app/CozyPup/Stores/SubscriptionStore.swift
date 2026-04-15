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
    @Published var isDuo: Bool = false
    @Published var currentProductId: String?

    static let productIDs = [
        "com.cozypup.app.weekly", "com.cozypup.app.monthly", "com.cozypup.app.yearly",
        "com.cozypup.app.weekly.duo", "com.cozypup.app.monthly.duo", "com.cozypup.app.yearly.duo",
    ]

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
            let product_id: String?
            let is_duo: Bool?
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
            currentProductId = resp.product_id
            isDuo = resp.is_duo ?? false
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
            let jws = jwsRepresentation(from: verification)
            await verifyWithBackend(signedTransaction: jws)
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
                    let jws = self.jwsRepresentation(from: result)
                    await self.verifyWithBackend(signedTransaction: jws)
                    await transaction.finish()
                    await MainActor.run { self.status = .active }
                }
            }
        }
    }

    nonisolated private func jwsRepresentation(from result: VerificationResult<StoreKit.Transaction>) -> String {
        result.jwsRepresentation
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

    private func verifyWithBackend(signedTransaction: String) async {
        struct VerifyBody: Encodable {
            let signed_transaction: String
            let sandbox: Bool
        }
        struct VerifyResp: Decodable {
            let status: String
            let expires_at: String?
        }
        #if DEBUG
        let isSandbox = true
        #else
        let isSandbox = false
        #endif
        do {
            let _: VerifyResp = try await APIClient.shared.request(
                "POST", "/subscription/verify",
                body: VerifyBody(signed_transaction: signedTransaction, sandbox: isSandbox)
            )
        } catch {
            print("[Subscription] Backend verify failed: \(error)")
        }
    }

    enum StoreError: Error {
        case verificationFailed
    }
}
