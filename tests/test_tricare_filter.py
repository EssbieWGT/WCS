import contextlib
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import aiFunc


class TricareFilterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        previous_directory = Path.cwd()
        os.chdir(temporary.name)
        self.addCleanup(os.chdir, previous_directory)
        self.rejects = Path("masterdata/TricareNo.csv")
        self.client = Mock()
        self.client.generate.return_value = {"response": "not interested"}
        client_patch = patch.object(aiFunc.ollama, "Client", return_value=self.client)
        client_patch.start()
        self.addCleanup(client_patch.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_reddit_is_accepted_without_model_review_even_if_previously_rejected(self):
        rows = [
            {"link": "https://www.reddit.com/r/TRICARE/comments/cached", "title": "Job posting"},
            {"link": "https://WWW.REDDIT.COM/r/Veterans/comments/new", "title": "Question"},
            {"url": "https://reddit.com/r/Military/comments/experience", "title": "Personal experience"},
        ]
        self.rejects.parent.mkdir()
        aiFunc.pd.DataFrame([dict(rows[0], date=datetime.now(timezone.utc).isoformat())]).to_csv(self.rejects, index=False)
        decisions = []
        accepted = aiFunc.tricare_interest_filter(
            rows, on_decision=lambda row, outcome: decisions.append((row, outcome))
        )
        self.assertEqual(accepted, rows)
        self.assertEqual(decisions, [(row, "accepted") for row in rows])
        self.client.generate.assert_not_called()

    def test_non_reddit_and_lookalike_urls_still_receive_model_review(self):
        urls = [
            "https://example.com/story",
            "https://www.reddit.com.example.com/post",
            "https://www.reddit.com@example.com/post",
            "https://example.com/www.reddit.com/post",
            "https://example.com/?url=https://www.reddit.com/post",
            "https://[invalid",
        ]
        rows = [{"link": url, "outlet": "Reddit", "title": "Reddit discussion"} for url in urls]
        self.assertEqual(aiFunc.tricare_interest_filter(rows), [])
        self.assertEqual(self.client.generate.call_count, len(rows))

    def test_other_topic_filters_still_review_reddit(self):
        rows = [{"link": "https://www.reddit.com/r/climate/comments/post", "title": "Discussion"}]
        self.assertEqual(aiFunc.c2es_interest_filter(rows), [])
        self.client.generate.assert_called_once()

    def test_reddit_checkpoint_failures_propagate(self):
        rows = [{"link": "https://www.reddit.com/r/TRICARE/comments/post"}]
        with self.assertRaisesRegex(OSError, "disk full"):
            aiFunc.tricare_interest_filter(rows, on_decision=Mock(side_effect=OSError("disk full")))
        self.client.generate.assert_not_called()

    def test_reddit_acceptance_respects_stop_callback(self):
        decision = Mock()
        rows = [{"link": "https://www.reddit.com/r/TRICARE/comments/post"}]
        self.assertEqual(aiFunc.tricare_interest_filter(rows, on_decision=decision, should_stop=lambda: True), [])
        decision.assert_not_called()
        self.client.generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
