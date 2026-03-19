import { useState, useMemo, useEffect, useRef } from "react";
import { X, ChevronLeft, ChevronRight, Pencil, Trash2, Check, Calendar } from "lucide-react";
import { EmptyState } from "./EmptyState";
import {
  getCalendarDays,
  MONTH_NAMES,
  WEEKDAYS,
  CalendarDay,
} from "../utils/calendar";
import {
  useCalendarEvents,
  calendarStore,
  seedDemoData,
} from "../stores/calendarStore";
import { usePets } from "../stores/petStore";
import type { CalendarEvent } from "../types/pets";
import styles from "./CalendarDrawer.module.css";

interface CalendarDrawerProps {
  open: boolean;
  onClose: () => void;
}

const CATEGORY_LABELS: Record<CalendarEvent["category"], string> = {
  diet: "Diet",
  excretion: "Excretion",
  abnormal: "Abnormal",
  vaccine: "Vaccine",
  deworming: "Deworming",
  medical: "Medical",
  daily: "Daily",
};

const ALL_CATEGORIES: CalendarEvent["category"][] = [
  "diet",
  "excretion",
  "abnormal",
  "vaccine",
  "deworming",
  "medical",
  "daily",
];

function formatTime(time: string | null): string {
  if (!time) return "All day";
  const [h, m] = time.split(":").map(Number);
  const suffix = h >= 12 ? "PM" : "AM";
  const hour12 = h % 12 || 12;
  return `${hour12}:${String(m).padStart(2, "0")} ${suffix}`;
}

