#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
import sys
import time
import uuid
from collections import Counter

DAY = 86400.0
REVIEW_GAPS = [1, 1, 2, 3, 8, 6]
WINDOW_DAYS = float(sum(REVIEW_GAPS))
GRADUATED_STABILITY = 90.0
MAX_STABILITY = 365.0
KINDS = {"episodic": 1.0, "semantic": 2.0, "procedural": 3.0}
KIND_AXIS = {"episodic": -1.0, "semantic": 0.0, "procedural": 1.0}
DEFAULT_STORE = os.environ.get("BRAIN_MEMORY_PATH", "brain_memory.json")


def now():
    return float(os.environ.get("BRAIN_NOW", time.time()))


STOP_EN = set(
    "a an the and or but if of to in on at by for with from as is are was were be been am it its this that these "
    "those i you he she we they me my your his her our their what which who whom how when where why do does did "
    "so than then too very can could will would should about into over not no yes just also have has had".split()
)
STOP_ZH = set("的了是在和与也都就而")


def tokenize(text):
    text = text.lower()
    tokens = [t for t in re.findall(r"[a-z0-9_]+", text) if t not in STOP_EN]
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            if run not in STOP_ZH:
                tokens.append(run)
            continue
        tokens += [
            run[i:i + 2]
            for i in range(len(run) - 1)
            if run[i] not in STOP_ZH and run[i + 1] not in STOP_ZH
        ]
    return tokens


def cosine(a, b):
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def edge_key(a, b):
    return "|".join(sorted((a, b)))


