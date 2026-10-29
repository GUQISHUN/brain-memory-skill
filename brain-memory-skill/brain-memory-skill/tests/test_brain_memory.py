import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "skill", "brain-memory", "scripts", "brain_memory.py")
spec = importlib.util.spec_from_file_location("brain_memory", SCRIPT)
bm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bm)

DAY = 86400.0
T0 = 1_790_000_000.0


def at(days):
    os.environ["BRAIN_NOW"] = str(T0 + days * DAY)


class BrainTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "brain.json")
        at(0)
        self.brain = bm.Brain(self.path)

    def tearDown(self):
        self.dir.cleanup()
        os.environ.pop("BRAIN_NOW", None)

    def test_store_and_recall(self):
        self.brain.store("User prefers concise answers", importance=0.7)
        self.brain.store("User likes green tea", importance=0.5)
        res = self.brain.recall("concise answers", update=False)
        self.assertEqual(res[0][0]["text"], "User prefers concise answers")

    def test_no_match_returns_empty(self):
        self.brain.store("User prefers concise answers")
        self.assertEqual(self.brain.recall("quantum chromodynamics", update=False), [])

    def test_chinese_recall(self):
        self.brain.store("用户正在学习深度学习和大语言模型")
        self.brain.store("用户喜欢喝茶")
        res = self.brain.recall("深度学习", update=False)
        self.assertTrue(res and "深度学习" in res[0][0]["text"])

    def test_duplicate_reinforces(self):
        first = self.brain.store("User develops on Linux")
        second = self.brain.store("User develops on Linux")
        self.assertEqual(second["action"], "reinforced")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.brain.mem), 1)

    def test_review_schedule_graduates_after_21_days(self):
        mid = self.brain.store("User is learning Rust", importance=0.5)["id"]
        for day in (1, 2, 4, 7, 15):
            at(day)
            self.assertEqual(self.brain.apply_review(self.brain.mem[mid], bm.now()), "advanced")
        at(21)
        self.assertEqual(self.brain.apply_review(self.brain.mem[mid], bm.now()), "graduated")
        self.assertEqual(self.brain.mem[mid]["stage"], "long")

    def test_early_review_does_not_advance(self):
        mid = self.brain.store("User is learning Rust")["id"]
        at(0.2)
        self.assertEqual(self.brain.apply_review(self.brain.mem[mid], bm.now()), "early")
        self.assertEqual(self.brain.mem[mid]["review_step"], 0)

    def test_late_review_steps_back(self):
        mid = self.brain.store("User is learning Rust")["id"]
        at(1)
        self.brain.apply_review(self.brain.mem[mid], bm.now())
        at(2)
        self.brain.apply_review(self.brain.mem[mid], bm.now())
        self.assertEqual(self.brain.mem[mid]["review_step"], 2)
        at(30)
        self.assertEqual(self.brain.apply_review(self.brain.mem[mid], bm.now()), "relearned")
        self.assertEqual(self.brain.mem[mid]["review_step"], 1)

    def test_weak_memory_is_forgotten_but_important_one_is_kept(self):
        weak = self.brain.store("Passing remark about the weather", importance=0.1)["id"]
        kept = self.brain.store("User majors in biology", importance=0.9)["id"]
        at(20)
        self.brain.consolidate()
        self.assertNotIn(weak, self.brain.mem)
        self.assertIn(kept, self.brain.mem)

    def test_pinned_never_forgotten(self):
        pid = self.brain.store("Never forget this", importance=0.1, pin=True)["id"]
        at(400)
        self.brain.consolidate()
        self.assertIn(pid, self.brain.mem)

    def test_kind_changes_stability(self):
        ep = self.brain.store("Went to the lab on Monday", kind="episodic")["id"]
        pr = self.brain.store("Always answer in a casual tone", kind="procedural")["id"]
        self.assertGreater(self.brain.mem[pr]["stability"], self.brain.mem[ep]["stability"])

    def test_kind_and_topic_filters(self):
        self.brain.store("Rust ownership rules", kind="semantic", topic="learning")
        self.brain.store("Rust meetup last night", kind="episodic", topic="social")
        res = self.brain.recall("Rust", update=False, kind="episodic")
        self.assertEqual([m["topic"] for m, _ in res], ["social"])
        res = self.brain.recall("Rust", update=False, topic="learning")
        self.assertEqual([m["kind"] for m, _ in res], ["semantic"])

    def test_abstraction_candidates(self):
        for text in ("Finished stack lab", "Finished queue lab", "Finished tree lab"):
            self.brain.store(text, kind="episodic", topic="coding")
        report = self.brain.consolidate(dry_run=True)
        self.assertIn("coding", report["abstraction_candidates"])

    def test_dry_run_changes_nothing(self):
        self.brain.store("Passing remark", importance=0.1)
        before = json.dumps(self.brain.mem, sort_keys=True)
        at(30)
        self.brain.consolidate(dry_run=True)
        self.assertEqual(before, json.dumps(self.brain.mem, sort_keys=True))

    def test_forget_removes_memory_and_links(self):
        a = self.brain.store("Rust ownership and borrowing rules")["id"]
        b = self.brain.store("Rust borrowing and lifetimes")["id"]
        self.assertTrue(self.brain.forget(a))
        self.assertNotIn(a, self.brain.mem)
        self.assertFalse(any(a in k.split("|") for k in self.brain.edges))
        self.assertIn(b, self.brain.mem)

    def test_spatial_map_shape(self):
        self.brain.store("Fact one", kind="semantic", topic="a")
        at(5)
        self.brain.store("Event two", kind="episodic", topic="b")
        m = self.brain.spatial_map()
        self.assertEqual(len(m["nodes"]), 2)
        for n in m["nodes"]:
            for axis in ("x", "y", "z"):
                self.assertTrue(-1.0 <= n[axis] <= 1.0)
            for field in ("tags", "created", "last_access", "next_review", "review_step", "review_total", "recalls"):
                self.assertIn(field, n)

    def test_old_files_are_migrated(self):
        old = {"memories": {"abc": {"id": "abc", "text": "legacy memory", "tags": ["x"], "importance": 0.5,
                                   "created": T0, "last_access": T0, "recalls": 0, "stability": 2.5,
                                   "stage": "short", "pinned": False}}, "edges": {}, "meta": {}}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(old, f)
        brain = bm.Brain(self.path)
        m = brain.mem["abc"]
        self.assertEqual((m["kind"], m["topic"], m["review_step"]), ("semantic", "x", 0))

    def test_persistence_roundtrip(self):
        self.brain.store("Persistent fact about Linux")
        again = bm.Brain(self.path)
        self.assertEqual(len(again.mem), 1)


if __name__ == "__main__":
    unittest.main()
