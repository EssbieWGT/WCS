import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import bounded_worker
import getFunc
import newsFunc
import process_limits
import run_scripts
from safe_files import atomic_text_file


class PipelineLimitsTests(unittest.TestCase):
    def test_log_file_updates_before_script_and_batch_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            logfile = directory / "live.log"
            logfile.write_text("launcher started\n", encoding="utf-8")
            script = directory / "progress.py"
            script.write_text(
                "import sys,time\n"
                "print('stdout marker', flush=True)\n"
                "print('stderr marker', file=sys.stderr, flush=True)\n"
                "sys.stdout.write('progress 1/2\\r'); sys.stdout.flush()\n"
                "time.sleep(3)\n"
                "print('script complete', flush=True)\n"
            )
            result = []

            def run_batch():
                with run_scripts.live_logging(logfile):
                    result.append(run_scripts.run_scripts(
                        [script], script_timeout=8, idle_timeout=5, run_timeout=10,
                    ))

            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                runner = threading.Thread(target=run_batch)
                runner.start()
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline:
                    live_content = logfile.read_text(encoding="utf-8")
                    if "progress 1/2" in live_content:
                        break
                    time.sleep(0.02)
                still_running = runner.is_alive()
                runner.join(timeout=10)
            self.assertTrue(still_running)
            self.assertIn("stdout marker", live_content)
            self.assertIn("stderr marker", live_content)
            self.assertIn("progress 1/2", live_content)
            self.assertNotIn("script complete", live_content)
            final_content = logfile.read_text(encoding="utf-8")
            self.assertTrue(final_content.startswith("launcher started\n"))
            self.assertIn("START", final_content)
            self.assertIn("END", final_content)
            self.assertIn("Run finished", final_content)
            self.assertEqual(result, [0])

    def test_output_is_visible_while_script_is_still_running(self):
        first_output = threading.Event()

        class LiveOutput(io.StringIO):
            def write(self, value):
                if "live output marker" in value:
                    first_output.set()
                return super().write(value)

        result = []
        with contextlib.redirect_stdout(LiveOutput()):
            runner = threading.Thread(target=lambda: result.append(run_scripts.run_command(
                [sys.executable, "-u", "-c", "import time; print('live output marker', flush=True); time.sleep(3)"],
                timeout=8, idle_timeout=5,
            )))
            runner.start()
            visible_during_run = first_output.wait(timeout=1.5)
            still_running = runner.is_alive()
            runner.join(timeout=10)
        self.assertTrue(visible_during_run, "output was buffered until the child exited")
        self.assertTrue(still_running)
        self.assertEqual(result, [(0, None)])

    def test_timeout_stops_child_processes_too(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "orphan_completed"
            child_code = f"import time; from pathlib import Path; time.sleep(1.5); Path({str(marker)!r}).write_text('orphan')"
            parent_code = f"import subprocess,sys,time; subprocess.Popen([sys.executable, '-c', {child_code!r}]); print('child started', flush=True); time.sleep(60)"
            with contextlib.redirect_stdout(io.StringIO()):
                code, reason = run_scripts.run_command(
                    [sys.executable, "-u", "-c", parent_code], timeout=0.5, idle_timeout=10,
                )
            time.sleep(1.7)
            self.assertEqual(code, 124)
            self.assertFalse(marker.exists(), "a child survived the timeout")

    def test_silent_hang_times_out_and_next_script_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            hung = directory / "hung.py"
            hung.write_text("import time\ntime.sleep(60)\n")
            failed = directory / "failed.py"
            failed.write_text("raise RuntimeError('fixture failure')\n")
            good = directory / "good.py"
            marker = directory / "completed"
            good.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('done')\n")
            started = time.monotonic()
            with contextlib.redirect_stdout(io.StringIO()):
                result = run_scripts.run_scripts(
                    [hung, failed, good], script_timeout=2,
                    idle_timeout=0.5, run_timeout=10,
                )
            self.assertEqual(result, 1)
            self.assertTrue(marker.exists())
            self.assertLess(time.monotonic() - started, 8)

    def test_busy_script_still_has_absolute_deadline(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code, reason = run_scripts.run_command(
                [sys.executable, "-u", "-c", "import time\nwhile True:\n print('busy', flush=True)\n time.sleep(.05)"],
                timeout=0.6, idle_timeout=10,
            )
        self.assertEqual(code, 124)
        self.assertIn("elapsed-time", reason)

    def test_article_hang_uses_feed_fallback_and_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            # Exercise the actual process deadline, with a deliberately stuck worker.
            (directory / "bounded_worker.py").write_text(
                "import json,sys,time\n"
                "row=json.load(sys.stdin)\n"
                "if row['link'].endswith('hung'):\n"
                " print('Navigation incomplete; checking loaded HTML', file=sys.stderr, flush=True)\n"
                " time.sleep(60)\n"
                "json.dump({'article': {'url': row['link'], 'error':'N'}, 'bytes':12, 'captured':1},sys.stdout)\n"
            )
            rows = [
                {"link": "https://example.com/hung", "summary": "Feed excerpt", "title": "Hung"},
                {"link": "https://example.com/good", "title": "Good"},
            ]
            with patch.object(process_limits, "__file__", str(directory / "process_limits.py")), \
                    patch.object(newsFunc, "ARTICLE_DEADLINE_SECONDS", 0.5), \
                    contextlib.redirect_stdout(io.StringIO()):
                result = newsFunc.process_articles(rows, min_delay=0, max_delay=0)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["text"], "Feed excerpt")
            self.assertEqual(result[0]["error"], "Y")
            self.assertEqual(result[1]["url"], rows[1]["link"])
            self.assertEqual(result[1]["error"], "N")

    def test_timeout_retains_content_saved_before_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            worker = directory / "checkpoint_worker.py"
            worker.write_text(
                "import json,sys,time\n"
                "json.load(sys.stdin)\n"
                "with open(sys.argv[2], 'w', encoding='utf-8') as handle:\n"
                " json.dump({'article': {'text': 'Already extracted body', 'error': 'N'}, 'bytes': 30, 'captured': 1}, handle)\n"
                "time.sleep(60)\n"
            )
            with contextlib.redirect_stdout(io.StringIO()):
                result = process_limits.run_worker("article", {}, 0.5, worker_path=worker)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["article"]["text"], "Already extracted body")
            self.assertEqual(result["article"]["error"], "N")

    def test_failed_feed_does_not_skip_later_feed(self):
        feeds = getFunc.pd.DataFrame([
            {"url": "https://example.com/bad", "name": "Bad"},
            {"url": "https://example.com/good", "name": "Good"},
        ])
        entry = {"link": "https://example.com/story", "title": "Story", "date": "2026-10-02", "summary": "Summary"}
        with patch.object(getFunc, "run_worker", side_effect=[subprocess.TimeoutExpired("feed", 30), {"entries": [entry]}]), \
                contextlib.redirect_stdout(io.StringIO()):
            result = getFunc.get_multi_feed(feeds)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Good")
        self.assertEqual(result[0]["date"], "2026-10-02")

    def test_feed_date_alias_survives_worker_json(self):
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Story</title><updated>2026-10-02T12:00:00Z</updated><link href="https://example.com/story" /></entry></feed>'
        class Response:
            url = "https://example.com/feed"
            headers = {"content-type": "application/atom+xml"}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def raise_for_status(self): pass
            def iter_content(self, size): return iter([xml])
        with patch("requests.get", return_value=Response()):
            result = json.loads(json.dumps(bounded_worker.fetch_feed("https://example.com/feed")))
        self.assertEqual(result["entries"][0]["date"], "2026-10-02T12:00:00Z")

    def test_failed_write_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "data.csv"
            target.write_text("previous complete data")
            with self.assertRaises(RuntimeError):
                with atomic_text_file(target) as handle:
                    handle.write("partial new data")
                    raise RuntimeError("interrupted")
            self.assertEqual(target.read_text(), "previous complete data")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