class Brain:
    def __init__(self, path):
        self.path = path
        self.mem = {}
        self.edges = {}
        self.meta = {"last_consolidate": None}
        self.last_status = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.mem = data.get("memories", {})
            self.edges = data.get("edges", {})
            self.meta = data.get("meta", self.meta)
        for m in self.mem.values():
            m.setdefault("review_step", 0)
            m.setdefault("last_review", m.get("last_access", m["created"]))
            m.setdefault("next_review", m["last_review"] + REVIEW_GAPS[0] * DAY)
            if m["stage"] == "long":
                m.setdefault("graduated", m["last_review"])
            m.setdefault("kind", "semantic")
            m.setdefault("valence", 0.0)
            m.setdefault("topic", (m.get("tags") or ["general"])[0])

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"memories": self.mem, "edges": self.edges, "meta": self.meta},
                f,
                ensure_ascii=False,
                indent=1,
            )
        os.replace(tmp, self.path)

    def vectors(self, extra=None):
        docs = {i: Counter(tokenize(m["text"])) for i, m in self.mem.items()}
        if extra is not None:
            docs["__q__"] = Counter(tokenize(extra))
        n = max(1, len(docs))
        df = Counter()
        for c in docs.values():
            df.update(c.keys())
        out = {}
        for i, c in docs.items():
            out[i] = {k: (1 + math.log(v)) * math.log(1 + n / df[k]) for k, v in c.items()}
        return out

    def retrievability(self, m, t=None):
        if m.get("pinned"):
            return 1.0
        t = now() if t is None else t
        dt = max(0.0, (t - m["last_access"]) / DAY)
        return math.exp(-dt / m["stability"])

    def apply_review(self, m, t):
        m["last_access"] = t
        if m["stage"] == "long":
            m["stability"] = min(MAX_STABILITY, m["stability"] * 1.2)
            return "maintained"
        step = m["review_step"]
        if t < m["next_review"]:
            m["stability"] *= 1.1
            return "early"
        status = "advanced"
        if t > m["next_review"] + REVIEW_GAPS[step] * DAY:
            m["review_step"] = max(0, step - 1)
            status = "relearned"
        else:
            m["review_step"] = step + 1
        m["last_review"] = t
        if m["review_step"] >= len(REVIEW_GAPS):
            m["stage"] = "long"
            m["stability"] = GRADUATED_STABILITY
            m["graduated"] = t
            return "graduated"
        gap = REVIEW_GAPS[m["review_step"]]
        m["next_review"] = t + gap * DAY
        m["stability"] = max(m["stability"], gap * 3.0)
        return status

    def due_list(self, t=None):
        t = now() if t is None else t
        rows = [m for m in self.mem.values() if m["stage"] == "short" and not m.get("pinned") and m["next_review"] <= t]
        return sorted(rows, key=lambda m: m["next_review"])

    def link(self, a, b, w):
        k = edge_key(a, b)
        self.edges[k] = min(1.0, max(self.edges.get(k, 0.0), w))

    def neighbors(self, i):
        for k, w in self.edges.items():
            a, b = k.split("|")
            if a == i:
                yield b, w
            elif b == i:
                yield a, w

    def store(self, text, importance=0.5, tags=None, pin=False, kind="semantic", valence=0.0, topic=None):
        vecs = self.vectors(extra=text)
        q = vecs.pop("__q__")
        best, best_sim = None, 0.0
        sims = []
        for i in self.mem:
            s = cosine(q, vecs[i])
            sims.append((s, i))
            if s > best_sim:
                best, best_sim = i, s
        t = now()
        if best and best_sim >= 0.9:
            m = self.mem[best]
            m["importance"] = max(m["importance"], importance)
            m["pinned"] = m.get("pinned", False) or pin
            status = self.apply_review(m, t)
            self.save()
            return {"id": best, "action": "reinforced", "similarity": round(best_sim, 2), "review": status}
        mid = uuid.uuid4().hex[:8]
        self.mem[mid] = {
            "id": mid,
            "text": text,
            "tags": tags or [],
            "importance": importance,
            "created": t,
            "last_access": t,
            "recalls": 0,
            "stability": (1.0 + 3.0 * importance) * KINDS[kind] * (1.0 + 0.5 * abs(valence)),
            "kind": kind,
            "valence": valence,
            "topic": topic or (tags[0] if tags else "general"),
            "stage": "short",
            "pinned": pin,
            "review_step": 0,
            "last_review": t,
            "next_review": t + REVIEW_GAPS[0] * DAY,
        }
        linked = []
        for s, i in sorted(sims, reverse=True)[:5]:
            if s >= 0.15:
                self.link(mid, i, s)
                linked.append(i)
        self.save()
        return {"id": mid, "action": "stored", "linked": linked}

    def recall(self, query, k=5, update=True, kind=None, topic=None):
        vecs = self.vectors(extra=query)
        q = vecs.pop("__q__")
        t = now()
        act = {}
        direct = {}
        for i, m in self.mem.items():
            if (kind and m["kind"] != kind) or (topic and m["topic"] != topic):
                continue
            s = cosine(q, vecs[i])
            if s >= 0.1:
                direct[i] = s
                act[i] = s * (0.3 + 0.7 * self.retrievability(m, t))
        seeds = sorted(act.items(), key=lambda x: -x[1])[:3]
        spread = Counter()
        for i, a in seeds:
            for j, w in self.neighbors(i):
                if j in self.mem:
                    spread[j] += 0.5 * w * a
        for j, v in spread.items():
            act[j] = act.get(j, 0.0) + v
        ranked = [(i, a) for i, a in sorted(act.items(), key=lambda x: -x[1]) if a >= 0.05][:k]
        if update and ranked:
            ids = [i for i, _ in ranked]
            for i in ids:
                if direct.get(i, 0.0) >= 0.3:
                    m = self.mem[i]
                    m["recalls"] += 1
                    self.last_status[i] = self.apply_review(m, t)
            for x in range(len(ids)):
                for y in range(x + 1, len(ids)):
                    key = edge_key(ids[x], ids[y])
                    w = self.edges.get(key, 0.0)
                    self.edges[key] = min(1.0, w + 0.1 * (1.0 - w))
            self.save()
        return [(self.mem[i], a) for i, a in ranked]

    def consolidate(self, dry_run=False):
        t = now()
        report = {"promoted": [], "lapsed": [], "forgotten": [], "merged": [], "edges_pruned": 0}
        vecs = self.vectors()
        ids = list(self.mem)
        removed = set()
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                a, b = ids[x], ids[y]
                if a in removed or b in removed:
                    continue
                if cosine(vecs[a], vecs[b]) >= 0.85:
                    keep, drop = (a, b) if self.mem[a]["importance"] >= self.mem[b]["importance"] else (b, a)
                    report["merged"].append({"kept": keep, "dropped": drop})
                    removed.add(drop)
                    if not dry_run:
                        self.mem[keep]["recalls"] += self.mem[drop]["recalls"]
                        self.mem[keep]["stability"] = max(self.mem[keep]["stability"], self.mem[drop]["stability"])
                        self.mem[keep]["pinned"] = self.mem[keep].get("pinned") or self.mem[drop].get("pinned", False)
        for i in ids:
            if i in removed:
                continue
            m = self.mem[i]
            r = self.retrievability(m, t)
            if m["stage"] == "short" and (m["importance"] >= 0.8 or m.get("pinned")):
                report["promoted"].append(i)
                if not dry_run:
                    m["stage"] = "long"
                    m["graduated"] = t
                    m["stability"] = max(m["stability"] * 4.0, 30.0)
            elif not m.get("pinned"):
                if m["stage"] == "short" and t > m["next_review"] + REVIEW_GAPS[m["review_step"]] * DAY:
                    report["lapsed"].append({"id": i, "from_step": m["review_step"]})
                    if not dry_run:
                        m["review_step"] = max(0, m["review_step"] - 1)
                        m["next_review"] = t + REVIEW_GAPS[m["review_step"]] * DAY
                if (m["stage"] == "short" and r < 0.05 and m["importance"] < 0.6) or (
                    m["stage"] == "long" and r < 0.02 and m["importance"] < 0.4
                ):
                    report["forgotten"].append({"id": i, "text": m["text"]})
                    removed.add(i)
        if not dry_run:
            for i in removed:
                self.mem.pop(i, None)
            for k in list(self.edges):
                a, b = k.split("|")
                self.edges[k] *= 0.98
                if a not in self.mem or b not in self.mem or self.edges[k] < 0.05:
                    del self.edges[k]
                    report["edges_pruned"] += 1
            self.meta["last_consolidate"] = t
            self.save()
        groups = {}
        for m in self.mem.values():
            if m["kind"] == "episodic" and m["stage"] == "short":
                groups.setdefault(m["topic"], []).append(m["id"])
        report["abstraction_candidates"] = {k: v for k, v in groups.items() if len(v) >= 3}
        return report

    def spatial_map(self):
        mems = list(self.mem.values())
        topics = sorted({m["topic"] for m in mems})
        t0 = min((m["created"] for m in mems), default=0.0)
        t1 = max((m["created"] for m in mems), default=0.0)
        t = now()
        nodes = []
        for m in mems:
            x = 0.0 if t1 == t0 else (m["created"] - t0) / (t1 - t0) * 2 - 1
            z = 0.0 if len(topics) < 2 else topics.index(m["topic"]) / (len(topics) - 1) * 2 - 1
            nodes.append({
                "id": m["id"], "text": m["text"], "kind": m["kind"], "topic": m["topic"],
                "importance": m["importance"], "valence": m["valence"], "stage": m["stage"],
                "pinned": bool(m.get("pinned")), "retention": round(self.retrievability(m, t), 3),
                "tags": m.get("tags", []), "created": m["created"], "last_access": m["last_access"],
                "next_review": None if (m["stage"] == "long" or m.get("pinned")) else m["next_review"],
                "review_step": m["review_step"], "review_total": len(REVIEW_GAPS), "recalls": m["recalls"],
                "x": round(x, 3), "y": KIND_AXIS[m["kind"]], "z": round(z, 3),
            })
        edges = [{"a": k.split("|")[0], "b": k.split("|")[1], "w": round(w, 3)} for k, w in self.edges.items()]
        return {"axes": {"x": "time", "y": "kind", "z": "topic"}, "topics": topics, "nodes": nodes, "edges": edges}

    def brief(self, n=10):
        t = now()
        scored = []
        for m in self.mem.values():
            if m.get("pinned") or m["stage"] == "long":
                scored.append((m["importance"] * (0.5 + 0.5 * self.retrievability(m, t)) + (1 if m.get("pinned") else 0), m))
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored[:n]]

    def forget(self, mid):
        if mid not in self.mem:
            return False
        del self.mem[mid]
        for k in list(self.edges):
            if mid in k.split("|"):
                del self.edges[k]
        self.save()
        return True

    def curve(self, importance=0.5, days=(0, 1, 2, 3, 4, 5, 7, 10, 15, 21, 30)):
        s0 = 1.0 + 3.0 * importance
        reviews = []
        c = 0
        for g in REVIEW_GAPS:
            c += g
            reviews.append(c)
        rows = []
        for d in days:
            r_none = math.exp(-d / s0)
            last, s = 0.0, s0
            for idx, rd in enumerate(reviews):
                if rd <= d:
                    gap = REVIEW_GAPS[idx + 1] if idx + 1 < len(REVIEW_GAPS) else None
                    last = rd
                    s = GRADUATED_STABILITY if gap is None else max(s, gap * 3.0)
            rows.append((d, r_none, math.exp(-(d - last) / s)))
        return reviews, rows

    def stats(self):
        t = now()
        longs = sum(1 for m in self.mem.values() if m["stage"] == "long")
        return {
            "due_for_review": len(self.due_list(t)),
            "in_21_day_window": sum(1 for m in self.mem.values() if m["stage"] == "short" and not m.get("pinned")),
            "total": len(self.mem),
            "short_term": len(self.mem) - longs,
            "long_term": longs,
            "pinned": sum(1 for m in self.mem.values() if m.get("pinned")),
            "by_kind": dict(Counter(m["kind"] for m in self.mem.values())),
            "by_topic": dict(Counter(m["topic"] for m in self.mem.values())),
            "associations": len(self.edges),
            "weak_memories": sum(1 for m in self.mem.values() if self.retrievability(m, t) < 0.2),
            "last_consolidate": self.meta.get("last_consolidate"),
        }