export function CalendarDrawer({ open, onClose }: CalendarDrawerProps) {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [selectedDay, setSelectedDay] = useState<CalendarDay | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editCategory, setEditCategory] = useState<CalendarEvent["category"]>("daily");
  const [editDate, setEditDate] = useState("");
  const [editTime, setEditTime] = useState("");

  const seeded = useRef(false);
  const pets = usePets();
  const monthEvents = useCalendarEvents(year, month);
  const days = useMemo(() => getCalendarDays(year, month), [year, month]);

  // Build a pet lookup map
  const petMap = useMemo(() => {
    const m = new Map<string, { name: string; color: string; index: number }>();
    pets.forEach((p, i) => m.set(p.id, { name: p.name, color: p.color, index: i }));
    return m;
  }, [pets]);

  // Seed demo data once when calendar is empty and pets exist
  useEffect(() => {
    if (!seeded.current && pets.length > 0) {
      seedDemoData(pets);
      seeded.current = true;
    }
  }, [pets]);

  const prevMonth = () => {
    if (month === 0) {
      setMonth(11);
      setYear((y) => y - 1);
    } else {
      setMonth((m) => m - 1);
    }
    setSelectedDay(null);
    setEditingId(null);
  };

  const nextMonth = () => {
    if (month === 11) {
      setMonth(0);
      setYear((y) => y + 1);
    } else {
      setMonth((m) => m + 1);
    }
    setSelectedDay(null);
    setEditingId(null);
  };

  const getDayDateStr = (day: CalendarDay): string => {
    const mm = String(day.month + 1).padStart(2, "0");
    const dd = String(day.date).padStart(2, "0");
    return `${day.year}-${mm}-${dd}`;
  };

  const getDayEvents = (day: CalendarDay): CalendarEvent[] => {
    const dateStr = getDayDateStr(day);
    const dayEvts = monthEvents.filter((e) => e.eventDate === dateStr);
    if (filter === "all") return dayEvts;
    return dayEvts.filter((e) => e.petId === filter);
  };

  const getDayDots = (day: CalendarDay): { petId: string; color: string }[] => {
    const events = getDayEvents(day);
    const seen = new Set<string>();
    const dots: { petId: string; color: string }[] = [];
    for (const e of events) {
      if (!seen.has(e.petId)) {
        seen.add(e.petId);
        const pet = petMap.get(e.petId);
        dots.push({ petId: e.petId, color: pet?.color || "#999" });
      }
    }
    return dots;
  };

  const selectedEvents = selectedDay ? getDayEvents(selectedDay) : [];

  const selectedDayTitle = selectedDay
    ? `${MONTH_NAMES[selectedDay.month]} ${selectedDay.date}${selectedDay.isToday ? " — Today" : ""}`
    : null;

  const startEdit = (evt: CalendarEvent) => {
    setEditingId(evt.id);
    setEditTitle(evt.title);
    setEditCategory(evt.category);
    setEditDate(evt.eventDate);
    setEditTime(evt.eventTime || "");
  };

  const saveEdit = () => {
    if (!editingId) return;
    calendarStore.update(editingId, {
      title: editTitle,
      category: editCategory,
      eventDate: editDate,
      eventTime: editTime || null,
    });
    setEditingId(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  const handleDelete = (id: string) => {
    if (window.confirm("Delete this event?")) {
      calendarStore.remove(id);
    }
  };

  return (
    <>
      <div
        className={`${styles.overlay} ${open ? styles.overlayActive : ""}`}
        onClick={onClose}
      />
      <div className={`${styles.drawer} ${open ? styles.drawerOpen : ""}`}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.title}>Calendar</div>
          <button
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Pet filter */}
        <div className={styles.filter}>
          <button
            className={`${styles.filterBtn} ${filter === "all" ? styles.filterActive : ""}`}
            onClick={() => setFilter("all")}
          >
            All
          </button>
          {pets.map((pet) => (
            <button
              key={pet.id}
              className={`${styles.filterBtn} ${filter === pet.id ? styles.filterActive : ""}`}
              onClick={() => setFilter(pet.id)}
            >
              <span
                className={styles.filterDot}
                style={{ background: pet.color }}
              />
              {pet.name}
            </button>
          ))}
        </div>

        {/* Month nav */}
        <div className={styles.nav}>
          <button
            className={styles.navBtn}
            onClick={prevMonth}
            aria-label="Previous month"
          >
            <ChevronLeft size={16} />
          </button>
          <div className={styles.navTitle}>
            {MONTH_NAMES[month]} {year}
          </div>
          <button
            className={styles.navBtn}
            onClick={nextMonth}
            aria-label="Next month"
          >
            <ChevronRight size={16} />
          </button>
        </div>

        {/* Weekdays */}
        <div className={styles.weekdays}>
          {WEEKDAYS.map((d) => (
            <span key={d}>{d}</span>
          ))}
        </div>

        {/* Day grid */}
        <div className={styles.grid}>
          {days.map((day, i) => {
            const isSelected =
              selectedDay?.date === day.date &&
              selectedDay?.month === day.month &&
              selectedDay?.year === day.year;
            const dots = getDayDots(day);
            return (
              <div
                key={i}
                className={[
                  styles.day,
                  !day.isCurrentMonth && styles.other,
                  day.isToday && styles.today,
                  isSelected && styles.selected,
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => {
                  setSelectedDay(day);
                  setEditingId(null);
                }}
              >
                <div className={styles.dayNum}>{day.date}</div>
                <div className={styles.dots}>
                  {dots.map((dot) => (
                    <div
                      key={dot.petId}
                      className={styles.dot}
                      style={{ background: dot.color }}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Empty state when no events in month */}
        {!selectedDay && monthEvents.length === 0 && (
          <EmptyState
            icon={Calendar}
            title="No events yet"
            subtitle="Chat with Cozy Pup to start recording health events"
          />
        )}

        {/* Events for selected day */}
        {selectedDay && (
          <div className={styles.events}>
            <div className={styles.eventsTitle}>{selectedDayTitle}</div>
            {selectedEvents.length === 0 && (
              <EmptyState icon={Calendar} title="No events on this day" />
            )}
            {selectedEvents.map((evt) => {
              const pet = petMap.get(evt.petId);
              const petName = pet?.name || "Unknown";
              const petColor = pet?.color || "#999";

              if (editingId === evt.id) {
                return (
                  <div key={evt.id} className={styles.event}>
                    <div
                      className={styles.eventColor}
                      style={{ background: petColor }}
                    />
                    <div className={styles.editForm}>
                      <input
                        className={styles.editInput}
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        placeholder="Title"
                        autoFocus
                      />
                      <div className={styles.editRow}>
                        <select
                          className={styles.editSelect}
                          value={editCategory}
                          onChange={(e) =>
                            setEditCategory(e.target.value as CalendarEvent["category"])
                          }
                        >
                          {ALL_CATEGORIES.map((c) => (
                            <option key={c} value={c}>
                              {CATEGORY_LABELS[c]}
                            </option>
                          ))}
                        </select>
                        <input
                          className={styles.editInput}
                          type="date"
                          value={editDate}
                          onChange={(e) => setEditDate(e.target.value)}
                        />
                        <input
                          className={styles.editInput}
                          type="time"
                          value={editTime}
                          onChange={(e) => setEditTime(e.target.value)}
                        />
                      </div>
                      <div className={styles.editActions}>
                        <button
                          className={styles.editSaveBtn}
                          onClick={saveEdit}
                          aria-label="Save"
                        >
                          <Check size={12} />
                          Save
                        </button>
                        <button
                          className={styles.editCancelBtn}
                          onClick={cancelEdit}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  </div>
                );
              }

              return (
                <div key={evt.id} className={styles.event}>
                  <div
                    className={styles.eventColor}
                    style={{ background: petColor }}
                  />
                  <div className={styles.eventInfo}>
                    <h5>
                      {petName} &middot; {evt.title}
                    </h5>
                    <p>
                      {formatTime(evt.eventTime)} &middot;{" "}
                      {CATEGORY_LABELS[evt.category] || evt.category}
                    </p>
                  </div>
                  <div className={styles.eventActions}>
                    <button
                      className={styles.eventBtn}
                      aria-label="Edit"
                      onClick={() => startEdit(evt)}
                    >
                      <Pencil size={12} />
                    </button>
                    <button
                      className={styles.eventBtn}
                      aria-label="Delete"
                      onClick={() => handleDelete(evt.id)}
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
