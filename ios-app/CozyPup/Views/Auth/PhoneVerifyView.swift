import SwiftUI
import FirebaseAuth

struct PhoneVerifyView: View {
    @EnvironmentObject var auth: AuthStore
    @Environment(\.dismiss) var dismiss

    @State private var phoneNumber = ""
    @State private var verificationCode = ""
    @State private var verificationID: String?
    @State private var codeSent = false
    @State private var error: String?
    @State private var isSending = false

    var body: some View {
        NavigationStack {
            VStack(spacing: Tokens.spacing.lg) {
                Text("绑定手机号")
                    .font(Tokens.fontTitle)
                    .foregroundColor(Tokens.text)

                Text("注册需要验证手机号，用于账号安全")
                    .font(Tokens.fontBody)
                    .foregroundColor(Tokens.textSecondary)
                    .multilineTextAlignment(.center)

                if !codeSent {
                    TextField("手机号（含国际区号，如 +86...）", text: $phoneNumber)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.phonePad)
                        .textContentType(.telephoneNumber)
                        .padding(.horizontal, Tokens.spacing.md)

                    Button {
                        sendCode()
                    } label: {
                        Text(isSending ? "发送中..." : "发送验证码")
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, Tokens.spacing.md)
                            .background(!phoneNumber.isEmpty && !isSending ? Tokens.accent : Tokens.textTertiary)
                            .foregroundColor(Tokens.white)
                            .cornerRadius(Tokens.radiusSmall)
                            .font(Tokens.fontCallout.weight(.semibold))
                    }
                    .disabled(phoneNumber.isEmpty || isSending)
                    .padding(.horizontal, Tokens.spacing.md)
                } else {
                    Text("验证码已发送至 \(phoneNumber)")
                        .font(Tokens.fontSubheadline)
                        .foregroundColor(Tokens.textSecondary)

                    TextField("6位验证码", text: $verificationCode)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.numberPad)
                        .textContentType(.oneTimeCode)
                        .padding(.horizontal, Tokens.spacing.md)

                    Button {
                        verifyCode()
                    } label: {
                        Text("验证并完成注册")
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, Tokens.spacing.md)
                            .background(verificationCode.count == 6 ? Tokens.accent : Tokens.textTertiary)
                            .foregroundColor(Tokens.white)
                            .cornerRadius(Tokens.radiusSmall)
                            .font(Tokens.fontCallout.weight(.semibold))
                    }
                    .disabled(verificationCode.count != 6)
                    .padding(.horizontal, Tokens.spacing.md)

                    Button("重新发送") { sendCode() }
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.accent)
                }

                if let error {
                    Text(error)
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.red)
                }

                Spacer()
            }
            .padding(.top, Tokens.spacing.xl)
            .background(Tokens.bg.ignoresSafeArea())
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
            }
            .onChange(of: auth.isAuthenticated) { authenticated in
                if authenticated { dismiss() }
            }
        }
    }

    private func sendCode() {
        isSending = true
        error = nil

        PhoneAuthProvider.provider().verifyPhoneNumber(phoneNumber, uiDelegate: nil) { id, err in
            isSending = false
            if let err {
                error = err.localizedDescription
            } else {
                verificationID = id
                codeSent = true
            }
        }
    }

    private func verifyCode() {
        guard let verificationID else { return }

        let credential = PhoneAuthProvider.provider().credential(
            withVerificationID: verificationID,
            verificationCode: verificationCode
        )

        Auth.auth().signIn(with: credential) { result, err in
            if let err {
                error = err.localizedDescription
                return
            }
            try? Auth.auth().signOut()
            auth.completeRegistration(phoneNumber: phoneNumber)
        }
    }
}
