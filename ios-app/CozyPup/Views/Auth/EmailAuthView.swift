import SwiftUI

struct EmailAuthView: View {
    @EnvironmentObject var auth: AuthStore
    @Environment(\.dismiss) var dismiss

    @State private var isRegister = false
    @State private var email = ""
    @State private var password = ""
    @State private var name = ""
    @State private var showPhoneVerify = false

    var body: some View {
        NavigationStack {
            VStack(spacing: Tokens.spacing.lg) {
                Picker("", selection: $isRegister) {
                    Text("登录").tag(false)
                    Text("注册").tag(true)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, Tokens.spacing.md)

                VStack(spacing: Tokens.spacing.md) {
                    if isRegister {
                        TextField("名字（可选）", text: $name)
                            .textFieldStyle(.roundedBorder)
                            .textContentType(.name)
                    }

                    TextField("邮箱", text: $email)
                        .textFieldStyle(.roundedBorder)
                        .textContentType(.emailAddress)
                        .autocapitalization(.none)
                        .keyboardType(.emailAddress)

                    SecureField("密码", text: $password)
                        .textFieldStyle(.roundedBorder)
                        .textContentType(isRegister ? .newPassword : .password)
                }
                .padding(.horizontal, Tokens.spacing.md)

                if let error = auth.errorMessage {
                    Text(error)
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.red)
                }

                Button {
                    Haptics.light()
                    if isRegister {
                        auth.registerWithEmail(email: email, password: password, name: name.isEmpty ? nil : name)
                        showPhoneVerify = true
                    } else {
                        auth.loginWithEmail(email: email, password: password)
                    }
                } label: {
                    Text(isRegister ? "下一步" : "登录")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, Tokens.spacing.md)
                        .background(canSubmit ? Tokens.accent : Tokens.textTertiary)
                        .foregroundColor(Tokens.white)
                        .cornerRadius(Tokens.radiusSmall)
                        .font(Tokens.fontCallout.weight(.semibold))
                }
                .disabled(!canSubmit)
                .padding(.horizontal, Tokens.spacing.md)

                Spacer()
            }
            .padding(.top, Tokens.spacing.lg)
            .background(Tokens.bg.ignoresSafeArea())
            .navigationTitle(isRegister ? "注册" : "登录")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
            }
            .sheet(isPresented: $showPhoneVerify) {
                PhoneVerifyView()
                    .environmentObject(auth)
            }
            .onChange(of: auth.isAuthenticated) { authenticated in
                if authenticated { dismiss() }
            }
        }
    }

    private var canSubmit: Bool {
        !email.isEmpty && password.count >= 6
    }
}
