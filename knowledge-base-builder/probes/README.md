# probes · 十二套探针 P1–P12（回归自检）

**这不是知识库内容，也不属于 skill 的交付物**——它只是回归自检，跑在临时库里，
被探测的对象是 `scripts/` 的十二个**只读校验面/门禁**。改任何一层（深抽规约 / 检索 / audit / verify）
之后跑一次，全绿才叫没回归。

```
python probes/wikilink_rules/probe.py         # 全绿 exit 0；有 FAIL exit 1
PROBE_WORK=/tmp/xxx python probes/wikilink_rules/probe.py   # 换临时目录
```

临时库落在 `probes/wikilink_rules/_work/`（每次运行先整目录删掉重建，不累积）。
它不会进 KB，也不参与 `verify.py` / `audit.py` 对主库的扫描。

## 测试台方法论（5 条，**所有探针都守这几条**；收在这一处，不散进台账）

1. **建夹具与出测量必须在同一条命令里完成。** `main()` 开头整目录删 `_work/` 重建——上一条命令手建的
   库在下一次全量复跑后就不存在了。跨命令复用夹具＝在测一个不存在的库，而输出看起来仍像结论。
2. **引用中间态读数前先 `ls` 确认夹具还在。** 不在就重建再测，不把"上次跑出来的数"当本次证据。
3. **反向还原出的「现状副本」必须显式 `PYTHONPATH=scripts`。** 副本躺在 `_work` 里时 `sys.path[0]`
   指向自身目录，import 不到同目录模块 → rc=1，会把台架故障误读成产品回归。连带一条铁律：
   **rc 不可作唯一信号**——A8 实测无条件 `TextIOWrapper` 在解释器收尾时 `lost sys.stderr` 而 **rc 仍为 0**，
   所以断言要扫 `Traceback` / `UnicodeEncodeError` / `lost sys.stderr` / `closed file` 这些字样。
4. **夹具的 `char` 区间由真文本算出，不硬编码偏移。** 用 `p10_split()` 一类算法现算；硬编码的夹具会在
   源文本被改过一次之后静默变成"全绿但没在测东西"。同理 P10 有"切块数 ≠ HIGH 表长度就 `SystemExit`"
   的夹具守卫——**夹具自己不合规时必须响亮地停下**，不许静默错位继续跑。
5. **造源文档必须显式检查长度门槛。** `doc_map.is_body` 对 **< 200 字节**的文件判"不是正文"：第 7 轮
   夹具源约 110B → `doc_maps.jsonl` 0 行 → `progress` 按设计拒绝出数，看着像脚本坏了，其实夹具没造对。
   该门槛已升格为**已知咬人门槛**（是否放宽/改按字符数另案裁决，见台账发现 32 附带项）；在裁决之前，
   夹具里一律显式 `assert len(源文档.encode("utf-8")) >= 200`。

## 十二套探针分别盯什么

| 探针 | 只读面 | 造什么 | 断言什么 |
|---|---|---|---|
| **P1** | `render_templates.py` + `verify.py --allow-empty-index` | Step 1–5 空骨架 | 骨架 verify exit 0；**`_meta/模板/note_atomic.template.md` 落地后不再有 `- [[相关笔记]]` 占位行**（模板改动唯一的回归面） |
| **P2** | `verify.py`（满库） | 三篇深抽笔记：A 正文引用 B、B 被引、C 同 topic 无引用 | **C10「双链目标存在」= PASS**（`[[B 的 stem]]` 解析得到）；C12/C13 仍 pass |
| **P3** | `audit.py --graph-mode explicit` | 同一内容的**两库对照**：有链库 / 把 A 里的 `[[ ]]` 拆成纯文本的无链库 | 有链库 `explicit.edges > 0`（`edges_by_source.wikilink` 计数）；无链库 `edges == 0`、孤岛 == 全部篇数；**两次调用 exit 都是 0**，报告里不出现告警字样 |
| **P4** | `check_hooks.py` | 两个库的 `工作流/` | 不合格 0 篇、待生成 0 篇、exit 0（证明双链改动没碰 q_hooks 口径） |
| **P5** | `search_index.py recall` | 有链库 vs 无链库，同一查询 | **命中笔记集合与顺序一致、通道标记一致** → 检索不依赖 explicit 边（`06_retrieval.md` 第 3 节的声明） |
| **P6** | `search_index.py recall` 的路由层 | 双工作流库（第二个 flow 只有 `render` 不会生成，探针现造一篇） | flow×stage 组合不存在 → `stage_flow_mismatch` + 丢 stage 留 flow + **命中 > 0**；非法 topic → `topic_not_found` + 落盘一行（字段齐全、`sort_keys`、`ts` 带时区）；三类硬错 + 三者全空 → **exit 2 且日志不新建不新增行**；多字段软错 → `--json warnings[]` 每项含 `code` 且 rc=0；`_meta/logs/` 缺失时能自建；退化路由（无 route）不落盘 |

