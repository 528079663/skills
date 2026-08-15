---
name: renshe-writer
description: "本技能是写作人设工坊，三大能力：①从样稿提炼可复用的「风格层+骨架层」人设并存库；②管理已存人设（列出/查看/编辑/补提/重命名/删除/导出）；③调用某套人设产出内容（图文文章/双版公众号+小红书/图片贴图文案+小红书 caption）。用自然语言描述意图即可触发，无需记命令。不覆盖纯标题生成（xhs-title-factory/meta-topic-plan）、纯出图渲染、OCR 预处理。可选 Web 管理端端口 8003。"
agent_created: true
disable-model-invocation: true
---

# 写作人设工坊 (renshe-writer)

从文章提炼「风格层 + 骨架层」人设并存库；基于人设产出防套路、带人味、双版适配内容。所有读写经 `scripts/persona_manager.py` 落地本地 JSON。

## 先判模式（决策表）

| 用户意图 | 进入 |
|---|---|
| 给文章/样稿，要"提取人设 / 分析风格 / 提炼身份 / 命名" | 功能一 提取 |
| "列出人设 / 查看 / 编辑 / 补提行文风格 / 重命名 / 删除 / 导出" | 功能二 管理 |
| "用某人设创作 / 仿写 / 出双版（公众号+小红书）/ 写贴图文案" | 功能三 创作 |
| 想用网页界面操作 | Web 管理端 |

> 三套创作硬规则已外移：`防套路`→`writing_rules_anti_pattern.md`、`人味`→`writing_rules_human_touch.md`、`双版`→`writing_rules_dual_version.md`。本文件只做路由与要点。

## 运行环境（固定）
- Python（固定）：`~/.workbuddy/binaries/python/envs/base/Scripts/python.exe`（base venv，flask 已预装）。缺包在该环境内 `pip install`，勿换环境。
- 下文 `python` 均指它；`<SKILL_DIR>` = 本 skill 根目录（user 级 `~/.workbuddy/skills/renshe-writer`）。
- Web 管理端在本机（Windows）前台跑，不用沙箱。

## 功能一 · 提取并命名
1. 收文章（粘贴/文件/HTML 先走 `preprocess_html.py` 预处理）。
2. 按 `references/persona_schema.md` 推断 `profile`+`writing_craft`，守证据溯源/频率量化/占位符；图文与贴图分模式。
3. 命名：据 role+tone 提 2–3 候选，`AskUserQuestion` 确认；已给名直用。
4. 保存：`python <SKILL_DIR>/scripts/persona_manager.py add --data '{...}'`（结构见 persona_schema.md）。
- 补提行文风格（缺 writing_craft）：`update "<id/名称>" --patch '{"profile":{"writing_craft":{...}}}'`（深层合并）。

## 功能二 · 管理（三步纪律）
查看意图严禁直接 dump：① `list` 给清单 → ② 等确认 → ③ `view "<id/名称>"` 给详情。修改 `update --patch`；`rename`/`delete`(先确认)/`export`。

## 功能三 · 创作
**总则（最高优先级）**：默认套用指定/默认人设，不弃权；除非用户明确说"不套 XX 人设"。套用 = 应用人设口吻/支招形态/排版骨架（"怎么写"），不审查"写什么"，不自行判定话题触雷/恐吓而改题或洗白。
- 两层定位：风格层+骨架层**复用**；samples/标志话术/示例**禁止照搬**。
- 身份映射流程、母婴固定映射、落款行、其他域首次确认、字数硬指标、三种标题口径 → 见 **`references/author_mapping.md`**（必读）。
- 按选题领域自动选默认人设：`python <SKILL_DIR>/scripts/persona_manager.py default <domain>`（如 `母婴 → p_20260707_001` 福宝妈·温柔坚定育儿），见 `author_mapping.md` §2.3；非母婴域未配置默认时由 `AskUserQuestion` 确认。
- 双版规则 → `writing_rules_dual_version.md`；防套路 → `writing_rules_anti_pattern.md`；人味 → `writing_rules_human_touch.md`。
- 交付附"本次如何避免套路"。

