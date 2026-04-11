# CozyPup E2E Test Plan

> Updated: 2026-04-04
> Category changes: `excretion`/`vaccine`/`deworming` merged into `abnormal`/`medical`
> Valid categories (create_calendar_event): `daily`, `diet`, `medical`, `abnormal`
> Total tools: 28 (from `_BASE_TOOL_DEFINITIONS`)

## How to Run

```bash
# Start backend
cd backend && uvicorn app.main:app --reload --port 8000

# Run full E2E audit
python tests/e2e/run_audit.py --lang en

# Run single case
python tests/e2e/run_audit.py --lang en --case 2.1

# Run pytest-based E2E
pytest tests/e2e/ -v --tb=short
```

---

## 1. Basic Chat

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 1.1 | "Hello" | Normal reply, no tool calls | `result.text` non-empty, no cards |
| 1.2 | "hi" | Reply in Chinese when lang=zh | `has_cjk(result.text)` == True |
| 1.3 | Send 3 casual messages in sequence | Each gets a reply, session context maintained | All 3 `result.text` non-empty |

---

## 2. Create Calendar Events

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 2.1 | "Weiwei ate dog food today" | Record card, category=**diet**, date=today | `card["category"]=="diet"`, `card["date"]==today` |
| 2.2 | "We went to the park for a walk yesterday" | Record card, category=**daily**, date=yesterday | `card["category"]=="daily"`, `card["date"]==yesterday` |
| 2.3 | "Got vaccinated last Friday" | Record card, category=**medical** | `card["category"]=="medical"` |
| 2.4 | "Took Weiwei to the hospital last week" | Ask for specific date (no event created) | No record card, reply contains `?` |
| 2.5 | "Had a checkup on March 20th" | Record card, category=**medical** | `card["category"]=="medical"` |
| 2.6 | "Weiwei vomited" | Record card, category=**abnormal** | `card["category"]=="abnormal"` |
| 2.7 | "Walked the dog and gave a bath today" | >=2 record cards | `card_count("record") >= 2` |
| 2.8 | "Weiwei has diarrhea" | Record card, category=**abnormal** | `card["category"]=="abnormal"` |
| 2.9 | "Dewormed today" | Record card, category=**medical** | `card["category"]=="medical"` |
| 2.10 | "Weiwei went swimming today" | Record card, category=**daily** | `card["category"]=="daily"` |
| 2.11 | "Took Weiwei to the vet, cost $300" | Record card, cost=300 | `card["cost"]==300` |
| 2.12 | "Gave Weiwei a bath, cost $80" | Record card, cost=80 | `card["cost"]==80` |
| 2.13 | "Weiwei ate dog food today" (no cost mentioned) | Record card, cost=None | `card["cost"] is None` |
| 2.14 | "Walked the dog, bought treats at pet store for $50" (multi-event+cost) | >=2 records, treat purchase cost=50 | Walk cost=None, treats cost=50 |
| 2.15 | "Checkup cost $1500" | Record card, cost=1500 | `card["cost"]==1500` |
| 2.16 | "Got free deworming" | Record card, cost=None | `card["cost"] is None` (free = no cost) |

---

## 2b. Update/Query Spending

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 2.21 | Create a spending record, then ask "How much have I spent recently?" | Reply includes spending total | `result.text` contains amount |
| 2.22 | "Actually the checkup cost $2000" | update_calendar_event updates cost | Event cost updated to 2000 |

---

## 3. Query Events

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 3.1 | Create vaccine record, then ask "When was the last vaccination?" | Reply includes vaccine-related content | `result.text` contains "vaccin" |
| 3.2 | Create a record, then ask "What was recorded this week?" | Non-empty reply listing weekly events | `result.text` non-empty |
| 3.3 | Create diet record, then ask "What has Weiwei eaten recently?" | Reply includes diet-related content | `result.text` contains "food"/"eat" |

---

## 4. Update/Delete Events

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 4.1 | Create event, then say "The date is wrong, should be March 25th" | Date updated successfully | `get_events("2026-03-25")` has record |
| 4.2 | "Delete yesterday's walk record" | Returns confirm_action card | `has_card("confirm_action")` |
| 4.3 | Confirm deletion from 4.2 | Event deleted | `get_events(yesterday)` count decreases |

---

## 5. Pet Management

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 5.1 | "I got a new cat named Huahua" | pet_created card, species=cat | `has_card("pet_created")`, `card["species"]=="cat"` |
| 5.2 | "Huahua is female" | confirm_action card (first gender set requires confirmation) | `has_card("confirm_action")` |
| 5.3 | Set gender=female first, then say "Actually Huahua is male" | Reject change (gender locked) | Reply contains "locked" |
| 5.4 | "Huahua weighs 5 kilograms" | pet_updated card | `has_card("pet_updated")` |
| 5.5 | "Huahua's birthday is March 5th, 2024" | pet_updated card | pet API returns `birthday` with "2024-03-05" |
| 5.6 | "Huahua is allergic to chicken" | Profile updated with allergy info | `get_pets()` profile contains allergy |
| 5.7 | "Change Huahua's name to Mimi" | pet_updated card, name changed | `get_pets()` has name="Mimi" |
| 5.8 | Already have Weiwei, say "I got a new dog named Weiwei" | Reject creation (duplicate prevention) | No pet_created card |
| 5.9 | "Delete Huahua" | confirm_action card | `has_card("confirm_action")` |
| 5.10 | "What pets do I have?" | Calls list_pets, reply lists all pets | `result.text` contains pet names |

