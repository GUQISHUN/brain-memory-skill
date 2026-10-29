# brain-memory-skill

[English](README.md)

一个给 AI Agent 用的轻量长期记忆引擎，灵感来自人脑记忆的运作规律。记忆保存在你自己的一个 JSON 文件里，不依赖任何第三方库。仓库里还带了 Claude Skill 封装和 3D 查看器。

它不是对大脑的复制，只是借用了遗忘、间隔复习、联想、巩固这些功能规律，并用普通 Python 实现。

## 功能

- **三类记忆**：`episodic`（事件）、`semantic`（事实和偏好）、`procedural`（做事方式），衰减速度各不相同。
- **21 天间隔复习**：存入后第 1、2、4、7、15、21 天各有一次复习，走完即转为长期记忆，错过会退回一步。间隔写在脚本开头的常量里，可以自行修改。
- **遗忘曲线**：保留率按指数衰减，每次按时复习都会提高该记忆的稳定性。
- **联想**：存入时自动连接相似记忆，一起被回忆的记忆连接更紧，回忆时会激活相邻记忆。
- **情绪增强**：`--valence` 取 -1 到 1，情绪强烈的记忆更稳定。
- **整理巩固**：合并重复、清除不重要的淡忘记忆，并提示哪些事件记忆该总结成一条语义记忆。
- **记忆立方体**：每条记忆在时间、类型、主题三个轴上有坐标，`brain map` 导出后用 `viewer.html` 查看可旋转的 3D 视图，支持点击查看、搜索和筛选。
- **中英文**：按英文单词和中文字对匹配，不需要模型，也不联网。

## 快速开始

需要 Python 3.9 及以上，只用标准库。

```bash
git clone https://github.com/<GUQISHUN>/brain-memory-skill.git
cd brain-memory-skill
alias brain="python skill/brain-memory/scripts/brain_memory.py --store ./brain_memory.json"

brain store "用户喜欢简洁的回答" --importance 0.7 --kind procedural --topic style
brain store "读完了 Rust 教程第 3 章" --kind episodic --topic learning --valence 0.5
brain recall "Rust"
brain due
brain consolidate --dry-run
brain map --out map.json
```

用浏览器打开 `skill/brain-memory/assets/viewer.html`，载入 `map.json` 或直接载入 `brain_memory.json` 即可，点击记忆可以查看完整内容和相连的记忆。

## 命令

| 命令 | 作用 |
|---|---|
| `store "文本" [--importance 0-1] [--kind K] [--topic T] [--tags a,b] [--valence -1..1] [--pin]` | 存入记忆，内容几乎相同时会强化已有记忆 |
| `recall "查询" [-k N] [--kind K] [--topic T] [--peek]` | 按相似度加联想检索，`--peek` 不算一次复习 |
| `due` | 列出到期需要复习的短期记忆 |
| `review <id>` | 把一次使用或确认记为复习 |
| `consolidate [--dry-run]` | 晋升、退回错过的复习、合并、遗忘、清理连接 |
| `brief [-n N]` | 最重要的长期记忆和置顶记忆，用于会话开头 |
| `list`、`stats`、`forget <id>` | 查看和删除 |
| `curve [--importance X]` | 对比有无复习计划的保留率 |
| `map [--out FILE]` | 导出 3D 坐标给查看器 |

环境变量 `BRAIN_MEMORY_PATH` 可以改默认存储位置，`BRAIN_NOW`（秒级时间戳）可以覆盖系统时间，测试就是靠它模拟时间流逝。

## 在 Claude 中使用

把 `skill/brain-memory/` 放进 skills 目录，或打包成 `.skill` 文件。`SKILL.md` 会告诉 Claude 何时、怎样使用引擎。Claude 的沙箱每次会话都会清空，所以开始时要上传记忆文件，结束时下载。

## 在其他 Agent（如 DeepSeek）中使用

引擎只是一个脚本，任何能运行命令或调用函数的 Agent 都能用。

1. 把 `store`、`recall`、`due`、`review`、`consolidate` 包装成工具，或者让 Agent 直接运行命令行。
2. 把 `skill/brain-memory/SKILL.md` 里的流程写进系统提示词：会话开始读 `brief` 和 `due`，回答过去的问题前先 `recall`，存入用户明确说过的持久信息，结束时 `consolidate`。

不同模型遵守这套流程的可靠程度不同，请用自己的模型测试。

## 局限

- 检索是词语匹配（TF-IDF 风格），不理解语义，查询和记忆没有共同词语就搜不到。换成嵌入向量是最主要的升级方向。
- 21 天窗口和各衰减常数只是可调的经验参数，不是实测值。"21 天"是流行说法，习惯养成的研究给出的范围很宽。
- 类型和主题由 Agent 在存入时判断，判断错了记忆就会放错位置。
- 查看器是 2D 画布加手写投影，节点上千后会变慢。
- 记忆以明文保存，文件没有加密。请不要存密码、密钥、证件号、支付信息，并谨慎对待敏感个人信息。

## 测试

```bash
python -m unittest discover -s tests -v
```

## 许可证

MIT，见 [LICENSE](LICENSE)。
