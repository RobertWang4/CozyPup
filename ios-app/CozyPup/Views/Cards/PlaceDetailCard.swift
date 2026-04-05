import SwiftUI

struct PlaceDetailCard: View {
    let data: PlaceDetailCardData
    @State private var expandedReviews: Set<Int> = []
    @State private var showHours = false

    var body: some View {
        VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                    Text(data.name)
                        .font(Tokens.fontBody.weight(.semibold))
                        .foregroundColor(Tokens.text)
                    Text(data.address)
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                        .lineLimit(1)
                }
                Spacer()
                if let isOpen = data.isOpen {
                    Text(isOpen ? "Open" : "Closed")
                        .font(Tokens.fontCaption.weight(.medium))
                        .foregroundColor(isOpen ? Tokens.green : Tokens.red)
                        .padding(.horizontal, Tokens.spacing.sm)
                        .padding(.vertical, Tokens.spacing.xxs)
                        .background((isOpen ? Tokens.green : Tokens.red).opacity(0.12))
                        .clipShape(RoundedRectangle(cornerRadius: Tokens.radiusSmall))
                }
            }

            // Rating
            if let rating = data.rating {
                HStack(spacing: 4) {
                    ForEach(0..<5, id: \.self) { i in
                        Image(systemName: i < Int(rating) ? "star.fill" : (Double(i) < rating ? "star.leadinghalf.filled" : "star"))
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                    Text(String(format: "%.1f", rating))
                        .font(Tokens.fontCaption)
                        .foregroundColor(Tokens.textSecondary)
                }
            }

            // Reviews
            if let reviews = data.reviews, !reviews.isEmpty {
                VStack(alignment: .leading, spacing: Tokens.spacing.sm) {
                    ForEach(Array(reviews.enumerated()), id: \.offset) { index, review in
                        let isExpanded = expandedReviews.contains(index)
                        VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                            HStack {
                                Text(review.author)
                                    .font(Tokens.fontCaption.weight(.medium))
                                    .foregroundColor(Tokens.text)
                                Spacer()
                                HStack(spacing: 2) {
                                    Image(systemName: "star.fill")
                                        .font(.caption2)
                                        .foregroundColor(.orange)
                                    Text("\(review.rating)")
                                        .font(Tokens.fontCaption2)
                                        .foregroundColor(Tokens.textSecondary)
                                }
                            }
                            Text(review.text)
                                .font(Tokens.fontCaption)
                                .foregroundColor(Tokens.textSecondary)
                                .lineLimit(isExpanded ? nil : 2)
                            Button {
                                withAnimation(.easeInOut(duration: 0.2)) {
                                    if isExpanded {
                                        expandedReviews.remove(index)
                                    } else {
                                        expandedReviews.insert(index)
                                    }
                                }
                            } label: {
                                Text(isExpanded ? "收起" : "展开")
                                    .font(Tokens.fontCaption2)
                                    .foregroundColor(Tokens.accent)
                            }
                        }
                    }
                }
            }

            // Hours (collapsed by default)
            if let hours = data.openingHours, !hours.isEmpty {
                VStack(alignment: .leading, spacing: Tokens.spacing.xxs) {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showHours.toggle()
                        }
                    } label: {
                        HStack(spacing: Tokens.spacing.xs) {
                            Text("Hours")
                                .font(Tokens.fontCaption.weight(.medium))
                                .foregroundColor(Tokens.text)
                            Image(systemName: showHours ? "chevron.up" : "chevron.down")
                                .font(.caption2)
                                .foregroundColor(Tokens.textSecondary)
                        }
                    }
                    if showHours {
                        ForEach(hours, id: \.self) { line in
                            Text(line)
                                .font(Tokens.fontCaption2)
                                .foregroundColor(Tokens.textSecondary)
                        }
                    }
                }
            }

            // Action buttons
            HStack(spacing: Tokens.spacing.sm) {
                if let phone = data.phone {
                    Button {
                        if let url = URL(string: "tel:\(phone.replacingOccurrences(of: " ", with: ""))") {
                            UIApplication.shared.open(url)
                        }
                    } label: {
                        Label("Call", systemImage: "phone.fill")
                            .font(Tokens.fontCaption.weight(.medium))
                    }
                    .foregroundColor(Tokens.accent)
                }

                if let website = data.website, let url = URL(string: website) {
                    Button {
                        UIApplication.shared.open(url)
                    } label: {
                        Label("Website", systemImage: "safari")
                            .font(Tokens.fontCaption.weight(.medium))
                    }
                    .foregroundColor(Tokens.accent)
                }

                if let mapsUrl = data.googleMapsUrl, let url = URL(string: mapsUrl) {
                    Button {
                        UIApplication.shared.open(url)
                    } label: {
                        Label("Maps", systemImage: "map")
                            .font(Tokens.fontCaption.weight(.medium))
                    }
                    .foregroundColor(Tokens.accent)
                }
            }
        }
        .padding(Tokens.spacing.md)
        .background(Tokens.surface)
        .clipShape(RoundedRectangle(cornerRadius: Tokens.radius))
    }
}

#Preview {
    PlaceDetailCard(data: PlaceDetailCardData(
        type: "place_detail",
        name: "Happy Paws Vet Clinic",
        address: "123 Main Street, Ottawa",
        rating: 4.5,
        phone: "+1 613-555-0123",
        reviews: [
            PlaceReview(author: "John D.", rating: 5, text: "Great vet! Very caring with my dog. The staff was incredibly friendly and knowledgeable about pet health issues.", time: "2 weeks ago"),
            PlaceReview(author: "Jane S.", rating: 4, text: "Good service, bit pricey but worth it for the quality of care they provide.", time: "1 month ago"),
        ],
        isOpen: true,
        openingHours: ["Mon-Fri: 9:00 AM - 6:00 PM", "Sat: 10:00 AM - 4:00 PM", "Sun: Closed"],
        website: "https://example.com",
        googleMapsUrl: "https://maps.google.com/?cid=12345"
    ))
    .padding()
}