---

## 6. Pet Avatar (set_pet_avatar)

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 6.1 | Send image + "Use this as avatar" | avatar_updated card | `has_card("avatar_updated")`, pet.avatar_url non-empty |
| 6.2 | Send >5MB image | Rejected with error | Reply contains "5MB" |

---

## 7. Daily Tasks

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 7.1 | "Remind me to walk the dog every day" | task_created card, type=routine | `has_card("task_created")`, `card["type"]=="routine"` |
| 7.2 | "Take Weiwei's temperature every day this week" | task_created, type=special, has start/end dates | `card["type"]=="special"` |
| 7.3 | "Cancel the dog walking task" | Task deactivated | manage_daily_task executed successfully |

---

## 8. Reminders

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 8.1 | "Remind me to give Weiwei medicine tomorrow" | Reminder card, type=medication | `has_card("reminder")`, `trigger_at` contains tomorrow's date |
| 8.2 | "Don't forget to take Weiwei for vaccination next Tuesday" | Reminder card, type=vaccine | `has_card("reminder")` |
| 8.3 | "What reminders do I have?" | Calls list_reminders, lists all active reminders | `result.text` non-empty |
| 8.4 | "Cancel tomorrow's medicine reminder" | Calls delete_reminder, reminder deleted | `has_card("reminder_deleted")` or confirmed in reply |
| 8.5 | "Change the medicine reminder to 3pm the day after tomorrow" | Calls update_reminder, updates trigger_at | Reply confirms change, time updated |
| 8.6 | "Cancel all reminders" | Calls delete_all_reminders, clears all | Reply confirms cleared, list_reminders returns empty |

---

## 9. Place Search

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 9.1 | "Are there any pet hospitals nearby?" (with location) | place_card 卡片 | `has_card("place_card")` or `has_card("map")` |
| 9.2 | "Help me find the nearest dog park" (with location) | place_card 卡片 | Same as above |
| 9.3 | search_places_text: "pet hospital Beijing" | Returns place list | Reply contains address info |
| 9.4 | "How are the reviews for the first one?" (after 9.1) | place_detail 卡片 + 文字回复 | `has_card("place_detail")` |
| 9.5 | "How do I get there?" (after 9.1) | directions 卡��� | `has_card("directions")` |

---

## 10. Draft Email

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 10.1 | "Help me write an email to the vet about Weiwei's skin allergy" | Email card with subject + body | `has_card("email")` |

---

## 11. Emergency

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 11.1 | "My cat is suddenly having seizures!" | Emergency SSE event + first aid advice | `result.emergency` non-null |
| 11.2 | "Weiwei has been poisoned and is dying!" | Emergency SSE event | `result.emergency` non-null |
| 11.3 | "When was the last poisoning incident?" | Does NOT trigger emergency (historical query) | `result.emergency` is null |

---

## 12. Language Switch

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 12.1 | "switch to English" | set_language card, language=en | `has_card("language")` |
| 12.2 | "切换成中文" | set_language card, language=zh | `has_card("language")` |

---

## 13. Multi-Pet Scenarios

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 13.1 | With 2 pets, say "Ate dog food" (no pet specified) | Ask which pet, or create shared event | Reply contains `?` or record card has pet_ids |
| 13.2 | "Weiwei and Huahua went for a walk together" | Event created covering both pets | Record card exists |
| 13.3 | With 1 pet, say "Ate dog food" | Auto-associate with the only pet | `has_card("record")` |

---

## 14. Profile Management

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 14.1 | "Weiwei is very afraid of thunder, timid personality" | Silently calls save_pet_profile_md, profile_md updated with personality info | `get_pets()` profile_md contains personality info |
| 14.2 | "Help me summarize Weiwei's profile" | Calls summarize_pet_profile, returns complete profile document | `result.text` contains profile content |
| 14.3 | After multi-turn conversation with new info, check profile_md | save_pet_profile_md silently called, doc contains history + new info | pet.profile_md contains all known info |

---

## 15. Context Compression

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 15.1 | Send 7 messages in sequence, then ask "How has Weiwei been?" | Reply references earlier conversation content | `result.text` non-empty |

---

## 16. Event Location (add_event_location)

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 16.1 | After creating event, say "It was at Central Park" | Event gets location added | Event API returns with location |

---

