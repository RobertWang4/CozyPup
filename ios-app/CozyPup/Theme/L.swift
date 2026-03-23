import SwiftUI

/// Observable language manager — views re-render smoothly when language changes.
@MainActor
class Lang: ObservableObject {
    static let shared = Lang()

    @AppStorage("cozypup_language") var code: String = "zh" {
        didSet { objectWillChange.send() }
    }

    var isZh: Bool { code == "zh" }
}

/// Convenience accessors for bilingual strings.
enum L {
    private static var z: Bool {
        (UserDefaults.standard.string(forKey: "cozypup_language") ?? "zh") == "zh"
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
        case "diet": return "饮食"
        case "excretion": return "排泄"
        case "abnormal": return "异常"
        case "vaccine": return "疫苗"
        case "deworming": return "驱虫"
        case "medical": return "就医"
        case "daily": return "日常"
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

    // Timeline
    static var timeline: String { z ? "时间线" : "Timeline" }
    static var noEvents: String { z ? "没有事件" : "No events" }
    static var back: String { z ? "返回" : "Back" }
}
