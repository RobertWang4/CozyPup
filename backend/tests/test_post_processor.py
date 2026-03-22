"""Tests for the deterministic post-processor."""

from app.agents.post_processor import response_claims_action


class TestResponseClaimsAction:
    def test_chinese_claims(self):
        assert response_claims_action("好的，已记录到日历了")
        assert response_claims_action("我已经帮你记录了")
        assert response_claims_action("已添加到日历")
        assert response_claims_action("帮你设好了提醒")

    def test_english_claims(self):
        assert response_claims_action("I've recorded the event.")
        assert response_claims_action("I saved it to the calendar.")
        assert response_claims_action("I created a new reminder for you.")

    def test_no_claim(self):
        assert not response_claims_action("你好，有什么可以帮你？")
        assert not response_claims_action("Golden Retrievers usually weigh 25-35kg.")
        assert not response_claims_action("维尼上次吐是3月19日")