| **P7** | `verify.py` 的 **C14 源目录只读** | 一个带源资料目录的库（`--snapshot-source` 建基线）+ 逐条制造增删改 | 建基线 → **PASS**；改内容 / 删文件 → **FAIL** 且 exit 1；新增资料文档 → **WARN**（不是 FAIL，文案带「未纳管 / 重建基线 / intake」）；新增媒体 → **WARN** 只报计数；**只改 mtime、内容不变 → PASS**（证明不比 mtime）；无基线 / 无源目录 / 基线路径不存在 → **WARN、exit 不变**；`--snapshot-source` 建不出来 → **非 0 退出**（不静默 warn）；另验写范围：`--snapshot-source` 只新建 `_meta/source_snapshot.json` 一个文件、不删不改任何既有 `.md` |
| **P8** | `validate_extraction.py` 的输入/退出码守卫 + verify 的 C5/C9/C15/C14 工单 | 自建 units 夹具（合法 / 三种削痕 / 空 / 缺文件）+ 临时劣质笔记（无 sources / 假来源 / 缺分标 / confidence low） | G1：units 缺失或 0 条 → **exit 1 且不打「通过 ✓」**；G1b：合法 units → exit 0、有错 → exit 1；T6：`evidence_thin`/`evidence_dup_locator`/`evidence_trimmed` 三种形态各自命中，且 `merge_count_checkable=false` 明写不可反查；G3：逐篇 `sources` 空/不可达 → **C5 FAIL**，无 config 时只 **WARN 不 fail**；G4 负控：缺三段分标 → **C9 必须 FAIL**（防它被改回 warn）；T4：low / 缺 confidence → **C15 WARN、exit 不变**；T3：源文件被改 → C14 FAIL + **工单列出依赖它的笔记**，且用 mtime 差分断言**工单没有写任何笔记** |

| **P9** | `check_verbatim_lite.py` + `search_index.matched_hooks()` + verify 的 **C10 目标解析范围** + `08` §3.1 前缀白名单 | 自建夹具源（两块 + 图片编号 + 列表标记）与六篇笔记：定稿逐字 / 自创数字 / 缺数拆篇 / 跨块引用 / 前缀豁免 / 前缀违规，外加一篇来源笔记 | **组1**「多」抓到自创的 15 且 extra 里只有它（剥噪没退化）；**组2** 定稿「多」=0、跨块篇「多」=0、「缺」列出主块有而本篇没写的数（=1:N 拆篇候选）、主块**包住**首项区间且比它宽（证明主块是块不是 quote 区间）、rc=0 且 `blocking=false` 且 `not_checked` 明写；**组3** units 开着 → 让位 validate 且明写「未做任何校验」（不报错也不假装跑过）；**组4** 带「作者未提、我的推论：」的 300 被豁免、不带前缀的 400 仍被抓（**前缀白名单本身进断言**，改匹配逻辑必红）；**组5** hook 阈值双向：长问句命中 >0（只用分母=query 会恒 0）、3 条无关查询命中必须全 0、路由短 keywords 不回归；**组6** C10 四步：指向来源笔记判 PASS → 来源笔记自己的死链**仍不报**（发现 25 残留②=未定的现状）→ 目标改名必报 WARN → 还原回 PASS |