### 同主题再创作差异化门禁（写前必过，硬约束）
> 解决"同主题+同人设再创作写出换皮文"的问题。**仅换案例人名 / 同义改写 / 换标题 = 不合格**，必须换「内容组织轴」。
当用户说"再创作 / 又一篇 / 同主题 / 换个标题再来 / 同主题再来一篇"等，且人设相同或话题同域时，动笔前必须：
1. **查已用角度**：`python <SKILL_DIR>/scripts/topic_log.py check <persona_id> --topic <规范化主题>`（如 `睡姿暗示性格`）。
2. **有冲突记录 → 必须换内容组织轴（新角度）**：新角度须改变"文章按什么维度展开"（例：把"枚举6种睡姿→性格"改为"按月龄 / 按场景 / 按性别 / 按睡眠质量"分维度，或换核心论点）；仅替换素材外壳（案例人名、同义词、标题）**不算**新角度。
3. **写前显式声明**：在回复里写出「本次角度 = X；与上次角度 Y 的差异 = Z」，形成可见硬约束后再动笔。
4. **写后登记**：`python <SKILL_DIR>/scripts/topic_log.py record <persona_id> --topic <t> --angle <a> --thesis <核心论点> --title <标题>`。
5. 若用户明确就要"同角度换皮"（如 A/B 测标题），**先与用户确认**再执行，不得默认换皮。
> 角度定义与"新角度合格标准"见 `writing_rules_anti_pattern.md` 规则2；登记工具细节见同文件规则5。

### 贴图创作流（route A ③ 步，含 caption 自动校验门禁）
- 产出两份文件：`0_tieutu_<主题>.md`（贴图文案，按卡分页）+ `0_tieutu_<主题>_小红书文案.md`（贴图 caption；规范与公式见 `references/tieutu_xhs_caption.md`；不需落款；文末 3–6 个 `#话题标签`）。
- **③ 步收尾必跑自动校验**：`python <SKILL_DIR>/scripts/validate_xhs_caption.py "03_创作/0_tieutu_<主题>_小红书文案.md"`，RESULT 全部达标才算 ③ 完成；不达标回到创作补正（补 emoji 分点 / 补 `#标签` / 收字数 / 加互动引导），**不得带着 FAIL 进 ④**。
- caption 校验脚本为独立 stdout 报告（stdlib only，无外部依赖）：仅判格式与基本合规（字数 / 无 markdown / emoji 数 / 互动引导），不判文风人味（文风由人设套用保证）。

## 输出物与目录
- 图文文章：`0_article_<主题>.md`（+ 可选 `0_article_<主题>.html` 公众号内联样式），写入统一会话目录 `~/WorkBuddy/renshe-writer_{YYYYMMDD-HHMM}`。
- 图片贴图文案稿：`0_tieutu_<主题>.md`（按卡分页，纯文本/Markdown；本 skill 交付物止于文字，渲染成图交给 meta-image-render / easy-tuwen 等）。
- 配套贴图小红书文案（caption）：`0_tieutu_<主题>_小红书文案.md`（规范见 `references/tieutu_xhs_caption.md`；**与文章双版「小红书体」无关**，由本 skill 一并创作；产出后须跑 `scripts/validate_xhs_caption.py` 验收，见「贴图创作流」）。
- 人设库（持久，非会话产物）：`~/.workbuddy/personas/personas.json`，跨会话复用。
- 主题做文件系统安全处理（去 `/ \ : * ? " < > |`、空格转 `_`、限长）。

## 数据存储
默认 `~/.workbuddy/personas/personas.json`；`--store <path>` 可覆盖；写入均经 `persona_manager.py`。

## Web 管理端（8003，默认常驻）
- 双击 `启动服务.bat` 启动、`停止服务.bat` 停止；或 `python <SKILL_DIR>/scripts/app.py start|stop`。
- 浏览器开 `http://localhost:8003`（前端 `scripts/webui.html`）：人设列表/查看/新建/PATCH/删除 + HTML 预处理。
- 仅绑 127.0.0.1，无 TLS/无登录态。端口被外部占用→报错退出，不降级不换端口。

## 脚本命令
`list` / `view <id>` / `add --data|--file` / `update <id> --patch|--file` / `rename <id> <新名>` / `delete <id>` / `export <id> <文件>` / `path` / `default <domain>`，均支持 `--store`。

## 注意事项
- 多套并存命名唯一；编辑前先 view，删除前确认。
- 频率必先量化：含频率字段先计数写 `frequency_notes`。
- 图文文章与图片贴图分模式；图片贴图 OCR 前标 `ocr_status:pending`；品牌名统一+占位符。
