import json
import re
import unittest
from unittest import mock

from notify_dingtalk import _filter_highlights, _send_highlights, build_message


class NotifyDingTalkTests(unittest.TestCase):
    def test_high_rating_or_explicit_deep_read_recommendation_qualifies(self):
        papers = [
            {"arxiv_id": "high", "rating": 4, "tldr": "方法有创新，可选读。"},
            {"arxiv_id": "worth", "rating": 3, "tldr": "对团队实验有帮助，值得精读。"},
            {"arxiv_id": "suggest", "rating": 2, "tldr": "建议精读评测设计。"},
            {"arxiv_id": "recommend", "rating": 3, "tldr": "推荐精读方法部分。"},
            {"arxiv_id": "optional", "rating": 3, "tldr": "有些启发，可选读。"},
            {"arxiv_id": "skip", "rating": 3, "tldr": "贡献有限，可跳过。"},
            {"arxiv_id": "negative", "rating": 3, "tldr": "不值得精读，可选读。"},
            {"arxiv_id": "negative_suggest", "rating": 3, "tldr": "不建议精读。"},
            {"arxiv_id": "empty", "rating": 5, "tldr": "  "},
        ]

        selected = _filter_highlights(papers, min_rating=4)

        self.assertEqual(
            {"high", "worth", "suggest", "recommend"},
            {paper["arxiv_id"] for paper in selected},
        )

    def test_since_date_applies_to_deep_read_recommendations(self):
        papers = [
            {"arxiv_id": "old", "date": "2026-09-20", "rating": 3, "tldr": "值得精读。"},
            {"arxiv_id": "new", "date": "2026-09-21", "rating": 3, "tldr": "值得精读。"},
        ]

        selected = _filter_highlights(papers, min_rating=4, since_date="2026-09-21")

        self.assertEqual(["new"], [paper["arxiv_id"] for paper in selected])

    def test_message_describes_both_selection_paths(self):
        paper = {
            "arxiv_id": "2609.12345v1",
            "title": "Example",
            "rating": 3,
            "relevance": 3,
            "tldr": "值得精读。",
        }

        title, body = build_message([paper], "https://example.com", min_rating=4)

        self.assertIn("值得关注论文", title)
        self.assertIn("创新度 ≥ 4⭐ 或推荐精读", body)
        self.assertNotIn("4⭐+ 论文", title)

    def test_large_chinese_batch_is_split_by_request_bytes(self):
        papers = [
            {
                "arxiv_id": f"2609.{i:05d}v1",
                "title": f"中文世界模型论文 {i} 🚀",
                "url": f"https://arxiv.org/abs/2609.{i:05d}",
                "date": "2026-09-29",
                "rating": 3,
                "relevance": 3,
                "tldr": "世界模型的几何表示与动作预测值得精读。" * 6,
            }
            for i in range(80)
        ]
        sent_messages = []

        def record_send(url, title, body):
            payload = {"msgtype": "markdown", "markdown": {"title": title, "text": body}}
            size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            self.assertLessEqual(size, 20000)
            sent_messages.append((title, body))
            return {"errcode": 0}

        with (
            mock.patch("notify_dingtalk.load_config", return_value={}),
            mock.patch("notify_dingtalk._dingtalk_settings", return_value=({}, "webhook", 4, "https://example.com")),
            mock.patch("notify_dingtalk.resolve_bot_url", return_value="https://example.com/webhook"),
            mock.patch("notify_dingtalk.send_markdown", side_effect=record_send),
            mock.patch("notify_dingtalk.time.sleep"),
        ):
            self.assertEqual(80, _send_highlights(papers))

        self.assertGreater(len(sent_messages), 1)
        for part_number, (title, _) in enumerate(sent_messages, 1):
            self.assertTrue(title.endswith(f" ({part_number}/{len(sent_messages)})"))
        numbers = [int(n) for _, body in sent_messages for n in re.findall(r"#### (\d+)\.", body)]
        self.assertEqual(list(range(1, 81)), numbers)

    def test_oversized_single_paper_is_rejected_before_sending(self):
        paper = {
            "arxiv_id": "2609.99999v1",
            "title": "Example",
            "rating": 3,
            "relevance": 3,
            "tldr": "中文" * 12000,
        }
        with (
            mock.patch("notify_dingtalk.load_config", return_value={}),
            mock.patch("notify_dingtalk._dingtalk_settings", return_value=({}, "webhook", 4, "https://example.com")),
            mock.patch("notify_dingtalk.resolve_bot_url", return_value="https://example.com/webhook"),
            mock.patch("notify_dingtalk.send_markdown") as send,
        ):
            with self.assertRaisesRegex(ValueError, "2609.99999v1"):
                _send_highlights([paper])
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
