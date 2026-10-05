import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bounded_worker
import newsFunc
import request_policy


class RequestPolicyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "state.json"
        state_patch = patch.object(request_policy, "STATE_PATH", self.path)
        state_patch.start()
        self.addCleanup(state_patch.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_spacing_survives_state_reload_and_does_not_delay_other_hosts(self):
        with patch.object(request_policy.time, "time", return_value=100), \
                patch.object(request_policy.time, "sleep") as sleep:
            self.assertTrue(request_policy.before_request("https://www.example.com/a"))
            self.assertTrue(request_policy.before_request("https://other.com/a"))
            sleep.assert_not_called()
        with patch.object(request_policy.time, "time", side_effect=[102, 102, 105]), \
                patch.object(request_policy.random, "uniform", return_value=5), \
                patch.object(request_policy.time, "sleep") as sleep:
            self.assertTrue(request_policy.before_request("https://example.com/b"))
            sleep.assert_called_once_with(3)
        self.assertEqual(json.loads(self.path.read_text())["example.com"]["last_request"], 105)

    def test_random_intervals_account_for_time_already_spent(self):
        request_policy.save_state({"example.com": {"last_request": 100}})
        with patch.object(request_policy.time, "time", side_effect=[100.25, 100.25, 100.5, 101, 101, 105.5]), \
                patch.object(request_policy.random, "uniform", side_effect=[0.5, 5]), \
                patch.object(request_policy.time, "sleep") as sleep:
            self.assertTrue(request_policy.before_request("https://example.com/a"))
            self.assertTrue(request_policy.before_request("https://example.com/b"))
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.25, 4.5])
        self.assertEqual(request_policy.load_state()["example.com"]["last_request"], 105.5)

    def test_block_persists_expires_and_respects_longer_retry_after(self):
        with patch.object(request_policy.time, "time", return_value=100):
            request_policy.record_block("https://www.example.com/a", "HTTP 429", "172800")
            self.assertFalse(request_policy.before_request("https://example.com/b"))
            self.assertEqual(request_policy.load_state()["example.com"]["blocked_until"], 172900)
        with patch.object(request_policy.time, "time", return_value=172901):
            self.assertEqual(request_policy.skip_reason("https://example.com/b"), "")

    def test_retry_after_http_date_and_invalid_header(self):
        with patch.object(request_policy.time, "time", return_value=0):
            request_policy.record_block("https://example.com", "HTTP 429", "Sat, 03 Jan 1970 00:00:00 GMT")
            self.assertEqual(request_policy.load_state()["example.com"]["blocked_until"], 172800)
            request_policy.record_block("https://other.com", "HTTP 429", "invalid")
            self.assertEqual(request_policy.load_state()["other.com"]["blocked_until"], 86400)

    def test_researchgate_preserves_feed_without_starting_browser(self):
        row = {"link": "https://www.researchgate.net/publication/123", "summary": "Feed excerpt", "title": "Paper"}
        with patch.object(newsFunc, "_browser_session") as browser:
            result = bounded_worker.fetch_article(row, self.path.with_name("checkpoint.json"))
        browser.assert_not_called()
        self.assertEqual(result["article"]["text"], "Feed excerpt")
        self.assertEqual(result["article"]["error"], "Y")
        self.assertTrue(request_policy.skip_reason("https://sub.researchgate.net/a"))
        self.assertFalse(request_policy.skip_reason("https://researchgate.net.example.com/a"))

    def test_financial_times_preserves_original_feed_without_starting_browser(self):
        for host in ("ft.com", "www.ft.com", "markets.ft.com"):
            with self.subTest(host=host):
                row = {"link": f"https://{host}/content/123", "summary": "Original FT feed excerpt", "title": "FT story"}
                with patch.object(newsFunc, "_browser_session") as browser:
                    result = bounded_worker.fetch_article(row, self.path.with_name("checkpoint.json"))
                browser.assert_not_called()
                self.assertEqual(result["article"]["text"], row["summary"])
                self.assertEqual(result["article"]["description"], row["summary"])
                self.assertEqual(result["article"]["title"], row["title"])
                self.assertEqual(result["article"]["error"], "Y")
        self.assertFalse(request_policy.skip_reason("https://ft.com.example.com/a"))

    def test_blocked_html_is_discarded_and_stops_later_navigations(self):
        url = "https://example.com/article"
        page = Mock()
        page.url = url
        page.content.return_value = "<html><title>Unusual activity</title><p>Access temporarily blocked.</p></html>"
        browser = Mock()
        browser.new_context.return_value.new_page.return_value = page
        self.assertEqual(newsFunc._fetch_article_with_browser(url, browser), "")
        self.assertTrue(request_policy.skip_reason(url))
        browser.new_context.reset_mock()
        self.assertEqual(newsFunc._fetch_article_with_browser(url, browser), "")
        browser.new_context.assert_not_called()

    def test_http_block_is_saved_before_html_capture(self):
        url = "https://example.com/article"
        page = Mock()
        response = Mock(status=429, url=url, headers={"retry-after": "172800"})
        response.request.resource_type = "document"
        response.frame = page.main_frame
        def navigate(*args, **kwargs):
            handler = page.on.call_args.args[1]
            handler(response)
        page.goto.side_effect = navigate
        browser = Mock()
        browser.new_context.return_value.new_page.return_value = page
        self.assertEqual(newsFunc._fetch_article_with_browser(url, browser), "")
        page.content.assert_not_called()
        self.assertTrue(request_policy.skip_reason(url))

    def test_client_navigation_to_researchgate_is_aborted(self):
        url = "https://example.com/article"
        page = Mock()
        route = Mock()
        route.request.resource_type = "document"
        route.request.frame = page.main_frame
        route.request.url = "https://www.researchgate.net/publication/123"
        def navigate(*args, **kwargs):
            handler = page.route.call_args.args[1]
            handler(route)
        page.goto.side_effect = navigate
        browser = Mock()
        browser.new_context.return_value.new_page.return_value = page
        self.assertEqual(newsFunc._fetch_article_with_browser(url, browser), "")
        route.abort.assert_called_once()
        route.continue_.assert_not_called()

    def test_challenge_detector_ignores_scripts_and_long_article_body(self):
        self.assertTrue(newsFunc.block_page_reason("<title>Security check</title><p>Verify you are human</p>"))
        self.assertFalse(newsFunc.block_page_reason('<script>"unusual activity"</script><article>A regular story.</article>'))
        html = "<title>News story</title><article>Police reported unusual activity. " + "Reporting details. " * 200 + "</article>"
        self.assertFalse(newsFunc.block_page_reason(html))


if __name__ == "__main__":
    unittest.main()
