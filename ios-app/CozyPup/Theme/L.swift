import SwiftUI

/// Observable language manager — views re-render smoothly when language changes.
@MainActor
class Lang: ObservableObject {
    static let shared = Lang()

    @AppStorage("cozypup_language") var code: String = Lang.systemDefault {
        didSet { objectWillChange.send() }
    }

    var isZh: Bool { code == "zh" }

    /// iOS system language → "zh" or "en". Used as the default when the
    /// user hasn't explicitly set a language preference.
    nonisolated static var systemDefault: String {
        let pref = Locale.preferredLanguages.first ?? "en"
        return pref.hasPrefix("zh") ? "zh" : "en"
    }
}

/// Convenience accessors for bilingual strings.
enum L {
    private static var z: Bool {
        (UserDefaults.standard.string(forKey: "cozypup_language") ?? Lang.systemDefault) == "zh"
    }

    // Navigation
    static var settings: String { z ? "设置" : "Settings" }
    static var calendar: String { z ? "日历" : "Calendar" }

    // Settings
    static var myPets: String { z ? "我的宠物" : "My Pets" }
    static var addPet: String { z ? "添加宠物" : "Add Pet" }
    static var editPet: String { z ? "编辑宠物" : "Edit Pet" }
    static var language: String { z ? "语言" : "Language" }
    static var responseLang: String { z ? "系统语言" : "System Language" }
    static var syncToAppleCalendar: String { z ? "同步到 Apple 日历" : "Sync to Apple Calendar" }
    static var notifications: String { z ? "通知" : "Notifications" }
    static var pushNotifications: String { z ? "推送通知" : "Push Notifications" }
    static var medReminders: String { z ? "用药提醒" : "Medication Reminders" }
    static var weeklyInsights: String { z ? "每周洞察" : "Weekly Insights" }
    static var privacyPolicy: String { z ? "隐私政策" : "Privacy Policy" }
    static var disclaimer: String { z ? "免责声明" : "Disclaimer" }
    static var about: String { z ? "关于" : "About" }
    static var logOut: String { z ? "退出登录" : "Log Out" }
    static var deletePet: String { z ? "删除宠物？" : "Delete Pet?" }
    static var delete: String { z ? "删除" : "Delete" }
    static var cancel: String { z ? "取消" : "Cancel" }

    // Chat
    static var chatPlaceholder: String { z ? "跟 Cozy Pup 聊聊..." : "Talk to Cozy Pup..." }
    static var welcomeTitle: String { z ? "欢迎来到 Cozy Pup！" : "Welcome to Cozy Pup!" }
    static var welcomeSubtitle: String { z ? "告诉我关于你的宠物吧 — 名字、品种、年龄，任何你想分享的！" : "Tell me about your pet — name, breed, age, anything you'd like to share!" }
    static var askAnything: String { z ? "问 Cozy Pup 任何问题" : "Ask Cozy Pup anything" }
    static var askSubtitle: String { z ? "健康咨询、日记记录、兽医推荐..." : "Health questions, record keeping, vet recommendations..." }
    static var aiDisclaimer: String { z ? "AI 建议仅供参考，紧急情况请就医。" : "AI suggestions are for reference only. In emergencies, see a vet." }
    static var errorMessage: String { z ? "抱歉，出了点问题，请重试。" : "Sorry, something went wrong. Please try again." }
    static var voiceSwipeCancel: String { z ? "上滑取消" : "Swipe up to cancel" }
    static var voiceReleaseCancel: String { z ? "松开取消" : "Release to cancel" }

    // Pet form
    static var name: String { z ? "名字" : "Name" }
    static var species: String { z ? "类型" : "Species" }
    static var dog: String { z ? "狗" : "Dog" }
    static var cat: String { z ? "猫" : "Cat" }
    static var other: String { z ? "其他" : "Other" }
    static var breed: String { z ? "品种" : "Breed" }
    static var birthday: String { z ? "生日" : "Birthday" }
    static var weightKg: String { z ? "体重 (kg)" : "Weight (kg)" }
    static var saveChanges: String { z ? "保存" : "Save Changes" }
    static var namePlaceholder: String { z ? "例如：豆豆" : "e.g. Buddy" }
    static var breedPlaceholder: String { z ? "例如：金毛寻回犬" : "e.g. Golden Retriever" }

    // Categories
    static func category(_ key: String) -> String {
        if !z { return key.capitalized }
        switch key {
        case "daily": return "日常"
        case "diet": return "饮食"
        case "medical": return "医疗"
        case "abnormal": return "异常"
        default: return key
        }
    }
    static var save: String { z ? "保存" : "Save" }
    static var title: String { z ? "标题" : "Title" }
    static var date: String { z ? "日期" : "Date" }
    static var time: String { z ? "时间" : "Time" }

