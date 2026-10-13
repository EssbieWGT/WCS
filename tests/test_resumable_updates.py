import ast
import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aiFunc
import getFunc as gf
import newsFunc
import run_scripts
import resumable_updates as updates
from process_limits import atomic_json_write
from update_queue import UpdateQueue, UpdateBusy, update_lock, PENDING_EXIT


class ResumableUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for folder in ("masterdata", "data", "uploads", "timestamps"):
            (self.root / folder).mkdir()
        self.outputs = {
            "archive": str(self.root / "masterdata/test.csv"),
            "data": str(self.root / "data/test.csv"),
            "uploads": str(self.root / "uploads/test.csv"),
            "timestamps": str(self.root / "timestamps/test.json"),
            "rejects": None, "days": 3, "sentiment": False, "companies": None,
        }
        self.path = self.root / "masterdata/pending/test.json"
        self.now = datetime.now(timezone.utc).isoformat()
        self.rows = [{"link": f"https://example.com/{i}", "title": f"Story {i}",
                      "date": self.now, "summary": "Feed excerpt"} for i in range(3)]
        self.result = lambda row: {
            "url": row["link"], "title": row["title"], "published": row["date"],
            "description": "Description", "image": "", "text": "Completed article", "error": "N", "firstEyes": "2026-10-13T10:00:00",
        }
        self.environment = patch.dict(os.environ, {"WCS_RESUME_ONLY": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        deadline = os.environ.pop("WCS_WORK_DEADLINE", None)
        if deadline is not None:
            self.addCleanup(os.environ.__setitem__, "WCS_WORK_DEADLINE", deadline)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def queue(self, stage="review"):
        queue = UpdateQueue(self.path, self.outputs)
        queue.add(self.rows, "article")
        for item in queue.state["items"]:
            item["stage"] = stage
            if stage in ("done", "sentiment"):
                item["result"] = self.result(item["row"])
        queue.save()
        return queue

    def run_update(self, **options):
        options = {**self.outputs, "sources": Mock(side_effect=AssertionError("resume fetched new feeds")), **options}
        return updates.run_update("test", **options)

    def test_classification_progress_survives_failure_and_is_not_repeated(self):
        self.queue()

        def interrupted(rows, on_decision, should_stop):
            on_decision(rows[0], "accepted")
            raise RuntimeError("interrupted review")

        with self.assertRaisesRegex(RuntimeError, "interrupted review"):
            self.run_update(classifier=interrupted)
        saved = UpdateQueue(self.path)
        self.assertEqual([item["stage"] for item in saved.state["items"]], ["article", "review", "review"])
        reviewed = []

        def complete(rows, on_decision, should_stop):
            reviewed.extend(row["link"] for row in rows)
            for row in rows:
                on_decision(row, "accepted")

        with patch.object(newsFunc, "process_articles", side_effect=lambda rows, **kw: [self.result(rows[0])]):
            self.assertEqual(self.run_update(classifier=complete), 0)
        self.assertEqual(reviewed, [row["link"] for row in self.rows[1:]])
        self.assertFalse(self.path.exists())
        self.assertEqual(len(gf.pd.read_csv(self.outputs["archive"])), 3)

    def test_failed_model_call_stays_queued_while_other_articles_finish(self):
        self.queue()

        def classify(rows, on_decision, should_stop):
            for row in rows:
                on_decision(row, "failed" if row == self.rows[0] else "accepted")

        with patch.object(newsFunc, "process_articles", side_effect=lambda rows, **kw: [self.result(rows[0])]):
            self.assertEqual(self.run_update(classifier=classify), PENDING_EXIT)
        self.assertEqual(len(gf.pd.read_csv(self.outputs["archive"])), 2)
        pending = UpdateQueue(self.path).state["items"]
        self.assertEqual([item["row"]["link"] for item in pending], [self.rows[0]["link"]])

    def test_soft_deadline_flushes_completed_work_without_starting_another_article(self):
        queue = self.queue("article")
        queue.state["items"][0].update(stage="done", result=self.result(self.rows[0]))
        queue.save()
        with patch.dict(os.environ, {"WCS_WORK_DEADLINE": "1"}), \
                patch.object(newsFunc, "process_articles") as process:
            self.assertEqual(self.run_update(), PENDING_EXIT)
        process.assert_not_called()
        self.assertEqual(len(gf.pd.read_csv(self.outputs["data"])), 1)
        self.assertEqual(UpdateQueue(self.path).pending, 2)

    def test_failed_export_keeps_results_and_recovery_is_idempotent(self):
        queue = self.queue("done")
        original = updates.gf.write_csv_atomic

        def fail_export(data, path):
            if path == self.outputs["data"]:
                raise OSError("export unavailable")
            original(data, path)

        with patch.object(updates.gf, "write_csv_atomic", side_effect=fail_export):
            with self.assertRaisesRegex(OSError, "export unavailable"):
                updates.flush_queue(queue)
        self.assertTrue(self.path.exists())
        self.assertEqual(len(gf.pd.read_csv(self.outputs["archive"])), 3)
        updates.flush_file(self.path)
        self.assertFalse(self.path.exists())
        for path in (self.outputs["archive"], self.outputs["data"], self.outputs["uploads"]):
            self.assertEqual(len(gf.pd.read_csv(path)), 3)

    def test_interrupted_sentiment_publishes_body_and_later_updates_same_url(self):
        self.outputs["sentiment"] = True
        queue = self.queue("sentiment")
        updates.flush_queue(queue)
        self.assertEqual(len(gf.pd.read_csv(self.outputs["data"])), 3)
        self.assertTrue(self.path.exists())
        timestamp = json.loads(Path(self.outputs["timestamps"]).read_text())[-1]
        self.assertEqual(timestamp["entries"], 0)
        self.assertEqual(timestamp["pending"], 3)
        self.assertTrue(timestamp["partial"])
        with patch.object(aiFunc, "tricare_sentiment_analysis", return_value=[1]), \
                patch.object(newsFunc, "process_articles") as process:
            self.assertEqual(self.run_update(), 0)
        process.assert_not_called()
        saved = gf.pd.read_csv(self.outputs["archive"])
        self.assertEqual(len(saved), 3)
        self.assertEqual(saved.sentiment.tolist(), [1, 1, 1])
        self.assertTrue(all(saved.firstEyes.str.startswith("2026-10-13 10:00:00")))

    def test_hard_kill_recovers_completed_and_inflight_content_then_resumes(self):
        worker = self.root / "worker.py"
        worker.write_text(
            "import json,sys,time\n"
            "from pathlib import Path\n"
            "row=json.load(sys.stdin)\n"
            "result={'article': {'url':row['link'], 'title':row['title'], 'published':row['date'], "
            "'firstEyes':'2026-10-13T10:00:00', 'description':'Description', 'image':'', 'text':'Extracted body', 'error':'N'}, 'bytes':10, 'captured':1}\n"
            "Path(sys.argv[2]).write_text(json.dumps(result),encoding='utf-8')\n"
            "if row['link'].endswith('/1'): time.sleep(60)\n"
            "json.dump(result,sys.stdout)\n", encoding="utf-8",
        )
        fixture = self.root / "fixture.py"
        fixture.write_text(
            f"import sys\nsys.path.insert(0,{str(SCRIPTS)!r})\n"
            "import newsFunc,process_limits\n"
            "from resumable_updates import run_update\n"
            "def classify(rows,on_decision,should_stop):\n"
            " for row in rows: on_decision(row,'accepted')\n"
            f"newsFunc.run_worker=lambda op,row,timeout,**kw: process_limits.run_worker(op,row,timeout,worker_path={str(worker)!r},**kw)\n"
            f"sys.exit(run_update('test',sources=lambda: [],classifier=classify,**{self.outputs!r}))\n",
            encoding="utf-8",
        )
        self.queue()
        code, reason = run_scripts.run_command([sys.executable, "-u", str(fixture)], timeout=5, idle_timeout=10)
        self.assertEqual(code, 124)
        queue = UpdateQueue(self.path)
        self.assertEqual(queue.state["items"][0]["stage"], "done")
        self.assertEqual(queue.state["active_url"], self.rows[1]["link"])
        updates.flush_file(self.path)
        saved = gf.pd.read_csv(self.outputs["data"])
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved.text.tolist(), ["Extracted body", "Extracted body"])
        # The interrupted article's saved body finishes it, avoiding the same
        # hanging URL on continuation. Only the third article remains.
        code, reason = run_scripts.run_command([sys.executable, "-u", str(fixture)], timeout=8, idle_timeout=10)
        self.assertEqual(code, 0, reason)
        self.assertFalse(self.path.exists())
        self.assertEqual(len(gf.pd.read_csv(self.outputs["archive"])), 3)

    def test_queue_lock_rejects_a_second_owner(self):
        with update_lock(self.path.with_suffix(".lock")):
            with self.assertRaises(UpdateBusy):
                with update_lock(self.path.with_suffix(".lock")):
                    pass
        with update_lock(self.path.with_suffix(".lock")):
            pass

    def test_bad_queue_is_reported_instead_of_silently_discarded(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            self.run_update()
        self.assertEqual(self.path.read_text(), "{broken")

    def test_fresh_collection_is_saved_per_feed_and_resumes_remaining_sources(self):
        sources = [{"url": "https://example.com/feed1", "mode": "preview"},
                   {"url": "https://example.com/feed2", "mode": "preview"}]

        def first_feed(frame):
            os.environ["WCS_WORK_DEADLINE"] = "1"
            return self.rows

        with patch.dict(os.environ, {"WCS_RESUME_ONLY": "0"}), \
                patch.object(gf, "get_multi_feed", side_effect=first_feed):
            self.assertEqual(self.run_update(sources=lambda: sources), PENDING_EXIT)
        queue = UpdateQueue(self.path)
        self.assertEqual(queue.state["sources"], sources[1:])
        self.assertEqual(len(queue.state["items"]), 3)
        os.environ.pop("WCS_WORK_DEADLINE", None)
        reviewed = []

        def classify(rows, on_decision, should_stop):
            reviewed.extend(rows)
            for row in rows:
                on_decision(row, "accepted")

        with patch.object(gf, "get_multi_feed", return_value=self.rows) as fetch, \
                patch.object(gf, "get_link_preview", side_effect=self.result):
            self.assertEqual(self.run_update(classifier=classify), 0)
        self.assertEqual(fetch.call_args.args[0].url.tolist(), [sources[1]["url"]])
        self.assertEqual(len(reviewed), 3, "duplicate URLs from another feed were reviewed again")
        self.assertEqual(len(gf.pd.read_csv(self.outputs["data"])), 3)

    def test_existing_state_articles_keep_their_text_without_refetching(self):
        queue = self.queue("article")
        for item in queue.state["items"]:
            item["mode"] = "ready"
            item["row"].update(self.result(item["row"]))
        queue.save()
        with patch.object(newsFunc, "process_articles") as article, \
                patch.object(gf, "get_link_preview") as preview:
            self.assertEqual(self.run_update(), 0)
        article.assert_not_called()
        preview.assert_not_called()
        self.assertEqual(gf.pd.read_csv(self.outputs["data"]).text.tolist(), ["Completed article"] * 3)

    def test_update_entrypoints_use_matching_queues_and_preserve_output_windows(self):
        import runpy
        from update_queue import queue_path
        for filename in run_scripts.SCRIPTS:
            if filename == "gitPush.py":
                continue
            with self.subTest(script=filename), patch.object(updates, "run_update", return_value=0) as update:
                with self.assertRaises(SystemExit) as result:
                    runpy.run_path(str(SCRIPTS / filename), run_name="__main__")
                self.assertEqual(result.exception.code, 0)
                name = update.call_args.args[0]
                self.assertEqual(name, queue_path(SCRIPTS / filename).stem)
                expected_days = 7 if name == "joly" else 3
                self.assertEqual(update.call_args.kwargs.get("days", 3), expected_days)

    def test_ai_callbacks_distinguish_accept_reject_and_retryable_failure(self):
        client = Mock()
        client.generate.side_effect = [{"response": "interested"}, {"response": "not interested"}, RuntimeError("offline")]
        decisions = []
        with patch.object(aiFunc.ollama, "Client", return_value=client):
            aiFunc.ai_filter_engine(self.rows, lambda *args: "prompt", reject_path=str(self.root / "rejects.csv"),
                                   on_decision=lambda row, outcome: decisions.append(outcome))
        self.assertEqual(decisions, ["accepted", "rejected", "failed"])

    def test_checkpoint_failure_is_not_swallowed_as_an_ai_failure(self):
        client = Mock()
        client.generate.return_value = {"response": "interested"}
        with patch.object(aiFunc.ollama, "Client", return_value=client):
            with self.assertRaisesRegex(OSError, "disk full"):
                aiFunc.ai_filter_engine(self.rows, lambda *args: "prompt", reject_path=str(self.root / "rejects.csv"),
                                       on_decision=Mock(side_effect=OSError("disk full")))

    def test_failed_worker_preserves_its_extracted_body(self):
        checkpoint = self.root / "attempt.json"
        result = self.result(self.rows[0])
        atomic_json_write(checkpoint, {"article": result, "bytes": 10, "captured": 1})
        with patch.object(newsFunc, "run_worker", side_effect=RuntimeError("cleanup failed")):
            saved = newsFunc.process_articles(self.rows[:1], min_delay=0, max_delay=0, checkpoint_path=checkpoint)
        self.assertEqual(saved, [result])

    def test_epn_checkpoints_a_batch_before_starting_the_next(self):
        # Exercise classification logic without loading a real GPU model.
        tree = ast.parse((SCRIPTS / "zeroAI.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "batch_classify_articles")
        namespace = {"pd": gf.pd, "os": os, "EPN_NO_PATH": str(self.root / "epnNo.csv"),
                     "tqdm": lambda items, **kwargs: items,
                     "get_classifier": lambda: lambda titles, *args, **kw: [{"labels": ["Issue"], "scores": [0.9]} for _ in titles]}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "zeroAI.py", "exec"), namespace)
        decisions = []
        rows = self.rows * 6
        result = namespace["batch_classify_articles"](
            rows, [{"prompt_label": "Issue", "name": "Name", "threshold": 0.7}],
            on_decision=lambda row, outcome: decisions.append((row, outcome)),
            should_stop=lambda: bool(decisions),
        )
        self.assertEqual(len(result), 16)
        self.assertEqual(len(decisions), 16)
        self.assertTrue(all(row["name"] == "Name" and outcome == "accepted" for row, outcome in decisions))


class BatchContinuationTests(unittest.TestCase):
    def test_other_scripts_and_first_push_precede_resume_and_second_push(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queuefile = root / "queue.json"
            scripts = [root / "slow.py", root / "other.py", root / "gitPush.py"]
            calls = []

            def command(command, timeout, idle_timeout, *, env_overrides):
                name = Path(command[-1]).name
                resume = env_overrides.get("WCS_RESUME_ONLY") == "1"
                calls.append((name, resume))
                if name == "slow.py":
                    if resume:
                        queuefile.unlink()
                    else:
                        queuefile.write_text("pending")
                        return PENDING_EXIT, None
                return 0, None

            with patch.object(run_scripts, "queue_path", side_effect=lambda script: queuefile if script.name == "slow.py" else root / "absent.json"), \
                    patch.object(run_scripts, "run_command", side_effect=command), \
                    contextlib.redirect_stdout(io.StringIO()):
                result = run_scripts.run_scripts(scripts, run_timeout=1000)
            self.assertEqual(result, 0)
            self.assertEqual(calls, [("slow.py", False), ("other.py", False), ("gitPush.py", False),
                                     ("slow.py", True), ("gitPush.py", False)])

    def test_no_progress_does_not_cause_an_endless_retry_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queuefile = root / "queue.json"
            calls = []

            def command(command, *args, **kwargs):
                calls.append(Path(command[-1]).name)
                if calls[-1] == "slow.py":
                    queuefile.write_text("unchanged")
                    return PENDING_EXIT, None
                return 0, None

            with patch.object(run_scripts, "queue_path", side_effect=lambda script: queuefile if script.name == "slow.py" else root / "absent.json"), \
                    patch.object(run_scripts, "run_command", side_effect=command), \
                    contextlib.redirect_stdout(io.StringIO()):
                result = run_scripts.run_scripts([root / "slow.py", root / "gitPush.py"], run_timeout=1000)
            self.assertEqual(result, 1)
            self.assertEqual(calls, ["slow.py", "gitPush.py", "slow.py", "gitPush.py"])
            self.assertTrue(queuefile.exists())

    def test_hard_timeout_recovers_before_first_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queuefile = root / "queue.json"
            calls = []

            def command(command, *args, env_overrides, **kwargs):
                if "--flush" in command:
                    calls.append("recovery")
                    queuefile.write_text("recovered; remainder pending")
                else:
                    name = Path(command[-1]).name
                    calls.append(name)
                    if name == "slow.py":
                        if env_overrides["WCS_RESUME_ONLY"] == "1":
                            queuefile.unlink()
                        else:
                            queuefile.write_text("completed articles")
                            return 124, "elapsed-time limit"
                    if name == "gitPush.py" and len(calls) == 3:
                        self.assertIn("recovered", queuefile.read_text())
                return 0, None

            with patch.object(run_scripts, "queue_path", side_effect=lambda script: queuefile if script.name == "slow.py" else root / "absent.json"), \
                    patch.object(run_scripts, "run_command", side_effect=command), \
                    contextlib.redirect_stdout(io.StringIO()):
                result = run_scripts.run_scripts([root / "slow.py", root / "gitPush.py"], run_timeout=1000)
            self.assertEqual(result, 0)
            self.assertEqual(calls, ["slow.py", "recovery", "gitPush.py", "slow.py", "gitPush.py"])


if __name__ == "__main__":
    unittest.main()
