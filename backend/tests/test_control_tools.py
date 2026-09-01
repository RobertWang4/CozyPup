from app.agents.control_tools import handle_control_tool
from app.agents.orchestrator import OrchestratorResult
from app.agents.tool_context import ToolDispatchContext
from app.agents.tool_invocation import ToolInvocation


def test_plan_control_tool_records_steps():
    result = OrchestratorResult()
    context = ToolDispatchContext(result=result, lang="zh")
    steps = [
        {"id": "1", "action": "记录喂食", "tool": "create_calendar_event"},
        {"id": "2", "action": "设置提醒", "tool": "create_reminder"},
    ]

    output = handle_control_tool(
        ToolInvocation(id="call-1", name="plan", arguments={"steps": steps}),
        context,
        load_images_from_urls=lambda urls: [],
    )

    assert result.plan_steps == steps
    assert output == {
        "status": "planned",
        "message": "已规划 2 个步骤: [1] 记录喂食; [2] 设置提醒",
        "steps": steps,
    }


def test_request_images_prefers_current_images():
    context = ToolDispatchContext(images=["base64-current"], lang="en")

    output = handle_control_tool(
        ToolInvocation(id="call-1", name="request_images", arguments={}),
        context,
        load_images_from_urls=lambda urls: ["should-not-load"],
    )

    assert output == {
        "status": "images_loaded",
        "message": "Images loaded",
        "_inject_images": ["base64-current"],
    }


def test_request_images_loads_recent_image_urls_when_no_current_images():
    loaded_urls = []

    def load_images(urls):
        loaded_urls.extend(urls)
        return ["base64-history"]

    context = ToolDispatchContext(
        images=[],
        recent_image_urls=["/api/v1/calendar/photos/photo.jpg"],
        lang="zh",
    )

    output = handle_control_tool(
        ToolInvocation(id="call-1", name="request_images", arguments={}),
        context,
        load_images_from_urls=load_images,
    )

    assert loaded_urls == ["/api/v1/calendar/photos/photo.jpg"]
    assert output == {
        "status": "images_loaded",
        "message": "已加载历史消息中的图片",
        "_inject_images": ["base64-history"],
    }


def test_request_images_returns_localized_error_without_images():
    context = ToolDispatchContext(images=[], recent_image_urls=[], lang="en")

    output = handle_control_tool(
        ToolInvocation(id="call-1", name="request_images", arguments={}),
        context,
        load_images_from_urls=lambda urls: [],
    )

    assert output == {"error": "No images attached"}


def test_non_control_tool_returns_none():
    output = handle_control_tool(
        ToolInvocation(id="call-1", name="create_pet", arguments={"name": "维尼"}),
        ToolDispatchContext(),
        load_images_from_urls=lambda urls: [],
    )

    assert output is None