    // Cards
    static var petAdded: String { z ? "宠物已添加" : "Pet Added" }
    static var reminderSet: String { z ? "提醒已设置" : "Reminder Set" }
    static var recordedToCalendar: String { z ? "已记录到日历" : "Recorded to Calendar" }
    static var confirm: String { z ? "确认" : "Confirm" }
    static var actionConfirmed: String { z ? "已执行" : "Done" }
    static var actionCancelled: String { z ? "已取消" : "Cancelled" }
    static var taskDeleted: String { z ? "待办已删除" : "Deleted" }
    static var taskCreated: String { z ? "待办已创建" : "Task Created" }
    static var taskUpdated: String { z ? "待办已更新" : "Task Updated" }
    static var taskTypeRoutine: String { z ? "常规" : "Routine" }
    static var taskTypeSpecial: String { z ? "特殊" : "Special" }
    static func taskDailyTarget(_ n: Int) -> String { z ? "每天\(n)次" : "\(n)x daily" }

    // Timeline
    static var timeline: String { z ? "时间线" : "Timeline" }
    static var noEvents: String { z ? "没有事件" : "No events" }
    static var back: String { z ? "返回" : "Back" }

    // Paywall
    static var paywallHeadline1: String { z ? "爱它的每一天，\n" : "For the love of\n" }
    static var paywallHeadline2: String { z ? "都有人替你操心。" : "your best friend." }
    static var paywallSubtitle: String {
        z ? "从吃饭到看病，那些你放不下的小事，它都替你记着 —— 你只管好好陪它。"
          : "Every meal, every vet visit, every worry — handled by a pet-care companion that actually listens."
    }
    static var paywallBenefitUnlimited: String { z ? "无限次聊天" : "Unlimited AI" }
    static var paywallBenefitReminders: String { z ? "智能提醒" : "Smart reminders" }
    static var paywallBenefitVetSearch: String { z ? "就近找医院" : "Vet search" }
    static var paywallBenefitFirstAid: String { z ? "紧急急救" : "First-aid help" }
    static var paywallTabIndividual: String { z ? "一个人" : "Individual" }
    static var paywallTabDuo: String { z ? "两个人" : "Duo" }
    static var paywallDuoHint: String {
        z ? "一份订阅两人用 —— 邀请 TA 一起养"
          : "Full access for two — invite your partner by email"
    }
    static var paywallIndividualHint: String {
        z ? "所有功能，都给你一个人用" : "Everything you need, just for you"
    }
    static var paywallPlanWeekly: String { z ? "周卡" : "Weekly" }
    static var paywallPlanMonthly: String { z ? "月卡" : "Monthly" }
    static var paywallPlanYearly: String { z ? "年卡" : "Yearly" }
    static var paywallTaglineWeekly: String { z ? "先试试水" : "Start small, try it out" }
    static var paywallTaglineMonthly: String { z ? "大家都选这个" : "Our most chosen plan" }
    static var paywallTaglineYearly: String { z ? "长期最划算" : "Best long-term value" }
    static var paywallPerWeek: String { z ? "每周" : "per week" }
    static var paywallPerMonth: String { z ? "每月" : "per month" }
    static var paywallPerYear: String { z ? "每年" : "per year" }
    static var paywallSave19: String { z ? "省 19%" : "SAVE 19%" }
    static var paywallSave29: String { z ? "省 29%" : "SAVE 29%" }
    static var paywallMostPopular: String { z ? "最热门" : "MOST POPULAR" }
    static var paywallCurrent: String { z ? "当前订阅" : "Current Plan" }
    static var paywallStartSubscription: String { z ? "立即订阅" : "Start Subscription" }
    static var paywallRestore: String { z ? "恢复购买" : "Restore Purchase" }
    static var paywallAutoRenew: String {
        z ? "自动续费 · 随时在设置里取消" : "Auto-renewable · Cancel anytime in Settings"
    }
    static var paywallNotNow: String { z ? "以后再说" : "Not now" }
    static var paywallStatChats: String { z ? "聊天" : "chats" }
    static var paywallStatReminders: String { z ? "提醒" : "reminders" }
    static var paywallStatRecords: String { z ? "记录" : "records" }
    static var paywallProductUnavailable: String {
        z ? "还没加载好，请稍后再试。" : "Product not available yet. Please try again."
    }
}
