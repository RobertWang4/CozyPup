# Event Location Tagging Spec

Add location tagging to diary/calendar events. AI proactively offers location when photos are present, shows nearby options from GPS, supports text search fallback. Locations are tappable to open Google Maps.

## Data Model

Add to `CalendarEvent` model:

| Field | Type | Notes |
|-------|------|-------|
| `location_name` | str, nullable | Display name ("Rideau Park") |
| `location_address` | str, nullable | Full address ("302 Rideau St, Ottawa") |
| `location_lat` | float, nullable | Latitude |
| `location_lng` | float, nullable | Longitude |
| `place_id` | str, nullable | Google Place ID for Maps deep link |

All nullable — most events won't have locations.

## AI Conversation Flow

### With photos (proactive)

```
User: [photo] 带维尼去公园玩
AI:   → create_calendar_event (with photo)
      → SSE card event (diary card)
      → detect: has photo + location-relevant context
      → search_places_nearby (using user lat/lng from context)
      → SSE location_card event (5 nearby options)
      → response text: "已记录！要标记地点吗？"
```

### Without photos (reactive)

AI does NOT ask about location. Only responds if user says something like "记录一下地点" or "加个位置".

### User selects option (tap)

```
User: [taps option in location_card]
      → POST /api/v1/calendar/{event_id}/location (with selected place data)
      → AI response not needed, card updates inline
```

### User types address

```
User: "记录在302 rideau st"
AI:   → search_places_text("302 rideau st")
      → add_event_location(event_id, place_data)
      → SSE card event (updated diary card with location)
      → "已添加地点 ✓"
```

## SSE Events

New event type for location selection:

```
event: location_card
data: {
  "event_id": "uuid",
  "options": [
    {
      "name": "Rideau Park",
      "address": "1 Rideau Park Dr, Ottawa",
      "distance_m": 300,
      "place_id": "ChIJ...",
      "lat": 45.123,
      "lng": -75.456
    },
    ... (up to 5)
  ]
}
```

## Backend Changes

### New API endpoint

`PUT /api/v1/calendar/{event_id}/location` — Add/update location on an event.

Request body:
```json
{
  "location_name": "Rideau Park",
  "location_address": "1 Rideau Park Dr, Ottawa",
  "location_lat": 45.123,
  "location_lng": -75.456,
  "place_id": "ChIJ..."
}
```

`DELETE /api/v1/calendar/{event_id}/location` — Remove location from event.

### New agent tools

**`add_event_location`** — Sets location on a calendar event. Accepts event_id + place fields. Called after user selects or AI resolves a text address.

**`search_places_text`** — Text-based place search via Google Places API. For when user types an address instead of selecting from nearby options. Returns top 5 results. Add to existing `PlacesService`:

```python
async def search_text(self, query: str) -> list[dict]:
    """Search places by text query (address, name, etc.)."""
```

Uses `https://maps.googleapis.com/maps/api/place/textsearch/json`.

### Orchestrator prompt update

Add instruction to system prompt: when a calendar event is created with photos, search nearby places and emit a location_card for the user to optionally tag location.

### Schema updates

- `CalendarEventResponse`: add `location_name`, `location_address`, `location_lat`, `location_lng`, `place_id`
- New `LocationUpdate` schema for the PUT endpoint

## iOS Changes

### CalendarEvent model

Add fields: `locationName`, `locationAddress`, `locationLat`, `locationLng`, `placeId`.

### Chat — LocationPickerCard

New card view rendered when SSE `location_card` event is received:
- Shows up to 5 nearby places as tappable rows
- Each row: place name, address, distance
- Tapping sends PUT to `/calendar/{event_id}/location` directly (no AI round-trip)
- Card dismisses or shows checkmark after selection

### Diary card — location display

On `TimelineEventCard` and `EventEditSheet`, if location exists:
- Show `📍 location_name` at bottom of card
- Tappable → open Google Maps via URL:
  - `comgooglemaps://?q={lat},{lng}` (if Google Maps installed)
  - Fallback: `https://www.google.com/maps/search/?api=1&query={lat},{lng}&query_place_id={place_id}`

### CalendarStore

- Add `updateLocation(eventId, location)` method
- Add `removeLocation(eventId)` method

### ChatService

- Parse new `location_card` SSE event type
- Add `SSEEvent.locationCard` case

### EventEditSheet

- Show location if present (tappable to open Maps)
- Option to remove location

## What stays the same

- All existing calendar event CRUD
- Photo upload/delete flow
- Multi-pet support
- Existing `search_places` tool for "附近有什么宠物医院" queries (that's a different feature — search results shown in chat, not attached to events)

## Migration

Alembic migration adding 5 nullable columns to `calendar_events`. No data backfill needed.