## 17. Image Request (request_images)

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 17.1 | Send image + "Help me record this" | LLM analyzes image content, records event | Record card or related action |
| 17.2 | Send image + "What breed is this?" | Calls request_images to view image, replies with breed info | `result.text` contains breed-related content |

---

## 18. Event Photo (upload_event_photo)

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 18.1 | Create event, then send image + "Add this photo to the last record" | Calls upload_event_photo to attach photo | Event API returns with photo_url |
| 18.2 | No event exists, send image + "Add to record" | Prompts user to create event first | Reply guides user to create event |

---

## 19. Calendar Sync (sync_calendar)

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 19.1 | "Sync events to my phone calendar" | Calls sync_calendar, frontend shows sync options | `has_card("sync_calendar")` or related SSE event |
| 19.2 | "Connect Apple Calendar" | Calls sync_calendar | Same as above |

---

## 20. Edge Cases

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 20.1 | Chat with no pets created | Normal reply | `result.text` non-empty |
| 20.2 | Have pet but no events, query events | Normal reply saying "no records yet" | `result.text` non-empty |
| 20.4 | "Record Weiwei ate dog food today, and remind me to take him for vaccination tomorrow" | >=2 cards (record + reminder) | `card_count >= 2` |

---

## 21. Health Q&A (RAG)

| # | Input | Expected | Validation |
|---|-------|----------|------------|
| 21.1 | "维尼呕吐了怎么办" | `search_knowledge` called with query containing "呕吐" | tool called, text non-empty |
| 21.2 | "维尼最近老是拉肚子" | `search_knowledge` called with pet_id | tool + pet_id present |
| 21.3 | "帮我记录维尼今天吃了狗粮" | `create_calendar_event` called, NOT `search_knowledge` | no search_knowledge |
| 21.4 | "My dog has been vomiting, what should I do?" | `search_knowledge` called | tool called |

---

## Category Reference

| Old Category | New Category | Trigger Words |
|-------------|-------------|---------------|
| `excretion` | **`abnormal`** | diarrhea, abnormal stool |
| `vaccine` | **`medical`** | vaccination, vaccinated |
| `deworming` | **`medical`** | dewormed, deworming |
| `diet` | `diet` (unchanged) | ate, fed, food, feeding |
| `abnormal` | `abnormal` (unchanged) | vomited, sick, unwell |
| `medical` | `medical` (unchanged) | vet visit, hospital, checkup |
| `daily` | `daily` (unchanged) | walk, bath, swimming |

## Validator Enums

```python
_CATEGORIES = {"daily", "diet", "medical", "abnormal"}
_SPECIES = {"dog", "cat", "other"}
_REMINDER_TYPES = {"medication", "vaccine", "checkup", "feeding", "grooming", "other"}
_TASK_TYPES = {"routine", "special"}
_EMERGENCY_ACTIONS = {"find_er", "call_vet", "first_aid"}
_LANGUAGES = {"zh", "en"}
_DAILY_TASK_ACTIONS = {"update", "delete", "deactivate", "delete_all"}
```

## Tool Coverage Checklist (28 tools from `_BASE_TOOL_DEFINITIONS`)

| Tool | Test Section | Status |
|------|-------------|--------|
| `create_calendar_event` | 2 (2.x) | Covered |
| `query_calendar_events` | 3 (3.x) | Covered |
| `update_calendar_event` | 4 (4.x) | Covered |
| `delete_calendar_event` | 4 (4.x) | Covered |
| `create_pet` | 5 (5.x) | Covered |
| `update_pet_profile` | 5 (5.x) | Covered |
| `delete_pet` | 5 (5.x) | Covered |
| `list_pets` | 5 (5.10) | Covered |
| `save_pet_profile_md` | 14 (14.x) | Covered |
| `summarize_pet_profile` | 14 (14.2) | Covered |
| `set_pet_avatar` | 6 (6.x) | Covered |
| `create_daily_task` | 7 (7.x) | Covered |
| `manage_daily_task` | 7 (7.3) | Covered |
| `create_reminder` | 8 (8.x) | Covered |
| `list_reminders` | 8 (8.3) | Covered |
| `update_reminder` | 8 (8.5) | Covered |
| `delete_reminder` | 8 (8.4) | Covered |
| `delete_all_reminders` | 8 (8.6) | Covered |
| `search_places` | 9 (9.x) | Covered |
| `search_places_text` | 9 (9.3) | Covered |
| `get_place_details` | 9 (9.4) | Covered |
| `get_directions` | 9 (9.5) | Covered |
| `draft_email` | 10 (10.x) | Covered |
| `trigger_emergency` | 11 (11.x) | Covered |
| `set_language` | 12 (12.x) | Covered |
| `add_event_location` | 16 (16.x) | Covered |
| `request_images` | 17 (17.x) | Covered |
| `upload_event_photo` | 18 (18.x) | Covered |
| `sync_calendar` | 19 (19.x) | Covered |
| `search_knowledge` | 21 (21.x) | Covered |
