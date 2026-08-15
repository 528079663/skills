# 成文身份映射与字数纪律（author_mapping）

本文件是「功能三 · 创作」的身份解析与字数硬指标的权威来源，从 SKILL.md 抽出，主文档只做路由。

## 1. domain / author_mapping 结构
人设顶层两个字段（与 `profile` 同级，persona_manager.py 透传存储）：
- `domain`：领域标签（母婴/美食/职场/科技/理财…），按素材主题判定。
- `author_mapping`：用户成文身份映射对象：
  ```json
  {
    "resolved": true,
    "sign_name": "署名/品牌名（如 福宝妈妈）",
    "signoff": "结尾落款（如 福宝妈妈育儿笔记）",
    "self_refer": "作者自称（如 小琳/福宝妈妈）",
    "baby_name": "宝宝小名（母婴填，其他可空）",
    "note": "映射说明（可选）"
  }
  ```
  母婴领域捷径（变量源，禁止写死）：`domain=母婴` 只写 `{"ip_key":"福宝妈妈","resolved":true}`，真实值以 `references/ip_identity.json` 单一事实来源为准，由 persona_manager 在 view/export 时解析展开。改落款/署名/自称只改 ip_identity.json 一处。

## 2. 两条规则
1. **母婴固定映射，不询问**：所有 `domain=母婴` 的人设，`author_mapping` 只存 `{"ip_key":"福宝妈妈","resolved":true}`，**禁止在 persona 内写死身份副本**。落款行固定为 `福宝妈妈育儿笔记`（独立成行，≠软引导≠署名行）；母婴人设落款不得出现「福宝妈妈说」，不另设 `#福宝妈妈说` 话题标签。依据：用户级 `~/.workbuddy/MEMORY.md`「内容创作 IP 约定」。
2. **其他域首次创作先确认**：`domain≠母婴` 且 `author_mapping.resolved=false` 时，**先用 `AskUserQuestion` 向用户确认成文身份**（署名/落款/自称/领域专属元素），确定后 `update` 写入 `author_mapping` 并 `resolved=true`，后续复用不再问。
3. **领域 → 默认人设路由**：`persona_manager.get_default_by_domain(domain)` 按选题领域返回默认人设 id（当前 `母婴 → p_20260707_001` 福宝妈·温柔坚定育儿）。route A 第③步拿到选题 `domain` 后，**先调此路由取默认人设，再走 §3 身份映射流程**；未列出的域返回 None，维持"首次创作 AskUserQuestion 确认"规则。新增/调整默认人设请改 `persona_manager.py` 的 `DEFAULT_PERSONA_BY_DOMAIN` 常量（单一事实来源，禁止写死在多处）。

> 成文替换纪律：`identity.brand_name/baby_name/self_refer` 是源作者专名，成文时一律用 `author_mapping` 覆盖，绝不保留源品牌名（饭饭妈/九龄等）。

## 3. 身份映射流程（创作前不可跳过）
1. `view` 取人设 →
2. 读 `domain` 与 `author_mapping`：母婴直接走 `ip_key` 固定映射；非母婴且 `resolved=false` 先 `AskUserQuestion` 确认并写入 →
3. 复用风格层（tone/voice/词汇/价值观/避雷）+ 骨架层（structure/标题公式/支招框/排版）→
4. 用 `author_mapping` 替换身份占位符（署名→sign_name、落款→signoff、自称→self_refer、宝宝名→baby_name）→
5. 按 `writing_rules_anti_pattern.md`+`writing_rules_human_touch.md` 起草自检 →
6. 交付附"本次如何避免套路"。

## 4. 字数硬指标（写前必看）
- 「字」= 汉字字符数，不含标点/空格/英文/emoji/#话题标签（定义见 `writing_rules_dual_version.md` 第 27 行注）。
- **图文文章（公众号体等逐条详述型）**：分点论述每点 **220~250 字（不含标点）**；善用断句/小标题/换行，禁止长篇文字墙（自检清单第 9 条强制勾选）。
- **图片贴图（本模式交付卡片文案文本，非图片）**：每卡字数**必须读取该人设 `profile.content_modes["图片贴图"].writing_craft.length_profile.per_item_chars` 实测值并以其为准**（常见母婴约 220~250 字），仅当该字段缺失才回退默认 ≤200 字；卡正文善用断句/换行。

## 5. 标题口径对照（三种"标题"勿混淆）

本 skill 涉及三种字面都叫"标题"的东西，**归属与上限完全不同**，错用会直接违规：

| 标题类型 | 出现在 | 字数上限 | 由谁拟定 | 依据 |
|---|---|---|---|---|
| 图文文章标题 | 公众号体文章 `0_article_<主题>.md` | ≤28 字（公众号） | `meta-topic-plan` skill（≥4 套公式） | `writing_rules_dual_version.md` 硬规则8 |
| 贴图封面主/副标题 | 图片贴图卡片**大艺术字** | 主、副**各 ≤15 字**（各自独立计数，非合计）；副标题前固定 `✅` | `xhs-title-factory` skill（禁止手写） | `writing_rules_anti_pattern.md` 硬规则8 |
| 小红书 caption 钩子标题 | 贴图发帖配文 `0_tieutu_<主题>_小红书文案.md` 首行 | ≤20 字（争议/反直觉型，禁用平铺） | 本 skill 按 `tieutu_xhs_caption.md` 公式现写 | `tieutu_xhs_caption.md` |

- 封面主/副标题是"图上的大字"，严禁把公众号长钩子原样搬来当封面标题。
- caption 钩子标题是"发帖正文第一行"，与封面主/副标题是两回事，互不复用。

> 详见 `references/persona_schema.md` §3.5（domain/author_mapping 权威结构）与 `writing_rules_dual_version.md`（双版与字数细则）。