| **P10** | `progress.py` 的**进度派生**（只读） | 自建四篇源文档（H1 标题块 + 2–4 个段块）+ 手写 `doc_maps.jsonl`（char 区间由真文本算出）+ 六篇笔记：docA 全抽 / docB 半抽 / docC 未抽 / docD 无高价值块 | **①** 三档计数 `done1/partial1/todo1/no_hv1` + 高价值块 9/已抽 5/未抽 4，逐文档 status 也对；**②** next_todo 全局=docB 未抽第一块、`--path-prefix` 只换起点不换判据（范围内给 docC 的**高价值**块 1，不是低价值块 0）、`--emit-todo` 单行与 json 版一致、带前缀时**全库与范围内两份计数都给**；**③** `coverage` 声称字段**已作废**的负控：把 docC 的 `chunks_processed` 改 2、`high_value_done` 改 true（夹具里 docA/docB 同时是"派生 done>0 而声称恒 0"）→ `--format json` **逐字节不变**、输出里不出现 `chunks_processed` 字样、不一致只可能是 ghost/unmapped 两类（旧的两类 `claim_*` 怎么都不报）；**④⑤** 保留的两类各造一例（改 locator→`ghost_locator` 且 done 从 5 退回 4；改 sources→`unmapped_source`）；**⑥** 编号已删不复用；**⑦** 两次 `--format json` 逐字节一致；**⑧** 跑完三种输出后整库 `.md` 与 `doc_maps.jsonl` 的 mtime+内容**一项都没变**（progress 是只读的）；**⑨** doc_maps 缺失/0 行、笔记目录不存在 → 一律 rc=1 且不打印进度，恢复后读数不变 |

| **P11** | `progress.py` 的 `--gate`（**默认关**的显式门禁） | **复用 P10 的夹具构建器、另起临时库 tag**（`p11_gate`，与 P10 不共享任何状态）：干净库 → 造 `ghost_locator` → 造 `unmapped_source` → 全部还原 | **①** 干净时加不加 `--gate` 都 rc=0，且 stderr 明写 GATE OK（判绿也要出声）；**②** 有一条不一致时**不加 gate 仍 rc=0**（默认关，绝不偷偷拦）；**③** 加 gate → rc=1，stderr 点名**条数 + 类型 +「不是百分比」**；**⑥** gate 与不加 gate 的 **stdout 逐字节相同**（json、markdown 各比一次，且 stdout 里绝不出现 `GATE` 字样——退出码才是信号）；**⑦** `--emit-todo --gate` 叠加：stdout 仍是**那一行起点**、rc 由 gate 决定；**⑧** gate 判**本视图**：ghost 在 docB → `--path-prefix docA` 判绿、`docB` 判红（**范围外不拦 = 主动缩小视图的代价**，文档 §12.5 明写）；**④⑤** 第二类不一致同样判红、还原后必复绿（判"有没有"，不是数量阈值）；**⑨** doc_maps 缺失 + gate → 仍是**输入守卫**的 rc=1 与守卫文案，**不打印 GATE 文案**（"没读到东西"≠"读到脏东西"）；**⑩** `--help` 明写"结构性错误 / 不是百分比"；**⑪** 跑完四种 gate 组合后整库 `.md` 与 `doc_maps.jsonl` 的 mtime+内容**一项都没变**（门禁也不许偷偷写） |

