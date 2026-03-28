from pydantic import BaseModel


class DailyTaskCreate(BaseModel):
    title: str
    type: str = "routine"  # "routine" | "special"
    daily_target: int = 1
    pet_id: str | None = None
    start_date: str | None = None  # YYYY-MM-DD, special only
    end_date: str | None = None    # YYYY-MM-DD, special only


class DailyTaskUpdate(BaseModel):
    title: str | None = None
    daily_target: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    active: bool | None = None


class DailyTaskResponse(BaseModel):
    id: str
    title: str
    type: str
    daily_target: int
    completed_count: int
    pet: dict | None = None  # {"id": "...", "name": "...", "color_hex": "..."}
    active: bool
    start_date: str | None = None
    end_date: str | None = None


class TodayResponse(BaseModel):
    tasks: list[DailyTaskResponse]
    all_completed: bool


class TapResponse(BaseModel):
    task_id: str
    completed_count: int
    daily_target: int
    all_completed: bool
