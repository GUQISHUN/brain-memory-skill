# brain-memory-skill

[中文说明](README.zh-CN.md)

A small, dependency-free long-term memory engine for AI agents, inspired by how human memory behaves. Memories live in one JSON file that you own. The repo also contains a Claude Skill wrapper and a 3D viewer.

It is not a copy of the brain. It borrows functional rules (forgetting, spaced review, association, consolidation) and implements them with plain Python.

## Features

- **Three memory kinds**: `episodic` (events), `semantic` (facts, preferences), `procedural` (how the user wants things done). Each decays at a different speed.
- **21-day spaced review**: reviews are due 1, 2, 4, 7, 15 and 21 days after storing. Finishing the schedule graduates a memory to long-term. Missed reviews step back. The gaps are constants in the script, so change them freely.
- **Forgetting curve**: retention decays exponentially with a per-memory stability that grows with each timely review.
- **Associations**: similar memories are linked on storage. Memories recalled together get stronger links. Recall spreads activation to linked neighbours.
- **Emotional salience**: `--valence` from -1 to 1 makes strongly felt memories more stable.
- **Consolidation**: merges near-duplicates, forgets faded low-importance items, and lists groups of episodic memories that should be summarised into one semantic memory.
- **Memory cube**: every memory has coordinates on three axes (time, kind, topic). `brain map` exports them and `viewer.html` renders a rotatable 3D scene with click-to-inspect, search and filters.
- **English and Chinese**: matching uses word tokens plus Chinese character pairs. No models, no network.

## Quick start

Python 3.9 or newer, standard library only.

```bash
git clone https://github.com/<GUQISHUN>/brain-memory-skill.git
cd brain-memory-skill
alias brain="python skill/brain-memory/scripts/brain_memory.py --store ./brain_memory.json"

brain store "User prefers concise answers" --importance 0.7 --kind procedural --topic style
brain store "Finished chapter 3 of the Rust book" --kind episodic --topic learning --valence 0.5
brain recall "Rust"
brain due
brain consolidate --dry-run
brain map --out map.json
```

Open `skill/brain-memory/assets/viewer.html` in a browser and load `map.json` or your `brain_memory.json` directly. Click a memory to see its full details and linked memories.

## Commands

| Command | Purpose |
|---|---|
| `store "text" [--importance 0-1] [--kind K] [--topic T] [--tags a,b] [--valence -1..1] [--pin]` | Add a memory, or reinforce a near-identical one |
| `recall "query" [-k N] [--kind K] [--topic T] [--peek]` | Retrieve by similarity plus association. `--peek` does not count as a review |
| `due` | List short-term memories whose review is due |
| `review <id>` | Count a use or confirmation as a review |
| `consolidate [--dry-run]` | Promote, step back missed reviews, merge, forget, prune links |
| `brief [-n N]` | Top long-term and pinned memories, for priming a session |
| `list`, `stats`, `forget <id>` | Inspect and delete |
| `curve [--importance X]` | Retention with and without the schedule |
| `map [--out FILE]` | 3D coordinates for the viewer |

Set `BRAIN_MEMORY_PATH` to change the default store location. `BRAIN_NOW` (epoch seconds) overrides the clock, which is how the tests simulate time passing.

## Use with Claude

Copy `skill/brain-memory/` into your skills folder, or zip it as a `.skill` file. `SKILL.md` tells Claude when and how to use the engine. Claude's sandbox is wiped between sessions, so upload the memory file at the start and download it at the end.

## Use with other agents

The engine is just a script, so any agent that can run commands or call functions can use it.

1. Expose `store`, `recall`, `due`, `review`, `consolidate` as tools, or let the agent run the CLI.
2. Put the workflow from `skill/brain-memory/SKILL.md` into the system prompt: read `brief` and `due` at session start, `recall` before answering questions about the past, store durable facts the user stated, `consolidate` at the end.

Models differ in how reliably they follow this loop. Test with your model.

## Limits

- Retrieval is lexical (TF-IDF style). It does not understand meaning, so a query that shares no words with a memory will miss it. Swapping in embeddings is the main upgrade path.
- The 21-day window and the decay constants are tunable heuristics, not measured values. "21 days" is a popular rule of thumb; research on habit formation reports a wide range.
- Kind and topic are chosen by the agent when it stores a memory. Wrong labels put a memory in the wrong place.
- The viewer draws on a 2D canvas with hand-written projection and slows down with thousands of nodes.
- Memories are stored as plain text. Do not store passwords, keys, ID numbers or payment details, and be careful with sensitive personal data. The file is not encrypted.

## Tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT. See [LICENSE](LICENSE).