| **P12** | **结构适配（可移植性）**。`enc` 组＝A8 编码保护；`dir` 组＝A2+A3 目录名/KB 根参数化；`src` 组＝A4 源类型与 C14 清单口径；`lang` 组＝A1 语言适配（多语言分词 / 停用词 / audit 口径 / schema）；`fb` 组＝同源 `except` 兜底不得产出可用常量值（防「兜底值随版本腐化」）；`sb` 组＝拆篇候选边界的三条规约（`split_boundaries.py`：①资产表**按内容**判、②代码围栏整体不可切、③超限先粘连不硬切）；**`agg` 组＝B8 收口：`_` 前缀豁免 → `AGGREGATE_PAGES` 白名单，另五站点（progress / check_hooks / build_flows / check_verbatim_lite / backfill_hooks）**；**`al` 组＝`autolocate.parse_note` 的 evidence 配对形状（紧凑／空行）** | 全仓 `scripts/*.py`（**文件数动态取，别写死**）+ `probe.py` 自身；`PYTHONIOENCODING=gbk` 与 `utf-8` 双跑；临时库复用 P10 构建器（tag `p12_enc`），**负控用剥掉保护的脚本副本**；`dir` 组**全部自建夹具**（`p12_dir` / `p12_dir_std` / `p12_dir_deep` / `p12_dir_bf`，不复用 P10/P11 的库，定位符 char 区间由真文本算出），负控用**反向还原出的「现状副本」verify_old.py**；`src` 组同样自建（`p12_src`，六种扩展名的源目录 + 手改基线 JSON 造口径差），负控用**还原回 A4 之前的 scan_sources 副本**；`lang` 组同样自建（`p12_lang_build`，五种语言各一篇、正文 ≥200B 断言、查询一律取**只出现在正文**的短语），负控用**探针生成的「旧口径 CLI」驱动器**——把 `gram_units`/`to_index_text` monkeypatch 回 A1 之前再跑真 `main()`；`fb` 组不建新库——复用 `p12_dir_build` 造 `notes` 目录名 + 建 v4 索引，违例负控现造（`_work/p12_fb/negcontrol.py`：handler 内 dict 兜底 + try 内 `getattr` 字面量兜底，两条各归一个子判据），导入失败用 `sys.modules['search_index']=None` 注入**不用** `sys.path` 遮蔽（verify 会自己把 scripts 插到最前，遮蔽对它无效） | **①防漏** stdout **和** stderr 两条 `reconfigure` 齐备，**缺一即红（脚本＋ probe 自身全部齐备，数量由代码动态取）**；**②** 逐个 `--help` 在 gbk 下 rc=0、无 `Traceback`/`UnicodeEncodeError`/`lost sys.stderr`，且**中文真打出来**（不接受"没输出所以没报错"）；**③** 同一脚本 gbk 与 utf-8 的 `--help` 输出**逐字节相同**（保护只改编码不改内容）；**④** `evaluate.report()` 的 `[gate] 通过 ✅ / 未通过 ❌` 两分支在 gbk 下都打得出来——**这行正是原先的崩点**；**⑤** 跨 import 链（progress→search_index 两层保护落在同一对象）不出现 `closed file`（**无条件 `TextIOWrapper` 会在这里关掉共享 BufferedWriter，且 rc 仍是 0**，故全仓统一 `reconfigure`）；**⑥ 负控**：删掉两条 reconfigure 的副本必红（rc≠0 + `UnicodeEncodeError`），证明 ①–⑤ 不是空断言；**⑦** enc 组跑完临时库指纹不变；**dir 组**：**①** `config.notes_dir` 生效（C4 检到 3 篇、整库 rc=0）＋**负控**「现状副本」只看到 0 篇、C12 报「磁盘笔记目录缺失：工作流」（622 行不传目录名时会把参数没接上伪装成忘了 rebuild）；**②** CLI `--notes` 单独生效；**③** 优先级 CLI > config；**④** 兼容红线——标准布局不带 `--notes` 时新代码与现状副本 **stdout 逐字节相同**；**⑤** `--kb`：嵌套库不给 → rc=1 且文案仍是「doc_maps 不存在」（默认推导没被改坏）、给了 → rc=0 读到 3 篇；**⑥** `build_flows --notes` 聚合页落在 `notes/…` 下；**⑦** **输入守卫改判**：目录不存在 → **rc=1** ＋文案走 stderr ＋一个文件都不写；**⑧** **单一真源防漏**：无条件 `DEFAULT_NOTES_DIR = "工作流"` 只允许 `search_index.py` 一处（try/except 兜底不算）；**⑨** `STEM_SOURCE_DIRS` 第二段**不跟 `notes_dir` 动**——指向 `概念索引/` 的链必报失效，谁把它参数化这条就红；**src 组**：**①** 两档登记（`documents.other_readable=[b.html,e.vtt]`、`needs_convert=[c.docx]`、totals 两计数）**＋负控**（还原成 A4 之前的副本：两档不存在、三篇掉进 `media.others`；副本还原不干净会 `SystemExit` 响亮停）；**②** 契约不破——`md/pdf/txt/srt` 四键与副本**完全相同**、`pairing` 相同，且 `d.pdf` 不进 `needs_convert` 列表但计入 `totals`；**③** `snapshot.text_body_ext == sorted(TEXT_BODY_EXT)` 且 files 覆盖 6 篇，而 `doc_maps.jsonl` **只含 `a.md`** —— 把「登记 + 只读保护 ≠ 可深抽」（发现 32）钉成断言；**④** 两类文案可区分：旧口径基线 → 文案 A 且**不出现**「未纳管」，口径一致但基线缺文件 → 文案 B「新增 N 个文档未纳管」；**⑤** **不放松校验**：旧口径下内容被改 / 文件被删仍 **FAIL**（赦免只作用于 `added`）；**⑥** 旧口径下媒体计数变化**仍按 warn 报出**，与口径 warn 并存不被吞；**lang 组** **①** 五语端到端各由 **FTS 通道**保住本篇（`kept==1` 且带 bm25 的 FTS 命中就是本篇自己；hook/topic/relation 补回的别的篇目**不算命中**——断言的对象是分词，不是通道数）；**② 负控** 退回 A1 之前跑同一条 CLI：韩文与西里尔查询切出 **0 个 gram**、FTS 保留 0、命中 0；**③** 中文篇在新旧口径下的 gram 差集**只出现在字母词段**（词干归一），汉字段一条不差；**④** 单字档只给汉字/假名开（韩文/泰文段索引里没有单字）；**⑤** 跨脚本相邻**不产跨段 gram**（没有「词ค」也没有「문한」，但两段各自的 gram 都在）；**⑥** 词干三性质：变音拉丁整词不碎（`vidéos` 不拆成 `vid`+`éos`）/ 非 ASCII 不剥（西里尔原样）/ 剥完至少留 3 个码点（`cats→cat`、`cas` 不剥）；**⑦** 停用词表规模 **en=50 / ru=30** 且**分侧**：索引侧不删（`the` 仍在 `to_index_text` 里）、查询侧删，中文段与韩文段 `drop` 与否逐条相同；**⑧** 护栏①：整段全是停用词时不删（不塌成空 MATCH），端到端 rc=0 且无 `Traceback`；**⑨** 红线②：停用词不进 `matched_hooks` 的 gram 分母（虚词占分母时 2/4=0.5 假阳性命中，实现里分母只剩 `price/what`、共同 1 个 < 地板 2 → 不命中，真命中不伤）；**⑩** 分词改了 schema 必须 +1：`SCHEMA_VERSION==4`，C12 对 v4 PASS、对改回的 v3 FAIL 并指名 `--rebuild`（否则新分词跑旧索引、静默按旧口径出结果）；**⑪** audit 的 A4 口径与 `gram_units` 同源：韩文篇现在**有** bigram（旧口径按「首字是汉字」筛，韩文/假名/泰文一条都进不去），长度恰好为 2 的 `ai` 不冒充 bigram。**fb 组**：**①** 规则条（判据不是清单）：AST 扫全仓 `scripts/*.py` + `probe.py`，`except` handler 内对**全大写常量**的赋值右值只能是 `None`，`getattr(x, "UPPER", 字面量)` 同判；**负控**＝现造的违例脚本必须被同一函数抓到 2 条（`handler` 与 `getattr` 各一、行号不同），证明 ① 不是空断言；**② fb-a**：屏蔽 `search_index` 导入 + 不给 `--notes` → rc=1、文案走 stderr 指名「search_index 导入失败」、stdout 一行 `[PASS]/[FAIL]` 都不打、无 Traceback、临时库指纹不变；**③ fb-b**：屏蔽导入 + 给 `--notes` → C12 `[FAIL]` 且文案只说「无法确定期望索引版本」，不出现「期望 None」「≠ 期望」这种拿兜底值比出来的误诊，同进程正常导入下 `SCHEMA_VERSION` 仍为 4。**④ 真负控（两臂）**：臂A 把 `si.VALID_UNIT_TYPES` 打成 `None`（＝`except` 分支的产物）跑 `recall` → 必须 rc≠0 且文案「unit_type 口径不可用」，不得 rc=0、不得 Traceback；臂B 打成集外值（口径存在但坏）→ rc=0 **且必须**往 `route_warnings.jsonl` 落一条 `unit_type_invalid`，钉成「有日志的软错」——改成静默丢弃就红。**两臂都打消费端绑定（`si.VALID_UNIT_TYPES`）与消费子命令（`recall`）**：实测 monkeypatch `build_units.VALID_TYPES` 对 si 无效（import 期已绑定）、`pull` 根本不读这张表，按字面写会让断言空跑。改前实测：`verify` 的期望版本停在 2、真库与 `search_index` 已是 4。**sb 组**（夹具 `SB_DOC` 自建，形状照 05 真实料扒：`![](assets/….jpg)`／`![缺失素材:None]` 的 HTML 资产表 + 「判据｜说明」文字表 + 带空行的 ```Markdown 围栏 + 1,800 字无空行墙 + 引子标题）：**①** 同一输入两次跑 JSONL **逐字节相同**（候选边界是可复核派生物，不是每次重猜）；**②** 规约①**按内容**判表——资产表整块不产候选段且计入 `table_chars`，文字表格**必须留在**候选段里（一起丢或一起留都红）；**③** 规约②——任何候选段起止都不得落在围栏**内部**，含【角色】的段必须同时含【禁词】且引子与围栏同段（正则配对会被 `replaceAll` 骗出行中间假边界，故整行配对）；**④** 规约③——超限单位先与引子段粘连、禁链式（单段内超限单位 ≤1），粘完仍超标 `oversized_frag`，**「切点前一字符非空白」必须为 0 处**；**⑤ 负控**：把 `sb.is_media_table` 摘成恒 False 再跑，资产表必须**漏回候选段**（或 `table_chars` 归零）且 rc 仍 0——证明 ② 的红由判据产生、不是脚本崩溃。**agg 组**（夹具 `p12_agg_a` / `p12_agg_b` 自建：一篇合法原子笔记＋`_总览.md`，B 臂再丢一个**无 frontmatter 的 `_临时.md`**）：**① 规则条**——AST 扫全仓 `scripts/*.py`＋`probe.py`，**文件名级** `startswith("_")` 违例必须为 0；同一条 `if` 判据里带 `isdir()` 的算**目录级**、豁免（`build_flows.py:148` 是唯一合法残留，它跳的是 `_` 开头的**环节目录**，与文件名白名单语义不同）；负控两形**现造**（文件名级必被抓、目录级**不**被抓），并钉住「正则命中数 **>** AST 命中数」——正则会把 probe.py 里那条**字符串字面量**（P12-dir⑩／agg⑤ 负控源码）也数进去，所以扫描口径必须是 AST 不是 grep；**② 真源条**——五个站点都引用 `search_index.AGGREGATE_PAGES`、都不自定义，全仓定义处**恰为** `audit/search_index/verify` 三份（第四份复制即红；三份逐字相同由 P12-dir⑩ 钉，这里不重复）；**③** 收口没收过头——A 臂 `notes_total` 仍＝1（`_总览.md` 照旧豁免）；**④** 白名单外不再免检——B 臂同一个 `_临时.md` 被 `progress`/`check_hooks`/`check_verbatim_lite`/`backfill_hooks` **四处点名**、计数 1→2；`build_flows` 按它的口径**不点名**（生成器不是校验器），改钉「临时页被当原子笔记**聚合进生成物**」：`_总览.md` 里必须出现 `[[_临时`；**⑤ 负控**——把 `progress` 的 `fn in AGGREGATE_PAGES` 反向着陆回 `fn.startswith("_")`，同一夹具必须**不再点名**、计数回 1（证明 ④ 咬在实现上）。**al 组**（夹具 `p12_al`：同一份源文，两篇笔记只用**配对形状**不同——紧凑＝一行 quote 紧接一行引用不空行，空行＝新笔记写法；区间现场算不手抄）：**①** 两种形状跑 `--check` 都要 3/3 复算通过、rc=0；**负控**＝摘掉 parse_note「往上收时遇上一条引用行即停」的旧解析副本，紧凑篇必须转红且红在**复算**不在条数（条数仍 3、通过由 3 掉到 1），而空行篇在旧副本下仍 3/3 通过——证明红的是配对形状。**②** 笔记**文件里** `> —— \`§` 引用行数 == `--check` 报出的 evidence 条数（专钉解析器静默漏配；踩过的坑：拿 `--check` 输出去数行数会得 0，因为它不回显原文行）。**起因是真库实测**：29 篇全库跑 `--check` 时 8 篇老笔记被误判「逐字不可回放」，查下去是解析器把上一条的引用行当正文吞了 |


外加一条**负控**（挂在 P2 后面）：临时塞一篇 `[[根本不存在的一篇]]`，
C10 必须仍然报出失效链接（warn、不 fail）——防止"允许孤岛"被误读成"取消目标校验"。

## P6 额外钉住的两条口径（改路由层前先看）

1. **软错 rc 恒为 0**，硬错恒为 2。降级是设计里的成功路径，调用方靠 `warnings` 判读，不靠退出码。
   别把软错改成非 0——那会打破现有调用方对 rc 的判读。
2. **硬错一行都不落**：落盘点在 `route_empty` 检查之后、检索之前，所以"软错 + 硬错并存"时
   硬错赢、日志里不留那次软错的痕迹。P6 有一条专门断言盯着这个顺序，别"顺手"把落盘提前。

## 已知且可接受的非一致

- P5 两个库的 **bm25 分值可能差在小数第三位**：`[[stem]]` 比裸 `stem` 多了方括号字符，
  正文 token 分布略有差异。命中集合 / 顺序 / 通道标记必须一致，分值不参与断言。
- P3 的 `edges_by_source` 是**来源计数不去重**，一篇里两条指向同一目标的链会计 2、
  无向边只算 1（`10_audit.md` 第 4 节口径）。断言只看 `edges` 是否 > 0 / == 0。

## P2 曾经红过一条（记在这里，别再退回去）

C10 最早在**同一趟 `os.walk` 里**边收集 stem 边校验链接，于是"引用了同目录下
尚未被扫到的那篇"会被误判失效链接——A 排在 B 前面就 WARN，换个文件名顺序又好了。
现在改为**先把全库 stem 收齐、再判链的目标存在性**（`scripts/verify.py` C10 段）。
校验语义没变：仍然只判"目标存在"，不判边数、不判连通、不改 warn/fail 口径。

深抽是按块写的，被引用的笔记完全可能比引用它的笔记晚落盘，所以这条顺序依赖
在真实批次里必然会踩到——P2 的三篇就是专门盯它的。