def fmt(m, extra=""):
    tags = f" #{' #'.join(m['tags'])}" if m["tags"] else ""
    pin = " [pinned]" if m.get("pinned") else ""
    step = f" step {m['review_step']}/{len(REVIEW_GAPS)}" if m["stage"] == "short" and not m.get("pinned") else ""
    return f"[{m['id']}] ({m['kind']}/{m['topic']}, {m['stage']}{pin}{step}{extra}) {m['text']}{tags}"


def main():
    p = argparse.ArgumentParser(description="Brain-inspired long-term memory store")
    p.add_argument("--store", default=DEFAULT_STORE)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("store")
    s.add_argument("text")
    s.add_argument("--importance", type=float, default=0.5)
    s.add_argument("--tags", default="")
    s.add_argument("--pin", action="store_true")
    s.add_argument("--kind", choices=list(KINDS), default="semantic")
    s.add_argument("--valence", type=float, default=0.0)
    s.add_argument("--topic", default=None)

    r = sub.add_parser("recall")
    r.add_argument("query")
    r.add_argument("-k", type=int, default=5)
    r.add_argument("--peek", action="store_true")
    r.add_argument("--kind", choices=list(KINDS), default=None)
    r.add_argument("--topic", default=None)

    c = sub.add_parser("consolidate")
    c.add_argument("--dry-run", action="store_true")

    b = sub.add_parser("brief")
    b.add_argument("-n", type=int, default=10)

    f = sub.add_parser("forget")
    f.add_argument("id")

    sub.add_parser("stats")
    sub.add_parser("list")
    sub.add_parser("due")
    mp = sub.add_parser("map")
    mp.add_argument("--out", default=None)

    rv = sub.add_parser("review")
    rv.add_argument("id")

    cv = sub.add_parser("curve")
    cv.add_argument("--importance", type=float, default=0.5)

    a = p.parse_args()
    brain = Brain(a.store)

    if a.cmd == "store":
        tags = [x.strip() for x in a.tags.split(",") if x.strip()]
        print(json.dumps(brain.store(a.text, min(1.0, max(0.0, a.importance)), tags, a.pin, a.kind, max(-1.0, min(1.0, a.valence)), a.topic), ensure_ascii=False))
    elif a.cmd == "recall":
        res = brain.recall(a.query, a.k, update=not a.peek, kind=a.kind, topic=a.topic)
        if not res:
            print("no matching memories")
        for m, score in res:
            status = brain.last_status.get(m["id"])
            note = f", review {status}" if status else ""
            print(fmt(m, f", relevance {score:.2f}{note}"))
    elif a.cmd == "consolidate":
        print(json.dumps(brain.consolidate(a.dry_run), ensure_ascii=False, indent=1))
    elif a.cmd == "brief":
        items = brain.brief(a.n)
        if not items:
            print("no long-term memories yet")
        for m in items:
            print(fmt(m))
    elif a.cmd == "map":
        out = json.dumps(brain.spatial_map(), ensure_ascii=False)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as fh:
                fh.write(out)
            print("written", a.out)
        else:
            print(out)
    elif a.cmd == "due":
        rows = brain.due_list()
        if not rows:
            print("nothing due")
        t = now()
        for m in rows:
            late = (t - m["next_review"]) / DAY
            print(fmt(m, f", overdue {late:.1f}d"))
    elif a.cmd == "review":
        m = brain.mem.get(a.id)
        if not m:
            print("id not found")
        else:
            status = brain.apply_review(m, now())
            brain.save()
            print(json.dumps({"id": a.id, "review": status, "step": m["review_step"], "stage": m["stage"]}))
    elif a.cmd == "curve":
        reviews, rows = brain.curve(a.importance)
        print("review days:", ", ".join(str(r) for r in reviews))
        print("day  no_review  with_schedule")
        for d, r0, r1 in rows:
            print(f"{d:>3}  {r0:>9.2f}  {r1:>13.2f}")
    elif a.cmd == "forget":
        print("forgotten" if brain.forget(a.id) else "id not found")
    elif a.cmd == "stats":
        print(json.dumps(brain.stats(), ensure_ascii=False, indent=1))
    elif a.cmd == "list":
        for m in sorted(brain.mem.values(), key=lambda x: -x["created"]):
            print(fmt(m))


if __name__ == "__main__":
    sys.exit(main())
