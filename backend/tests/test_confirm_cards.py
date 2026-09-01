from app.agents.confirm_cards import confirm_card_details


def test_create_pet_confirm_card_uses_label_value_rows_in_zh():
    details = confirm_card_details(
        "create_pet",
        {"name": "维尼", "gender": "male", "breed": "可卡布", "species": "dog"},
        "zh",
    )

    assert details == {
        "title": "新增宠物确认",
        "action_kind": "create_pet",
        "fields": [
            {"label": "名字", "value": "维尼"},
            {"label": "性别", "value": "公"},
            {"label": "品种", "value": "可卡布"},
        ],
    }


def test_create_pet_confirm_card_falls_back_to_species_when_breed_missing():
    details = confirm_card_details(
        "create_pet",
        {"name": "Max", "species": "dog"},
        "en",
    )

    assert details == {
        "title": "Confirm New Pet",
        "action_kind": "create_pet",
        "fields": [
            {"label": "Name", "value": "Max"},
            {"label": "Type", "value": "Dog"},
        ],
    }
