"""톤 모듈 테스트. 외부 모델 없이 순수 로직과 폴백 경로를 검증한다.

실행: cd nlp-worker && python -m unittest tests.test_tone -v
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import unittest
from pathlib import Path

import numpy as np

# pipeline/__init__.py가 pycountry/gliner를 import하므로 tone만 직접 로드한다.
_TONE_PATH = Path(__file__).resolve().parent.parent / "pipeline" / "tone.py"
_spec = importlib.util.spec_from_file_location("tone_under_test", _TONE_PATH)
tone = importlib.util.module_from_spec(_spec)
sys.modules["tone_under_test"] = tone
_spec.loader.exec_module(tone)


class TestCategoryMapping(unittest.TestCase):
    """worker의 field_id 5종 → 학습 파이프라인의 분야 6종."""

    def test_field_id_maps_to_category(self):
        self.assertEqual(tone.resolve_category(1), "POLITICS")
        self.assertEqual(tone.resolve_category(2), "ECONOMY")
        self.assertEqual(tone.resolve_category(3), "SOCIETY")
        self.assertEqual(tone.resolve_category(4), "TECH")
        self.assertEqual(tone.resolve_category(5), "SPORTS")

    def test_culture_themes_override_field(self):
        # theme_catalog에 CULTURE field가 없어 문화·종교(38)/관광(37)은 field 3이다
        self.assertEqual(tone.resolve_category(3, 38), "CULTURE")
        self.assertEqual(tone.resolve_category(3, 37), "CULTURE")
        self.assertEqual(tone.resolve_category(3, 27), "SOCIETY")

    def test_unknown_field_falls_back(self):
        for bad in (None, "x", 99, -1, 0):
            self.assertEqual(tone.resolve_category(bad), "SOCIETY")

    def test_every_category_has_hypotheses(self):
        cats = set(tone.FIELD_ID_TO_CATEGORY.values()) | {"CULTURE"}
        for c in cats:
            self.assertIn(c, tone.TONE_HYPOTHESES)
            self.assertEqual(len(tone.TONE_HYPOTHESES[c]["pos"]), 3)
            self.assertEqual(len(tone.TONE_HYPOTHESES[c]["neg"]), 3)

    def test_economy_and_tech_negatives_avoid_risk(self):
        # risk 계열은 중립 기사가 과반응해 부정 축 기저율을 올린다
        for c in ("ECONOMY", "TECH"):
            for h in tone.TONE_HYPOTHESES[c]["neg"]:
                self.assertNotIn("risk", h.lower())


class TestLabelDecision(unittest.TestCase):
    def test_mixed_wins_over_larger_side(self):
        self.assertEqual(tone.decide_label(0.72, 0.69), "mixed")
        self.assertEqual(tone.decide_label(0.70, 0.65), "mixed")

    def test_neutral_when_both_weak(self):
        self.assertEqual(tone.decide_label(0.33, 0.30), "neutral")
        self.assertEqual(tone.decide_label(0.10, 0.05), "neutral")

    def test_one_sided(self):
        self.assertEqual(tone.decide_label(0.88, 0.12), "positive")
        self.assertEqual(tone.decide_label(0.10, 0.75), "negative")

    def test_tone_point_range(self):
        self.assertEqual(tone.tone_point(1.0, 0.0), 100.0)
        self.assertEqual(tone.tone_point(0.0, 1.0), 0.0)
        self.assertEqual(tone.tone_point(0.5, 0.5), 50.0)

    def test_mixed_and_neutral_can_share_a_score(self):
        """점수만 저장하면 두 라벨을 구분할 수 없다. label 병행 저장 근거."""
        a = tone.tone_point(0.72, 0.69)
        b = tone.tone_point(0.33, 0.30)
        self.assertEqual(a, b)
        self.assertNotEqual(tone.decide_label(0.72, 0.69),
                            tone.decide_label(0.33, 0.30))


class TestAggregation(unittest.TestCase):
    def test_topk_beats_mean_on_diluted_article(self):
        """중립 청크가 붙어도 topk_mean은 흔들리지 않는다."""
        pos = np.array([0.88, 0.85] + [0.15] * 8)
        neg = np.array([0.12, 0.15] + [0.45] * 8)
        self.assertEqual(tone.decide_label(pos.mean(), neg.mean()), "neutral")
        a, b = tone.agg_topk_mean(pos, neg, 2)
        self.assertEqual(tone.decide_label(a, b), "positive")

    def test_single_chunk(self):
        self.assertEqual(tone.agg_topk_mean(np.array([0.9]), np.array([0.1]), 2),
                         (0.9, 0.1))

    def test_empty(self):
        self.assertEqual(tone.agg_topk_mean(np.array([]), np.array([])), (0.0, 0.0))

    def test_deterministic_on_ties(self):
        pos = np.array([0.6, 0.6, 0.6, 0.6])
        neg = np.array([0.4, 0.4, 0.4, 0.4])
        first = tone.agg_topk_mean(pos, neg, 2)
        for _ in range(5):
            self.assertEqual(tone.agg_topk_mean(pos, neg, 2), first)

    def test_both_axes_come_from_same_chunks(self):
        """max 집계와 달리 청크를 통째로 고르므로 축이 어긋나지 않는다."""
        pos = np.array([0.9, 0.1])
        neg = np.array([0.1, 0.9])
        a, b = tone.agg_topk_mean(pos, neg, 1)
        self.assertIn((round(a, 3), round(b, 3)), [(0.9, 0.1), (0.1, 0.9)])


class TestTextHandling(unittest.TestCase):
    def test_strip_title_tail(self):
        self.assertEqual(
            tone.strip_title_tail("指定河川洪水予報＝東京都 気象庁 共同発表 | 岩手日報ONLINE"),
            "指定河川洪水予報＝東京都 気象庁 共同発表")
        self.assertEqual(tone.strip_title_tail("삼성전자 3분기 실적 발표 ｜ 한국일보"),
                         "삼성전자 3분기 실적 발표")

    def test_short_title_is_not_mangled(self):
        # 꼬리를 떼면 너무 짧아지는 경우 원본 유지
        self.assertEqual(tone.strip_title_tail("A|B"), "A|B")

    def test_boilerplate_removed_without_merging_lines(self):
        out = tone.clean_text("본문입니다.\nⓒ 연합뉴스. 무단전재 및 재배포 금지\n다음 단락.")
        self.assertNotIn("무단전재", out)
        self.assertIn("본문입니다.", out)
        self.assertIn("다음 단락.", out)
        # 상용구를 개행으로 치환하므로 앞뒤 줄이 붙지 않는다
        self.assertNotIn("본문입니다.다음", out)

    def test_sentence_split_protects_abbrev_and_decimal(self):
        s = tone.split_sentences("U.S. 경제는 3.5% 성장했다. 그러나 위험도 있다. 정말?")
        self.assertEqual(len(s), 3)
        self.assertIn("U.S.", s[0])
        self.assertIn("3.5%", s[0])

    def test_empty_inputs(self):
        self.assertEqual(tone.clean_text(None), "")
        self.assertEqual(tone.strip_title_tail(None), "")
        self.assertEqual(tone.split_sentences(""), [])


class TestSentimentContract(unittest.TestCase):
    def test_shape(self):
        s = tone.make_sentiment(0.88, 0.12, model="m", category="ECONOMY", n_chunks=3)
        for k in ("score", "label", "confidence", "p_pos", "p_neg",
                  "category", "n_chunks", "model"):
            self.assertIn(k, s)
        self.assertEqual(s["score"], 88.0)
        self.assertEqual(s["label"], "positive")

    def test_score_is_json_safe_and_in_range(self):
        import json
        for p in (0.0, 0.25, 0.5, 0.75, 1.0):
            for q in (0.0, 0.5, 1.0):
                s = tone.make_sentiment(p, q, model="m", category="TECH", n_chunks=1)
                self.assertGreaterEqual(s["score"], 0.0)
                self.assertLessEqual(s["score"], 100.0)
                json.dumps(s, allow_nan=False)


class TestFallback(unittest.TestCase):
    """모델을 못 올려도 배치가 죽지 않아야 한다."""

    def setUp(self):
        logging.disable(logging.CRITICAL)
        tone._scorer = None
        tone._load_failed = False

    def tearDown(self):
        logging.disable(logging.NOTSET)
        tone._scorer = None
        tone._load_failed = False

    def test_disabled_returns_neutral_dummy(self):
        original = tone.TONE_ENABLED
        tone.TONE_ENABLED = False
        try:
            r = tone.score_article({"article_id": "a", "title": "t", "body": "b"},
                                   field_id=2)
            self.assertEqual(r["score"], 50.0)
            self.assertEqual(r["label"], "neutral")
            self.assertEqual(r["model"], "disabled")
            self.assertEqual(r["category"], "ECONOMY")
        finally:
            tone.TONE_ENABLED = original

    def test_load_failure_falls_back_and_does_not_retry(self):
        def boom():
            raise RuntimeError("no model")
        original = tone.ToneScorer
        tone.ToneScorer = boom
        try:
            r = tone.score_article({"article_id": "a", "title": "t", "body": "b"},
                                   field_id=4)
            self.assertEqual(r["score"], 50.0)
            self.assertEqual(r["model"], "dummy")
            self.assertEqual(r["category"], "TECH")
            self.assertTrue(tone._load_failed)
            self.assertIsNone(tone.get_tone_scorer())
        finally:
            tone.ToneScorer = original

    def test_inference_error_is_isolated_per_article(self):
        class Boom:
            def score(self, *a, **k):
                raise RuntimeError("inference failed")
        tone._scorer = Boom()
        r = tone.score_article({"article_id": "a", "title": "t", "body": "b"},
                               field_id=1)
        self.assertEqual(r["model"], "error")
        self.assertEqual(r["score"], 50.0)


class TestSparkContract(unittest.TestCase):
    """spark/apps/article_event.py의 _tone_score를 실제로 통과하는지."""

    @classmethod
    def setUpClass(cls):
        spark_apps = Path(__file__).resolve().parent.parent.parent / "spark" / "apps"
        if not (spark_apps / "article_event.py").exists():
            raise unittest.SkipTest("spark/apps/article_event.py not found")
        sys.path.insert(0, str(spark_apps))
        import article_event
        cls.ae = article_event

    def test_real_scores_pass_validation(self):
        for p, q in [(1.0, 0.0), (0.0, 1.0), (0.5, 0.5), (0.88, 0.12), (0.72, 0.69)]:
            s = tone.make_sentiment(p, q, model="m", category="ECONOMY", n_chunks=2)
            self.assertEqual(self.ae._tone_score(s), s["score"])

    def test_dummy_score_passes_validation(self):
        s = tone.make_sentiment(0.0, 0.0, model="dummy", category="SOCIETY", n_chunks=0)
        self.assertEqual(self.ae._tone_score(s), 50.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestModelSourceResolution(unittest.TestCase):
    """가중치는 models/ 에서 읽는다. 없으면 폴백/실패가 명시적이어야 한다."""

    def setUp(self):
        self._dir = tone.TONE_MODEL_DIR
        self._allow = tone.TONE_ALLOW_DOWNLOAD

    def tearDown(self):
        tone.TONE_MODEL_DIR = self._dir
        tone.TONE_ALLOW_DOWNLOAD = self._allow

    def test_local_dir_is_used_offline(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "tone-teacher"
            target.mkdir()
            (target / "config.json").write_text("{}", encoding="utf-8")
            tone.TONE_MODEL_DIR = target
            source, local_only = tone.resolve_model_source()
            self.assertEqual(source, str(target))
            self.assertTrue(local_only)

    def test_falls_back_to_hub_id_when_allowed(self):
        tone.TONE_MODEL_DIR = Path("/nonexistent/tone-teacher")
        tone.TONE_ALLOW_DOWNLOAD = True
        source, local_only = tone.resolve_model_source()
        self.assertEqual(source, tone.MODEL_NAME)
        self.assertFalse(local_only)

    def test_raises_when_download_disallowed(self):
        tone.TONE_MODEL_DIR = Path("/nonexistent/tone-teacher")
        tone.TONE_ALLOW_DOWNLOAD = False
        with self.assertRaises(FileNotFoundError):
            tone.resolve_model_source()

    def test_incomplete_dir_is_not_treated_as_local(self):
        """디렉터리만 있고 config.json 이 없으면 로컬로 보지 않는다."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "tone-teacher"
            target.mkdir()
            tone.TONE_MODEL_DIR = target
            tone.TONE_ALLOW_DOWNLOAD = False
            with self.assertRaises(FileNotFoundError):
                tone.resolve_model_source()

    def test_default_dir_follows_models_convention(self):
        self.assertEqual(tone.MODELS_DIR.name, "models")
        self.assertEqual(self._dir.name, "tone-teacher")
        self.assertEqual(self._dir.parent.name, "models")
