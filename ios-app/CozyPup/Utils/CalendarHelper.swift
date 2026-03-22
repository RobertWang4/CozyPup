import Foundation

struct CalendarDay: Identifiable {
    let id = UUID()
    let date: Int
    let month: Int
    let year: Int
    let isCurrentMonth: Bool
    let isToday: Bool
}

enum CalendarHelper {
    private static var isZh: Bool {
        (UserDefaults.standard.string(forKey: "cozypup_language") ?? "zh") == "zh"
    }
    static var monthNames: [String] {
        isZh
            ? ["一月", "二月", "三月", "四月", "五月", "六月",
               "七月", "八月", "九月", "十月", "十一月", "十二月"]
            : ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]
    }
    static var weekdays: [String] {
        isZh
            ? ["日", "一", "二", "三", "四", "五", "六"]
            : ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
    }

    static func getCalendarDays(year: Int, month: Int) -> [CalendarDay] {
        let cal = Calendar.current
        let today = Date()
        let todayComps = cal.dateComponents([.year, .month, .day], from: today)

        var comps = DateComponents(year: year, month: month + 1, day: 1)
        guard let first = cal.date(from: comps) else { return [] }
        let startPad = cal.component(.weekday, from: first) - 1

        comps.month = month + 2; comps.day = 0
        guard let last = cal.date(from: comps) else { return [] }
        let daysInMonth = cal.component(.day, from: last)

        comps = DateComponents(year: year, month: month + 1, day: 0)
        let prevLast = cal.date(from: comps).map { cal.component(.day, from: $0) } ?? 28
        let prevMonth = month - 1 < 0 ? 11 : month - 1
        let prevYear = month - 1 < 0 ? year - 1 : year

        var days: [CalendarDay] = []

        for i in stride(from: startPad - 1, through: 0, by: -1) {
            days.append(CalendarDay(date: prevLast - i, month: prevMonth, year: prevYear,
                                    isCurrentMonth: false, isToday: false))
        }

        for d in 1...daysInMonth {
            let isToday = d == todayComps.day && month == (todayComps.month ?? 0) - 1 && year == todayComps.year
            days.append(CalendarDay(date: d, month: month, year: year,
                                    isCurrentMonth: true, isToday: isToday))
        }

        let remaining = 7 - (days.count % 7)
        if remaining < 7 {
            let nextMonth = month + 1 > 11 ? 0 : month + 1
            let nextYear = month + 1 > 11 ? year + 1 : year
            for i in 1...remaining {
                days.append(CalendarDay(date: i, month: nextMonth, year: nextYear,
                                        isCurrentMonth: false, isToday: false))
            }
        }

        return days
    }

    static func dateString(year: Int, month: Int, day: Int) -> String {
        String(format: "%04d-%02d-%02d", year, month + 1, day)
    }
}
