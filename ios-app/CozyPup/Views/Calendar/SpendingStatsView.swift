import SwiftUI

struct SpendingStatsView: View {
    @EnvironmentObject var calendarStore: CalendarStore
    @EnvironmentObject var petStore: PetStore

    @Binding var year: Int
    @Binding var month: Int

    // Computed: events with cost for current month
    private var monthEvents: [CalendarEvent] {
        let prefix = String(format: "%04d-%02d", year, month)
        return calendarStore.events.filter { $0.eventDate.hasPrefix(prefix) && $0.cost != nil && $0.cost! > 0 }
    }

    private var totalCost: Double {
        monthEvents.reduce(0) { $0 + ($1.cost ?? 0) }
    }

    private var categoryBreakdown: [(category: EventCategory, amount: Double, color: Color)] {
        let grouped = Dictionary(grouping: monthEvents) { $0.category }
        var result: [(category: EventCategory, amount: Double, color: Color)] = []
        let cats: [(EventCategory, Color)] = [(.medical, Tokens.accent), (.daily, Tokens.blue), (.diet, Tokens.green), (.abnormal, Tokens.purple)]
        for (cat, color) in cats {
            let sum = grouped[cat]?.reduce(0.0) { $0 + ($1.cost ?? 0) } ?? 0
            if sum > 0 { result.append((cat, sum, color)) }
        }
        return result
    }

    private var dailyBreakdown: [(day: Int, amount: Double)] {
        let cal = Calendar.current
        let daysInMonth = cal.range(of: .day, in: .month, for: cal.date(from: DateComponents(year: year, month: month))!)?.count ?? 30
        let grouped = Dictionary(grouping: monthEvents) { Int($0.eventDate.suffix(2)) ?? 1 }
        return (1...daysInMonth).map { day in
            (day, grouped[day]?.reduce(0) { $0 + ($1.cost ?? 0) } ?? 0)
        }
    }

