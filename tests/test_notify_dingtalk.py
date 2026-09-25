import unittest

from notify_dingtalk import _filter_highlights, build_message


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


if __name__ == "__main__":
    unittest.main()