    private var petBreakdown: [(pet: Pet, amount: Double)] {
        var map: [String: Double] = [:]
        for e in monthEvents {
            let pid = e.petId ?? "unknown"
            map[pid, default: 0] += e.cost ?? 0
        }
        return petStore.pets.compactMap { pet in
            guard let amount = map[pet.id], amount > 0 else { return nil }
            return (pet, amount)
        }
    }

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(spacing: 0) {
                monthSelector
                    .padding(.bottom, Tokens.spacing.sm)

                if monthEvents.isEmpty {
                    emptyState
                } else {
                    donutSection
                    divider
                    barChartSection
                    divider
                    spendingList
                    if petBreakdown.count > 1 {
                        petSummaryBar
                    }
                }
            }
        }
        .task {
            await calendarStore.fetchMonth(year: year, month: month)
        }
        .onChange(of: month) { Task { await calendarStore.fetchMonth(year: year, month: month) } }
        .onChange(of: year) { Task { await calendarStore.fetchMonth(year: year, month: month) } }
    }

    // MARK: - Month Selector

    private var monthSelector: some View {
        HStack {
            Button { prevMonth() } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(Tokens.textSecondary)
            }
            .buttonStyle(.plain)
            Spacer()
            Text(monthYearLabel)
                .font(Tokens.fontHeadline.weight(.medium))
                .foregroundColor(Tokens.text)
            Spacer()
            Button { nextMonth() } label: {
                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(Tokens.textSecondary)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, Tokens.spacing.lg)
        .padding(.top, Tokens.spacing.sm)
    }

    // MARK: - Donut Chart

    private var donutSection: some View {
        VStack(spacing: Tokens.spacing.md) {
            ZStack {
                // Background ring
                Circle()
                    .stroke(Tokens.divider, lineWidth: 16)
                    .frame(width: 150, height: 150)

                // Category segments
                ForEach(Array(donutSegments.enumerated()), id: \.offset) { _, seg in
                    Circle()
                        .trim(from: seg.start, to: seg.end)
                        .stroke(seg.color, style: StrokeStyle(lineWidth: 16, lineCap: .round))
                        .frame(width: 150, height: 150)
                        .rotationEffect(.degrees(-90))
                }

                // Center text
                VStack(spacing: 2) {
                    Text(formatCurrency(totalCost))
                        .font(Tokens.fontTitle.weight(.bold))
                        .foregroundColor(Tokens.text)
                    Text(Lang.shared.isZh ? "本月总花费" : "This month")
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textTertiary)
                }
            }

            // Legend
            HStack(spacing: Tokens.spacing.md) {
                ForEach(categoryBreakdown, id: \.category) { item in
                    HStack(spacing: 4) {
                        Circle()
                            .fill(item.color)
                            .frame(width: 6, height: 6)
                        Text("\(item.category.label) \(Int(item.amount / max(totalCost, 1) * 100))%")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textSecondary)
                    }
                }
            }
        }
        .padding(.vertical, Tokens.spacing.lg)
    }

    private var donutSegments: [(start: CGFloat, end: CGFloat, color: Color)] {
        guard totalCost > 0 else { return [] }
        var segs: [(start: CGFloat, end: CGFloat, color: Color)] = []
        var cursor: CGFloat = 0
        let gap: CGFloat = 0.01
        for item in categoryBreakdown {
            let fraction = CGFloat(item.amount / totalCost)
            if fraction > 0.01 {
                segs.append((cursor + gap, cursor + fraction - gap, item.color))
            }
            cursor += fraction
        }
        return segs
    }

    // MARK: - Bar Chart

    private var barChartSection: some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
            Text(Lang.shared.isZh ? "每日花费" : "DAILY")
                .font(Tokens.fontCaption.weight(.semibold))
                .foregroundColor(Tokens.textTertiary)
                .tracking(0.5)
                .padding(.horizontal, Tokens.spacing.lg)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .bottom, spacing: 3) {
                    let maxAmount = dailyBreakdown.map(\.amount).max() ?? 1
                    let today = Calendar.current.component(.day, from: Date())
                    let isCurrentMonth = Calendar.current.component(.month, from: Date()) == month
                        && Calendar.current.component(.year, from: Date()) == year

                    ForEach(dailyBreakdown, id: \.day) { item in
                        let isToday = isCurrentMonth && item.day == today
                        let barHeight = item.amount > 0 ? max(8, CGFloat(item.amount / maxAmount) * 60) : 0

                        VStack(spacing: 3) {
                            if item.amount > 0 {
                                Text(shortCurrency(item.amount))
                                    .font(.system(size: 7, weight: .medium))
                                    .foregroundColor(Tokens.textTertiary)
                            } else {
                                Text(" ")
                                    .font(.system(size: 7))
                            }

                            RoundedRectangle(cornerRadius: 3)
                                .fill(Tokens.accent.opacity(item.amount > 0 ? (isToday ? 1.0 : 0.5) : 0))
                                .frame(width: 14, height: barHeight)

                            Text("\(item.day)")
                                .font(.system(size: 8, weight: isToday ? .bold : .regular))
                                .foregroundColor(isToday ? Tokens.accent : Tokens.textTertiary)
                        }
                    }
                }
                .frame(height: 90)
                .padding(.horizontal, Tokens.spacing.lg)
            }
        }
        .padding(.vertical, Tokens.spacing.md)
    }

    // MARK: - Spending List

    private var spendingList: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(Lang.shared.isZh ? "花费明细" : "DETAILS")
                .font(Tokens.fontCaption.weight(.semibold))
                .foregroundColor(Tokens.textTertiary)
                .tracking(0.5)
                .padding(.horizontal, Tokens.spacing.lg)
                .padding(.bottom, Tokens.spacing.sm)

            ForEach(monthEvents.sorted(by: { $0.eventDate > $1.eventDate })) { event in
                HStack(spacing: Tokens.spacing.sm) {
                    // Category emoji
                    Text(emojiForCategory(event.category))
                        .font(.system(size: 15))
                        .frame(width: 32, height: 32)
                        .background(colorForCategory(event.category).opacity(0.1))
                        .cornerRadius(10)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(event.petName.flatMap { n in n.isEmpty ? nil : "\(n) · " } ?? "" + event.title)
                            .font(Tokens.fontBody)
                            .foregroundColor(Tokens.text)
                            .lineLimit(1)
                        Text("\(formatDate(event.eventDate)) · \(event.category.label)")
                            .font(Tokens.fontCaption)
                            .foregroundColor(Tokens.textTertiary)
                    }

                    Spacer()

                    Text(formatCurrency(event.cost ?? 0))
                        .font(Tokens.fontBody.weight(.semibold))
                        .foregroundColor(Tokens.text)
                }
                .padding(.horizontal, Tokens.spacing.lg)
                .padding(.vertical, Tokens.spacing.sm)

                if event.id != monthEvents.sorted(by: { $0.eventDate > $1.eventDate }).last?.id {
                    Rectangle()
                        .fill(Tokens.divider)
                        .frame(height: 0.5)
                        .padding(.leading, Tokens.spacing.lg + 32 + Tokens.spacing.sm)
                }
            }
        }
        .padding(.vertical, Tokens.spacing.md)
    }

    // MARK: - Pet Summary

    private var petSummaryBar: some View {
        HStack(spacing: Tokens.spacing.xl) {
            ForEach(petBreakdown, id: \.pet.id) { item in
                VStack(spacing: Tokens.spacing.xs) {
                    Circle()
                        .fill(item.pet.color)
                        .frame(width: 28, height: 28)
                        .overlay(
                            Text(String(item.pet.name.prefix(1)))
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(Tokens.white)
                        )
                    Text(formatCurrency(item.amount))
                        .font(Tokens.fontSubheadline.weight(.semibold))
                        .foregroundColor(Tokens.text)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Tokens.spacing.md)
        .background(Tokens.surface)
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: Tokens.spacing.md) {
            Image(systemName: "yensign.circle")
                .font(.system(size: 36, weight: .thin))
                .foregroundColor(Tokens.textTertiary.opacity(0.4))
            Text(Lang.shared.isZh ? "本月暂无花费记录" : "No spending this month")
                .font(Tokens.fontBody)
                .foregroundColor(Tokens.textTertiary)
            Text(Lang.shared.isZh ? "记录事件时提到金额即可自动统计" : "Mention costs when recording events")
                .font(Tokens.fontCaption)
                .foregroundColor(Tokens.textTertiary.opacity(0.7))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 60)
    }

    // MARK: - Helpers

    private var divider: some View {
        Rectangle()
            .fill(Tokens.divider)
            .frame(height: 0.5)
            .padding(.horizontal, Tokens.spacing.lg)
    }

    private var monthYearLabel: String {
        let monthNames = Lang.shared.isZh
            ? ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"]
            : ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        let name = monthNames[month - 1]
        return Lang.shared.isZh ? "\(year)年\(name)" : "\(name) \(year)"
    }

    private func prevMonth() {
        if month == 1 { month = 12; year -= 1 } else { month -= 1 }
    }

    private func nextMonth() {
        if month == 12 { month = 1; year += 1 } else { month += 1 }
    }

    private func formatCurrency(_ amount: Double) -> String {
        if amount >= 10000 {
            return String(format: "%.1fw", amount / 10000)
        }
        return amount.truncatingRemainder(dividingBy: 1) == 0
            ? "¥\(Int(amount))"
            : String(format: "¥%.0f", amount)
    }

    private func shortCurrency(_ amount: Double) -> String {
        if amount >= 1000 { return String(format: "%.1fk", amount / 1000) }
        return "\(Int(amount))"
    }

    private func formatDate(_ dateStr: String) -> String {
        guard dateStr.count >= 10 else { return dateStr }
        let m = Int(dateStr.dropFirst(5).prefix(2)) ?? 0
        let d = Int(dateStr.suffix(2)) ?? 0
        return Lang.shared.isZh ? "\(m)月\(d)日" : "\(m)/\(d)"
    }

    private func emojiForCategory(_ cat: EventCategory) -> String {
        switch cat {
        case .medical: return "🏥"
        case .daily: return "🐕"
        case .diet: return "🦴"
        case .abnormal: return "⚠️"
        }
    }

    private func colorForCategory(_ cat: EventCategory) -> Color {
        switch cat {
        case .medical: return Tokens.accent
        case .daily: return Tokens.blue
        case .diet: return Tokens.green
        case .abnormal: return Tokens.purple
        }
    }
}
