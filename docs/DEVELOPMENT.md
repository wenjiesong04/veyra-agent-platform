# Veyra Agent Platform — 主开发文档

## GitHub 开发分支检查点（2026-11-09）

在干净的锁定依赖环境复现了 macOS 内置服务因缺少 ElementTree 而启动失败。
补齐 PyInstaller 的 ElementTree 和 keyring 收集项后，重建的内置服务通过启动、
健康检查、退出和端口占用测试。另用隔离探针验证 macOS 钥匙串后端可初始化。
安装包签名和 DMG 校验由 GitHub Actions 的 desktop-package 作业执行。
路由清单测试已同步社区「我的插件」接口，仍核对完整路由集合。

## Studio 左右工具栏几何对齐（2026-11-08）

按用户截图将右侧外框按左侧.view-switcher对齐：11px圆角、3px内边距、30px内容
控件，实际浏览器测得两组外框均38px高。提交改ArrowUpToLine向上提交图标，1px
虚线边框（含hover保留虚线），其余title/aria/disabled/handler不变。
类型/生产构建和diff check通过；本轮仅视觉与图标，不新增镜像CSS单测。生产组件
隔离预览实测radius=11/11、height=38/38、borderStyle=dashed；对照截图位于
/tmp/veyra-studio-toolbar-radius-20261108/toolbar-pair.png。临时入口清除，无服务重启、
业务草稿/版本/Provider操作或提交推送。

## Studio 提交图标与视觉收敛（2026-11-06续）

用户否定GitCommitHorizontal的歧义及操作组视觉。当前已换普通Check确认图标，
提交按钮改浅青底/细边框并覆盖primary hover，删掉旧深色var(--paper)文字覆盖；
操作组减轻阴影/边框、调整圆角与间距，图标统一18px/1.8描边。保存徽标、全图标
动作、title/aria与所有提交/自动保存门禁不改，既有窄屏定位规则保留。
Studio定向40项、类型/生产构建通过。实际生产组件隔离预览核对浅/深色，深色为
亮青字+深青底；截图和日志在/tmp/veyra-studio-toolbar-20261106/visual-refinement-*。
本轮未声称新的320浏览器验证（隐藏预览未应用viewport override，已reset）。临时
QA入口清除；无后端/用户草稿/版本/Provider/服务重启/提交推送操作。

## 网页发布中心、桌面社区外链与插件记录报错修复（2026-11-06续）

最新用户要求已落地：网页账号入口移到官网导航最右侧，侧栏仅发现/已发布/已收藏/
我的；旧account统一到Mine，资料与安全在Mine子路由。Mine按参考图显示身份、版本
统计、发布中心、最近版本/待处理/反馈，支持Agent YAML和声明式Plugin Pack上传。
选择文件只在浏览器本地预览，冻结字节快照后单独确认；上传绑定expected_publisher_id，
服务端在实际POST会话中核对身份。按账号隔离预览/列表；晚到GET保留已确认发布回执。
个人插件新接口含全部状态/版本，避免pending插件刷新后消失，统计合并Agent/Plugin。
Workflow/Project/Template分享契约尚未接通，发布中心显示不可用，不伪造上传成功。

Desktop社区正常点击外开网页且保留当前hash；旧深链显示兼容入口。配置公开基础
URL的VITE_COMMUNITY_SITE_URL，DEV默认5174，PROD未配置显示提示而不误跳localhost。
复用现有Tauri shell插件，公开core.invoke配合HTTP(S)专属scope，无新增依赖/锁。
安装包需填域名后重构建并实测，静态验证不能代替DMG点击验收。见COMMUNITY_WEBSITE.md。
Studio恢复原点+文字的保存徽标；GitCommitHorizontal提交紧挨徽标；四项操作均仅
图标，title/aria保留名称与作用，全部autosave/retry/conflict/版本/导出门禁保留。

最终Community 66项、Desktop 965项、相关Community后端14项通过；双App类型/生产
构建、后端4文件mypy与Ruff/format通过；Desktop已有大bundle警告保留。UI用隔离
合成账号/草稿核对默认桌面、390/320、文件本地预览与确认前禁用；选择文件导致
外层滚动的问题已修复。截图和日志在/tmp/veyra-community-creator-20261106；合成
截图有标注，不冒充用户账号真实发布。没有真实上传发布/导出/模型Run、提交或推送。

用户随后要求处理截图错误。确认为运行中的旧8772无mine/plugins接口（404），非
丢失已发布数据。完成后端回归后，通过既有launchd只重载com.veyra.agent-platform.community，
社区PID928→69209，新接口匿名访问为正确401；本地8771仍PID4232。未读/改凭据，
没有重启本地运行服务。自动化浏览器当前没有用户已登录会话，真实账号页面未做
认证后发布操作；接口权限/个人记录已由临时SQLite+FakeMail的FastAPI回归验证。
新增OwnedPlugin用例初次因跨作者使用完全相同归档触发既有全局storage_id唯一约束
而失败，改为B使用独立4.0.0归档后14项通过，保留失败诊断；未扩大该既有约束范围。
临时QA入口已备份到证据目录并从应用根清除，既有大范围dirty保留。

## Studio 自动保存与操作工具栏（2026-11-06）

按用户反馈删除常驻“保存草稿”，保留既有2秒闲置自动保存。右上角合并为紧凑工具组：
保存状态（修订/行为哈希放悬停说明）、对话修改图标、打开应用、主要提交版本、导出图标。
复用现有Lucide与Petronas主题；Agent/Workflow的Canvas/Form/Source共用操作区。
保存失败且dirty时才显示“重试保存”；冲突继续保留加载磁盘版本。保存/继续编辑清旧
提示，避免恢复后将旧错误画成成功。导出在dirty/保存中/无效buffer/图诊断/冲突/离线时
阻止，失败toast；打开App正常点击先用既有navigate保存草稿，仍去committed App，不
隐式提交/运行。保留Commit的dirty/revision/ETag门禁。

本轮仅studio页面、专属CSS、测试及此记录。实际Studio定向40项（原32+8），最终
Desktop全量96文件940项、类型和生产构建通过；现有大bundle警告仍在，不改分包。
新增测试覆盖Retry、导出门禁/成功、旧保存回执保护新编辑、Open App保存/失败/冲突、
Workflow自动保存，使用模拟API，未触发真实Provider。真实浏览器只读查看既有对账
助手三视图、1440/390/320和双主题；320保存状态与四操作均可见，深色主按钮文字为
深色以提升对比度。临时viewport/主题恢复。未编辑业务草稿、提交版本、导出或运行。
证据 `/tmp/veyra-studio-toolbar-20261106/`，before备份保留既有dirty成果；不提交/推送/
重启，前端证据不代表完整产品或真实模型验收。

## 官网社区原位整合与文档精简（2026-11-06）

按用户最新反馈删除 header 阅读进度条（保留分区导航高亮），删除 Docs 顶部返回/
介绍/大标题区，直接显示粘性目录与第一章。Community 接入同一个 Showcase header，
不再切成 ApplicationShell；发现/已发布/已收藏/我的放入左栏，手机为粘性横向栏。
发现读取真实 Agent/Plugin 注册表，含作者搜索、分类计数、排序和卡片/列表切换；
个人 Agent 版本/收藏读取现有认证接口，匿名不请求私有列表。我的保留账号入口，
本地发布/导入/执行仍归 Desktop。列表与详情切换隔离晚到响应，不以旧结果覆盖新路由。

最终 Community 7文件58项、TypeScript 与生产构建通过；定向验证含实际前端 API
客户端配合模拟 HTTP 的认证门禁、收藏失败/成功反馈与请求竞争。真实浏览器已核对
四分区、作者搜索、分类空态、视图切换、唯一官网header/零进度条、Docs直接首章；
390中文/320英文无横向溢出。复用既有5174预览，无重启、提交、推送、Provider请求
或真实收藏写入。截图/检查日志在 `/tmp/veyra-showcase-community-20261106/`。
这些是本轮前端证据，不代表后端/真实授权安全/完整产品或发布验收。

## 官网六项反馈与文档滚动目录（2026-11-02）

导航收敛为五个英文单词 Demo/Product/Control/Docs/Community，社区第五项，删除
home/docs footer；复用共享主题 Petronas 青色 token，Hero 单色轻字重产品说明。
Brief 默认展示原始需求节选、场景/目标/约束与照片；Output 展示真实候选图与设计
要点，未验证说明和原始运行图可展开，旧状态不改。40秒剪辑以需求/定义/产物为主，
去掉长篇 Run Details，不调用新模型或重跑业务。

Docs 目录以实际滚动位置更新、保留深链与历史，桌面sticky/手机横向sticky均有
实际检查；390px定位149px，目录64..125px未遮标题，页末第四章高亮且无footer。
本轮48项Community、类型和生产构建通过，视频解码1200帧/Range206及真实社区入口
已核对。证据/tmp/veyra-showcase-review-20261102。无后端/契约/依赖锁/共享token
写入，无Provider、Run、版本变更、服务重启、提交或推送。业务结果仍是历史候选。

## 官网首屏比例调整（2026-11-01）

按用户反馈将居中大标题+超宽视频上下堆叠收敛为桌面左文案/右视频，h1最大52px、
视频上限760px；平板紧凑排文案后接视频，手机标题40px/窄屏36px。清除旧媒体独立
宽度和上边距、重复流程行，保持真实包装案例、16:9、无边框自动循环。实际核对
1440/1920宽屏、1280×720、768×1024、390/320布局；1280下媒体完整底部约670px，
未见横向溢出。43项Community、类型检查与构建通过。无后端/素材/Provider/Run变更，
无服务重启、提交或推送。详细边界见SHOWCASE_DESIGN首节。

## 官网礼物包装统一与无边框循环媒体（2026-11-01）

根据用户纠正，当前展示全部统一为真实分格糖果盒/圣诞礼盒案例，替换上一轮对账
媒体与说明；文档首个任务和单独标注的审批交互例也统一。使用现存 Workflow 与
Analyzer/Renderer 的实际记录及 Artifact，父流程 failed、子任务 unverified 的
事实保留，不以候选图伪造完整交付。无新 Provider、Run、source 或版本变更。

40 秒、30fps 的 H.264 媒体移除标题框/黑边，以淡化和缓慢镜头连接；页面无边框、
圆角、阴影，静音自动循环，支持暂停、离屏/后台节流、主动暂停保持和 reduced-motion。
大面积绿色替换成中性黑白灰，少量冰蓝强调。43 项 Community、类型检查和生产
构建通过；媒体全解码 1,200 帧、Range206，应用内实际 autoplay/muted/loop 与暂停
通过，390/320无横向溢出。详见 SHOWCASE_DESIGN 当前首节和公开媒体 README。
仅前端/媒体切片，不是完整包装业务、安装包或正式发布验收。无提交/推送/服务重启。

## 官网真实界面剪辑、站内文档与发布边界复核（2026-10-31）

本轮只改 Community/Showcase、展示媒体与说明，保留现有大范围 dirty 成果。
首屏改成真实 Veyra 界面 48 秒视频：输入填写演示之后，回放同一合成对账案例的
已有 Builder、Studio、固定 v1、报告和执行记录。用户指出自绘概念界面不一致后，
已将该初版移除。视频没有提交新生成/Run，没有改变 source、版本或历史结果，
保留原有未验证状态。新增站内 docs、滚动高亮、阅读进度与完整章节定位。

最终 Community 41 项、类型检查与生产构建通过；视频全量解码 1,152 帧、HTTP 206
Range 与 Chrome 实际播放/seek 通过。桌面/768/390/320 与中英文/主题检查有记录。
本轮未修改后端；辅助在当前代码执行 CSV mainline 12 项通过，使用合成模型而非
真实 Provider。没有将这些结果称为全仓门禁、安装包或整体验收。

只读复核仍发现：Qwen 普通兼容配置不传 reasoning_effort；Workflow evaluation
缺少独立原始输入 hash；模型审查非独立认证；ad-hoc preview 不证明正式分发。
详见 `docs/SHOWCASE_DESIGN.md`。证据在 `/tmp/veyra-showcase-20261031/`，仅新启动
5174 官网预览，未重启既有后端、未提交/推送/部署、未调用收费 Provider。

## 百炼授权恢复与正式 App 对照：绑定修复，审查仍超时（2026-10-24）

用户先要求尝试截图外模型，随后补充SLens-dev授权截图并要求再试；仅只读筛选了
其它候选，未调用它们。最新截图显示固定qwen3.8-max-0902已获模型调用授权，故在
相同既有北京Provider、相同A实际两条消息下仅一次隔离复测：158.365秒正常stop，
明确纠正原先遗漏的交付必要依赖前提；root和唯一辅助按冻结A标准评分通过，仍有
后续确认措辞偏硬等风险，非正式App、重复稳定性或独立业务认证。旧403记录未改。

正常App创建隔离Reviewer Qwen 0902 Acceptance，同v5只改identity/name/slug，保留
完整原需求、方法、五条criteria、I/O、Skill锁、权限和16轮Source预算。提交v1后发现
Studio给loop Model误写node.model，实际primary_model仍回退Kimi；在任何正式Run前
拦住此错配。Workbench现仅loop不传nodeId，legacy graph与Workflow保留node槽位；
真实Studio调用方3路回归通过。重新选择后GET主槽与readiness均确认实际Qwen0902。
正式设置的单次普通文字能力probe通过，未设全局默认，未修改原Reviewer/WF绑定。

Desktop相关34项、最终932项/96文件、typecheck/build通过。全量首次因旧焦点测试
同步断言requestAnimationFrame恢复失败，单独复核通过；root仅把断言改为waitFor，
未改Shell行为或放宽结果断言，失败日志保留。后端未改，不将此前2257门禁冒称本轮
重跑。仅前端HMR，无8771重载。最终代码素材manifest为
84a150cb1c18426c652c0ac390f95cb4398e0279a9859f0bbb55f9b0d1ff6c8b，非Git SHA。

正式App固定clone v1完成一次A提交：行动191.406秒正常返回候选，候选已实质纠正
必要依赖缺失；但交付审查累计266.742秒后read180秒超时，1029事件、0最终正文，
总458.594秒/2轮，Run failed/result null，0工具图片。原始输入、实际首轮消息与固定
版本均校验一致；候选内容通过不是最终交付通过。按收费前协议停止B/J及后续收费，
不重跑/恢复/延时凑成功。现可证明授权后可调用，不能证明完整业务或时延已合格。

仅核实的后续性能变量：maas域目前不发送reasoning_effort，Qwen0902使用服务默认
思考档位xhigh；当前max_tokens=8192按厂商文档只限制最终回答，不是思考加回答的
硬上限。前述隔离收据的max_completion_tokens字段是RuntimeSettings名称，不等于
真正发送了同名Qwen参数，旧收据保留、解释在新审计中补充。不能据此断言xhigh就是
本次180秒空闲超时的原因；后续需明确模型参数适配并另冻质量/时延对照，不能在
当前冻结样本之间改档位。依据官方Chat参数页与深度思考页，不从泛化示例猜默认值。

持久acceptance/2026-10-24-qwen-authorized保存隔离诊断、能力与失败截图、冻结协议/
版本/输入、Run快照/候选/收据、932门禁、final-audit。旧v1-v5、原模型绑定和默认值、
旧A/B/J结果及原事件均不变；最终四类active0，Source与代码冻结后未变。正式质量
验收尚未完成，不发布、不commit/push，不迁移Electron。以下为历史阶段。

## 百炼对照接入：解码缺陷已修，真实文本请求仍被拒绝（2026-10-24）

根据用户提供的百炼授权截图，选用现有北京工作空间Provider的固定
`qwen3.8-max-0902`，不改Kimi默认、原Reviewer/Workflow绑定、Source或旧Run。
同一保留A输入的首两条实际消息单次隔离诊断，模型目录预检通过，随后发生
HTTPX DecodingError，原统一错误runtime_unavailable没有证明模型不可用或缺权限。

共享completion_stream现按请求偏好identity，仍支持正常压缩响应；HTTPX已解码的
错误正文不再带原Content-Encoding构建另一Response，避免二次解压掩盖真实错误。
解码失败单独归runtime_invalid_response/response_decoding，保留白名单HTTP状态、
媒体/编码类别与计数；不存正文、自由文本异常或全量headers，不重发POST。
新20项编码回归及相关112项通过，最终make check2255项/863原警告/480.41秒，
环境、依赖锁、format、Ruff和mypy通过。这是首次真实诊断对应修订的门禁。

仅8771空闲守护重载96214→2771，25表摘要与其它服务状态不变；5174原本未运行，
未将其启动。初次重载准备因脚本错误要求5174在线而在guard/SIGTERM前停止，
修正私有审计脚本后只实际重载一次。无重复launcher；health旧build_sha仍非来源证明。
生产代码/素材manifest
6bcf2e906434334ccafd91e7195e806ba4f013efdcc5e59a6cfa6e4676b609bf，非Git SHA。

修复后仅一次新隔离completion：0.400秒返回runtime_permission_denied，HTTP403、
content-type归other、encoding identity，无模型文本结果；收费调用随即停止。
模型目录可见、控制台显示授权、实际生成可调用是三个不同证据，不能由403确定
具体厂商子码或断言是哪一方配置错误。已请用户核对截图默认工作空间与现有北京
工作空间（本地记录）/API Key所属空间；不索要密钥、不更换域名或遍历模型。
没有正式Qwen App Run或A/B/J质量分数，原Kimi漏检与发布缺口仍未解决。

只读审计确认上述元数据能随node.failed/finalization.failed事件保存并在执行记录
查看，但原HTTP403通用文案过度断言为“密钥无权限”。随后仅修正backend及Desktop
连接检查/正式Run的中性双语文案，不改错误码、布局、协议或重试策略；两项新回归
验证非JSON403不猜原因、单POST和不泄露正文。最终相关114项、make check2257项/
863原警告/484.82秒及全部静态门禁通过；Desktop929项/96文件、类型检查/构建通过，
保留原jsdom Canvas和bundle体积警告。之后仅8771再空闲加载文案2771→4232，未再
调用Provider，25表及其它服务状态仍不变。最终生产代码/素材manifest为
5f0da4f6c340debd1eb7bdab52ec4c3ed3e450be37ef276e3ca4879a47d024ec（非Git SHA）。

持久证据acceptance/2026-10-23-qwen38含前后独立诊断、一次性guard、最终门禁、
reload和final-audit。最终四类active0，诊断后25表仍完全不变。QUALITY_NOT_ACCEPTED/
RELEASE_NOT_ACCEPTED，不commit/push、迁移Electron或发布。以下为历史阶段。

## 审查方法真实对照：未达质量目标（2026-10-23晚）

已实现显式opt-in evidence_first：只选声明原始输入做盲账本，直引核对出处，预算内
额外计轮；按原文/契约/实际回复缓存，同候选修订复用，完成事件前保存缓存，断点
恢复不重复收费。默认direct、旧Source不迁移，Studio不猜原始字段。共享review_request
提取已有请求/取消/安全诊断路径，非另起Runtime。后端2235、桌面924及静态/构建通过。

正式App固定v4三例：A仍漏检89.306s/3轮，B正确95.908s/3轮，未见H因果纠偏正确
65.171s/3轮。盲账本已提示证据不足，比较仍错误pass，故不默认推广到生成器。随后
固定v5只改为650字符的通用逐段主张/相容反例检验方法，恢复direct、不增加调用：
A仍失败62.809s/2轮，B通过42.610s/2轮，新J主错纠正但新增示例前提不充分，
PARTIAL/42.414s/2轮。六Run均unverified/native pass，零工具/图片；不能拿执行结束
或prompt方法存在代替质量。v5 A实际模型消息完整、含新方法、无旧会话上下文。

同消息单次隔离K3 max诊断37.893s仍漏检，未改全局/绑定/Source/Run，非正式App验收。
现有备用Provider上的qwen3.7-plus一次隔离诊断runtime_unavailable后停止，无收费重试；
只存统一码的脚本诊断记录缺口已注明，未臆断额度/认证或所有Qwen可用性。已询问是否
有另一套已可正常文本生成的现有模型名称，不索要密钥。不把此次失败方法推广所有Agent。

v5 A通过App追加明确署名Codex辅助（非用户本人/专家）的rejected验收，Run/result/
旧事件不变，只追加evaluation两事件；旧v1-v3/v4/v5和早前失败/完成A均不变，原WF
仍v2。仅8771空闲重载84551→96214，25表摘要/其它服务不变。最终四类active0，
代码素材manifest0033a5b4633d7e620a31c2223e2e00d5b79b3567524d139debbc065aeda84947，
非Git SHA。持久acceptance/2026-10-23-counterexample-review/RESULT.md及相邻
2026-10-23-evidence-first目录保存预冻结协议、完整输入/Source/Run/评分/门禁证据。
QUALITY_NOT_ACCEPTED，不发布、不commit/push、不扩大到CI/安装/Electron。以下为历史。

## 行动响应传输修复与单次真实复测（2026-10-23续）

行动与审查复用completion_stream严格聚合器，行动请求不再等待完整buffered响应；
保持90s空闲读超时、独立600s总期限，不增加Source轮次。完整正常结束才返回可执行
动作；截断/异常EOF/拒绝/原生tool_calls不能触发工具。公开model.progress仅包含状态/
时间/计数，不含推理或部分动作；前端保存Run与SSE共用解析器已补齐，并折叠传输摘要。

原固定Reviewer v3和原A输入只新跑一次：Run（本地记录），
74.608s/2模型轮，0工具/图片，行动44.859s接收完成。后端完成后暴露前端漏接事件，
修复并恢复同Run，不再收费。事实保留和确定性措辞有改善，但仍漏检到货先后不足以
证明可/不可交付的必要依赖前提；native pass不代表质量通过。SEMANTIC_FAIL，不发布。

后端2201与静态门禁通过；最终Desktop917/95文件、类型/构建通过。误用pnpm造成
本地依赖双实例后已用原npm锁npm ci恢复，失败与成功日志均保留，未修改依赖版本。
空闲8771仅守护重载至84551；旧失败Run/所有Reviewer版本与新结果均保持不变，
四类active最终0。持久acceptance/2026-10-23-action-stream/RESULT.md含准确证据。
最终代码素材manifest f75e38ead2d6a7b1ba7181f36bd788e2298dd977c135928cdc950e2c224aad12，
非Git SHA。原Workflow未升级，包装图像、跨任务重复质量、远程CI与签名安装仍待验。
以下为历史阶段结论，不覆盖上述终态。

## 审查契约与字段身份修正（2026-10-23）

生成/Coverage区分字段必返与至少发现几条问题，允许有依据的零发现并保留用户明确
数量要求；不全局删criteria或迁移已提交版本。Runtime审查携带同Source的typed输入/
输出契约，保留原资料和上游分析的身份，并检查条件推断的必要前提，合理正例仍允许。
正式Studio对原Reviewer显式提交v3，修正两条矛盾criteria、精简重复角色指令；权限、
原需求、I/O名称类型、资源锁、模型引用及16轮预算不变。原Workflow仍固定Reviewer v2。

后端完整门禁2187项、相关138项与静态检查通过；空闲8771守护重载后25表/其它服务
不变。真实App按冻结协议只提交A一次，首个行动文本请求90.637s读超时，尚未进入
新增审查，只用1/16轮，未调用工具/图片。停止后续收费、未跑B/H、未自动重试；不能
据此说新审查质量通过或失败。页面新增中文说明，并直接呈现原诊断的读取阶段/90秒，
不混为执行预算不足；原码和记录保留。桌面911项、类型/构建与1280/390实际浏览器
检查通过。详见HANDOFF和持久acceptance/2026-10-23-review-contract/RESULT.md。
行动请求目前仍buffered，与已有审查stream不同；下一阶段先核传输证据，不简单增
超时或轮次。图像原始字节、质量重复基线、CI与签名安装仍缺，不发布。以下为历史。

## 固定Reviewer质量对照（2026-10-21，10-22续接核对）

正式App对同一已提交Reviewer v2完成三例受控测试，预先冻结输入及判断标准，
例间未修改模型/指令/权限/预算。原错误分析固定重放仍漏掉缺必要依赖前提的履约
结论（209.488s/4模型轮）；正确条件正例保留（151.333s/4轮）；跨领域混合负例
五类错误均修正（80.628s/2轮）。三个Run均unverified，不能用模型最终pass代替
业务质量。正例第一次仅因空问题清单返工额外60.571s，说明生成契约的非空要求
在制造形式成本；不应通过增加预算或强迫找错来解决。总体质量未通过，不发布。

验收中修复普通string单行框无法原样接收多段报告的问题，改为textarea并保留路径
datalist；三项新增回归、桌面905项、类型/构建通过，1280/390实际页面无横向溢出。
无后端修改/重载。10-22核对三例API快照完全未变、代码manifest未变、服务健康无活跃
任务。原包装四图在10-21目视仍有认证章/标识/水印缺陷，但旧临时目录在续接时已
不存在，未确认移除原因；真实图审在请求前停止，0新增费用，不冒充图审已通过。
本轮合成测试证据转存至Application Support/Veyra Agent Platform/acceptance/
2026-10-21-fixed-reviewer-quality，详见HANDOFF及QUALITY_ACCEPTANCE_20261021.md。
随后通过正式App给A登记辅助评审rejected，明确非用户本人/专家认证，原Run字段和旧
事件未变，仅追加两个验收事件，无模型调用。同hash包装Source已从正式旧版本恢复并
校验16条criteria，但四图exact hash在canonical存储/元数据均未找到，图审仍受阻。
受控负例仍有漏检，图像合格正例、重复稳定性、远程CI与签名安装仍未验收。
以下是此前历史过程。

## 正式Workflow链路验收终态（2026-10-21）

本轮保留计划单次审查约37秒通过，修复canonical Apply漏绑companion Skills后，
原提案零追加模型完成1Workflow+2Agents创建。正式Studio/App验证固定v1拒绝后
cancelled/null且未执行Output；外部质量审查抓到履约推断错误和自审漏检，未批准
错误v1报告。加入通用证据/推断/引用范围准则后提交Reviewer v2与Workflow v2，
正式运行到审批约110秒，批准后精确交付候选，状态仍unverified，不冒称事实已验证。
Runtime实际输入确认原文与Analyst结果均正确传入Reviewer；v1历史Run完全未变。

编辑过程还发现检查器打开即改映射且被自动保存；已移除隐式写入，恢复正确草稿，
并验证升级版本保留数据别名和其它锁，未提交/运行错误映射。最终后端2181项、
桌面902/官网31及双App类型构建通过。仅8771此前空闲重载，之后只有前端HMR。
桌面/手机实际无导航重叠和页面横向溢出，未新增网站或修改运行结果。

结论是本例功能链路通过、业务质量部分改善，不是整个产品可发布。v2与v1的
Analyst输出不同，未固定重放同一错误，因此不能证明通用Reflection漏检已修复；
还需受控负例、跨任务重复评测、图像质量、CI和签名安装。完整证据与残余问题
见HANDOFF和私有WORKFLOW_BUSINESS_ACCEPTANCE_20261021.md。以下为历史过程。

## 额度恢复后的Workflow验收进展（2026-10-21）

额度恢复后正式页面已完成一次真实TaskCoverageV1审查，约37秒/1请求，保留原始
两角色Workflow并进入确认。旧quota失败卡的手动恢复入口已补，不自动探测/重试。
随后创建草稿暴露canonical聊天应用入口漏绑companion Skills；Factory直接入口
已有该逻辑，所以此前对应门禁未覆盖正式用户路径。这是内部Apply问题，不是
额度、预算或模型拒绝。当前复用既有精确hash资源绑定，补正式HTTP全链路5项及
原提案零模型创建恢复；最后全量回归进行中，修复尚未加载。准确终态见HANDOFF。
此阶段尚无新的正式Workflow Run，不把审查通过写成业务完成或可发布。

## 当前验收终态（2026-10-21）

Workflow审批/Stop/保留方案检查已通过2176项后端全量、893桌面/31官网测试和双App
类型/构建，仅8771空闲重载并核对25表不变。原官网普通5174/#home已统一新版，
不再有平行预览实现。源码manifest、重载审计与具体日志见HANDOFF。

正式UI从原失败草稿继续，只发1个TaskCoverageV1请求，约0.775秒被Moonshot/Kimi
账户额度以429/exceeded_current_quota_error拒绝。已停止，没有重新规划、自动重试、
Provider切换、提案应用或新Run/图片；旧记录及固定Source保留。不是执行预算
耗尽，不能宣称真实Workflow业务验收通过。下一步需要先恢复该API账户额度。
以下“验收中/尚未加载”段落为本轮历史过程，不代表当前进程状态。

## Workflow 审批控制与终止路径（2026-10-20，验收中）

创建范围修正已通过2154项全量并加载。正式UI原Workflow需求现能进入规划，但
8文本/约423秒仍因审批条件编译失败，未创建或运行，不把它算成功。平台曾提示
审批输出为boolean，实际却仅有控制端口；新编译现在保留两角色数据交接，将
专属审批谓词折叠为控制分支，并用Workflow专用Stop终止拒绝路径，不交付结果。
审批问题同时包含实际报告和复核问题，不另付费摘要。旧版本的显式拒绝路由不改。

保留IR已0调用离线编译通过；兼容草稿在当前Schema/语义重新验证后续接，需求和
资源锁不放松。当前最终全量回归仍运行，未加载此阶段代码或再次收费续接。
普通失败卡片正在补显式的单次保留方案检查，不把“检查”悄悄变成整案重写。
准确日志、操作ID与进程见HANDOFF；以下早期“尚未加载”描述均是当时状态。

## 官网已原位整合，Workflow路由修正进入回归（2026-10-20）

用户明确指出独立预览造成混乱，当前普通 http://127.0.0.1:5174/#home 已直接使用
新版，旧Showcase被替换，不再通过preview query分流两套实现。组件/样式/文案/
素材归位showcase正常命名，保留旧锚点及Community/账号路由，复用已有偏好。
Desktop877、Community31与双App类型/构建通过；CUA正常入口可见新版，实际
点击进入Community再返回首页成功，390px正常。无模型请求或API重载发生在官网验证。
详见 [官网设计说明](SHOWCASE_DESIGN.md)。下面独立预览段为已被替代的历史记录。

同轮修正创建意图：一个Workflow及其新角色属于单一新工作产品，不再被旧multi_object
编辑标记误挡；多个已有对象修改仍不支持且零部分写入。缺乏明确scope的旧多对象
响应先澄清，不猜成单Agent。9项新回归通过，覆盖真实组合提案链与失败诊断脱敏；
目前全量后端回归进行中，尚未加载8771或新收费复测。此段不是业务验收通过。

## 官网高保真原型（2026-10-20，历史，已整合）

按用户最新产品叙事重做完整首页原型，未替换现有官网。入口为
http://127.0.0.1:5174/?preview=studio&lang=zh#home 。以真实合成案例产品画面连接
描述需求、结构编辑、交付依据和人工决策，白/深色节奏替代图标六宫格；无虚假
下载。审批仅本地交互示意，不冒充该案例的真实文件写入。图像、Workflow和安装
未通过的事实仍保留，不以视觉升级代替发布验收。

预览模块与CSS按需加载，现有Community/账户先分流；语言、主题键和滚动容器独立。
Desktop877、Community33与双App类型/构建通过，CUA覆盖320/390/768/1440/1920、
中英/明暗、实际滚动、模态与键盘/审批交互。无新Provider或Run，无API重载/推送。
详见 [官网说明](SHOWCASE_DESIGN.md) 与HANDOFF。Electron尚未迁移。

## 主对话布局与安装验收新证据（2026-10-20）

Agent App现在直接在主对话阅读结果、底部输入；右侧可选上下文收纳完整需求、
版本、文件与历史，不再额外占左侧运行栏，也不自动打开Canvas。移动上下文为
原生模态dialog，Escape关闭并回焦。实际CUA检查桌面/手机及明暗色；最终本地
Desktop877、Community24测试与双App类型/构建通过。Backend全量2137通过，
另加打包专项8通过，不把两者冒称新2145项全量。详见HANDOFF与相应私有日志。

正式UI新Workflow请求12秒/1文本后被意图层判unsupported，未创建Factory session、
提案或Run；外层operation=succeeded不是生成成功。保留完整需求，无付费重试。
这条正式产品路径仍不通过，后续需要从该operation诊断，不能用编译测试替代。

当前桌面仍Tauri2+PyInstaller Python sidecar。新增检查实际App签名及已签名内置
服务启动，发现ad-hoc App签名虽通过，libpython因Team ID不匹配仍无法加载。
未关闭系统安全检查；本机0有效签名身份，尚缺一致签名、公证和干净安装证据。
DMG生成不等于可安装发布。当前没有Electron迁移、API重载、commit/push或新远端CI。
图像质量与跨任务稳定性也未因此通过。

## Agent 应用与运行详情界面改版（2026-10-20）

按项目记录中指定的 taste-skill 与 web-design-guidelines，改为结果优先的平面工作台：
任务输入独立、提交后可收起且保留字段，文件使用简洁附件行；新任务不混入旧结果，
历史报告可只读重新打开 Canvas。桌面保留可调整并排阅读，窄屏一次一个内容区，
宽表格内部横滚。品牌/固定版本/权限/运行与审批协议不变，样式限定 App/Run 表面。

运行详情默认报告阅读，UUID/完整时间/原始输出和完整事件按需获取；执行完成不
冒称结果已验证。验收先展示历史结论，显式编辑时才展示完整条件。新增只读入口
的迟到读取竞态已用请求 epoch 和 deferred 反例修复，避免旧报告顶替新任务。

表单新运行就绪只判断当前显示的输入，不借历史会话中隐藏的文件引用启用运行；
hybrid后续输入继承保持。最终桌面876项、双App类型检查及构建通过；实际CUA覆盖
1440/768/390与明暗色。
本轮未调用Provider、未新建Run、未提交验收或改历史数据，未重载API、提交/推送。
这只证明本轮前端改版，不替代下述跨任务、业务质量、CI与安装发行验收。

## 正式CSV交付与异常处理通过（2026-10-20，非发布验收通过）

将旧不确定项的整案重写改为独立TaskUncertaintyReviewV1：模型只返回已被现有计划/
能力解决的原索引与理由，系统保留其它IR；显式恢复从有疑问的已grounded anchor
起步，不接受失败修正的改名。非法协议不可部分应用或自动整案修复。原全文覆盖、
权限、精确Skill及输入保护字段锚继续。144专项及同源全量2137项通过，静态门禁
通过；源码6f319a10，仅重载8771，25表摘要一致，其它服务未动。

正式UI原计划继续35秒/2文本进入确认，未重识别或整案重写；创建CSV Agent并在
Studio提交固定v1后，实际上传两文件。真实运行40.291秒/3文本/2工具完成，订单
260.10、收款200.00、净差60.10，四项差异及原始行号、文件哈希与独立基线一致，
原文件不变。实际CSV/Math工具输出已留证，非仅模型自称读过；unverified不改称
verified。此定义未增加额外语义审查调用，不把这次成功冒称Reflection全面达标。

正式结果验收还验证金额变异的错误基线被精确比较器拒绝，原Run状态/结果不变。
这不是模型能自动识别所有业务错误的证明。异常列名真实运行20.474秒/1文本，
基于实际Runtime输入正文正确说明amount缺失，未猜金额或擅自映射。随后重新
上传正确文件的另一Run47.190秒/3文本/2Tool仍正确，同一固定v1，原文件均未改。
两正一异常是小样本，不代表稳定率或p95；35秒创建是保留计划续接，不是空白
项目首轮耗时证明。包装图像质量、固定角色Workflow、安装发行证据仍未通过。

重复报告暴露Markdown表格被当源码显示，阅读器已采用react-markdown/remark-gfm，
实时与历史共享渲染；原HTML保持安全文本，危险URL不成链接，Markdown远程图片
不自动加载，ArtifactRef预览和technical JSON不变。实际桌面/窄屏表格可读、独立
横滚、全文可达；原Run渲染前后API响应相同，未发新模型请求。前端861项、双App
类型/构建通过，官方npm生产依赖audit0，不等于安全认证或新发行验收。
详见HANDOFF与私有CSV_ACCEPTANCE.md。没有提交、推送、新CI或新发行包。

## 正式App文字闭环与跨任务验收（2026-10-19，未达发布标准）

持久编辑链已经正式UI确认应用并提交v2。同会话首轮与更正分别42.897/47.604秒
交付合格文本，但第3轮48.904秒失败：13项审查只返回9项，预算仍余14轮。这证明
此前两轮不能当稳定性结论。当前将审查条件编码为动态required slots，由服务器汇总
结论；实际Runtime身份匹配且验证过strict支持才启用Schema，未知保持旧协议。
条件、Source、权限不删改；缺项仍拒收，不通过自动重试掩盖失败。

bbecf0ef同源后端2084、桌面857与双App tsc/build通过后，仅重载8771，25表历史摘要
不变。正式UI从失败断点继续31.374秒，仅1次审查就完整返回13项并交付；旧失败记录
原样保留。再完整运行130.556秒、1执行+1审查也交付，独立对照原资料事实正确。
均为unverified，模型评审不是独立验证。131秒重复运行说明效率尚未达标；样本不足以
宣称成功率或p95。桌面/窄屏真实文档载体不再展示执行图，全文可读可滚动。

另补原生Anthropic与ChatCompletions格式能力隔离，74专项通过，最终全量尚在跑、
尚未加载。正式UI独立CSV创建已经开始；完整工具/文件证据、包装图像质量及目标
返工、固定角色Workflow、重复和故意错误、同源CI/安装包/干净安装仍是未通过门禁。
详见HANDOFF和私有/private/tmp/veyra-formal-acceptance-20261017/TEXT_ACCEPTANCE.md。
没有提交、推送或公开发布，不把已有旧DMG当作当前源码交付。

## 正式App验收推进（2026-10-18，业务尚未通过）

正式创建首轮5m42s/8文本失败后，修正编译绑定、局部IO修复合同和内建提问资源
误报；同原计划真实继续1次覆盖审查/约22秒进入确认，已从UI创建并提交文本Agent
v1。但真实运行1次执行+1次审查在约77.68秒进入强制澄清，未交付：模型把“报告
缺失矛盾、允许以后纠正”升级为“交付前必须澄清”，不符合原要求，已取消并留证。

规划/覆盖审查/Runtime已明确可选对话不等于交付前置条件，覆盖双向检查遗漏与
额外门槛。语法修复保义务；实际覆盖反馈可纠正模型错误推断，并重编译、重新
审完整原需求，输入保护/写范围/精确Skill不放宽。恢复以最新语义修正版为准；
有界完整修复JSON不再40KB截断。实际ask_user回复同事务进入后续对话历史，
恢复Run先追原任务回合。创建提案与编辑列表分流，历史不改。该6bfdfc59源码日志
2033后端/846桌面通过，已仅reload8771至5503，19表摘要一致；详见HANDOFF。

随后正式修改遇到Factory超时，但operation仍waiting且Source请求未纳入收据。
当前正在把正式edit提案生成从浏览器后续步骤统一到后端持久流程；前端只展示
并确认，不重复调用生成。新链未最终回归/加载，不用上轮门禁证明新源码。完整
原需求、旧版本、Run和失败报告保留；CSV、包装结果质量、固定角色Workflow及
发行候选仍需真实正式路径证据。用户当前直接授权本任务必要修改/重载/真实验收，
不包含提交、推送、公开发布、账户修改或删除旧数据。

## parser阶段修正已加载（2026-10-17，仅重载、无收费测试）

用户直接授权call_a0f84cd98f934d9593849b53a444b9cb后，无active任务才仅reload
8771：89899->91450，health/local0038 ready。源内容清单464d9c93与1982门禁相同，
19张历史表完整摘要相同，5173/8772未动，0模型/图片/评审提交，没有新Run。
旧Run/固定版本和私有业务报告不改，本次授权已消费。该记录仅证明服务加载，
真实修图质量仍未验收；不自动继续旧收费余量。审计见HANDOFF最新段。

## readiness解析阶段修正（2026-10-17，本地全量通过、未加载）

最新授权真实续接仍失败：Run（本地记录），1text/0image/
64.75秒，HTTP200完整审查，16项准备度均pass；parser未接phase，以“A passed review
cannot invalidate images”终止。失效项已校验属于Source，但具体列表旧诊断未保存。
不是预算耗尽或Provider超时。授权已消费，无后续收费/新Run重试；旧失败行、版本
及执行期原目录摘要不变（准备期SHM例外明确记录）。可读报告位于
/private/tmp/veyra-pre-render-resume-20261017/BUSINESS_RESUME_ACCEPTANCE.md。

Root把phase贯通到parser：只在pre_render允许ready pass与声明内旧图失效并存，
终审仍严格。Owner在存断点前仅处理当前待生成视角缓存，明确复用/计划外/已完成
项不自动重画，并记录applied/unapplied；不把未应用建议冒称修复，不升级advisory。
显式与隐式路径一致，真实图片与全部原条件仍在终审核对。专项102通过，最终
make check1982pass/782warnings/435.79秒/exit0，format522/Ruff/mypy280及依赖门禁
通过，后增API断言已覆盖。日志/tmp/veyra-review-phase-semantics-full-check-20261017.log。
实际16项公开findings配原Source离线检查15种非空图片失效组合：预审全部接受，
两个交付阶段共30种拒绝；0Provider。这是合成失效组合，不是未知原列表的重放。
源码清单464d9c93807e835cad341419a3a15712b1a953562dbb960427640f68c473a4a7，
未再次reload/收费，main89899仍10b64687；前端未改，无commit/push/CI/新包。

## readiness修正加载与有界续接（2026-10-17，历史执行记录）

call_2c8e5bc469ff4640916441dfee3067fa新直接授权后，10b64687/1973门禁同源码仅
reload8771至89899，health/local0038 ready、19表完整摘要一致，5173/8772未动。
新私有副本从最近失败断点续一次，6text/1目标image/900秒，原Source/版本/需求
不变，不重跑前六轮。最终1text/0image/64.75秒失败，原因见本文最新记录。
执行/重载授权已消费，失败不得自动再收费。准备期SQLite只读备份更新原SHM，
mainDB/WAL和所有其他文件hash不变；精确变动与0收费准备失败已保留，不隐瞒。
详细脚本、Run与边界见HANDOFF最新段。未提交/推送/新CI/新包。

## 预审与交付阶段分离（2026-10-16，本地全量通过、未加载）

call_bc10269024bd43a3a4daf1b298a22fe3已消费：仅reload8771至83933后，一次真实
续接Run（本地记录），1text/0image/162.61秒。完整HTTP200
后在pre_render失败agent_finalization_review_invalid，image_scope/invalidate_images。
旧Run/version行与原目录摘要不变。当前没有验收进程继续收费，不自动花余下6次。
可读报告位于/private/tmp/veyra-review-presentation-resume-20261016/
BUSINESS_RESUME_ACCEPTANCE.md；原JSON及请求收据不改。

已确认平台问题：预审删除Source图片字段后又从该Source推导失效范围，合法范围
恒空；本次原返回名称未保存，不能断言全部合法。预审也未收到实际新图/复用计划，
公开findings多项在出图前要求新图、后续引用及持久化齐备；算术工具回执缺失是
另一项仍需真实证据的意见，不自动放行。

Root将readiness独立于最终交付门禁，reviewer保留原Source/criteria/图片声明，
接收当前图片计划与设计上下文；仅离线输出校验使用文字投影。phase明确区分
pre_render/candidate/images；终审仍核实际产物与原全部条件，预审不发accepted。
未知图片名仍拒绝并记录安全声明范围/错误索引。缓存v2包含图片请求和设计上下文，
已审计划独立于逐图缩减的执行集，部分效果断点恢复不重复预审或已完成图片。
唯一辅助只读复审指出恢复额外预审风险，Root修正并以剩2轮恢复测试验证。

阶段专项及已有API修订78通过，断点/生命周期22通过，最终新阶段模块14通过，
最终make check1973pass/782warnings/439.33秒/exit0，format521/Ruff/mypy280及依赖
门禁通过。源码内容清单10b64687f1573138779f4f7ff4cac879a675af8026aba38b31d869b8516c0f6e，
不是Git提交。日志/tmp/veyra-pre-render-scope-full-check-20261016.log。
前端未改，845/tsc/build为该未改部分上轮证据；Canvas独立tsc通过。未再次reload/
收费/commit/push，main83933仍旧eec30020版，业务修图及发布仍未验收。

## 实际流式返回与审查展示容错（2026-10-16，历史门禁与授权）

流式版本1951后端/845桌面及tsc/build通过后，按新授权仅reload8771至82505，
19表摘要一致。真实断点只发1次文本、0图片，56.712秒收到完整审查；未重跑
前六轮，也未再次180秒整包等待。但Run在57.95秒仍失败：needs_input没有question
文案，被原解析器作为无效报告终止。此时具体公开findings尚未保存，不能反推
缺什么事实；这不是Provider失败，也不意味着业务通过。旧目录/记录/Source保留。

本地已修展示与语义分离：全部检查结构/状态先严格校验，needs_input缺提问时
用该结论已有的公开reason/evidence作为提示，保持原结论并同Run暂停，不调用
模型重做格式。其他语义错误保留已验证公开findings、具体位置和缺失检查索引，
不存raw/unknown/hidden内容。通过投影忽略附带metadata，不能变成工具动作或
权限；语义缺陷仍严格。没有放宽pass、删criteria或新增修复次数限制。
新完整回归1959pass/782warnings/431.42秒，format520/Ruff/mypy280通过，Desktop
未改动部分仍为845及tsc/build通过；只读复审和专项已通过。新源码清单
eec30020fe946eb1cb1819912ee2523ab14842f8de3d80d482f5b4ebfdaa75bb，非Git提交。
用户新直接授权后仅reload8771至83933/local0038 ready，19表完整摘要一致、其它
服务未动；该授权已消费。新的7文本/1目标图/900秒断点续接已收失败终态，
具体原因见本文最新阶段记录；没有打包、commit/push或CI。

## 流式审查与交付收敛（2026-10-16，回归中）

从实际失败发现complete_review仍走整包HTTP POST，180秒期间不能观察Provider
活动。已改成专用聚合SSE：单次POST读取正常结束证据，只发布安全计数/阶段，
隐藏推理不记录；完整候选仍由原JSON和全部criteria校验。无finish/截断/错误/
异常JSON终止/超大响应均拒绝，同响应JSON兼容不发第二次请求。保留read180，
活动流总期限默认600可配置，按网络chunk检查（包括未换行数据）。停止后不交付
迟到结果，但空闲同步socket不冒称即时中断。此次不靠加轮次或删检查通过。

Root独占生产与契约写入，唯一辅助只读审查。已收148项运行/恢复/传输组合回归、
90项最终协议与wire、mypy280通过；后端全量make check和桌面最终门禁在执行。
新直接授权仅reload8771及1次新隔离数据副本断点续跑，8文本/1目标图片/900秒，
不重跑前六轮，失败即停。0费用准备已验证Source/资源/断点identity与累计预算。
原项目工作目录只读，所有新Run/实体/图像在副本，不能改断点身份绕过保护。
未reload/未提交新收费请求；上一轮1921/838和旧DMG不作为本轮版本证明。

用户指出交付重心失衡，本轮不增加模式；后续按代表任务、正式App入口、同一
源码CI和安装包收敛发布候选。详细退出标准见AGENT_IMPROVEMENT_PLAN最新段。

## 定向返工验收与显式结果修订（2026-10-16，本地门禁通过并已加载）

用户新直接授权一次隔离定向返工，最多16文本/1图片/900秒、不重载。实际在新的
私有副本中从原固定版本和conversation开始：7次文本、0图片、290.77秒，出图前
pre_render审查180秒read timeout，Run failed/runtime_timeout；预算仍余9轮。
失败即halt，未收费重试。原业务目录完整文件指纹、旧Run/版本行和Source hash不变。
不是移除预算就能解决。执行者依据此前真实PNG核对记录，通过副本local_user接口
提交验收意见，不冒称本轮用户亲手逐项评审或专家认证。原报告没有修改。

本地修正是显式结果修订协议，而非降低业务检查：同Project/Agent/committed版本/
conversation的上一份结果提供base_run_id，模型明确选择后可只交改动字段，系统从
实际保存的结果合并完整候选并继续所有输出、预审和带图终审；图片仍显式复用。
跨版本/跨对话/过期基线拒绝，恢复沿原用户回合边界。基线不授予任何工具权限。
完整图片动作示例明确design_context在顶层；复用ID统一解析为真实Project产物，
错误批量返回字段位置，持久化model.output_rejected并在事件列表直接显示未执行。
审查只剔除有明确effect_started=false和协议错误证据的参数修复噪音；真实工具/
图像/业务审查/用户事实保留。新增请求内容大小与观察数量，未调整超时/推理强度。

最终make check1921pass/782warnings/450.82秒、format517/Ruff/mypy279及依赖锁
通过。Desktop838/92files、双App tsc/build通过。浏览器实际组件+合成数据发现并
修复旧网格把诊断挤成26px的问题；390/1280字段全宽、无横向溢出且证据可展开。
不是实际API/Provider E2E，临时页/标签已清理。源码清单
b5bbe1aef3be5c2a4df22e110e6fceb71dc4e522762ff7a48edc2e896204f383。
用户新直接授权仅reload后，8771从71722到78258、health/local0038 ready，19张
历史表完整摘要一致，5173/8772未动。审计/tmp/veyra-result-revision-reload-20261016.json。
本次reload授权已消费，0模型/图片/人评POST，不再收费测试。此改动不
证明180秒Provider超时或Logo一致性已经解决。私有失败证据与后续动作见HANDOFF。

## 外部人评与定向图片修订（2026-10-16，门禁通过并已加载）

结果验收的人评不再只是等待标记：本地用户可对human_review条件提交通过/未通过/
证据不足及依据。提交绑定固定版本、spec/result快照和链头，重新核对所选内容与
真实Artifact字节；并发冲突刷新后重提。只追加evaluation.reviewed派生报告及幂等
收据，保留父报告、改判谱系和原Run，不改机器检查、不冒称专家认证。evaluator v2
记录人工图像依据，旧v1仍可读但不补造历史字节证明。预览需主动开启，核对size/SHA
后仅显示支持的位图，历史报告只读，未知网络结果不自动重发。

提交意见不会运行Agent。下一次同版本对话的明确用户回合可将上次结果的人评作为
有界数据使用，不获得额外权限。native render_images可显式复用同Project真实图片，
坏/外部引用在新请求前拒绝；新视角可共享design_context。该brief不是图像编辑输入，
不能保证视觉一致。脚本API/SQLite/PNG完整场景验证4初始图片后仅重画1份、复用3份，
旧结果与版本保留；没有额外模型调用发生在人评提交时。

原生图片已固定且可读取时，带图终审覆盖最新文字和图片，不再重复纯文本审查。
隐式brief缓存可能触发新出图，仍保留出图前审查。所有原必需规则和图像条件不变。
这证明减少一次特定路径的重复请求，不代表真实Kimi/Qwen延迟已改善。

最终make check1874pass/776warnings/434.19秒，format513/Ruff/mypy278及依赖锁通过；
Desktop836/92files、双App tsc/build通过。390/1280浏览器仅生产组件+合成API交互，
未操作实际Run或Provider。生产内容清单97fc9aec72b292474c473152ecd2a608be02d519d913bdfa51a4e478fdf144dd。
按本轮新直接授权仅8771从64137重载至71722/local0038，实际人评POST已加载，19张
历史表摘要不变，5173/8772未动，零收费/人评提交。没有新打包、提交或CI。本轮不是
视觉质量重新验收；原标识漂移、额外贴章、935.88秒案例仍需新的有界真实修订验证。

## 调度固定版本与执行安全（2026-10-16，门禁通过并已加载）

WorkItem在创建时锁定已提交Agent版本与Source hash，后续Draft或新提交不影响执行。
旧NULL绑定不自动猜latest，未尝试项可明确选版本；已尝试项不能改执行身份/输入。
dispatch/retry要求稳定请求键与预期attempt，Run创建和任务绑定同事务，重复网络请求
不生成第二次执行。已知失败Run经既有Runtime retry检查，不绕过未知副作用保护。

取消先持久化cancelling，再确认Runtime停止；停止未确认时保留并发槽位与Run链接。
租约恢复领取时重新核对过期快照和实际进展，避免迟到回收中止已续租任务。历史Graph
图片请求通过固定Source识别，新请求另有前置dispatch事件；未知效果不自动重新出图。
Monitor显示固定版本、前次Run与具体attempt错误，并提供旧未尝试项显式版本绑定。

最后复审补齐两处相同边界：历史Graph图片的Retry/Resume共用dispatch检查；WorkItem
拥有的Run拒绝从详情创建未跟踪子Run，创建型恢复统一经Monitor，同Run控制仍可用。
新增claim后/Run创建后的进程中断幂等回归，恢复/调度组合41通过。最终make check
1847pass/766warnings/445.35s，验收请求守卫另15项通过；全目录format509/Ruff/mypy276
通过，Desktop821/90files、双App tsc与打包内Desktop build通过。

已构建46MB本机DMG，sidecar独立启动/健康/Stop/端口冲突及hdiutil镜像验证通过。
Source/迁移/资源/前端/打包内容清单为
581c6e2860a9685494a1f530f26bdc35253ab04690b1a1ac33f0517038898bc3，非Git提交。
DMG SHA256为90daa0560b1bd5989e2636dd67b3383ffa37ea5749e057ff2faa97bd3380fc4c。
尚无Apple Team签名/公证，严格bundle签名检查未通过，也未安装验收，不能称正式发行。

新直接授权后仅8771从PID52001重载至64137/local0038 ready；15张历史表旧字段
摘要不变，旧绑定未填latest，5173/8772未动。此次reload授权已消费。新的独立真实
包装验收在/private/tmp/veyra-packaging-acceptance-20261016进行，固定原Source与1113字
需求，预发送text32/image8硬界限与Provider失败halt只作用本次收费验收，不改产品额度。
最终已收一次真实Run：18次文本、4次图片、0 Provider错误，935.88秒走完三方案/
选2/深蓝银15元修改/确认/四图/模型最终审查，status=unverified。预算曾同Run续额，
原Source未改；四张实际Artifact的字节/hash/大小/归属经正式离线评价4项通过。
V1/V2与5次实体修订完整可查，成本独立Decimal合计15，仍不等于真实价格/物理认证。

业务质量没有验收通过：独立视觉检查发现Logo漂移和未要求的认证贴章等，模型图片
审查未检出；revision4在0图片时已经由模型写为finalized。此状态不是平台交付证据。
需要正式候选/已审交付边界与外部反馈，不以状态字符串黑名单补丁处理。15分36秒
时延仍不达标；下一阶段优先减少重复审查、图像一致性与定向返工、按阶段实测效率，
不是先扩张更多角色。可读业务报告在私有验收目录，完整定位见HANDOFF。本次reload
和真实收费授权均已消费，不自动再次收费。旧包装Run/版本未改写，无commit/push/新CI。

## 运行结果验收基础闭环（2026-10-15，本地门禁通过并已加载）

在运行详情展开“结果验收”后才读取历史报告；不在普通查看时增加验收请求。
用户明确选输出路径、必需/建议、检查方法和独立期望，不从Agent输出自动填答案。
支持严格JSON、精确十进制、集合、实际Artifact完整性及等待人工评审的状态。
后者尚无提交人评结论的入口，不将awaiting_human自动判通过。数字基线采用文本，
不以浮点容差隐藏差额；含点、中文、嵌套$和空键通过路径段数组精确定位。

新EvaluationSpec为私有版本绑定规格，不改Source、TaskStructure或旧版本。
RunEvaluationService离线读取实际Run/固定Source与Artifact字节；比较独立基线，
保存spec/input/result/source/behavior/lock摘要与评估器版本，逐条状态和公开原因。
模型生成基线始终unknown；reference/fixture是用户声明，不伪装已认证资料。
报告accepted只覆盖所选条件，独立于Run.status，不能当全部原需求通过。
小值保留实际值，较大值仅保存摘要，报告展示条件对应的期望、实际或摘要。
Workflow旧记录缺独立原始输入快照时input_hash=null/not_saved，不反推已变上下文。

Agent与Workflow均有GET/POST .../runs/{run_id}/evaluations；显式POST绑定版本，
拒绝活跃Run，幂等并发只追加一份evaluation.completed本地证据，不触发模型、
Tool、审批或Workflow续跑。历史报告不可变；结果未知只刷新，人工重试复用键；
成功后明确再验收可用新键核对后续损坏，不返回旧快照冒充当前检查。
输出契约另按固定Source检查；产物核对所属Project、摘要、大小和声明元数据，
不把图片存在等同视觉一致性、真实报价或物理认证。未记录的事实保持未知。

专项：19单测、8个实际API/SQLite与原生文件场景；加旧契约共124通过。
运行详情/验收/client/Knowledge相关55通过；Desktop最终全量794/88files通过
（maxWorkers=4），最终typecheck/build已通过，bundle-size warning保留。
首轮Schema枚举顺序/闭合规则不一致已修正并通过专门回归；旧全量已中止、
不当最终结果。一次Desktop全量命中既有导航focus时序失败，未改无关产品代码
或弱化断言，限制测试并发后全量通过。当前生产目录manifest：
b731a6ac41965937f25731e3b5d7a2becfd51ee06afa2d7081e0b8ef76597715。
完整回归首次收1828pass/1fail（新增端点未加入scaffold路由清单），已补正式
Agent/Workflow路径命名和清单，未弱化清单相等断言。最终make check已收exit0：
1829 passed/747 warnings/411.89s；format501/Ruff/mypy272及依赖锁通过。
最终全量日志/tmp/veyra-result-evaluation-route-safe-final-check-20261015.log。
桌面最终日志/tmp/veyra-result-evaluation-desktop-safe-final-20261015.log与
/tmp/veyra-result-evaluation-desktop-safe-final-build-20261015.log。

浏览器仅隔离合成页面：390px及1280px无横向溢出，编辑/报告交互通过；无真实
用户数据、Provider或实际API请求。截图/tmp/veyra-result-evaluation-synthetic-
mobile-20261015.png与同前缀desktop，临时HTML和测试tab已移除。不是完整App
浏览器/真实Provider/包装业务验收。门禁后收到本次新直接授权，仅重载8771、
不做收费测试；零active后优雅重载PID47499至52001，health ok/local_0037 ready。
新进程工作目录与b731内容清单一致，实际OpenAPI的Agent/Workflow验收GET/POST
均已加载，既有budget字段保留。13张运行/等待/收据/命令/幂等/两类固定版本表
前后计数及SHA256完全一致；5173/8772进程未变。未提交验收POST或运行命令。
审计/tmp/veyra-result-evaluation-reload-20261015.json，单次submitted guard已消费。
health build_sha仍为旧启动环境标签，不作为当前源码身份或新Git提交证明。
本轮没有收费调用、主库验收报告或commit/push。后续仍需用例批次/版本回归、
有证据的修改提案与人评闭环、父Workflow整体恢复及单独授权的真实包装交付。

## 执行预算续接与可恢复断点（2026-10-15，本地门禁通过并已加载）

本轮实现完整预算授权路径：耗尽/交付余量不足保存预算等待；extend_budget
绑定当前request ID与幂等键，在同Run累加额度，不改Source/业务检查/工具权限。
默认主机总模型额度512、单次人工追加64均可配置；初始Factory额度统一可配置
默认16，不再根据Tool有无猜测。次数不是Token/金额/图片请求硬上限。

Actor/Reviewer请求前、准备动作后和效果完成边界持久化execution checkpoint，
保留累计消耗、工具观察、候选/检查/图片缓存。终态恢复沿现有descendant语义，
原Run不改写。未知Tool/图片dispatch出现在checkpoint之后时仍拒绝自动重放。
收据使用稳定call ID去重，避免多次checkpoint/取消/失败存储重复同一调用。
复核修正无finalization图片Agent的初始空缓存问题，图片结果入缓存后才可形成
可恢复完成点；首次final合法复用已有ArtifactRefs的原行为保留。

Advisory-only审查无额度或Provider失败不阻断有效交付，披露未评估项；Required
检查仍严格。相同候选的有效文本预审可复用，不能把单元测试节省调用写成真实
Provider响应已更快。失败的已消费调用仍计入预算，恢复不隐式重置。

Desktop统一BudgetContinuation，覆盖Agent Chat、Run Detail、Studio/执行画布、
Workflow App/Panel；Builder试跑可进入详情，不把预算当工具批准。预算Stop与
追加绑定请求，未知网络结果只刷新。Agent Chat移除start(lastInputs)式盲重试。
补齐client事件解析器对预算/审查失败三个已有事件的识别，避免新证据被丢弃。

已收：生命周期API11个场景通过，含父子预算原子回滚、并发单次消费、后续写入
仍需审批、写入后超时恢复不重写、4图和Entity修订保留、grant后未调度即重启、
无policy图片完成点中断不重出图；控制/请求/Builder专项30pass；策略/图片66pass；
桌面最终769/86files、typecheck/build通过。最终make check已收exit0：1802 passed、
739 warnings、390.68s；format496/Ruff/mypy269及依赖锁检查通过。生产目录
manifest为23778cbe99145f79f2e21d954614aa8c010f0e31873e58f102e1a0d6b797e4d4，
不是Git提交。日志/tmp/veyra-execution-lifecycle-safe-final-check-20261015.log。
所有这些为隔离临时数据与脚本模型证据，不是真实Kimi/Qwen或完整浏览器验收。
本轮门禁后收到新直接授权，仅重载8771、不做收费测试：确认零active后优雅
重载PID14371至47499，health ok/database_ready=true/local_0037，进程工作目录
及源码manifest匹配，实际OpenAPI已包含additional_turns。10张运行/等待/收据/
固定版本表完整摘要不变，5173PID918与8772PID928未动，未改旧失败Run或版本。
health build_sha仍是启动环境旧标签，不当作新内容身份。私有审计
/tmp/veyra-execution-lifecycle-reload-20261015.json，单次guard已消费。
本轮新增Provider/图片请求为0；不能把服务加载视为真实业务交付验收。
父Workflow进程丢失后的整体恢复、通用业务质量与真实图片交付仍未完成。

## 上一阶段：审查专用超时与运行预算可见性（2026-10-15）

当前生产代码新增同客户端的complete_review：默认180s read timeout，配置
VEYRA_RUNTIME_REVIEW_TIMEOUT_SECONDS可调至300s；普通行动默认90s与其他
HTTP阶段设置不变。模型/凭据/transport不复制或切换，未增加自动收费重试。
HTTP超时分类只保存read/connect/write/pool及阈值，不泄漏异常原文/请求内容。
审查失败事件保留pre_render/candidate/images阶段、code、公共原因、耗时和
安全Provider诊断；不能把失败变成finalization.accepted或rule_verified。

新增预算事件由真实模型发起事件计数，恢复沿用checkpoint累计；行动与必需
审查一起显示used/limit/remaining，不代表Token/金额/图片请求数。出图前额度
不足公开所需最少交付余量，未请求图片、未发布结果。Python事件分类与JSON
Schema、TypeScript客户端同步，旧记录不补造原因。Source、版本和Run预算
没暗改：当时平台默认8/硬上限32，composer有工具16的粗略规则；现已由上节
统一配置初始额度与显式续额取代，旧版本仍不改写。

证据：Runtime定向156 pass；正式契约/HTTP/SQLite20 pass；Factory/batch79
pass。桌面最终753 pass/85files/15.98s，typecheck/build通过，已有bundle warning
保留。第一轮全量在事件分类/Schema同步完成前启动，缓存旧契约，5failed /
1774passed，不是本次最终门禁；契约已同步并重新运行完整make check。
最终完整make check已收：1779 passed/728warnings/358.82s/exit0，format492/
Ruff/mypy267与依赖锁通过；日志
/tmp/veyra-budget-review-final-check-20261015.log。该次已包含完整新事件分类
及Schema，正式契约与实际HTTP/SQLite路径通过，不沿用首轮失败作当前结果。
桌面最终日志/tmp/veyra-budget-review-final-desktop-test-20261015.log与
/tmp/veyra-budget-review-final-desktop-build-20261015.log。生产目录内容清单
SHA256为0cbd2ad7d1ef5d34c4ed37693a4191c7494f8070d5f314a7b3eaa66348768e43，
由backend/src、contracts/schemas、Desktop src与TS API contracts的排序文件
摘要清单计算，非Git commit或运行数据hash。

不把默认审查等待延长解释为速度已提升。最近真实终态仍是2026-10-14图片前
runtime_timeout/204.11s/0图片，真图最终交付未验收。此前收费授权已消费，不
新增Provider调用。全量门禁后用户新明确授权仅重载8771、不收费：已从
PID21696优雅重载至PID14371，health ok/database_ready=true/local_0037。
10张运行/等待/收据/固定版本表的计数和SHA256完全一致，5173PID918与8772PID928
不变；源目录manifest一致。健康接口build_sha仍为旧环境标签，不当作新的
Git提交或唯一内容身份。私有审计/tmp/veyra-budget-review-reload-20261015.json，
执行guard已消费。当时该阶段代码已加载，但没有新增模型/图片测试，下一次真实收费
验收仍需独立新授权。

## 批处理、参数证据与图片续接终态（2026-10-14）

本轮新增 `tool_batch`：一次模型动作内顺序执行独立本地原生观察/纯计算，整批
无效果预检、逐项重授权与实现身份复查；不借用旧 approval，不支持网络、写入、
图片或自定义工具批处理。每项收据、索引、真实成功/失败和截断标记分别保留。
拒绝批次不清除此前重复写入保护。3 次实际原生算术用 batch+final 两个模型
turn，实际 API/SQLite 保存 3 份收据；这是脚本模型路径证据，不是实际响应
时间提升的证明。批处理定向10 pass，旧输入/loop回归81 pass，图像契约106 pass。

输入检查集中到 tool_input_contract，不保留重复的字符串判断管线。MCP/Native
诊断仅包含 schema-owned path、类别、类型、公开限值，隐藏实例值和动态键。
新事件和模型反馈使用同一证据，页面可读；旧失败不猜测补原因。算术的既有
观察恢复仍保留失败收据，补充安全表达式原因；不是把错误标成成功。恢复依据
实际执行的原生 adapter 快照，不因之后的注入/漂移假装可信观察。

原生出图契约修正两处实际矛盾：旧 prompt 尾句不再禁止返回已生成的真实Refs，
无 finalization 的 native 图像也在 final 复用缓存；显式图片 Prompt 不追加
已被后续选择/预算修改覆盖的旧原始输入。Graph 旧行为保留，两个专项负例通过。

第一次本轮全量门禁为1769 passed/728warnings/368.28s，Desktop749/84files，
build/typecheck通过。随后按新明确授权只重载8771至PID91171/local0037 ready，
所有等待记录（含已有Run）哈希保持，5173/8772未动。从当前V2同Run、同固定
版本继续，没有重规划、改Source、重建Run或取消criteria。

本次真实图片验收**没有完成**。实际终态 `runtime_timeout`，发生于 pre_render
交付审查，约204.11s。新增4个actor模型turn（两个未声明Entity Write参数拒绝、
一次成功写入、一次render action）及1个review尝试；服务90s文本超时边界命中。
0图片响应/0产物/0Qwen图片请求，未输出最终结果。Source v1未改，设计记录
保留revision1/2/3及V1/V2/V3，最新confirmed/预算15/generated_images=[]。
不是Qwen拒绝，也不是本次已由budget error终止；剩余轮次不足是同时发现的
另一个问题。Root尝试停止以免继续图片费用时，Run已经自行超时失败，停止
脚本在状态断言处退出，没有发stop命令，不把它写成取消成功。

失败后停止全部新增收费调用，保留完整证据并做本地修正：未声明参数反馈列
出允许的schema参数路径；native出图前检查是否留够预审/状态保存/final及复检
轮次，旧final自动出图也先检查两阶段审查预算；review使用完整任务描述及
criteria，去掉未执行工具尝试和重复final/render候选，保留真实用户回复、问题
及成功工具证据。没有盲目加全局timeout或删除交付检查。这些修正只证明本地
行为，尚无新真实图片/交付验收，不能把前1769计数代替修正后的最终门禁。

本次收费授权已消费。私有审计 `/tmp/veyra-image-delivery-20261014.json`、
`/tmp/veyra-image-delivery-20261014.log`、提交guard
`/tmp/veyra-image-delivery-20261014.submitted`。不得重执行continue/start、修改
失败Run或复用旧授权收费。后续还需解决合适的执行预算/审查时延并重新授权
完整业务验收；不通过无上限循环、静默改pinned版本或需求降级制造成功。

失败后的最终门禁已收：`make check` **1772 passed /728warnings /366.93s /
exit0**，format492/Ruff/mypy267通过，日志
`/tmp/veyra-delivery-safe-final-check-20261014.log`。Desktop最终 **749 passed /
84files /18.49s**、typecheck/build通过，bundle warning保留；最终日志
`/tmp/veyra-delivery-safe-desktop-test-20261014.log` 与
`/tmp/veyra-delivery-safe-desktop-build-20261014.log`。之后仅文档、只读页面核对。
本轮明确8771授权下零active后加载最终本地修正至PID21696/local0037 ready，
5173PID918/8772PID928不动，无追加模型调用或收费重试。真实页面显示timeout、
V3确认进度与两次无效果的额外参数类别；缺失的旧参数名未猜补。
截图 `/tmp/veyra-image-delivery-failure-browser-20261014.png` 和
`/tmp/veyra-input-diagnostic-browser-20261014.png`，仅当前Run、未点击安全重试。
精简上下文和预算预留没有新的真实通过证明，文本90s默认超时并未改成无限。

## 已创建固定版本与真实文字交互（2026-10-14，最新）

用户要求继续下一阶段后，在上轮隔离 Project 应用精确 review 提案并保存 v1，
没有重新生成或手改业务 Source。草稿及 committed 版本的 source/behavior/lock
hash 与提案一致，固定版本的无副作用预检 ready=true、setup_issues=[]，模型
和全部 5 个工具依赖就绪。没有手动新增 Key、全局设置或不兼容模型绑定。
初次私有 commit 脚本的非 UUIDv7 idempotency key 被 422 拒绝、未创建版本；
仅修正测试脚本键后从已创建 Draft 续接，commit 成功，不重复 Apply。

提案的历史 requires_configuration 不代表这个 v1 实际缺配置：它来自 Catalog
通用 Model 行的静态默认值。新增纯 Agent 生成现在只有在角色解析完整、唯一、
issue-free、每个角色有可信的 will_bind/already_bound 证据时才投影 ready。
缺角色/未知能力/显式失效或冲突/缺证明/optional issue/非纯 Agent/不可用资源
不被提升，旧提案和 Catalog 不改写。模型执行仍按当前配置和证据重新预检。

本轮最终 backend `make check` **1749 passed /725 warnings /351.77s /exit0**，
format487/Ruff/mypy265/依赖与锁通过；日志
`/tmp/veyra-next-stage-final-check-20261014.log`。模型就绪定向 **119 passed**；
Runtime/State/Finalization 定向 **43 passed**。新增脚本模型 API 验收覆盖精确
Apply/commit、同 Run 用户选择、4 个真实本地测试产物、画像检查返工后只重做
front、两次实际 Entity Write 与历史核对。其他 3 个引用保留；只证明执行/证据
路径，不是图片质量或真实 Provider 的最终业务交付验收。

用户随后明确授权仅重载 8771 和一次文字 Run，到选择及一次修改，不确认最终
方案、不主动触发图片。零 active 后仅 8771 重载为 PID9190/local0037 ready；
原 30 waiting Builder rows 哈希保持，5173 PID918 与 8772 PID928 未动。
实际 Run 只执行 committed v1，不从可变 Draft 读取；10 轮模型调用事件完成
三方案展示和一次修改，保持同 Run、同 Entity，停在第二次等待用户输入。
首轮展示 **85.64s**，修改段 **64.82s**，由公开事件时间计算，不含两次等待
间的人工检查。当前仍有串行模型/工具往返成本，不能称响应速度问题全部解决。

真实验收核对初始预算 40、三方案成本 14/19/28；修改后第二方案为深蓝银、
预算 15、算术成本 14.5。数据库 revision 1/2 和设计 V1/V2 实际存在，新状态
为 revising，未冒称 confirmed/finalized；旧版本保留。一次工具输入 Schema
拒绝 effect_started=false，随后 Agent 按观测自修并成功写入，Run error=null。
它不是整轮失败，也不是测试器重发收费调用。现有该类拒绝只公开 Schema
类别，细到参数路径的诊断仍需完善，不能将通用 code 当完整原因证明。

本轮没有新 Builder Provider 请求、新 Run 重试或图片请求；隔离 Project 只有
1 个 Run，图片响应事件/产物数量均 0，最终 result 未发布。等待是本次刻意不
批准最终方案的验收终点，不是业务最终通过；后续仍需真实图片、交付复检及
历史回退验收。私有完整数据只在 `/tmp/veyra-finalization-text-run-20261014.json`；
无副作用核对 `/tmp/veyra-finalization-text-verifier-20261014.json`，未将用户输入
或业务状态复制进仓库。公开计划确有更新，仍为模型自报，不当独立真值。

浏览器复核后修正 RunDetail 文案：当前 native/Workflow input 等待显示等待输入，
真正工具审批保持等待审批；最新请求覆盖历史请求。工具输入拒绝有可读标题，
原始 event code 留作证据，不改变命令或授权。当前 Desktop 最终 **746 passed /
83 files /15.95s**，类型检查和 production build 通过，bundle-size warning
保留；日志 `/tmp/veyra-next-stage-desktop-test-20261014.log` 与
`/tmp/veyra-next-stage-desktop-build-20261014.log`。没有因此重新运行模型或重启
后台。真实页面在当前 468px 视口显示完整 V2 内容与等待输入/公开计划，截图
`/tmp/veyra-agent-real-v2-20261014.png` 和
`/tmp/veyra-agent-real-waiting-20261014.png`；这不是多视口或打包验收。

## 自治交付闭环与真实生成审查（2026-10-14，当前证据）

本轮修正的不是取消覆盖审查，而是让 actor 内部的检查拥有实际 Runtime 路径：
候选 final 先经过可选 finalization，规则/模型/实际图片反馈回到同一个 Run，
revise、needs_input、required uncertain 不发布最终 result。独立门禁仍属于
Workflow。旧无策略 Source 不自动升级，旧 behavior hash 保持；公开短计划不是
隐藏推理或独立完成证明。render_images 返回真实 ArtifactRefs，可在 final 前
通过现有 Entity Tools 记录历史；状态写入是进度，不是原子业务发布或验收证明。

首次完整门禁为 1730 passed /2 failed，暴露 wire enum 顺序与输入保护字段
alias 两项回归；两项修正后最终 `make check` exit0：**1732 passed /723
warnings /354.78s**，487 格式文件、Ruff、mypy 265 source files、依赖与锁检查
均通过。最终日志 `/tmp/veyra-finalization-final-check-20261014.log`。Desktop
全量 **735 passed /83 files**，两端 typecheck、Desktop production build 通过；
大 bundle warning 保留，未将其当作性能已优化的证明。独立只读窄查复跑相关
单元/脚本模型 API 集成 **39 passed**，未发现非 pass 绕过 finalization 发布。

用户新授权在这些门禁之后仅重载 8771、从保留计划继续最多一次真实覆盖审查。
重载前无活跃 Runtime/Workflow/Builder，原 30 waiting rows 完整哈希保存；
8771 由原 supervisor 重载至 PID51648，local_0037 ready。5173 PID918、8772
PID928 未动。health 的旧 build_sha 是环境标签，不能代替本轮源码身份；私有
审计保存 backend/contracts/nodes/Desktop/contracts-client 内容摘要，真实调用
前后摘要一致。没有 migration、commit、push、reset 或清理。

真实审查 **41.96s /1 次 TaskCoverageV1 /Provider success**，生成 review 提案，
Operation waiting，error_code null，Factory state review。没有重新识别需求或
生成 TaskStructure；显示的 intent/compile 阶段包含本地续接事件，不是额外模型
请求。完整原需求、原两条失败 Operation/Factory rows 及原 30 waiting rows
哈希一致；新提案产生第 31 条 waiting，是本轮新记录，不是旧记录被改写。
临时审计首次将新增 waiting 计入旧集合导致 assertion exit1，已仅修正私有审计
的集合范围并只读重查 exit0；没有重发收费请求或修改产品源码来制造成功。

精确提案 Source 验证和三类 hash/roundtrip 一致：自治 loop、16 条 required
criteria、实际图片审查和选择前预审、4 个图片输出、gift_packaging_project 的
revision 历史及完整原需求指令。真实浏览器显示审查方案和等待确认；截图
`/tmp/veyra-finalization-review-browser-20261014.png` 不含账号/侧栏。私有审计
`/tmp/veyra-finalization-review-only-20261014.json` 与
`/tmp/veyra-finalization-review-only-20261014-audit.log`。没有把原用户需求、IR
或 Provider 原始响应复制进仓库。

提案仍标 requires_configuration；primary kimi-k3 与 image qwen-image-3.0
均为 will_bind 候选，但通用 Model resource 仍 runtime_not_configured。该状态
不能当作运行预检已完成，也不表示本次 Provider 失败。未执行 Apply、commit
版本、Agent/Workflow Run 或图片生成，隔离 Project 的这些实体/Run 数仍为 0。
本次从保留计划的 42s 不等于全新复杂需求生成端到端只需 42s。下一验收应在
明确授权后核对 exact proposal Apply/绑定/committed preflight，再做真实多轮
选择、修改、图片审查、状态/历史核对；当前不能宣称整个产品的业务验收通过。

## 请求绑定、父子恢复与真实页面验证（2026-10-12，最新）

桌面七条动作路径（Agent Chat/Studio、独立执行画布、Run Detail、Workflow App、
Workflow Studio、Builder Test）提交用户实际看到的 expected_request_id；缺 ID
不发送，失败后只刷新，不使用新 ID 自动重放旧回答或批准。真实 API client 已保留
子问题的 schema/context/ID/实际 Tool 目标，补上此前只在组件 mock 中存在的字段。

Runtime 将 ID 校验、命令记录和审批解决放在同一 SQLite 事务；新 ID 是 approval_id，
旧 event_id 可作为当前请求别名。ID 参与幂等摘要。父 Workflow 的继续状态和 child
命令记录同事务提交，使用独立 child key 避免与直接 Child App 操作冲突。旧 API
无 ID 的 current-wait 调用仍兼容，但不享有过期保护；桌面控制不走此路径。

直接回复/停止 Child App 后，父等待投影会更新或继续已启动流程；重复读取不重复
派发。历史独立等待补稳定 ID，不执行任务。独立输入/审批跨节点时补 node.completed；
原生追问不会提前将整个 AgentCall 标记完成。9 项新增隔离 HTTP/SQLite/原生 Tool
场景覆盖过期问题、后续写入误审批、两个记录回滚、并发刷新、取消和旧等待恢复。

最终 make check **1548 passed /623 warnings /312.96s /exit0**，日志
`/tmp/veyra-request-binding-final-check-20261012.log`。Desktop **716 passed /
80 files**，两端 typecheck 和 Desktop production build 通过。首次 1548 full
属于完成事件修复前，不能代替本节最终结果；组件/jsdom 层不替代真实 Provider。

按用户本轮“仅重载8771、不做收费测试”授权加载，最终 PID29496/local0037 ready；
5173/8772 不重启，原30 waiting构建IDs精确保持。health build标签仍是旧环境标识，
不能用它当唯一 Source revision，实际新OpenAPI字段和启动时间已核准。

独立无模型 Project 中，通过正式 API 创建和 commit 仅含 Start/HumanApproval/
Transform/Output 的 Workflow。真实浏览器连续两次回复得到 Selection: Beta，
最终进度4/4；旧请求实测返回422且当前等待不变，children为空，Project Provider
receipts=0。该验证没有调用模型，不是 CSV 真实生成或业务对账验收。
截图 `/tmp/veyra-request-binding-browser-complete-20261012.png`，安全审计
`/tmp/veyra-request-binding-browser-audit-20261012.json`。真实生成主线仍待完成。

## 原生追问、状态归属与用途预算（2026-10-12，最新本地修复）

基于上节实际失败 IR，零 Provider 复放确认新校验能提前返回
`business_gate_needs_independent_stage`。actor 自身 human_input 现在归其 loop
指令，不再无条件追加到调用之后；独立 actor-less HumanInput 仍是 typed Workflow
步骤。同一单 actor 的原生状态遇外部 Verifier 时，子 Agent 保留 state_contract
和完整 Entity 能力，不生成重复 state_write 或父 Workflow 的无用 Tool 锁。
underscore/hyphen stage alias 用一致归属比较，问题与状态都不丢。

Workflow 已传递子 Agent 的当前 question/context/request_id/input_schema，reply
转给同一个 pinned child Run；不把 reply 转为 approve，也不扩大后续 Tool 授权。
隔离 HTTP/SQLite/原生文件测试覆盖连续两次追问、同 key 重放、无效命令、业务
拒绝、停止与后续独立写审批；前置资料不变，未批准不写，批准后产物可读。
原生 state+Verifier 组合当前是静态编译证据，不冒充该组合的真实模型运行验收。

门禁检查与编译共用 effective_actor_capabilities，包含原生状态派生的写能力。
审查发现的 text_generation 原始角色自动获得 entity_write 后越过门禁的案例
已修并加负例；两个检查入口均拒绝，无 Source 或 orchestration。它只检查明确
capability 的权限/阶段关系，不宣称证明所有效果参数、复杂分支或自定义 Tool。

默认 semantic repairs=3、protocol fallback=1、new method grounding=2，Planner
全部规划/修复/coverage requests<=8。正常 grounding 与协议协商不占 semantic
纠错份额；max_repairs 可由调用方配置，不再硬夹为3，仍受总请求预算限制。
协议回退只针对 JSON/schema 事实，不把删除语义职责当作解码协议问题。预算耗尽
保留安全阶段/原因/位置；真实 Condition 类型诊断保留，不含实例值。
前置 Builder intent/interview 不在此计数，尚无操作级 Token/费用硬预算。

Desktop 全量 **701 passed /79 files**，Desktop/Community typecheck、Desktop
production build 通过；jsdom 的 canvas getContext 警告和 bundle size warning
不是新增验收证据。后端最终门禁日志为
`/tmp/veyra-native-boundaries-budget-final-check-20261012.log`，**1539 passed /
614 warnings /299.81s /exit0**，464格式、Ruff、依赖/锁、mypy254通过。
上一 full 1538 属于派生能力门禁修复前，不能作为当前 Source 的最终门禁。

下一切片先绑定 expected waiting request 到父子 Runtime 同一事务，防止旧标签页
新 key 回复/审批错对象；目前 request_id 只用于显示与清空字段。同 key 幂等重放
不等于过期命令防护。继续补原输入保护、审批快照/确定性保存和业务验收入口。
这一切片没有新 Provider 请求、重载服务、Git commit/push；8771 仍为上轮授权
重载的 PID17922，本节 backend 源码未加载，不声称真实主线已通过。

## 真实复测：原生证据与边界归属（2026-10-12）

本轮修复了最终repair异常被旧coverage诊断覆盖、精读Skill按旧actor ID冻结
导致合法重分配失败两处问题。精确ref/hash/capability及必要用途次数、真实Tool
职责和写范围继续保留；同一已读方法重分配不新增grounding调用。API/SQLite
回归确认错误阶段、schema位置、预算和last_validated标记可保存，不泄漏模型值。

CSV Tool新增1.2公开并校验真实源SHA、精确十进制、物理行跨度及截断字段，
采用显式opt-in原生结果Schema验证，收据记录output_verification。1.0/1.1的
hash与pin保持不变。Schema通过仍不是业务答案正确的证明。

完整门禁 **1528 passed / exit0**，464文件格式/Ruff/依赖与锁、mypy通过；
日志 `/tmp/veyra-phase0-final-full-check-20261011.log`。脚本Factory缺writer→
coverage→repair→Apply/commit→原生运行的12路径通过，两输入来源和三种审批
结果均有报告/原始bytes验证。该层次不能代替真实模型生成。

收到本轮明确授权后，仅重载8771为PID17922；原30条waiting构建记录未变，
5173/8772 PID不变。新隔离Project（本地记录）提交
同一完整243字需求一次。6次Provider请求全success，462秒后内部失败，未生成
Proposal/Agent/Workflow/Run，未写报告，原CSV SHA保持。终态证据
`/tmp/veyra-phase0-real-acceptance-terminal-20261012.json`。

此次已过规划与编译但coverage拒绝：单一reconciler声称内部完成全部循环，
编译却把其human_input/Verifier/businessapproval/state追加到完整ActorCall之后，
而该companion已拥有filesystem.write和entity.write。追问无条件且太晚、写入
在业务确认前可达、记录重复；不能撤掉覆盖检查来让该候选通过。用保存的IR
零Provider复放已核准这种顺序与权能矛盾，确定性fidelity尚不能拦截。

下一步修边界归属/编译前诊断及有总调用上限的分阶段预算。正常方法grounding
与一次协议回退目前消耗同一3次修复配额，coverage发现问题后已无空间纠正；
必须调整这一不合理耦合。停止本轮收费重试，不手补生成Source，不改写历史失败。

## Agent 自主性与执行反馈（2026-10-11，本地门禁通过）

已核对《Agent生成流程分析》正文、审查附件、当前代码与真实 Builder 终态。
最新有效 CSV 构建已恢复完整需求，但候选只有只读对账能力，缺报告写工具、
写范围和报告角色，TaskCoverage 因此阻断；这轮不是 Provider 限流。截图中
同时存在历史 429 与内部规划失败，不能合并为一个原因。真实主线尚未通过。

本轮优化实际执行反馈：loop 获得完整公共输出契约；有界离线 JSON Schema
在首个模型调用前检查，final 按实际约束校验并回灌不含实例值的纠错反馈。
可信内建只读工具的明确业务错误保存失败收据后交给模型决定下一步；写入、
自定义或未知副作用、权限/凭据/锁与取消仍保持独立执行语义。没有引入额外
固定 Judge 调用，不将同模型自评或 Schema 通过写成业务 verified。

单角色自己 actor stage 的 state 使用现有 Entity 工具，不单因 state 强制
Workflow。独立状态步骤、业务审批、条件与外部 Verifier 仍有真实门禁。两个
独立有序角色即可组成多 Agent Workflow，纯文本角色也保留真实 typed handoff，
main/editor 名称不再删除实际调度；原生提问进入 loop instructions，未来工作
笔记引用仍拒绝。没有动态委派、Supervisor 或并行执行的完成声明。

Builder/CSV 相关 93 tests 通过，含原生文件路径/上传 × 批准/业务拒绝/工具
拒绝六路径；状态 Apply/commit/Run 三项通过，第二 committed Run 更新同一
记录为 revision 2。模型为 scripted，不能替代真实 Provider 或浏览器验收。
最终 `make check` 退出 0，**1501 passed**；依赖/锁、462 文件格式、Ruff 和
mypy 253 源文件通过。已核准失败、取消及审批竞态的收据退出路径：四种真实
API 取消场景保持 cancelled、不重复收据、无后续效果。首次 full 的旧产品形态
断言失败已修正，不能把首次 1489 pass/1 fail 写成最终通过。没有重启 8771、
新增付费请求、Git commit/push 或修改用户 Project。

已结合新增 Cursor 构建闭环讨论形成 [后续方案](AGENT_IMPROVEMENT_PLAN.md)：
优先真实生成与交付，然后任务验收、隔离用例与回归、证据驱动修复，最后按需
扩展预算、动态规划与协作。该文是待实施方案，不是新能力已经验收的声明。

## 需求来源与共享引用契约（2026-10-11）

最近两次真实 CSV 构建的五次模型调用均成功返回，但内部规划校验失败，未生成可
Apply 的候选。后一次核对发现 Factory 仅收到短的“按上面要求重新生成”，最初完整
需求已掉出近期聊天窗口。更严格的校验不能解释或免除这种生成器主线回归；当前
尚未证明完整需求能生成并运行出正确报告。

需求来源现在与有界聊天分离：每个 Builder Operation 冻结用户原文和按顺序的修改，
意图理解与 Factory 规划消费同一快照；助手解释和失败消息不升级为用户要求。
重试复用冻结快照，旧记录从原请求恢复，不掺入之后的新修改。没有复制原始模型
返回或 Secret，也不改变用户历史消息。超限明确失败，不静默截去硬性要求。

任务输入引用与 Workflow 编译共用声明符号解析：支持明确命名的任务输入、
`input(s).name` 和已到达的 `stage.port`，大小写及下划线/连字符别名一致；未知、
未来、路径/自然语言和歧义别名不能被猜成端口。错误提供已声明输入及可用 producer，
让纠正依据真实符号表。该修复并不证明最近失败的具体原始引用内容；它修复了
已在本地复现的合同双标准。

评价分三层：生成契约与需求覆盖、真实固定版本运行、业务效果及重复使用。
TaskCoverage 是同一模型的候选复核，不能代替业务真值；现有 Verifier 的
`schema_valid` 仅检查对象、`artifact_exists` 仅检查绑定非空，不能宣称完整结果
Schema 或文件可打开。Tool use 有真实参数/授权/执行/回执；Planning 有结构化
编译；Reflection 尚未提供通用独立质量证明；多 Agent 为固定 Workflow 调用，
没有动态委派、自由消息和并行协作。Factory 默认高推理强度但仅支持的 Provider
发送，不能据参数或名称宣称所有 Agent 都使用经验证的推理模型。

本切片 72 相关测试及六个生产文件静态检查通过，最新完整 `make check` 退出 0、
**1463 passed**。旧失败记录只读复放恢复完整 243 字原文及修改，零 Provider 调用。
真实 CSV 主线、持久复用和统一浏览器回归仍需完成；准确终态及版本见 HANDOFF。

## Builder 生成协议与失败诊断（2026-10-09）

最新完整需求真实复测已越过输出格式与方法细化，仍在编译失败，未创建对象。
已声明输入支持 singular/plural前缀及下划线/连字符别名，15相关本地检查通过；
未知输入和路径表达式继续拒绝。零Provider复放捕获IR又发现阶段引用未声明输出：
单个actor只声明最终结果，阶段却假设多个中间端口。后续必须修任务规划的阶段
契约、产品形态和前置引用检查，不能改生成出的Agent或用虚构端口让它过检查。
当前仍未达到真实生成/运行产品验收；停止重复付费重试，先做本地复现与修复。

用户要求节制真实测试费用。Builder 不再在意图理解后重复付费 interview，独立
Factory访谈仍保留；理解/访谈上下文只传资源身份、说明、能力和可用性，实际 Tool
契约与所选 Skill 正文继续在规划阶段提供。内置资源 fixture 上下文字节减少59.6%，
真实理解请求包43643→25492bytes；这些是请求体证据，不是精确 token/账单统计。
已失败的 strict 格式按接口/模型/probe/schema 在服务内记忆为 JSON 模式偏好，
新 probe 或进程重新判断，严格本地校验始终保留。没有换模型降低生成质量。

实际方法已提供后的纠正复用该正文，不再再次消耗 grounding 调用；修复请求带原
必需交互契约，省略仍会失败，诊断标出 kind/stage。稳定 policy v4 区分模型配置
与 Agent runtime 能力，产品形态按任务职责决定。客户端保留安全限流type/code与
Retry-After数字，原始错误body不作为诊断保存。最新真实链曾429停止，补充充值后
仅做一次完整需求重试，仍须收取实际终态和Run验收。

该切片full make check1318 pass；catalog receipt hash后续补强另做harness定向，
不能把此前full当作后续所有源码的证明。Desktop终态preview清理65 tests/typecheck
通过。CSV只通过正式API导入隔离Project供后续运行，不是浏览器上传证明。

真实 CSV 构建在生成阶段失败，未创建 Agent。失败记录分别涉及缺输出定义和
不完整的 actor/task 输入输出字段；Provider 请求返回成功，但结果未通过本地校验。
最小七字段对照也复现当前接口 strict 输出空嵌套对象，而 json_object 返回完整且
校验有效的字段。这是输出协议兼容性证据，不能归因于用户需求太复杂或余额。

Factory 现在对实际违反 schema 的 strict 响应使用一次有界 JSON mode 回退，
保留同一模型、原始任务与严格本地校验；profile 声明 JSON mode unsupported 时
不回退，receipt 明确记录格式切换，仍与解析、语义和编译修复共享三次预算。
仅 IO 字段错误时，使用 server 选定路径的局部闭合修复契约；模型不能修改任意
位置，既有合法名称、类型、必填、多值及来源字段被冻结，合并后整份任务再校验。
后端 canonical TaskStructure 送回模型前转完整 wire projection，避免把省略默认
metadata 的内部格式与 Provider 命名数组格式混用；没有自动补全原始 Provider payload。

界面改为“生成失败”，提示具体的输入输出定义问题，保留原需求、重试和技术诊断；
旧对话消息保持原记录。重试尚未建立自己的 Factory session 时，不再显示上一轮
失败工作台。浏览器真实重试无需手动刷新就能看到阶段/计时和终态，生成成功与
运行成功仍须分别验收。设计审查沿用指定 skills 与现有组件，无新样式或动效依赖。

IO 切片全量 make check **1313 passed**；后续协议回退/合法字段保护的最新
Factory、Builder、Planner 定向 **79 passed**，mypy/Ruff/diff 通过。Desktop
相关 **64 passed**、typecheck/build通过。1313 数字属于协议回退前源码，后续
完整需求真实复测、CSV 读取/准确报告、持久状态与重复使用仍未通过产品验收。
最新运行和复测终态以 HANDOFF 与真实数据库为准；未 Git commit/push。

## Builder 实时进度恢复修复（2026-10-08）

用户报告刷新后才看到最新阶段。已复现慢查询饥饿：旧轮询每秒创建请求并递增
pullSeq，只接纳最后一轮；GET耗时超过1秒时会持续废弃已返回结果。现在每轮完成后
再排下一轮，保留卸载/替换token保护。Stream末尾旧snapshot不再覆盖poll已确认的
终态；当前会话身份提前记入URL、晚到旧resolution不会再应用。空operations的活跃
会话按conversation状态继续观察，首快照落后本地event时仍保留可信会话ID。

后台SSE在无新事件时每15秒发送注释heartbeat，不制造虚假进度、不暴露模型思考。
验证：Builder页面/API客户端96 tests、Backend conversation35 tests（含首快照先于慢
解析和idle heartbeat）、Desktop typecheck/build、相关Ruff/mypy/diff check通过。
该验收证明传输、慢响应与终态恢复；不能据此声称真实生成任务已成功。
8771仅在无活跃任务时重载为PID88611，build标签
`be8f36e-dirty-live-follow-20261008`；前端Vite热更新。未Git提交或推送。

## 生成器精确方法与编辑闭环（2026-10-08）

最新真实复测：充值后 retry 请求全部返回，但任务规划输出数组为空，修复耗尽后阻塞；
不是这次记录里的Provider限流/余额失败。已将 top-level outputs 的非空约束提前到provider
闭合schema，并统一精读阶段的normalize/validate；修复保留原需求，不靠默认result掩盖缺失。
该修复还需重载后真实再测。Directory full为1304 passed/1旧Artifact输入fixture failed，
已修fixture正确传path，Planner+Artifacts 29pass；不能将此full标记全通过。

在当前 HEAD `be8f36e` 上继续实现，未提交。TaskStructure 增加可审查的
`skill_choices`，记录使用方法的 actor、能力、准确引用及理由；旧契约仍可读。
Factory 先看资源元数据，再精读所选 Skill 的实际 hash/正文，以同一个最多三次
修复预算细化真实工具、输入输出、确认步骤和产物路径。代码验证目录、版本、hash、
Project pin 和选择资格；Skill 不替代可执行 Tool。复合产品按 actor 分别解析资源，
不把同能力的两种方法同时发给所有子 Agent。已精读的方法及新增必需能力、交互
契约跨 repair 保留；未精读的自动方法不能直接进入 Factory composition。

普通用户流程：Builder 复用已有验证证据的 Project binding 或用户默认文字模型，
不会替用户选任意其他 Provider。Agent App 的状态依据真实 readiness；App/Studio
可进入同一 Agent 的对话修改；Studio 各编辑视图都有保存与显式提交。保留
revision/ETag、冲突处理和不可变版本语义，没有隐式 Apply、Run 或版本提交。
前端使用 design-taste preserve 与 web-design-guidelines 终审，沿用 Design System。

证据：94 相关后端检查、后续强化义务检查 63 tests、Desktop 全量 689 tests、
Desktop build/typecheck 通过；Ruff/444 文件格式与 mypy/248 sources 通过。
首次 backend full 为 1260 passed / 1 过期 scaffold fixture failed；该 fixture 已改为
真实 API 补完整方法、批准、绑定、committed Run，单文件 7 passed。该切片最终
`make check` 为 **1263 passed**；随后新增目录范围与安全诊断，不把该数字用于后续改动。
目录范围相关 70 生成/HTTP tests、109 native unit 与 60 HTTP tests 通过；最新
格式 446/Ruff/mypy249 clean，新的 full 正在运行
`/tmp/veyra-generator-directory-final-full.log`（exec1518）。

已仅重载 8771（最新 PID28980），health 确认 `be8f36e-dirty-directory-scope-20261008`、
数据库 `local_0037_entity_revision_history` ready。没有改变其他服务或原用户 Project。
浏览器确认了能力/源码视图的保存与提交入口；截图 `/tmp/veyra-studio-actions-20261008.png`。
新隔离 CSV 复测 Project 为 `（本地记录）`；首轮真实生成
所有六次 Provider 请求返回成功，但 TaskStructure repair budget exhausted，未创建。
已补安全末次 issue，旧记录不能追溯更具体原因；再次真实生成正在进行，尚未
Apply/commit/运行成功。用户随后明确说余额已补，仍以真实响应确认恢复。扩展自动上传
仍报 file URL 权限，系统 picker 尝试尚未
导入成功，不能声明新 CSV 浏览器上传通过。后续仍须完整报告、状态历史、重复稳定性
和普通用户修改后重测；静态通过不是产品级结论。

后续硬限制：TaskStructure.filesystem_write_roots 接入 Composer，生成器可以把原生
filesystem 写范围缩为 `project/reports`。Library 与 Tool 路径检查按目录段执行，
approval 恢复后再次检查，越界在 adapter/mkdir 前拒绝，不向 Shell/MCP/custom
推广保证。builtin hash 不变，旧 `project` 行为保留。尚未保护同目录已读取输入文件
免于覆盖，不能将目录范围称为完整原文件保护。

## 生成质量参考评估与生成器方法修复（2026-10-08）

已读取《提高Agent生成质量》两轮对话，作为不可信参考与当前代码对照；取舍见
[GENERATOR_REFERENCE_REVIEW.md](GENERATOR_REFERENCE_REVIEW.md)。采用后半版的现有
TaskStructure/编译/门禁主线，保留有界语义审查；不新增平行TaskSpec、多模型评分链或
Factory真实副作用自动执行。静态通过、可启动与任务验收不能合并成“产品级”。

本轮修改生成器自身：TaskStructure阶段方法/信息源进入自治loop指令；coverage包含
Workflow Tool锁，读取选中Skill的准确hash正文并把方法提供给修复。只增加相关上下文，
不增加固定模型调用。能力名字生成的Skill保持scaffold，Factory/Workshop批准与启用
入口均不将其伪装ready；真实方法通过现有准确快照流程，幂等发布清除旧pending元数据。
精确Skill选择的resolver接口已有基础，自然语言选择及完整生成路径仍需集成验收。

当前切片相关8个pytest文件 **95 passed**；3源码mypy、相关Ruff、diff check及分析画布
TypeScript检查通过。未新跑真实Provider/浏览器/打包验收，未重新启动服务来宣称本切片
已加载，未commit/push。此前长任务的状态/表格/前端改动保留，不能据本切片测试声称
整个脏工作树全部通过。

## Generator Harness 与普通用户实测（2026-10-05）

生成链已换为真实TaskStructure规划、完整closed schema验证、有界修复、资源能力与typed交接、独立覆盖审查；原生ask_user/reply可在同一固定版本Run暂停/恢复。实测继续修复了context、阻塞终态、registry前端兼容、原生Tool参数、Agent状态契约/安装/查询与并发scope。新增Entity Query和安全Arithmetic资源，不改变旧资源hash、依赖或迁移。结果阅读使用Veyra现有设计系统与指定Skills审查。

真实多轮陈列案例已从浏览器完成生成/提交/运行/选择/改预算/刷新恢复/确认交付，保持一个Run与v1；status为unverified，不是独立语义校验通过。初版合计错误记录为质量问题，新算术工具的真实使用仍待验收。对账与周计划后续真实生成收到HTTP429，不能计为通过。当前产品级结论：尚未证明。代码门禁：后端1142、Desktop661通过；mypy241 sources、Ruff/format/diff、两web typecheck/build通过。最新微调另有schema/state13与reading38定向通过；Desktop构建仍有既有large chunk提示。详细案例、修复与证据边界在[GENERATOR_USER_ACCEPTANCE.md](GENERATOR_USER_ACCEPTANCE.md)，当前检查日志与继续点在HANDOFF。

## Settings / Workflow 运行页与真实校验故障（2026-10-05，本地未提交）

- Settings 改为 Veyra 既有视觉语言中的单内容工作区：我的 API、界面偏好、工具授权、创作助手。服务预设填写地址，自定义协议仍走通用 transport；阿里云专属业务空间地址提供明确引导。保存连接→发现/手动添加模型→显式测试→任务默认值在同一上下文内完成；大量模型支持搜索和分批展示。界面偏好具有实际主题、语言和减少动态效果设置。没有新依赖、React Bits 或 GSAP。
- Workflow App 按 design-taste-frontend 的 preserve/audit 指导重构：紧凑标题与版本、完整说明弹窗、单一任务输入；运行后只显示提交摘要和真实节点状态，图片输入为缩略素材条；成功后结果只显示一次，已完成进度与技术证据按需展开；失败保留步骤和子 Agent 结果入口。历史错误可回到新任务，缺失旧版本不会冒用最新说明。committed version/hash/预检与收费运行授权边界保持。
- 最终 web-design-guidelines 审查修复状态温和播报、焦点返回、重名字段覆盖、缺失版本说明、错误恢复及回链 run_id；真实浏览器另外发现全局标题段落样式截断弹窗全文，已修 CSS 优先级并复验390px/暗色全文与 Escape。隔离模拟验收准备、运行、完成、失败；临时源码/标签页/viewport已清理。
- 真实历史故障：两个子 Agent 均完成，Renderer 的 PNG 与非空对象已经保存；shared required_fields 校验构造包含列表的集合，引发 TypeError，被压成 workflow_execution_failed。已修安全比较，Workflow Verifier仅检查声明输出，与 Agent graph一致，并记录 verifier.result。用真实已保存输出执行修复后的三项check均通过，PNG内容存在；没有重新调用收费模型，也没有改写历史失败记录。
- 证据：Desktop全量630 tests通过；Backend运行/Artifact/Workflow/Agent相关91 tests通过（包含新校验11项和Workflow integration15项）；Ruff、format、两Runtime source mypy、Desktop/Community typecheck/build和diff check通过。Community全量23/24，已有account测试期待Name而页面已用Display name，隔离复跑同样失败，未扩大修改该模块。Earlier image protocol focused88 tests仍属于独立定向证据。
- Live：用户此前重启的8771进程加载了图片API适配；用户主动测试Qwen图片生成成功，模型证据active_probe/supported。当前新Verifier修复尚未由该进程加载，5173后续停止；已请求本轮明确服务重启授权，不能从历史handoff推断。未stage/commit/push、未由代理新增真实图片/Workflow调用。
- 生成质量的未完成边界：完整的三方案/用户选择/修改/状态保留需求，当前确定性生成器降为single_run的分析→出图→校验；companion执行说明只有通用角色brief，Renderer未消费Analyzer结果，生成validation不验证需求覆盖。修复执行校验不代表复杂自然语言生成已经可靠，也不代表用户原助手需求完整实现；后续必须修Planner与需求保真门禁，不能靠增加业务关键词或修改历史版本掩盖。

> 当前实现状态、验收证据和模块优先级。
> 产品边界以 [`PROJECT_DESIGN.md`](./PROJECT_DESIGN.md) 为准；长期 AI 职责见
> [`AI_DEVELOPMENT_BRIEF.md`](./AI_DEVELOPMENT_BRIEF.md)。
> 本文记录代码里已经落地的事实，不用计划、旧 Session 或历史测试数字替代证据。

## 1. 环境

- 工作目录：`/Users/spectre/PycharmProjects/veyra-agent-platform`
- 集成分支：`codex/agent-platform`
- 远端：`https://github.com/wenjiesong04/veyra-agent-platform.git`
- Conda：`veyra-agent-platform`
- Python：`/opt/anaconda3/envs/veyra-agent-platform/bin/python`（3.11.15）
- Desktop：`5173`；Public Showcase：`5174`；Local API：`127.0.0.1:8771`；Community API：`127.0.0.1:8772`

验收围绕 `Idea → Build → Run → Observe → Trust → Reuse → Share`。
页面数量、静态演示数据和过期测试计数都不是完成依据。

## 当前实现（2026-10-04，Model Capability Registry 与 Workflow 使用页）

- Provider connection 与 Model Profile 分离；16 项 tri-state capability/evidence、目录发现、手动 ID、能力默认、确定性 ModelResolver 已落地。未知不满足 required，图片理解不等同图片生成。
- Builder 按 actor/role 派生实际 Provider 协议需要的模型能力；模型缺口留在 Model Registry，Draft 可审核/Apply 并标 Needs Setup。当前平台 JSON-action loop 不强制要求 Provider 原生 tools/JSON mode。
- Agent/Workflow preflight 与实际调用共用当前能力证据标准，检查连接、Profile 与 digest/revision；支持 metadata/adapter 和 active probe，错误显式绑定及 stale evidence fail closed。
- Settings 和运行页可配置模型。原页配置窗口支持添加 API、手动模型、显式费用确认后的验证、绑定及自动检查；不丢失本次任务输入。当前主动探测覆盖 text generation / structured output / image input / image generation。
- Workflow 使用页按 taste-skill 的既有项目审计收敛：紧凑配置条，主输入区单一边界，明确运行 CTA，流程/历史渐进展开；修复历史重试、预检过期响应、390px CTA 与版本控件裁切。
- 门禁：Backend `env -u PYTHONPATH make check` **982 passed**（依赖/format/lint/mypy 通过）；Desktop **72 files / 574 passed**、typecheck/build 通过；`git diff --check` clean。真实登录态页面与只读明暗/390px 验收通过；未在浏览器启动 Workflow 或调用真实 Provider。
- Live：用户在原启动环境重启后，8771 新进程加载最终代码；health `ok`、schema `local_0036_model_capabilities`、database_ready=true，Builder configured=true。真实 Workflow committed 预检 version/hash 匹配；当前只剩图片生成能力未验证，需要用户补配置。未 stage/commit/push，未由代理调用真实 Provider。
- 详细 A–R 报告见 [Model Capability Registry V1](MODEL_CAPABILITY_REGISTRY_V1_REPORT.md)。以下日期条目保留历史证据，不覆盖本条当前边界。

## 当前修复（2026-10-02，Builder 实时跟进与 Workflow 映射校验）

- Builder 新对话在慢速解析前先通过 SSE 发送已持久化的初始快照；Desktop 收到每帧快照立即更新并取得 conversation ID，让 1 秒持久化轮询能在最终流结束前工作。进入 Runtime 模型绑定等待时，无需刷新才看到选择面板。中文等待提示也已本地化。
- Desktop 的运行模型面板改为清晰的 Provider / 模型选择表单，使用可读的等待状态与本地密钥说明；`create_workflow` 的 Runtime 绑定等待也能显示该面板。项目切换时不再暂时展示上一项目的聊天。`unsupported` 与一般失败的创建请求不再保留假进度工作台，`unsupported` Activity 明确标为未创建。
- Workflow Studio 的 AgentCall 校验现在按后端契约分别检查 Agent 字段 slug（允许连字符）和 Workflow 变量 ID（允许下划线）。用户示例中的合法 `model-known → model_known` 不再被误报；错误提示不再写死无关的 `request → prompt` 示例。
- 验证：Builder Desktop 定向 4 文件 / 99 tests、Workflow Studio 定向 2 文件 / 51 tests；Backend Builder conversation 文件 34 tests；Desktop typecheck/build 与 `git diff --check` 通过。实际浏览器看到旧 `unsupported` 对话不再留假工作台、运行模型面板宽屏与窄屏布局、示例 Workflow 红条消失且测试入口恢复。获用户本轮授权后已重启 Local API `8771`，health `ok`、数据库就绪且 revision 为 `local_0034_project_entities`。没有对真实 Project 再发一次 Builder 请求做端到端流式复验。
- Workflow App（`#/projects/:projectId/workflows/:workflowId/run`）是 Workflow 的独立使用窗口：只运行明确提交的 Workflow 版本（`source=committed` + `version_id`），预检结果必须与所选版本的 `version_id`、`source_hash` 一致才可启动。Studio 测试运行仍使用 Draft。迁移 `local_0035_workflow_versions` 新增 `workflow_versions.committed`，旧快照需重新提交才会出现在 App 中。需要审批的 Workflow Tool 在预检与运行时都会被拒绝，直到有经过验证的 Workflow Tool 审批关卡。

## 当前产品边界（2026-09-29，Builder Generation Architecture V2）

Builder 主链不再是「用户说 Agent → Start→Model→Output → 把逻辑塞进 instructions」。生成先得到 `TaskStructure` 与 `ExecutionBoundary`，再做 `ProductShapeDecision`，再编译 `ExecutionPlan`，再走既有 CapabilityRequirement → ResourceResolver → Composer → Proposal → Apply。

```text
User Request
→ TaskStructure / ExecutionBoundary
→ ProductShapeDecision
→ ExecutionPlan
→ CapabilityRequirement
→ ResourceResolver / Resource Factory
→ Composite Proposal
→ Composite Apply
→ Agent loop 和/或 typed Workflow
```

- 产品模型未改：Agent = 自主 model/tool loop；Workflow = typed deterministic DAG。
- `classify_builder_target` 只记录 `user_requested_surface` 偏好。用户说「帮我做一个 Agent」不会锁死 `PURE_AGENT`。
- Shape：`PURE_AGENT` / `WORKFLOW` / `AGENT_WORKFLOW` / `MULTI_AGENT_WORKFLOW` / `UNSUPPORTED`。判断用结构边界，不用 gift/research/translation/software engineer 职业分支。
- HumanApproval 分两类：业务节点 vs Runtime Tool permission。HumanInput 复用 `HumanApproval.review="input"` + Workflow `reply` / checkpoint，不新造 pause engine。
- Persistent State 是窄的 Project Entity Store V1：migration `local_0034_project_entities`（`project_entities` / `entity_records` / `entity_events`）+ catalog `entity.read` / `entity.write`。不是通用数据库产品。
- Verifier 进入 Workflow DAG。缺 `image_generation` 时 Proposal 标 `missing_required`，Apply 拒绝，不假装 vision 能出图。
- Planner 默认确定性结构抽取；若注入 Provider，最多 3 次 schema repair，失败 `planner_invalid`，不回退关键词启发式。
- Proposal UI 展示 Product Shape、阶段、Execution Plan、Resources/bind、业务审批 vs 工具审批、缺失能力。操作：审查并创建草稿 / 修改方案 / 取消。
- Apply 复合路径：companion Draft → commit → Workflow AgentCall pin `agent_id@version_id`；失败 rollback。
- Local head：`local_0034_project_entities`（`entity_records(project_id, entity_type)` 与 `entity_events(entity_id)` 索引；`entity_events → entity_records` ON DELETE CASCADE）。`EntityStore.write` 拒绝跨 Project / 跨 entity type 覆写同一 `entity_id`（`entity_scope_conflict`）。
- Workflow Tool 节点：mapping key 必须是连字符 slug，所以 `entity_id` 由 Runtime 从 values 默认传给 entity 工具；无 `result` 时默认 payload 是 values 快照（避免自引用 checkpoint 失败）。
- Factory `generate()` 不再要求 Platform Builder Provider（V2 编译是确定性的）；interview / capability probe / planner repair 仍按需检查。Runtime Provider 要求未放宽（`runtime_not_configured`）。
- 8771 已安全重启并加载 0034：live DB 自动备份 `.pre-migration` 后 0033→0034，Projects/Agents/Versions/Conversations/Runs 行数不变。未重启 5173/5174/8772。未 commit / push。

验证（V2 Closeout，2026-09-30）：`env -u PYTHONPATH make check` **947 passed** + ruff format/check + mypy 通过（sandbox 内）。原 `test_plugin_registry` PermissionError 根因是 Community test fixture 未注入 `registry_storage_root`，回落到用户 Application Support；已在 fixture 中注入 tmp 根并断言。Desktop `npm test` **68 files / 536 passed**；typecheck/build 通过；`git diff --check` 干净。Live Entity Store smoke（临时 Project，已清理）通过。Browser E2E unavailable。未调用真实外部 Provider。

## 当前产品边界（2026-09-28，V1 Release Candidate Cleanup）

本轮不增加产品能力。把已完成的 V1 主链整理成可审查的 Release Candidate：dirty tree 分类、Fixture 隔离回归、对话标题不再泄漏 UUID、Agent App 主交互面可用、migration 0027–0033 线性 head 校验、文档诚实记录 V1 限制。

- 产品模型不变：Agent = loop；Workflow = typed DAG。
- Local DB head：`local_0033_agent_app_versions`。
- Agent App 对话 `title` 是用户可见文案；`conversation_id` 只作内部 ID。UUID / 空 title 显示 `New conversation` 或首条用户消息摘要。
- `/projects/:id/agents/:aid` = App；`/design` = Studio；`/run?run_id=` = Run Detail。树点击进 Studio；Open App / Edit in Studio / Back to Agent 是产品入口。
- 自动化测试必须用临时 DB + 隔离 `project_storage_root`。不删除无法证明归属的真实用户 Project。
- 测试分层：unit（`tests/unit`）/ integration（`tests/integration`）/ acceptance（`tests/integration/local/test_complex_agent_acceptance.py` 是 V1 核心产品链回归）。
- 未实现且不是 RC blocker：loop 出图、真实浏览器自动化、完整 Policy、vector RAG、MCP 产品化、任意可执行 Tool 生成、Community marketplace、音视频。

验证：`env -u PYTHONPATH make check` **915 passed**（ruff/mypy 通过）；Desktop `npm test` **68 files / 519 passed**；typecheck/build 通过；`git diff --check` 干净。8771 已安全重启：`pid=46045` `status=ok` `database_ready=true` `database_revision=local_0033_agent_app_versions` `build_sha=0ad7a3e0…-dirty`。未重启 5173/5174/8772。未 commit / push。Browser E2E unavailable。Real Provider 未执行。

## 当前产品边界（2026-09-28，Complex Agent Product Acceptance）

本轮不增加新的大能力。证明 User Request → Specification → Resolver →（缺能力时 Factory）→ Composer → Apply → Commit → Agent App → AgentLoopRuntime 能作为一条产品链跑通三类不同 Agent，并修掉阻断闭环的问题。

- Research Analyst：自然语言请求得到 web_search / knowledge / research_planning / evidence_synthesis；Resolver 选 Web Search、Research Brief、Evidence Ledger、Project Knowledge；Apply pin/lock；Commit 后 App conversation 跑 scripted Web Search（无公网）+ Knowledge marker + 第二 turn 历史。
- Software Engineer：workspace search/read/write + shell；临时 Project 内真实写文件、真实 pytest；observation 驱动第二次修复；write/shell 按 Catalog approval；reject 无 side effect。无领域 hardcode。
- Packaging Analysis：image_understanding + Project Knowledge + Skill；hybrid App、synthetic PNG 以 `data:image/png;base64,` 进入 Model；第二 turn 保留 Artifact；`image_generation` 仍 missing/unsupported。
- Factory Skill：`comparative_risk_method` missing → Draft → validate → approve → publish → Resolver retry → Commit → App → `skill.loaded`。
- Composer 把 `needs_configuration` 工具写入 lock/bindings，committed GitHub Agent 在 App preflight 返回 422 `needs_configuration`，不创建 Run。
- 本轮 generate 是 Specification-seeded HTTP Factory chain + scripted interview completions，不是真实 Builder Provider。
- 无新 migration：`local_0033_agent_app_versions` 足够。无领域 `if research_agent` 分支。

验证：`env -u PYTHONPATH make check` **909 passed**；Desktop **67 files / 515 passed**；typecheck/build 通过；`git diff --check` 干净。Browser E2E unavailable。Real Provider acceptance was not performed.

## 当前产品边界（2026-09-28，Agent Run App V1）

Studio Test Run 执行当前 Draft；Agent App 只执行 committed immutable Agent version。未 Commit 时 App 显示 empty state，不偷偷跑 Draft。Conversation 在创建时 pin `agent_version_id`；新对话默认最新 committed version。`interaction_mode` 为 `auto|chat|form|hybrid`，只决定产品交互面，不改变 Runtime tool 语义。旧 Agent 缺省 `auto`。App 复用 RuntimeInputForm / RuntimeOutputView / useLiveRun / SSE；审批摘要由 Server 根据 tool id 与校验后的 args 生成；Run 前 preflight Runtime model 与 resource configuration。image Artifact / document 走既有 multimodal 抽取链。本轮不宣称 loop 出图。

验证：`env -u PYTHONPATH make check` **901 passed**；Desktop **67 files / 515 passed**；typecheck/build 通过；`git diff --check` 干净。Browser acceptance unavailable。

## 当前产品边界（2026-09-28，Resource Factory V1）

Resolver 确认 `missing_required` 后进入正式 Factory seam。`ResourceFactoryStrategy` 分类为 `generatable` / `requires_user_configuration` / `requires_external_integration` / `unsupported`。可生成的只有 Skill instruction 与对已有 adapter 的 declarative Tool Wrapper（`http.request`、filesystem read/search/list）。Draft 先隔离，校验后用户确认才发布为不可变 Catalog overlay；Resolver 通过 Catalog metadata 重新发现，Composer 再 pin/lock。不静默发布，不发明任意代码 executor，不为 `image_generation` 造假资源。

验证：`env -u PYTHONPATH make check` **890 passed**；Desktop **65 files / 498 passed**；typecheck/build 通过；`git diff --check` 干净。Browser acceptance unavailable。

## 当前产品边界（2026-09-28，Resource Resolver & Agent Composer）

create_agent 主链是 Capability Requirement → Resource Resolver → ResourcePlan → Agent Composer。Resolver 只从 Catalog/Project snapshot 选资源；不再用 `_CAPABILITY_TOOLS` 或领域关键词把 capability 映射成 tool ID。Proposal 保存 ResourcePlan snapshot，Apply pin 该 snapshot 的 content_hash。缺失 required capability 显示 `missing`，不生成假资源。Policy 绑定仍是 `runtime_support=partial`。旧 graph Template 不进入 loop composition。

验证：`env -u PYTHONPATH make check` **854 passed**；Desktop **65 files / 497 passed**；typecheck/build 通过；`git diff --check` 干净。Browser acceptance unavailable。

## 当前产品边界（2026-09-28，Loop Agent Resource Truth）

Agent / Workflow 产品模型不变。本轮只把 loop Agent 的资源链做成可执行事实：

```
Catalog resource
+ availability
+ Project pin
+ Agent lock hash
+ Agent permission
+ Runtime adapter
+ required configuration
```

缺 pin 时 Runtime fail-closed（`resource_unbound`），Apply 不会静默换成更新版本（`resource_identity_conflict` / `resource_binding_conflict`）。Skill 是 instruction resource，不是 Tool。Knowledge V1 仍是 txt/md 有界检索。image Artifact 进入 ModelRequest Image part；document/pdf 进入有界抽取文本。

本轮不做 Resource Resolver、Resource Factory、新 Run App、Workflow Builder、真实 Provider、浏览器自动化。

验证：`env -u PYTHONPATH make check` **831 passed**；Desktop **65 files / 497 passed**；typecheck/build 通过；`git diff --check` 干净。8771 需重启后加载此代码。Browser acceptance unavailable。

## 当前产品边界（2026-09-27）

以 `0ad7a3e0b2a11ccf9186f23dab40628375509c73` 的本机闭环为准。那一版的生成、Chat
和其余本机页面是正常的。之后未提交的 Cloud data plane（Cloud Project、Conversation、
File、Credential、Cloud Run，以及把 `8772` 换成 Cloud Host）不再作为产品。

- `5173` 和 `8771` 是本机软件。Builder、Chat、Studio、Runtime 只走 Local API。
- `5174` 是公开展示，加上 `#/community`、登录和账号。不提供云端工作区。
- `8772` 继续做 Community 账号和 Registry，启动模块是
  `veyra_agent_platform.community.app:app`，不是 `veyra_agent_platform.cloud.app:app`。
- 桌面端不再把 Project 或 Builder 对话自动同步到云端。侧边栏「最近」读本机
  `GET /api/v1/builder/activity`。

## 当前产品模型（Agent ≠ Workflow）

Veyra 是 Agent + Workflow 的 AI 工作室。两者在 Project 中平级，contract、Builder、
Runtime、Studio、Source、Run 语义分开；共享 Provider / Tools / Knowledge / Files /
Credentials / Runs / Events / Receipts / Resource Library。

- **Agent**：自主能力单元。Builder `create_agent` 编译 `execution_kind=loop` 的
  AgentSource（说明、工具绑定、知识、typed I/O、`max_turns`）。Runtime 是
  model↔tool loop，不是 DAG scheduler。Studio Canvas 是能力图。
- **Workflow**：显式 typed 图。Builder `create_workflow` 编译 WorkflowSource
  （Start / AgentCall / Tool / Condition / Transform / HumanApproval / Verifier /
  Output、`data_edges`）。AgentCall 必须锁定已提交 Agent version。上一轮 typed
  dataflow、DataflowStore、quality、structural simulation 归 Workflow 基础设施；
  Artifact / 多模态类型仍可被 Agent 与 Workflow 共用。
- 历史 Start→Model→Condition→Approval 图作为 `execution_kind=graph` 保留，可打开、
  不可静默迁移。简单 Start→Model→Output 可转为 loop Agent；明显编排图应转为
  Workflow。
- 本轮不做 Community marketplace、RAG、Loop/Parallel/Schedule/Webhook 节点、
  audio/video Runtime、浏览器自动化。

## 2. 已发布模块（Git 事实）

| 模块 | SHA | 范围 |
| --- | --- | --- |
| Chat-first Builder Phase 1 | `9153617` | Project Chat 修改已有 Agent/Workflow：提案 → 确认 → Draft；不是全 Project 事务 |
| Runtime V1 | `ea94b64` | 事件/回执、审批、Stop、安全 Retry、checkpoint Resume、run_id 历史证据 |
| Resource Library V1 | `ee814e2` | Catalog 真实 readiness → Project pin → Agent lock → Runtime 按 pin 执行 |
| Knowledge V1 | `8351806` | 本地 txt/md ingest → 显式索引 → 绑定检索 → Run 引用证据 → Resource-Library 风格工作台；浏览器闭环在 `560a912` 上验收 |
| Graph Compiler V2 | `8bef91c` | SemanticPlan → 可执行 Agent 图 + Default Canvas Note + Provider schema hardening |
| Typed I/O + Artifact Runtime | `5f8e8a8` | TypedField / ArtifactRef、Project-scoped object store、Runtime modality truth、shared Test UI |
| Agent Composition & Capability System V1 + Canvas Runtime Execution Overlay V1 | `0ad7a3e` | Slice 1–5 已随该提交发布；Alpha/Beta branch 与 approval overlay 已有隔离 fixture 手工浏览器证据。此前获准的真实 Builder Proposal 曾语义失败；Branch Semantics 修复后未再次调用真实 Provider，因此 Builder real-provider acceptance 仍未通过/未复验 |

GitHub Actions Billing 仍是外部阻塞，不把未执行的 CI 写成代码失败或 CI PASS。

以下 Slice 2–5 测试数字和未发布状态是 2026-09-22 的历史 checkpoint；它们已被上表的 Git 事实与后续验收取代。不要再把 Agent Composition V1 写成 uncommitted。

Slice 2 先前基线：后端 687 tests、Desktop 436 tests、Community 15 tests，以及
当时记录的 typecheck/build；这些数字不代表 Slice 3 精确修订的验收。

Slice 3 当前证据（2026-09-22）：`env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`
通过（后端 693 tests、Ruff format/check、mypy、dependency/lock checks）；
`npm test --workspace=@veyra/desktop` 通过（55 files / 439 tests），Desktop
typecheck 通过；Builder/Component/Resource/client/Studio 聚焦测试 107 passed；
`git diff --check` clean。尚无真实浏览器 E2E、真实 Provider/sidecar 验收或
release checkpoint；未 commit/push，因此这是本地实现与门禁通过，不代表发布完成。
实现边界及剩余验收见 `.backboard/HANDOFF.md` 最新的
**Agent Composition V1 — Slice 3** checkpoint。

Slice 4 当前证据（2026-09-22）：Conda `veyra-agent-platform` 下
`env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check` 通过（后端 **695 passed**、
Ruff format/check、mypy、dependency/lock checks）；Web 全量测试通过（Desktop
56 files / 450 tests，Community 3 files / 15 tests），两应用 typecheck 与
production build 通过。Desktop build 有既存的大 chunk 提示。`git diff --check`
最终核对通过。没有真实浏览器 E2E、Provider/sidecar 验收、GitHub CI 或 release
checkpoint；这是 Slice 4 阶段的历史门禁记录；Slice 1–4 未提交/推送，Slice 5 当前进度见下文。
Slice 4 细节与证据见 `.backboard/HANDOFF.md` 的
**Agent Composition V1 — Slice 4** checkpoint。

Slice 5 当前证据（2026-09-22）：Conda `veyra-agent-platform` 下
`env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check` 通过（后端 **695 passed**、
Ruff format/check、mypy、dependency/lock checks）；Web 全量测试通过（Desktop
59 files / 463 tests，Community 3 files / 15 tests），两应用 typecheck 与
production build 通过；Slice 5 聚焦 Desktop 测试 **133 passed**。Desktop Vite
报告主 JS chunk 超过 500 KB。另完成有限的 Chrome 手工 UI/Runtime 验收：Run 画布按
immutable version 恢复；一次合成输入的 Runtime Test Run 经配置 Provider 执行成功，
输出可见且刷新可恢复，Run 状态为 `unverified`（无 verifier 证据）。这不是正式浏览器
E2E 或发布验收。此处“Slice 1–5 未 commit/push”和浏览器验收待完成均为当时历史状态，
已由后续 `0ad7a3e` 发布与 2026-09-23 Alpha/Beta 手工浏览器验收取代。真实 Builder
Provider 的旧 Proposal 语义失败仍是当前验收缺口。

## 3. Knowledge V1（本轮收口）

本轮把未提交的 Knowledge 切片收成一个可发布模块，并按 Desktop 现有资源库风格做了友好工作台。

闭环：

`本地 UTF-8 txt/md 上传 → 真实 ingest/parse 状态 → 显式索引 → Agent 绑定且不静默升级 → 本地词汇检索 → Run 引用证据 → 使用中删除保护`

诚实边界：

- 不是 PDF/DOCX/OCR，不是 embedding/向量库，不是逐句 citation
- 文件在 Project 中不会自动进入模型
- 未索引、hash 漂移或跨 Project 引用会在调模型前失败
- Run 证据是实际进入 context 的 chunk locator，不是答案归因

工作台：

- 列表以状态徽章和下一步动作为主，hash 放在详情事实区
- 上传是主入口；空白“创建知识”仍保留为次要能力
- 详情区分未索引 / 已索引 / 需重建 / 失败，并提示下一步
- Run Detail 展开片段时核对历史 hash；来源链接打开当前资料

### 本轮验收（2026-09-16，专用 Conda，隔离测试环境密钥）

```text
模块：Knowledge V1
修订：`83518068937271c4a0372674284782b56500e47c`（`8351806`）
代码范围：Knowledge ingest/index/retrieval/evidence、Project API、Desktop 知识工作台
用户可操作路径：上传 → 构建索引 → 绑定 Agent → Run 查看引用 → 使用中无法删除
后端证据：env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check → 452 passed；
          Ruff format/check passed；mypy 157 files；dependency/lock checks passed
前端证据：web npm test → Desktop 309 passed，Community 15 passed；
          npm run typecheck / npm run build 通过（Desktop 主 chunk 约 958 kB warning 保留）
仍未实现：PDF/Office、历史全文仓库、Community 知识依赖重建、真实浏览器 E2E、真实 Provider
```

首次 `make check` 在沙箱里因无法写入
`~/Library/Application Support/Veyra Agent Platform/.../community/registry` 失败；
在未沙箱环境复跑后 plugin registry 用例通过。这不是产品回归。

### 发布验收（2026-09-17，`560a912`，隔离浏览器 E2E 补齐）

`8351806` 收口时未跑浏览器 E2E。本轮在**同一修订**上补完模块门禁和真实浏览器闭环，
Knowledge V1 由此记为 released。

```text
模块：Knowledge V1 = complete / released
修订：`560a912609c1b2e658a2b62b3ad22d9212bfbb20`（代码与 `8351806` 一致，`560a912` 仅文档）
Focused review：按 24 项边界逐条核对 Knowledge diff，未发现真实 bug，未改产品代码
后端门禁：env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check → 452 passed；
        Ruff format/check、mypy、dependency/lock checks 通过
前端门禁：web npm test → Desktop 309 passed（41 文件），Community 15 passed；
        npm run typecheck 通过；npm run build 通过（Desktop 主 chunk warning 保留）
浏览器 E2E：Chrome + playwright-core，隔离栈 27 checks / 0 failed
```

E2E 隔离方式（harness 在仓库外的临时目录，不入库）：临时 SQLite、临时 Project 根
`/private/tmp/.../projects`、loopback 脚本 provider `127.0.0.1:8899`，以及临时 Community
库中的一次性账号。脚本内断言 `root_path` 与 `runtime/status.model_base_url`，确保没有
触碰真实工作区、也没有调用外部模型。

真实浏览器覆盖的闭环：

- 上传 `knowledge.txt` → `ingested / parsed / not_indexed`，徽章 `Not indexed`
- 点击 Build index → `ingested / parsed / indexed`，`chunk_count = 1`
- Studio 绑定 → Draft 记录 `knowledge_refs` 且 `lock` 固定 source hash
- Validate & commit → 一个不可变版本携带 Knowledge pin
- Run（脚本 provider）→ `Chunk index 0 · Lines 1–1 · Rank 1 · Score 5`，证据带 reference
  与运行时 source hash；脚本 provider 收到的 prompt 只含绑定片段
- 展开片段 → 显示 `ORBIT-731`
- 按精确 `run_id` 刷新 → 不新建 Run（1 → 1），证据逐字节不变
- 空检索 → Run 合法，显示 `No relevant Knowledge chunks retrieved.`，无伪造引用
- 显式改内容 → 索引转 `stale` / 徽章 `Needs rebuild`；旧 Run 证据身份不变；
  旧片段预览被 422 拒绝（`Historical source changed`），不泄漏新 marker
- 使用中删除 → 409 `knowledge_in_use`，Knowledge 仍在 Project 中

未验收边界不变：PDF/Office、embedding/向量检索、reranker、GraphRAG、逐句归因、
历史 Knowledge artifact 仓库、真实外部 Provider、Community 知识依赖重建。
GitHub Actions billing 是外部阻塞，本轮未 rerun CI，也不当作本地发布阻塞。

## 4. 对照原六模块判断（已核对）

旧 Codex 总结里的测试数字（Python 289 / Desktop 211 / Community 15）和“六个模块都未完成闭环”已经过时，不得再当当前门禁。

| 模块 | 旧结论 | 当前事实 |
| --- | --- | --- |
| Canvas / Studio | 可演示，编辑闭环未完成 | 手动 Canvas/Form/Source 仍在；自然语言改单个 Agent/Workflow 已由 Builder Phase 1 承担。Component 完整编辑和视觉收尾仍弱 |
| Resource Library | 目录有了，日常工作台未完成 | V1 已发布：Catalog → Project → Agent → Runtime。没有历史 artifact 仓库 |
| Agent Chat | 只能生成新 Agent | Builder Phase 1 可改已有对象。Phase 2 Slice 1/2（未提交）已把 Knowledge 与 Project `filesystem.read` 从模型猜测改为服务端确定性绑定。仍不是整个 Project 的自然语言入口 |
| Runtime | 能跑，还看不清 | V1 已发布：审批/Stop/Retry/Resume 与持久证据。Canvas 节点级实时态和真实外部 Provider 仍缺 |
| Knowledge | 只有绑定，不是知识库 | V1 本轮收口：上传、索引、检索、引用。仍无 PDF/RAG |
| Community | 注册表第一版，差得最多 | Agent Directory 已走真实注册表 API；本轮补入 Published/Starred 真实列表和横向四意图导航。Following 后端关系/Feed 仍未实现，Agent/Plugin lane 之外的资源类型不伪装为可用 |
| 数据分析页 | 未点名完成 | 已读真实 Run 计数，不是友好分析工作台 |

三个跨模块闭环：

1. 设计闭环：V1 可用（Chat 改结构 + 资源绑定 + 知识绑定）。
2. 执行闭环：Runtime V1 + Knowledge 引用已齐；不是真实外部 soak。
3. 分享闭环：仍是最大缺口。

## 5. Builder Phase 2

Git 事实：Slice 1–4 与 ProviderCapabilityProfile / Harness Receipt 已包含在
`8f71a1e`。Agent Graph Compiler V2 + Default Canvas Note + SemanticPlan V2
Provider Hardening 已发布为 `8bef91c`。Phase 2 模块整体仍未做最终
Playwright CASE 1–3 release gate。

已落地：

- 自然语言 Knowledge 绑定：服务端解析、歧义追问、`knowledge_refs` + `source.lock`
  由服务端计算，Proposal 展示索引就绪状态
- 自然语言“让这个 Agent 可以读取项目文件”：只处理已 Project-bound 的
  `filesystem.read`，Proposal 展示 `bound_content_hash` / readiness / 最小权限；
  不自动 Add Catalog、不静默升级 stale、不自动授权、不自动 Test Run
- Apply 后 validation failure 是业务结果：typed Builder issue cards、仅对
  服务器已知 pin / 缺权限 / Knowledge hash 生成一条 EditProposal 修复；
  `resource_unbound` 与 `requires_configuration` 只解释不假修

证据见 `.backboard/HANDOFF.md` Slice 1 / Slice 2 / Slice 3 checkpoint；窄测试与
静态检查已过，全量 `make check` 与浏览器 E2E 留到模块收尾。

**Builder Phase 2 Slice 3（Apply 后 validation repair，历史切片编号）= complete**
（未发布；这不是 Agent Composition V1 的 Slice 3）。

闭环：Apply → backend validation → typed Builder feedback → deterministic
repair proposal → confirmation → repair apply → revalidation。

**Factory structured generation compatibility = resolved**（未发布）。

Root cause：kimi-k3 接受 `response_format.type=json_schema` + `strict=true`，
但完整 AgentBlueprint schema 不是 Moonshot MFJS。真实 400 是
`invalid_request_error`：`enum` 缺 `type`；随后 `$ref`→`oneOf` 被 Walle
误判无限递归。`const` 也不是 MFJS 关键字。

修复：`local/factory/structured_schema.py` 做 provider-compatible projection
（enum 补 type、`oneOf`→`anyOf`、`const`→enum、inline `$ref`）。完全空的
`verification` 可默认成 `{required:false, checks:[]}`。该投影保留为
compatibility bridge，不再是默认 Provider 合同。

**Builder durable conversation = complete**（未发布）。

用户消息在 resolve / Factory / 模型调用前写入 `builder_conversations` /
`builder_messages` / `builder_operations`。失败是历史事实；Retry 新建
`retry_of` 操作，不改写旧失败。左侧「最近」只投影 Builder Conversation
（聊天记录），不含 Runtime Run。右上「历史」仍是 Runtime Run History。

**AgentSemanticPlanV1 + SemanticPlanCompiler = complete**（未发布）。

默认 Factory generate：NL → Intent → AgentSemanticPlanV1 →
SemanticPlanCompiler → canonical AgentBlueprint → validation → review →
Confirm 后才 Apply。Compiler 复用 Slice 1/2 resolver，不猜、不 Catalog
auto-add。完整 AgentBlueprint 不再是默认 Provider-facing contract。

**Builder Interaction Model V2 = complete**（`aba074d`）。

Chat 不再把 Builder 生命周期渲染成系统气泡。`builder_operation_events`
是 server-owned 进度；Activity 一个 operation 一块，完成默认折叠。
Workbench 按真实阶段打开（理解 → 语义计划 → 编译 → 审查），Proposal
留在右侧，不作为 Chat 消息。Apply 使用 Semantic Plan `suggested_name`；
CJK slug 走现有 `agent-{hash}` 合同。Recent 两阶段标题：第一条 user
message 持久化后写 deterministic provisional title；semantic plan 成功
且标题仍是 provisional 时才升级为 `suggested_name`。失败会话不再叫
`Chat`。Create 与 Edit 共用 Conversation → Activity → Workbench →
Confirm → Result。`target_kind` 预留 agent | workflow。

Live Moonshot CASE 1（`New project`，「创建一个中英文翻译 Agent。」）：
generate → waiting → confirm → apply → 一次 result 通过。Agent 名
`中英文翻译 Agent`，slug `agent-0f68d95b`。HTTP 429 是 provider rate
limit，不是 V2 缺陷。CASE 2/3 走同一条真实 Builder path 的
scripted/local provider 验收。

完整 Playwright CASE 1–3 浏览器验收未在本环境执行（无 Playwright）。
产品证据是 live Moonshot CASE 1 + scripted CASE 2/3 + Desktop focused
tests。真正 browser acceptance 留到 Builder Phase 2 最终 release gate。

**ProviderCapabilityProfile = complete**（本 checkpoint）。

Profile 只回答「这个 Provider + Model + Endpoint 支持怎样的模型请求
协议」，不定义 Veyra Agent 语义。Canonical 仍是 AgentSemanticPlanV1 →
SemanticPlanCompiler → AgentBlueprint。`/models` 只证明模型可见，不是
structured-output 能力。

身份：`provider_id` + `model` + `endpoint_kind` + `base_url` fingerprint
（无 query / 无密钥）+ `probe_version`。缓存命中则普通 Builder generate
只读 profile，不 probe。显式 `POST /api/v1/factory/capability-probe`
用固定 `{ok: boolean}` synthetic schema；401/403/429/5xx/unknown 4xx
不降级 capability，429 记 `inconclusive` 而不是 unsupported。

Factory generate：probe 已知则 strict → 允许的 json_object；否则沿用
Moonshot static_known / 其它主机 fail-closed json_object。schema /
response_format 不兼容才允许一次 json_object fallback。结果仍走
AgentSemanticPlanV1 校验，再编译为 canonical AgentBlueprint。

Settings 只显示很轻的能力摘要 + Recheck。Builder Activity 不刷
profile 技术细节。

一次有界 live Moonshot probe（`api.moonshot.cn` / `kimi-k3`）：
`strict_json_schema_support=supported`，`status=known`，`source=probe`。
不是 429，不是 inconclusive，不是 unsupported。未创建 Agent。

**Builder Harness Receipt = complete**（本 checkpoint）。

一次真实模型调用一条 `BuilderHarnessReceipt`：先 persist
`prepared`，请求后再 finalize `success`/`failed`。失败也保留证据。
Receipt 只存安全 metadata（Harness / Policy / Contract / structured
mode / included+excluded categories / 有界 snapshot hash / 当时
ProviderProfile 摘要）。不存 prompt、Knowledge/File 正文、密钥、
Authorization、provider body、hidden reasoning。

五者不同：

```text
Conversation Message  ≠  BuilderOperationEvent  ≠  BuilderHarnessReceipt
≠  Proposal  ≠  Runtime Run
```

Activity 折叠「构建详情」展示人类可读 Provider / Contract / Mode；
hash 只在 Technical details。Chat 不刷 Receipt。无模型调用的
operation 不报 “No receipt found”。历史 Receipt 在 Recheck 后不变。
API 只走 Project-scoped conversation/operation。

明确未完成：Builder Phase 2 最终 release gate、Catalog → Project
mutation from Chat。

**Builder Phase 2 Slice 4 = complete**（已包含在 `8f71a1e`）。

闭环：

`Build → Validate → Explicit Test Run → Observe → Explain → optional
Repair Proposal → Confirm → Apply → Validate → explicit Run again`

Builder 只关联 `run_id` + 有界 `RunObservation`。Runtime V1 仍是
Run / events / evidence / approvals 的唯一 store。Test Agent 必须用户
显式点击；Apply / Repair 后不自动 Run。未配置 Runtime model 返回
`runtime_not_configured`，不把 Builder Kimi 绑给 Agent。

Builder Model ≠ Agent Runtime Model。当前 live 两者碰巧都是 Moonshot
`kimi-k3`：Factory 是 Builder；host default Runtime profile 是 Agent
执行模型。UI 不得把 Builder Kimi 标成 Agent Runtime，除非该 Agent 的
有效 Runtime 确实是 Kimi。

### 本轮基线（2026-09-22，`8f71a1e baseline verified`）

Git HEAD：`8f71a1e15481cddeb45830eb2482992fa4c20d8e`。

首次 `make check` 在该修订上因两处已提交 Ruff format 失败（decorator
折行、f-string 引号）。授权只修这两处后，完整 `make check` 通过：

```text
Backend pytest: 596 passed
Ruff format/check: passed
mypy: passed（175 files）
git diff --check: clean
```

先前同修订上的前端门禁：Desktop 409 passed、Community 15 passed、
web typecheck / build passed。这是 Compiler V2 开始前的 verified baseline。
不要再把 HEAD 写成 `4e3c2e6`，也不要把 Slice 4 写成未提交。

**Agent Graph Compiler V2 + Default Canvas Note + SemanticPlan V2
Provider Hardening = complete / released**（`8bef91c`）。

正式锁定：

- Agent = 可独立执行的能力内部图：Start / Model / Tool / Condition /
  Transform / HumanApproval / Verifier / Output
- Workflow = 多个 immutable Agent version 的编排；AgentCall 只属于 Workflow
- Knowledge 仍是 binding，不是计算节点
- `ui.notes` 默认存在、不是必填、不进 `behavior_hash`、用户可删
- `ui.labels` 只用于画布语义标题；Inspector 仍显示 component type

`AgentSemanticPlanV1` 保留 `steps: string[]`。可选 `step_intents` 描述
职责、operation kind、depends_on。Provider-facing schema 不包含
`branches`；Condition / Approval / Verifier 的额外 port 由 Compiler
确定性展开。模型不输出 node/edge id、resource hash、permission、
source.lock、canvas 坐标。

如果 `step_intents` 已表达 approval / condition / verification /
transform，生成失败不得静默退回 Start → 单 Model → Output。

Compiler V2：无 `step_intents` 且只有一个 summary step 时仍编译简单
Start → Model → Output；多个 summary steps 编译为顺序 Model 节点。
有真实职责边界时才生成多 Model / Tool / Transform / Condition /
HumanApproval / Verifier。不 hallucinate Tool，不 Catalog auto-install，
不 silent upgrade，不 permission overgrant。Verifier 只映射
`output.not_empty`；不能映射时编译为 Model + warning，不造假 Verifier。
默认 Note 由 SemanticPlan 确定性生成，不再额外调模型。

Live CASE C 根因（真实 Moonshot / kimi-k3）：Provider schema 曾包含
嵌套 `branches.then`，而 MFJS 投影会剥掉名为 `then` 的 property，导致
连续三次 `missing field(s): then` → `factory_generation_invalid`。
已去掉 Provider-facing `branches`，并做 bounded repair / 拒绝静默 V1。
验收：CASE A Start→Model→Output；CASE B 三个 Model；CASE C
Start→Model→HumanApproval→Model→Output（风险项检查不能映射
`output.not_empty`，保持 truthful）；CASE E 真实 `condition` intent。
裸 CASE C 文本可能被 resolver 判成 `create_kind=workflow`；加上
「做一个 Agent」后进入 SemanticPlan。未 Confirm / Apply。

**Typed I/O + Artifact Runtime = released**（本 checkpoint commit）。

Canonical contract：`TypedField` 兼容旧 compact `text: string`；binary 值为
Project-scoped `ArtifactRef`，复用 `objects/sha256/<digest>`。Runtime Model
modalities 与 Builder `ProviderCapabilityProfile` 分开。当前 Moonshot
`kimi-k3` 以及其它用户绑定 Runtime 模型：`image_input=supported`。仅已知
纯文本 Moonshot 模型（`kimi-k2`、`moonshot-v1-8k`、`moonshot-v1-32k`）保持
`image_input=unsupported`。PDF/document/Office/file 抽取纯文本进 prompt，
bytes 不进 Run JSON。audio/video adapter 仍未启用。缺 pdf_parser /
pdf_renderer / image_generation Tool 保持 Compiler 侧 truthful
`missing_capability`。Studio Test、Workflow Test、Builder Test、Run Detail
共用 `RuntimeInputForm` / `RuntimeOutputView`。独立 Agent Playground 与
Workflow Builder Compiler **尚未实现，也不是当前主任务**。 Builder
Workspace/Test 位于每次 Builder operation 对应的 Conversation 历史中，不是
固定右侧栏。

Release gate（2026-09-22，真实 `.env`，非 temp DB / 非 fake provider）：

```text
backend：env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check → 675 passed
Ruff format：312 files；Ruff check passed；mypy 184 files；git diff --check clean
Desktop vitest：53 files / 430 passed；Community vitest：3 files / 15 passed
Desktop/Community typecheck passed
Desktop production build：2025 modules，1.40s
Community production build：1722 modules，656ms
```

Live Local API（dirty SHA `8bef91c-typed-io-dirty`，head `local_0025_project_artifacts`）：
text Agent Run 得到 translation；string+number → object 保留 summary/score/report；
image Run 前 422 `runtime_model_incompatible`；Artifact upload/metadata/download
Project 隔离、MIME mismatch、超限拒绝；PDF bytes 不进入 Run JSON。
Authenticated Desktop UI 仍需登录，仓库内无 Playwright；Chrome + playwright-core
停在 `#/login`。Compiler 对 image/pdf 的 typed semantics 由 unit tests 覆盖。
Moonshot Builder 在本轮 Runtime 验收后返回 `factory_rate_limited`（HTTP 429）。

## 6. 下一步

当前切片是 **5174 Product Boundary Alignment + Showcase V1**，不是新的 Community 或 Registry 开发：

1. 将 5174 固定为匿名产品 Showcase；核心页面不依赖 8772。
2. 由 5173 保留 Community 发现、发布、收藏与导入工作流；8772 保留 Registry 服务。
3. 诚实展示源码构建入口与发行状态；没有公开且验证过的安装包时不提供假的下载按钮。
4. 用 5174 focused tests、typecheck/build、全仓门禁和手工浏览器检查收口，并同步产品边界与当前状态文档。

完成本切片后停止，不开始 Community 多资源分享、Following/Feed、Production Community、Desktop Distribution、Builder Provider 复验或 Custom Component lifecycle 验收；这些保留为后续独立排序。

## 7. 仍不能宣称完成

- Knowledge 工作台已有一条隔离浏览器闭环证据；其余页面仍没有浏览器 E2E
- 没有 PostgreSQL + 对象存储演练，就不能宣称 Community production ready
- 没有真实外部 Provider，就不能宣称 Runtime 已在生产网络下验证
- Builder 不能一次修改多个对象，也不是全 Project 操作入口
- Builder Phase 2 仍未作为独立 Git 发布标签。Durable Conversation、
  Semantic Plan Compiler V1、Interaction Model V2、ProviderCapabilityProfile、
  Harness Receipt 与 Slice 4 Test Run 已包含在 `8f71a1e`。Agent Graph
  Compiler V2 已发布为 `8bef91c`。Typed I/O + Artifact Runtime 已发布为
  `5f8e8a8`。独立 Playground 不是当前主任务。Agent Composition V1 已包含在
  当前 HEAD `0ad7a3e`；这不代表真实 Builder Provider 在 Branch Semantics 修复后已复验成功。
- 手写 PDF/document/file input Agent 的 Runtime readiness 不会自动变成
  `pdf_parser` missing；缺专用 parser Tool 的 truthful 点在 Compiler。
  Runtime 抽取有界纯文本写入 prompt，不把 PDF/Office bytes、host path 或
  `artifact://` 写入 Run JSON。audio/video adapter 仍未启用；文件夹不是
  ArtifactRef 种类
- 旧 Factory session 目前只恢复最新 canvas，不是完整 conversation/workbench
- Community directory 已改为真实 API；生产 PostgreSQL/S3 备份恢复演练仍未完成

## 8. 提交规则

获得明确提交要求后：

1. 查看 `git status`、`git diff` 和最近提交
2. 只暂存当前模块文件；不暂存 `.env`、凭据、`.backboard/sessions`、`.backboard/settings.json`
3. 在专用 Conda 环境跑对应验收
4. 记录精确 commit SHA
5. 重启受影响服务并用 `/api/v1/health` 核 SHA
6. 历史交接中的授权不是永久许可

## 9. 技术决策

- `PROJECT_DESIGN.md` 是产品和工程权威；本文只维护事实状态
- Local 与 Community 独立部署；Community 不执行下载的 Agent 或插件
- Agent 与 Workflow 平级；Workflow 只调用固定 immutable Agent version
- Catalog 与 Project Resource Library 分离；MCP 是 Tool discovery，不是独立产品层
- Project 文件是用户可检查的 source；运行、聊天、账号、秘密和缓存留在应用数据区
- Knowledge 绑定固定 source hash；内容变化必须显式重建索引并重新绑定
- 先补可验收闭环，再做视觉扩展、推荐算法或资源数量扩张

## 10. Agent Composition release acceptance update（2026-09-22）

- 用户明确授权的唯一 Builder 合成请求已发送一次；Provider 没有返回 429。Provider
  生成的 Proposal 含一个 `Condition` 和两个 `HumanApproval` 节点，但 Condition 仅判断
  request 是否为空，两个审批与两个 Transform 又被串成一条路径；输出仅为通用 `result`
  对象，Transform 返回原始 request，没有满足 urgent/routine 分支语义或
  `{priority, summary}` 输出契约。Proposal Note 对分支与输出的描述和实际图不一致。
  这是语义降级，未 Confirm / Apply；无 Custom Component、外部 Tool 或权限提案。没有为
  验收再次调用 Provider，也没有把 Provider 原始响应写入文档。
- Builder Provider receipts 显示请求自动携带 Project/Agent、Workflow、Knowledge
  metadata、Project resource bindings、Catalog capabilities、Project file metadata、
  Project config；Interview/Semantic Plan 阶段还含当前对话消息。receipts 标记未包含
  Knowledge/file 正文、credentials、secrets、真实 Runtime events、隐藏推理和原始
  Provider response bodies。此项是对自动上下文范围的披露，不把它误写成完全零上下文请求。
- 用户截图中的 Custom Components `Not Found` 已复核：运行中的 `127.0.0.1:8771` health
  为 `build_sha=5f8e8a8`、DB revision `local_0025_project_artifacts`，组件列表 endpoint
  返回 HTTP 404；当前 dirty 源码已注册相同 endpoint。隔离 TestClient + 临时 SQLite 的
  生命周期集成测试通过，证明当前源代码路由正常，但不能替代 live sidecar/browser 证据。
- Custom Components 面板在列表 API 出错时原先仍允许编辑/保存，造成“表单可用但请求
  必然失败”的误导。现已将加载/错误期间的编辑、保存、校验、发布和生命周期操作锁定；
  404 显示服务/API 不可用提示，成功重试后恢复。Focused Desktop panel tests **3 passed**，
  对应 Backend isolated lifecycle integration test **1 passed**，Desktop typecheck passed。
- `8771` 未在本 checkpoint 重启：发布流程要求先有合理完成的 Slice/acceptance 与提交，
  而 Builder semantic acceptance 尚未通过。正式服务重启、live Custom Components 浏览器
  acceptance、Condition/Approval/Component Proposal 完整浏览器路径、release commit/push
  仍未完成；不得将上述隔离测试称为 Browser E2E 或发布验收通过。

## 11. Local API restart + Custom Components read/UI smoke（2026-09-22）

- 用户单独授权后，只重启 `8771`。从仓库根目录使用 Conda Python、显式指向当前
  `backend/src`，启动命令为：
  在仓库根目录的 Conda 环境执行 `env PYTHONPATH=backend/src VEYRA_BUILD_SHA=5f8e8a8-dirty python -m uvicorn veyra_agent_platform.local.app:app --host 127.0.0.1 --port 8771`。
  应用按正常启动流程读取现有 host config；没有查看、打印或改写 `.env` 值，也没有调用 Provider。
- 重启 health：`service=local`、`build_sha=5f8e8a8-dirty`、
  `database_revision=local_0026_builder_semantic_plan`、`database_ready=true`。进程打开的是
  已有 user-data Local SQLite，而非临时 DB； Project root 由正常 Local config 提供。
  startup 将 schema 从 `local_0025_project_artifacts` 升级到 `local_0026_builder_semantic_plan`；
  此 migration 仅给 `factory_sessions` 加一个 nullable `semantic_plan_json` 列，迁移 helper
  按设计保留 pre-migration SQLite copy，没有修改 Project 资源/文件记录。
- 当前 test Project 的只读 `GET /api/v1/projects/{project_id}/custom-components` 返回
  HTTP **200**、Project identity 匹配、`components=[]`。未创建、保存、校验、发布或删除
  Custom Component；没有真实 Project 资源 mutation。
- 手工浏览器复核：重启前实际错误态是 404 + “组件列表不可用”，新建和编辑/保存控件被锁；
  重启后错误提示消失，显示“还没有自定义组件”，New Component、草稿表单和 typed I/O
  JSON 可编辑；实现类型可切换至 `transform`，实现模板随之更新。随后刷新页面清除未保存
  表单状态，再次确认 API 组件数仍为 0。此为真实页面手工 smoke，不是自动化 E2E。
- 没有识别到可确认隔离的既有 Project，因此未做 Draft → Validate → Publish lifecycle
  浏览器 smoke。空白新建表单的 Publish 控件现已 disabled；保存/发布路径不在真实 test
  Project 上执行。
- 本次只重启 `8771`；`5173`、`5174`、`8772` 未重启。当前 `5173`、`5174` HTTP 200；
  `8772` health ready、build SHA 仍为 `5f8e8a8`。Builder Proposal semantic acceptance
  仍 failed；未 Confirm/Apply、未重新调用 Provider，Agent Composition V1 仍不可标记完成。

## 12. Builder Branch Semantics & Output Wiring hardening（2026-09-23）

- 根因已定位在 `AgentSemanticPlan -> semantic_compiler -> canonical graph`：旧
  `step_intents` 只有 `depends_on`，没有通用的 Condition branch declaration、branch-local
  identity 或 deterministic multi-output mapping；Compiler 因而按拓扑顺序把 sibling branch
  steps 线性化，Transform 又只保留第一个 output field。
- SemanticPlan 现支持最小通用 branch contract：Condition 必须声明两个 `{key,label}`
  semantic branches；branch-local step 声明 `branch_condition` + `branch_key`，依赖只能
  留在自己的 branch；Transform 可声明 `output_mapping`，目标必须是 declared output field，
  值只能是 deterministic literal 或 `{{input_field}}` 引用。Provider 不生成 node/edge/port
  IDs；Compiler 将两个 semantic branch 按声明顺序确定性投影为 Runtime `true`/`false`，并
  在 `ui.branch_labels` / Note 中保留业务 labels。当前 V1 Runtime contract 仍是双分支；
  多于两个分支会 fail closed，不静默折叠。
- Compiler 现在生成真实 DAG：Condition 分别连接 branch-local roots；每条 branch 的
  Approval 只连接本 branch 的 downstream；branch Transform 映射全部 declared outputs，
  多 branch 可汇入同一个 Output；共享 successor 只在真实依赖存在时合并。Sibling branch
  不再被 ordered steps 串联。Note 由 compiled graph branch truth 生成，不再直接复述 Provider
  描述；branch labels 同时可投影为 Canvas edge label。
- SemanticPlan repair/prompt/MFJS projection 已同步扩展并保留 `branches`、`branch_condition`、
  `branch_key`、`output_mapping`；非 Condition 的 malformed `branches` 只会带诊断地丢弃，
  Condition branch cardinality/identity 错误会拒绝；semantic compile topology error 返回
  `semantic_compile_failed` 路径，不能 ready/success。没有真实 Provider 重试或新 Provider 调用。
- Runtime deterministic integration fixture 已覆盖两条任意命名 branch：True 只进入 Alpha
  Approval/Transform，False 只进入 Beta Approval/Transform；未选 branch 没有 `node.started`，
  同一 Output 保留两个 typed fields。Desktop overlay 既有 projection tests 覆盖 canonical
  Condition edge、unselected idle、Approval waiting 和 approved successor。
- 修复 Custom Components 空白表单 Publish 状态：没有 persisted `component_id`、草稿尚未
  Validate、或 API error 时 Publish disabled；Save Draft 后仍需 Validate 成功才可 Publish。
  新增/更新草稿会清除 validation gate。没有新增 migration；SemanticPlan/Blueprint/Source
  contract 是同一 schema version 的 additive extension。
- Focused evidence：Backend semantic/compiler/factory/runtime/contracts **169 passed**；
  Desktop focused **36 passed**；Desktop typecheck passed；Ruff format/check passed；生产
  touched modules mypy **8 files, no issues**。首次对既有测试文件直接跑 mypy 暴露仓库原有
  test typing debt，未将其混入生产模块结果。未运行 full `make check`，未重启任何服务，未
  调用真实 Builder Provider，未 Confirm/Apply，未修改真实 Project 数据。

## 13. Live 8771 deterministic browser acceptance（2026-09-23）

- 按用户授权只重启 `8771`，命令使用当前 working tree 的 `backend/src`、真实 Local DB
  和正常 Project root：`VEYRA_BUILD_SHA=5f8e8a8-dirty`。health HTTP **200**，
  `database_ready=true`，revision `local_0026_builder_semantic_plan`。没有读取/打印 `.env`
  secret；5173、5174、8772 未重启，未调用 Builder Provider。
- 在真实 Local DB 创建了隔离 Project `Browser Branch Fixture - 2026-09-23`
  (`project_id=01a0ca52-c8d1-7582-a773-7b4f3d6bf2c8`) 和 deterministic Agent
  (`agent_id=01a0ca52-c8d1-763d-876f-9fd2c7e8514f`)。fixture 只使用 `mode=alpha|beta`，
  不包含旧的 urgent/routine 语义；没有修改既有 `test` Project 或已有 Agent。该隔离
  Project 和两个验收 Run 保留，未执行删除操作。
- Manual browser CASE A Alpha：Run `01a0ca53-a2bf-7b24-957a-86dcd8c8a0f8` 先到
  `approval_alpha` waiting；`approval_beta` 未开始。Approve 后同一 Run 继续，
  `transform_alpha`、Output completed，`transform_beta` 未开始；Run Detail 显示
  `{branch: "alpha", summary: "Alpha summary for alpha"}`。
- Manual browser CASE B Beta：Run `01a0ca54-c517-787b-bd8d-d4034403f38c` 先到
  `approval_beta` waiting；`approval_alpha` 未开始。Approve 后同一 Run 继续，
  `transform_beta`、Output completed，`transform_alpha` 未开始；Run Detail 显示
  `{branch: "beta", summary: "Beta summary for beta"}`。
- Execution Overlay 手工确认：running/waiting/completed 节点、选中 branch edge、未选 branch
  edge 与 Runtime events 一致；两次截图均未出现两条 branch 同时高亮。Alpha/Beta 完成后
  刷新 `design?run_id=...`，对应 immutable Run 状态和节点状态恢复。事件日志显示同一 Run
  的 `approval.requested/resolved`、branch Transform 和 Output completion。
- Canvas edge label 实际显示 `Alpha` / `Beta`；Note 实际描述两条 branch 各自经过 Approval
  与 Transform 后进入双字段 Output，与 graph truth 一致。以上是 manual browser acceptance，
  不是 jsdom/unit 或 integration test。
- 同一隔离 Project Resource Library 空白组件页手工确认：空白新建表单中 Save Draft enabled，
  Validate disabled，Publish disabled；未输入、未保存、未校验、未发布任何 Component。
- 这是 live API + fixture/browser 证据，不是完整 release acceptance：真实 Provider、正式
  test Project 不变、Custom Component lifecycle browser smoke、full gate、commit/push 仍未做。

## Community Sharing UI and navigation refresh（2026-09-23，本地未发布）

- Community 页面改为四个水平意图入口：Discover / Published / Starred / Following。Desktop 继续
  使用 Veyra 全局侧栏；独立 Community Web 也采用同一组顶部导航。Discover 读取真实 Agent Registry，
  搜索走 API，排序只用真实发布时间、Star 数和 Review 评分；没有伪造 Featured、下载量或导入量。
- Published 与 Starred 新增认证 API：`GET /api/v1/registry/mine/agents`、
  `GET /api/v1/registry/starred`。它们复用现有 immutable version 与 version-bound Star 表；
  Published 显示 published/quarantined/rejected 真实状态，不显示不存在的 Community draft。
- Following 导航和页面可见，但明确显示未开放：当前服务还没有 creator-follow 关系或 release feed。
  未添加示例创作者、假动态或伪收藏。Discover 当前仍只展示 Agent；现有 Plugin Pack 发布仍在 Publish 区，
  但 Plugin Pack 浏览/导入详情、Workflow/Component/独立 Tool/Skill 市场都未伪装成已实现。
- Agent 发布在本机先生成规范化 package preview，再由用户显式确认才上传；host Secret 引用和机器路径
  在 UI 禁止，并由 Community 后端二次硬拒绝。导入分析带目标 Project 的只读依赖报告；确认前不改 Project，
  确认时重算并检查 source hash 与依赖快照，漂移返回 conflict。成功后只创建新的本地 Agent Draft，不运行、不授权、不安装依赖。
- 手工浏览器检查了 5174 Community Discover 的真实 API 空目录与 Following 未开放状态；当前公开目录实际为
  0 个版本。该检查不等于自动浏览器 E2E，也没有登录真实账户、Star、Publish 或 Import 用户资源。
- 全量门禁：Conda `make check`：**703 passed**，Ruff format/check、dependency lock、mypy（187 source files）通过；
  Web Desktop **471 passed**、Community **18 passed**，两端 typecheck 与 production build 通过。
  Desktop build 仍有大 chunk 提示，Alembic 测试有既有 `path_separator` deprecation warning。
- 没有重启服务：5173/5174 当前由本地 Vite 工作树热更新；8771/8772 health 仍为 200、build
  `0ad7a3e`，Local revision `local_0026_builder_semantic_plan`、Community revision
  `community_0008_plugin_registry`。因此 Published/Starred API 与新的目标 Project 导入分析尚未进入 live API，
  需要单独授权重启对应服务后才能做 live browser acceptance。
- 未 stage、commit 或 push。原有 `shell.tsx`、`shell.css`、`app.test.tsx`、scroll-driven UI 修改、
  `.backboard/sessions/`、`.backboard/settings.json` 与 `$DB` 均保留。

## Community Sharing V1 live API reload + read-only browser acceptance（2026-09-23，历史 checkpoint）

- 只重启 Local API `8771` 与 Community API `8772`；没有重启 `5173` / `5174`。使用项目根目录
  的专用 Conda Python 3.11.15、当前 `backend/src` 和正常应用配置；只显式设置 dirty build marker，
  未设置 temp DB、E2E Project root、fake provider 或 loopback provider。Community 按仓库已有
  `python -m dotenv -f .env run -- env ... uvicorn` 启动；没有输出、查看或改写 `.env` secret。
- 两个 API health 均 HTTP 200、`database_ready=true`、`schema_version=health.v1`，build marker
  均为 `0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`；Local revision 为
  `local_0026_builder_semantic_plan`，Community revision 为 `community_0008_plugin_registry`。
  OpenAPI 3.1.0 已加载 Local Agent import analyze/read/apply 和 Project Agent import；Community
  已加载真实 publish/list/detail/version/download/star/unstar/moderation 路由，以及认证
  `GET /api/v1/registry/mine/agents` 和 `GET /api/v1/registry/starred`。
- 只读 API 检查：匿名公开 Agent Registry 返回 HTTP 200、0 releases；Published 与 Starred
  endpoints 返回 HTTP 401 `authentication_required`。没有创建、修改或删除账号、release、Star、
  Project、Agent、Run 或 Component，也没有生成假目录数据。
- Manual browser acceptance（独立 Community Web，非 Playwright/jsdom）：5174 Discover 显示真实
  `0 releases` / 空态；搜索输入可用；Recently published、Most starred、Top rated 可切换。
  Published 与 Starred 显示真实 Sign in 边界；Following 显示 `Creator following is not available yet`、
  无 Following API，并明确 Star 是收藏 immutable release、Following 是订阅 creator。浅色与深色页面
  均未见明显破版。Desktop `5173/#/community/published` 因隔离浏览器未登录而按设计跳转 Login。
  两个 Vite 服务保持 HTTP 200，未重启。以上是手工浏览器状态检查，不是自动化 E2E。
- 真实 Publish / Published authenticated listing / Star / Unstar / Agent detail / Import Preview、
  Preview 零变更复核、Import as Draft 与 Studio 打开尚未完成：认证注册会请求投递邮箱验证码；本轮没有
  指定的隔离测试账号或邮箱，因此没有触发验证码投递或创建账号，也没有借用用户账号。当前公开目录
  仍为 0 releases；Community Sharing V1 release acceptance 被隔离账号/邮箱授权阻塞，不能标记 complete。
- Conda 后端完整 `make check`：703 passed；Ruff format/check、依赖锁检查、mypy 187 source files
  通过。Web `npm test`：Desktop 471 passed、Community 18 passed；两端 typecheck/build 通过。Desktop
  build 仍有既有 >500 KB chunk warning；pytest 保留 Alembic `path_separator` deprecation warnings。
  `git diff --check` clean。
- Git HEAD 仍为 `0ad7a3e0b2a11ccf9186f23dab40628375509c73`；无 staged files；未 commit/push。
  用户独立 shell/sidebar-scroll/UI 改动、`.backboard/`、`$DB` 均保留。

## 5174 Product Boundary Alignment + Showcase V1（2026-09-23）

- 当前产品职责：5173 Desktop 是主要工作台与 Community 交互面；8771 是 Local API；8772 是独立账号/immutable Registry 服务；5174 是匿名 Public Showcase。Registry 是服务能力，不是 5174 的网站身份。历史上 `web/apps/community` 临时发展成独立 Registry UI，本 Slice 将入口改为 Showcase；目录/package 重命名与旧页面 dead-code cleanup deferred。
- 5174 展示 Product、How it works、Local-first/Safety、Share、Getting Started/Docs、Download/Build；不显示 Published/Starred/Following、Account、Publish、Import 管理工作流。
- 5174 的 main entry 不导入 Community API/Auth/Registry 页面；Vite `5174` 不代理 `/api` 到 `8772`。`ShowcaseApp` 首屏是静态产品内容，`8772` 离线仍 HTTP 200；unit tests 断言首屏没有 `fetch`，旧管理 hash 刷新后转到 `#home`。
- 内容边界：产品示意明确标记非真实 Run；没有假指标、客户或 Community 资源。没有可验证的公开 DMG/下载 URL，页面明确提示暂无公开安装包并链接到真实仓库构建文档；GitHub 文档链接可能需要仓库权限。无数据库 migration、无 Registry/API/schema/data 改动、无 Builder Provider 调用、无 Project 数据 mutation。
- Manual browser acceptance（Chrome 真实 5174；8772 未监听）：首页/全部 section 可见；Legacy `#/community/published` 直接打开并刷新后归一到 `#home`，没有管理 UI；中文/英文、light/dark 可切换；200% 浏览器缩放后响应式 Header 显示折叠菜单。实际截图确认展示示意有明确非实时标识。用户接管 Chrome 后未继续点击窄屏菜单；该菜单状态由 Showcase unit test 覆盖，未把这项写成 mobile-device E2E。
- Focused/Full validation：`npm run test --workspace=@veyra/community` **22 passed**；全 Web `npm test` Desktop **472 passed**、Community **22 passed**；两端 typecheck/build 通过。Desktop build 有既有约 1.16 MB chunk warning；Community Showcase JS bundle **230.93 KB**。Conda `make check` **703 passed**，Ruff format/check、dependency/lock checks、mypy 187 files 通过；pytest 有既有 Alembic `path_separator` deprecation warnings。
- 新增 ADR `0006-public-showcase-and-community-boundary.md`。README、AI brief、PROJECT_DESIGN、DEVELOPMENT、HANDOFF/GPT historical note 已同步四服务职责。no stage/commit/push；`git diff --check` clean（以本 checkpoint 最终核验为准）。
- Browser acceptance 时 8772 确实离线，5174 root 仍 HTTP 200；旧 Registry hash 刷新后没有管理 UI。完成离线验收后按用户先前选择恢复四服务：5173/5174 HTTP 200；8771/8772 health HTTP 200、`database_ready=true`，Local `local_0026_builder_semantic_plan`、Community `community_0008_plugin_registry`，均为 `0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`。启动前数据库已在 schema head，因此无 migration。
- 工作区仍在 `codex/agent-platform` / HEAD `0ad7a3e0b2a11ccf9186f23dab40628375509c73`，本 Slice 未暂存/提交/推送；既有 Community Sharing、shell/sidebar/scroll UI、`.backboard` 状态和 `$DB` 保持。

## Builder Real Provider Re-Acceptance + Custom Component isolated lifecycle（2026-09-24）

- Builder 使用隔离 Project `Veyra Builder Acceptance 20260923-1530Z`。仅提交一条合成用户级请求；
  Provider 身份为 Moonshot `kimi-k3`，意图解析与一次 Semantic Plan + 两次有界 repair 的 receipts
  均为成功响应（`json_object` / strict JSON Schema，MFJS）。最终 Builder operation 失败于
  `semantic_generation`：`factory_generation_invalid`，Semantic Plan 在三次产品内尝试后仍无效；
  不是 429。没有 reviewable Proposal / proposal_id，因此没有可审的实际 graph；未点 Retry、未
  Confirm/Apply、未创建组件、未 Run。没有保存 raw Provider response、secret 或日志。
- Custom Component 浏览器验收使用隔离 Project `Veyra Component Acceptance 20260923-1545Z`。
  空表单 Save Draft 可用、Validate/Publish disabled；保存 Draft 后 Validate enabled；Validate 返回
  `ready` 后 Publish 创建不可变 `1.0.0`。随后编辑并保存新 Draft，旧版 description 与 SHA-256
  `e7de5249088a601226431f3e8946ad22a6b226b4226717e8f0996200fd67a2bc` 未改变。
- Resource Library 显示绑定的 `Acceptance Echo`；Studio Palette 在存在未发布 Draft 时只显示已发布
  `1.0.0` 与同一哈希。隔离 Agent Draft 的 `CustomComponent` node 保存成功：`uses` 精确固定到
  `01a0cef2-ec07-7379-b55c-8eb581150d0e@1.0.0`，lock 与 Project 绑定哈希一致，输入/输出映射为
  `text <- request`、`result -> result`，Agent 没有额外 Tool 权限。Canvas、Form、Source 的引用、
  hash 与映射一致；Canvas 无 blocking graph diagnostics（Validate & Commit 按钮未点击）。Local API
  validate 为 `valid=true`、component dependency `ready`。该 `runtime_ready` 是 dependency scope，
  不是一次实际 Run；未执行 Run 或模型调用。
- 浏览器复核为 **manual browser acceptance**，不是 Playwright/jsdom E2E。确定性后端 focused tests
  **37 passed**；Ruff、format、touched production modules mypy 通过（后端全仓与 Web 全量门禁待本轮
  后续运行）。发现并修正了 `CustomComponent.uses` 被 Draft 保存/依赖检查误按 Tool manifest binding
  查找的问题；现在分别核对 Project-owned published component reference/hash 与 Tool manifest pins。
- 仅重启 `8771` 使修复进入 live API；health HTTP 200，`database_ready=true`，build
  `0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`，DB revision `local_0026_builder_semantic_plan`。
  `5173` / `5174` / `8772` 未重启；检查仍分别为 HTTP 200 / HTTP 200 / health 200 ready。无 migration、
  temp DB、E2E root 或 fake provider。两 Projects 都是本轮验收 fixture；用户既有 Project/Agent 未改。
- 未 stage、commit 或 push。Slice 仍未 complete：Builder real-provider semantic acceptance failed；
  两个隔离验收 Project 与组件/Agent fixture 保留以供复核。最终门禁：Conda `make check` **704 passed**，
  Ruff format/check、dependency lock、mypy **187 source files** 通过；Web Desktop **472 passed**、
  Community **22 passed**，两端 typecheck/build 通过。保留 Alembic `path_separator` warnings、jsdom
  Canvas `getContext` stderr 和 Desktop >500 KB chunk warning；`git diff --check` clean。

## Builder Semantic Generation Failure RCA + Offline Hardening（2026-09-24）

- 本 Slice 没有第二次真实 Provider 请求、服务重启、Run、Apply、migration、stage、commit 或 push。
  继续使用 `codex/agent-platform` / HEAD `0ad7a3e0b2a11ccf9186f23dab40628375509c73`；工作树原先
  已含 Community/Showcase、Sidebar/scroll、Custom Component 与 Branch Semantics 等未提交变更，均保留。
- 只读 Builder identity：Project `01a0cee5-90fb-78f4-99ab-e42e9a6365c9`；conversation
  `01a0ceeb-5dfb-7f5a-9944-2320254d181c`；operation
  `01a0ceeb-5dfb-71b8-a4f7-06a1542144f6`；Factory session
  `01a0ceeb-cabd-7e1e-bc58-df67cdeb51fc`。没有修改该 Project/Agent 或清理 acceptance 数据。
- 原 turn 共 5 个 receipt：`resolve_intent`、`interview`、`semantic_plan`、两次
  `semantic_plan_repair` 均记录成功响应；后三次都使用 `strict_json_schema` / `mfjs`。
  structured-response 请求成功；应用代码在 `json.loads` 后走 Python SemanticPlan contract 与 semantic
  checks，并没有另跑 Draft 2020-12 JSON Schema response validator。事件进入 `semantic_plan.completed`
  与 `builder.capabilities.started`，证明三次均越过 JSON parse、Python contract 和 branch/obligation
  validation，之后才在 compiler 失败。Receipt 没保存初始/repair 的完整内容，也没有记录可重取的 HTTP
  数字状态码；本记录不补造这些内容。
- Attempt 1（`semantic_plan`）：JSON/contract/branch validation pass；Compiler 报
  `semantic_compile_failed`，Transform `normalize_result` 引用未声明输入 `advice_priority`。
  Repair 1（`semantic_plan_repair`）：同层失败，`normalize_result` 引用改成了仍未声明的
  `urgent_priority`。Repair 2：同层失败，`normalize_urgent` 又引用 `advice_priority`。三次 Provider
  调用都成功，失败不是 429/auth/network，也不是 MFJS 400；最终是
  `factory_generation_invalid` / `semantic_generation`，无 `proposal_id`、canonical Blueprint/Proposal、
  Agent Draft、Run 或 Component。
- 数据库只保留了最终 attempt 的 `semantic_plan_json`。其安全结构为：Agent input `request:string`；
  top-level outputs `priority:string`、`summary:string`；Condition 声明两个分支；每支有 branch-local
  HumanApproval 与 Model，再各有 Transform 把 `{{advice_priority}}` / `{{advice_summary}}` 映射到顶层
  输出。分支 identity、审批 placement 与 dependency contract 都通过解析；失败点是 Transform 借用了
  Provider 定义的 step-local Model 字段，而 compiler/runtime 的变量域只有 Agent 顶层 inputs/outputs。
  该错误不是 outputs 名称不存在，而是 mapping source 不在 Agent input contract。
- 历史 Repair prompt 的精确字符串未持久化。按当时实现，它包括原 compiler diagnostic 和截断至 1200
  字符的 `step_intents` schema 片段；通用说明只说 mapping 可引用 `{{input_field}}`，没有列出当前允许的
  Agent input/output 名称，也没说 step `inputs/outputs` 不代表普通 Model→Transform dataflow。诊断文本虽含
  未知字段名，但没有 machine `code/path/expected/allowed_inputs`。Provider 因此把 source token 从
  `advice_priority` 改成 `urgent_priority` 再改回；receipt 不足以比较其它原始字段变化。
- 根因分类：首个失败层是 **Compiler boundary**（不是 JSON、MFJS projection 或 branch validator）。
  辅因是 SemanticPlan 允许普通 step 夹带 `inputs/outputs`，但未定义 inter-step 数据流；prompt/schema
  结构容易让 Provider 把它误用为数据传递；旧 repair 缺少字段白名单与可修复操作说明。另发现现有 contract
  有一处相反边界过窄：可复用 Component planner 明确支持 reusable `model` / `transform` / `capability`，
  因此保留这些 kind 的 `reusable_capability=true` typed I/O；普通非 reusable step I/O 才拒绝。
- MFJS 排除结果：原 receipts 为 `mfjs` profile + strict JSON Schema；branch、nested branch item、
  branch references、outputs、depends_on、output_mapping 与 nested typed fields 均保留在 projection。
  失败前 canonical schema hash 与当时 receipt 的 schema hash 一致。没有证据支持 MFJS 删字段/压扁 array
  是根因；没有强制退回 `json_object`。本轮 schema description 改后 hash 自然会变化，历史 hash 不用来
  表示当前工作树 hash。
- 离线修复：普通 Transform 只能从 Agent inputs/literals 映射到声明 outputs；step `inputs/outputs`
  仅属于 reusable capability contract。Model prompt明确列出完整顶层 output contract，包含首字段与类型。
  Repair 将收到精确 Agent field names；compiler 错误包含 machine `code`、`path`、expected 与 allowed
  input。只有合法的 input/literal Transform 才形成“必须保留”的 transform obligation；非法的 mapping-only
  step 可被移除并由其 Model 直接生成顶层字段，不能因此丢掉真实用户职责。Sibling branches 仍不能串联。
- 脱敏回归 fixture：[`agent-semantic-plan-real-provider-failure.json`](../contracts/fixtures/invalid/agent-semantic-plan-real-provider-failure.json)。它来自数据库中唯一保存的最终 plan shape，去掉自由文本与身份信息；初始响应和 repair 1 的 raw structure 不可用，因此没有伪称 fixture 覆盖那些原文。测试另派生一个移除非法 step-local I/O 的形状，以重现原 compiler unknown-input 故障。
- 自动回归覆盖：真实失败 fixture 的 contract/compiler 两级诊断；MFJS provider-visible schema nested branch/output 字段；scripted Builder turn `invalid → invalid → valid` 并进入未 Apply 的 reviewable neutral `valid/invalid` graph；repair exhaustion 三次后仍 `factory_generation_invalid` 且无 Proposal/Agent mutation；同 branch dependency 接受、cross-sibling reject；两个与三个顶层 output names 保留；branch-local Approval 和 truthful Note；reusable Transform Component proposal continuation 与 Custom Component focused regression。
- Offline graph 摘要：`Start → Condition`；`true → Approval(valid) → Model(valid) → Output`；
  `false → Approval(invalid) → Model(invalid) → Output`。两支各自输出 `{status, summary}`；Approval
  不串联；Note/edge label 来自成功编译图的 `Valid` / `Invalid`。失败 plan 的 compiler result 没有 Blueprint，
  所以不会产出误导 Note。该测试是 scripted integration，不是真实 Provider 验收或 Browser E2E。
- 本 Slice 修改/增加：SemanticPlan contract/parser、Builder create prompt 与 model output prompt、
  repair diagnostics/obligation filter、semantic compiler structured path diagnostic、canonical schema，
  脱敏 fixture 与 hardening/compiler/conversation regression tests；PROJECT_DESIGN 修正过期 branch contract
  描述。本轮没有 Community/Showcase/API/UI 功能变更。
- Focused backend: **156 passed**，覆盖 SemanticPlan/MFJS/Factory/Builder/Compiler/Proposal/Custom Component。
  Full Conda `env -u PYTHONPATH -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`: **713 passed**；Ruff
  format/check、dependency lock、mypy **187 source files** passed。Web `npm test`: Desktop **472 passed**、
  Community **22 passed**；Desktop/Community typecheck 与 production build 均通过。保留已有 Alembic
  `path_separator` deprecation、jsdom Canvas `getContext` stderr、Desktop >500 KB chunk warning。
  `git diff --check` clean；没有新 migration，也没有真实 Provider call。
- 结论：这是 Offline Hardening 成功，不代表 Builder real-provider acceptance 通过。下一步仍需单独授权
  **Builder Real Provider Re-Acceptance #2**；在那之前不称 Builder accepted / V1 complete，不重启服务，不发布。

## Builder Real Provider Re-Acceptance #2（2026-09-24，本次结果 FAIL）

- 开始时仍为 `codex/agent-platform` / HEAD `0ad7a3e0b2a11ccf9186f23dab40628375509c73`，working tree dirty、无 staged files。旧失败 Conversation `01a0ceeb-5dfb-7f5a-9944-2320254d181c`、Operation `01a0ceeb-5dfb-71b8-a4f7-06a1542144f6`、Factory session `01a0ceeb-cabd-7e1e-bc58-df67cdeb51fc` 未 retry、未修改；原 Project 保留。
- 新一轮复用隔离 Project `01a0cee5-90fb-78f4-99ab-e42e9a6365c9`，开始前 Agent=0、Workflow=0、Custom Component=0、Project-owned resource binding=0、Runtime Run=0、Workflow Run=0；仅有先前那条失败 Builder Conversation。Project 未新建，也未改动。
- 仅发送一次获准的真实 Builder turn；新 Conversation `01a0d1a6-3580-71d9-84d4-550407c34ef7`、Operation `01a0d1a6-3580-721b-b709-57c59c0a17e3`、Factory session `01a0d1a6-72d7-713a-b749-ca0df9c9eaf7`。Local API HTTP **200**；Intent/Interview/Semantic Plan 三条 receipts 均 success；唯一 Semantic Plan attempt=1、repair=0，`strict_json_schema` / `mfjs`；没有额外 Provider probe 或第二次 Builder turn。
- Provider 生成了 review 状态 Blueprint，operation=`waiting`、Factory session=`review` / `ready=true`，并发出 `builder.proposal.ready`。但 operation 的 `proposal_id=null`，事件 facts 也没有 `proposal_id`；只有 Factory session 中的 Blueprint candidate，不是本验收要求的带 ID canonical Proposal。因此第一个 release success gate 未达到，不能标记 PASS。
- 最终 Semantic Plan（从本机 DB 只读并输出脱敏结构）：input `request:string`；outputs `priority:string`、`summary:string`；Condition `classify_priority` 有 `urgent/routine` 两 branch；每支各有 branch-local HumanApproval 与 Model；没有 step-local intermediate I/O、没有 external capability。Approval 拓扑正确：`Condition true → approve_urgent → advise_urgent`，`false → approve_routine → advise_routine`；sibling branches 不互相依赖；不是线性假分支，也没有退回单 Model。
- 新发现的确定性编译问题：Semantic Plan 的 Condition `purpose` 是自然语言“按 request 内容分类 urgent/routine”；compiler 静默 fallback 编译成 `request != ""`。这实际区分的是空/非空，不是 urgent/routine，Note 却声称根据内容区分两类。故 branch labels、审批 placement 虽真实，Condition semantic truth 与 Note truth **不通过**。top-level output contract 保留两个字段；两个 branch Model 的 system prompt 均包含 `priority (string)`、`summary (string)` 和完整 JSON contract。Output node 的 `output_name=priority` 是节点标签字段，Runtime Output 执行时通过 `_prepare_outputs` 校验完整 `source.outputs`；本轮按要求没有 Run，故不声称有实际执行值证明。
- 新脱敏 fixture：`contracts/fixtures/invalid/agent-semantic-plan-condition-fallback-reacceptance-2.json`。只复现语义计划结构，不保存 provider raw response、凭据或完整 reasoning。最小修复：编译器不再把无法解析的自然语言 Condition 猜成非空测试；只接受 Runtime 支持的显式比较表达式并验证其字段属于 Agent input，否则返回 `condition_expression_required` / `condition_input_not_declared` 与路径，fail closed。Prompt/schema 已说明此边界。未修改 Builder proposal persistence、UI、Community 或其他功能。
- 浏览器：本地 Desktop `5173` 起初因 Vite 未运行显示 connection refused；启动 `5173` 后可加载登录页。登录错误提示根因是 Community auth service `8772` 当时未启动；启动 8772 后该错误消失，但当前登录表单没有账号/密码，显示必填提示。本轮没有读取、输入或传输凭据，因此 **5173 UI Proposal review/Canvas browser acceptance unavailable (unauthenticated)**；按附件授权使用 API + persisted canonical Factory Blueprint 检查，并将 UI 层明确留为缺口。
- 项目副作用核对：turn 前后 Agent=0、Workflow=0、Custom Component=0、Runtime Run=0、Workflow Run=0、Project-owned resource binding=0；没有 Apply/Confirm、Run、外部 Tool/HTTP 动作、资源创建或 migration。旧 Conversation 仍是原 `factory_generation_invalid` 失败状态；新 Conversation/Factory Blueprint/receipts 留存。
- 四服务按本轮要求已全部启动：5173/5174 HTTP 200；8771 health 200、`database_ready=true`、`local_0026_builder_semantic_plan`；8772 health 200、`database_ready=true`、`community_0008_plugin_registry`；build 均为 `0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`。8771 使用当前 Conda Python 与仓库 `backend/src`；8772 使用仓库配置，无 temp DB/root/fake provider；`.env` 未被人工读取或打印。代码修正后只重启过 8771 以加载 latest working tree；无 schema migration。
- 修复后验证：SemanticPlan/Compiler/Factory/Builder/Proposal/Custom Component focused **158 passed**。最终 `env -u PYTHONPATH -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check` **714 passed**，Ruff、依赖锁、mypy 187 个源文件通过；Web Desktop **472 passed**、Community **22 passed**，双端 typecheck/build 通过。warning 保留：Alembic `path_separator`、jsdom Canvas `getContext`、Desktop 大 chunk。
- 总结：**Builder Real Provider Re-Acceptance #2 = FAIL**（无 `proposal_id` canonical Proposal；Condition 语义错误；UI 登录层未验收）。未再次调用 Provider。Agent Composition V1 仍不能进入 Release Audit/标记 accepted；需下一轮先处理 proposal identity/persistence 与可表达的自然语言分类语义，再单独授权 Re-Acceptance #3。

## Condition Semantic Contract + Canonical Proposal Identity Hardening（2026-09-24，本地 dirty slice）

- 本 Slice 延续 `0ad7a3e` 工作树，不是 Re-Acceptance #3；没有调用真实 Provider、没有 Confirm/Apply/Run、没有重启服务、没有 stage/commit/push。
- 当前 Runtime Condition grammar 已审计并集中到共享 contract：`field == literal` / `field != literal`，literal 仅 string/boolean/integer。运行时有 per-run values，但没有可供 Builder 任意命名的正式 typed intermediate namespace；没有引入 `eval`、脚本、隐式 Model classifier 或新的 generic dataflow engine。
- `AgentSemanticPlan` 新增 additive `condition_expression`。`purpose` 只做人类意图，compiler 只读取 `condition_expression`；缺失、未知输入、非法 operator 或注入语法分别 fail closed，不能降级成 `field != ""`。Canonical Canvas Note 只记录已验证的 executable expression 与 branch labels。
- Factory semantic repair sanitizer、Builder prompt、Python contract、JSON Schema、MFJS projection parity 与 Runtime parser 已同步；保留 `agent-semantic-plan-condition-fallback-reacceptance-2.json` 作为失败 fixture，并新增 Condition parser/adversarial tests。
- Factory review candidate 现在 materialize 为现有 `edit_proposals` store 中的 `proposal_kind=create_agent` canonical snapshot，保存 candidate source/Blueprint/resource plan/semantic plan/provenance；`builder_operations.proposal_id` 与 `builder.proposal.ready` facts 在同一事务写入。`local_0027_builder_creation_proposals` 为 operation 关联和唯一性增加窄 migration；重复 materialization 复用同一 ID。
- Builder `records` 不再接受客户端伪造或跨 operation 的 proposal_id；Proposal 必须属于当前 operation 或其真实 focus target。Confirm/Apply 仍保留在后续独立边界，当前 Slice 不执行创建 Agent。
- Focused Builder/Condition/Proposal/Custom Component suite：**129 passed**；完整 `env -u PYTHONPATH -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`：**720 passed**，Ruff、依赖锁、mypy **188 source files** 通过；Web Desktop **472**、Community **22**，typecheck/build 通过；`git diff --check` clean。
- 当前仍不能宣称 Builder accepted / Agent Composition V1 complete。下一步是用户单独授权的 Builder Real Provider Re-Acceptance #3，继续 proposal-only、隔离 Project、无 Confirm/Apply/Run。

## Canonical create_agent Proposal Confirm / Apply identity closure（2026-09-24，本地 dirty slice）

- 本 Slice 只闭合已有 Builder `create_agent` 的 Confirm / Apply 边界；没有进入新模块，没有调用真实 Provider、没有执行真实 Project 的 Run、没有重启服务、没有 stage/commit/push。
- Builder review 生成的 `candidate_source`、Blueprint、resource plan、semantic plan、identity 和 hash provenance 继续写入现有 `edit_proposals` 的 `proposal_kind=create_agent` 快照。新增的 Builder Agent Proposal command 校验 Project、conversation、operation、proposal 四重归属；Confirm 只按 `proposal_id` 取持久化快照。
- Apply 不再从可变 `factory_sessions.blueprint_json` 重新 compile。它重新解析并校验 Proposal 的 `AgentSource`、source/behavior/lock hashes 和当前 Project dependency readiness，然后以 preserve-identity 模式安装完全相同的 Agent source；Factory session 只作为 review/workbench 状态，成功后标记 completed。
- Apply 具备明确的重复语义：相同候选 Agent 已存在且 source 完全相同则复用 applied result；重复 Builder Apply 不新增 Agent、不重复终态事件或 result。Rejected、错误 operation、跨 Project、身份冲突和篡改快照均 fail closed。旧的直接 Factory `apply-draft` endpoint 保留为兼容路径，但 Builder canonical create-agent UI 已切换到 Proposal command。
- 新增回归覆盖：Factory session 漂移不改变最终 source；canonical Apply 幂等；Reject 后 Apply 返回 409；Proposal hash/snapshot 被篡改时不安装。既有 Custom Component proposal lifecycle tests 保持通过。
- 验证：canonical Builder conversation focused **32 passed**；完整 Conda `env -u PYTHONPATH -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check` **724 passed**，Ruff、dependency/lock checks、mypy **188 source files** 通过；Web Desktop **472 passed**、Community **22 passed**，双端 typecheck/build 通过；`git diff --check` clean。保留既有 Alembic `path_separator`、jsdom Canvas stderr 与 Desktop >500 KB chunk warning。

## Provider Credentials & Runtime Binding V1/V2（2026-09-25，本地 dirty slice）

- Platform Builder Provider 与 User Runtime Provider 继续严格分域。Platform secret 由部署/服务器配置管理；Local Runtime 不读取 Platform `model.primary` 或 `MOONSHOT_API_KEY` 作为隐式 fallback。
- `local_0028_provider_credentials_runtime_bindings` 建立 metadata 与 binding；`local_0029_provider_credential_scope` 增加 `credential_scope`。当前 Local API 只接受 `device`，`cloud` 只是未来契约 seam，不代表 Cloud Vault 已实现。
- `provider_credentials` 只保存 provider type、label、base URL、状态、scope、masked hint、capabilities、时间和 opaque `secret_ref`。真实 API key 由 `SecretStore` 交给跨平台系统 credential backend：macOS Keychain、Windows Credential Manager、Linux Secret Service/KWallet；不进入 SQLite、AgentSource、Project YAML、Proposal、Builder event、Run evidence、导出或 Community payload。
- Metadata 存在但 device secret 缺失时，API 明确返回 `secret_state=missing`、`readiness=needs_reentry`；系统 credential backend 不可用时返回 `readiness=unavailable`，不会伪装为可用，也不会降级到明文文件或 process-memory store。
- Local Credential API 与 Runtime binding API 保持不变形状并增加 scope/readiness metadata。Runtime resolver 仍按 Agent binding → Project binding → User default → missing；只有 readiness 为 `ready` 的 credential 可以进入 Runtime。
- Phase A 已用合成 `127.0.0.1:8790` Mock 完成正式 Replace、系统 credential store 写入、8771 停止/重启和 resolver-after-restart 验收；真实 Moonshot Runtime 未使用。
- Phase B Applied Agent Runtime Closure 已完成：确认既有 Request Review Agent active；正式 Validate/Commit 生成 immutable version；修复 output `status-2` 残留为 `status`，并修复同名 input/output 的 Runtime JSON 解析。approved 与 pending 两条本地 Mock Run 均按条件只执行对应 branch，结果和事件证据正确；Studio UI 复核确认 Catalog Model `requires_configuration` 与 Instance Runtime Binding 分离。
- 最终验证：backend full `make check` **733 passed**、mypy **190 source files**；Desktop **475 passed**、Community **22 passed**；Desktop typecheck/build 通过；真实 Studio Browser acceptance 通过；`git diff --check` clean。保留既有 jsdom Canvas stderr 与 Desktop large-chunk warning。

## Project Sync Foundation #1（2026-09-25）

- 产品模型已从两个独立的 Local Project / Cloud Project 收敛为一个 Logical
  Project：Local Working Copy 先创建，登录且 Cloud 可用时用完全相同的
  project_id 建立 Cloud Replica。首页没有新增 Cloud Project 卡片、页面或
  Sidebar 分类，现有 Create Project 是唯一用户入口。
- Cloud Host 仍运行在 8772，复用 Community Account/session/CSRF 和数据库
  lineage；新增 community_0010_project_sync_revision，cloud_projects.revision
  从 1 开始单调递增。8772 不导入 Local app、Local Project directory 或
  DeviceSecretStore。
- Local 新增 local_0030_project_sync_state 和 project_sync_states。它只保存
  state、Cloud revision、metadata hashes、pending operation、remote metadata
  和冲突诊断；不保存 Cookie、secret、credential ID、Keychain ref 或 local path。
- 本轮只同步 Project metadata（identity/name/description/lifecycle/schema），不
  同步 Agent、Workflow、Knowledge、Files、Runs、Chat、Provider Credential 或
  Runtime Binding。Desktop ProjectSyncCoordinator 负责 8771/8772 协调，Local
  API 不读取 Cloud Cookie。
- Cloud 协议是 explicit-ID ensure、pull、expected-revision push；同用户重复
  ensure 幂等，跨用户 claim 返回 404，stale revision 返回 409 sync_conflict，
  不使用 silent last-write-wins。Cloud 不可用时 Local 创建仍成功并进入
  pending_upload，页面重载/恢复后可 retry。
- 本轮没有实现 Project Artifact Sync、Cloud Files、Cloud Chat、Cloud Credential
  Vault、Cloud Runtime，也没有恢复上一轮独立 Cloud Project UI。
- 最终门禁：backend make check **741 passed**、Ruff format/check、依赖锁、mypy
  **201 source files**；Desktop **479 passed**、Community **22 passed**；两端
  typecheck/build 通过；Project Sync Coordinator focused **4 passed**、Local
  sync integration **2 passed**；git diff --check clean。保留既有 Alembic
  path_separator、jsdom Canvas stderr 和 Desktop large-chunk warnings。

## Cloud Files & Library Foundation #1（2026-09-25，已完成）

- 新增 Cloud File domain 与 `community_0012_cloud_files` forward-only migration：
  `cloud_files` 保存账号私有 metadata，`cloud_project_file_references` 保存
  Project 引用。没有修改已应用的 `community_0011`，Local DB 不新增文件表。
- 新增窄 `BlobStore` contract 与开发/self-host `FilesystemBlobStore`。文件 bytes
  在服务器 Cloud data root 的临时对象中流式写入，完成 size/SHA-256 和 upload limit
  校验后原子 finalize；数据库只保存 metadata 和 server-generated storage key。
  storage key/root 不返回前端；当前没有安装 S3 SDK，未来 S3/MinIO/R2 只通过该 seam
  替换。
- Cloud API 已支持 authenticated list/upload/get/stream-download/delete，以及
  Project File attach/detach/list。所有 operation owner-scoped；跨账号返回非披露
  404；有引用时 Library delete 返回 `file_in_use`；detach 不删除 blob；无引用删除
  同时删除 metadata/blob。上传不扫描 Local Project，也不接受 base64 JSON 整文件。
- Local 只增加安全 materialize foundation：Cloud 下载字节必须显式指定目标，限制在
  Project `assets/` 或 `knowledge/`，拒绝绝对路径、`..`、symlink，并校验预期 hash/size。
  Knowledge 增加可选 `cloud_file` source reference；仍不自动下载、不自动 index。
- Web/Desktop 共用 `CloudFile*`、`ProjectFileReference` contracts 和 connected-account
  client；本轮没有新增页面、Sidebar、Files 大 UI、Knowledge 重做或 Community UI。
- 真实本机验收：Chrome 已确认账号仍可用、现有 Artifact Project 页面和 Sidebar 正常；
  Cloud File bytes 使用授权测试账号的 isolated acceptance harness 上传。首次上传、
  metadata、list、download、SHA/size、Project attach/list 通过；重启 8772 后
  metadata/blob/download 仍通过；随后 detach、delete、Project archive 清理成功，
  blob count 为 0。Harness 不是纯 UI upload E2E，浏览器部分只验证现有页面路径和回归。
- 真实服务：8771 Local `local_0031_project_artifact_sync_state`、8772 Cloud
  `community_0012_cloud_files`；Cloud `/api/v1/ready` 返回 `ready=true`。
- 本 Slice 最终验证：backend `make check` **754 passed**、399 warnings，Ruff/format/
  dependency lock PASS，mypy **216 source files**；Desktop **484 passed**（64 test
  files）、Community **22 passed**（3 test files）；两端 typecheck/build PASS；
  `git diff --check` PASS。保留既有 Alembic `path_separator`、jsdom Canvas stderr
  和 Desktop large-chunk warning。
- Real Platform Provider、Real Runtime Provider、Agent Run、Cloud Chat、Cloud Runtime、
  Cloud Credential Vault、PDF/OCR/vector RAG、public sharing、S3 production deployment
  均未执行或未实现。

## Existing Chat Server Authority & Cross-Client Persistence #1（2026-09-25，已完成）

- 审计确认当前现有 Chat 是 Project Builder Chat：Desktop Chat UI → Local API →
  `BuilderConversationService` → `BuilderConversationStore` → Local SQLite 的
  `builder_conversations` / `builder_messages` / `builder_operations`。本轮没有创建
  第二套 Chat UI，也没有重写 Builder、Proposal 或 Apply。
- Cloud/Community 新增 `community_0013_conversations` forward-only migration，建立
  account-owned `conversations`、`conversation_messages`、`conversation_operations`、
  `conversation_operation_events`。Cloud Host head 已从 `community_0012_cloud_files`
  正向升级；Local head 保持 `local_0031_project_artifact_sync_state`。
- Server API 支持 Conversation list/create/get、Message append、import、rename、
  archive、restore。Conversation 使用 owner_user_id、可选 Project/Agent relation、
  revision 和 server sequence；Message 支持稳定 message_id、append 幂等、ordering、
  operation/proposal/event refs。跨账号读写和跨账号 Project 绑定返回非披露 404。
- Message attachment 只接受当前账号的 Cloud File ID；Message JSON 不携带 bytes、Local
  path、credential、secret 或 storage key。Cloud File authority 仍是上一 Slice 的
  `/api/v1/cloud/files`。
- Desktop 新增薄 `ConversationMigrationCoordinator`：首次有账号 session 时读取
  现有 Local Builder activity/snapshot，以原 conversation_id、message_id、operation_id、
  proposal_id 和 event_id 幂等 import 到 Server；不删除 Local 旧数据。Recent 优先读
  Server Conversation list，Server endpoint 不可用时保留明确的 Local cache fallback。
  现有 Builder 页面继续通过 Local Host 执行本机 Project 操作，Server 只成为账号 Chat
  persistence authority；没有长期的 Local↔Cloud Chat 双主同步产品。
- 真实 API cross-client acceptance：Desktop A 创建 C1、写入 M1；Web B 读取同一 C1/M1
  并写入 M2；A 重新读取 M1/M2；Cloud File F1 作为 attachment ref 在 B 端可见且可通过
  Cloud File endpoint 下载。8772 重启后 Conversation、Messages、Project relation 和
  attachment ref 仍存在，随后已清理 isolated Project/Conversation/File。未发送真实
  Provider 请求。
- 本 Slice focused：Cloud Conversation **4 passed**、Desktop migration coordinator
  **2 passed**；最终 backend `make check` **758 passed**、399 warnings，mypy **221
  source files**；Desktop **486 passed**（65 files）、Community **22 passed**；两端
  typecheck/build PASS；`git diff --check` PASS。保留既有 Alembic `path_separator`、
  jsdom Canvas stderr 和 Desktop large-chunk warning。
- Browser boundary：没有发送 Chat 消息或 Provider 请求；本轮尝试用真实 Chrome 打开
  现有 Chat 页面时，Chrome debugger connection 不可用，因此没有把页面检查伪称为通过。
  cross-client 数据证据来自 authenticated API acceptance harness；没有新增 UI 页面或
  Sidebar。

## Project Artifact Sync #2（2026-09-25，已完成）

- 在 Logical Project / 同一 project_id 上增加统一 Project Artifact envelope，当前
  kind 为 agent、agent_version、workflow、custom_component、knowledge_metadata。
  Cloud 使用 community_0011_project_artifacts；Local 使用
  local_0031_project_artifact_sync_state。旧的 0010/0030 migration 没有修改。
- Cloud Artifact API 提供 owner-scoped manifest、get、expected-revision put；
  mutable Artifact 独立 revision，immutable Agent version 允许同 hash 幂等重传，
  同 ID 不同 hash 返回 integrity conflict。payload 递归拒绝 API key、credential、
  secret、Keychain、absolute path、local URI 和 device-only 字段。
- Local Artifact API 负责 discovery、portable payload、materialize 和 per-artifact
  sync state。Agent/Workflow/Knowledge pull 继续走现有 domain contract 与 Project
  canonical writer；Custom Component 只安装当前真实定义，design_only 不会被升级。
  Knowledge 只同步 metadata/hash，另一设备得到 metadata_only，不可假装可检索。
- Desktop 已有 ProjectArtifactSyncCoordinator，负责 dependency order、delta/no-op、
  push/pull/conflict/pending；本轮没有增加页面或 Sidebar UI。Cloud Files、raw Knowledge、
  Runs、Chat、Credential、Runtime 仍不在范围内。
- 本轮 focused：Cloud/Local Artifact 与 Project Sync **31 passed**；Desktop Artifact
  Coordinator **5 passed**、既有 Project Sync **4 passed**；Local second-device
  materialization **3 passed**。最终 backend `make check` **746 passed**、mypy
  **208 source files**、Ruff/format/依赖锁 PASS；Desktop **482 passed**、Community
  **22 passed**；typecheck/build PASS；git diff --check PASS。保留既有 Alembic
  path_separator、jsdom Canvas stderr 和 Desktop large-chunk warnings。

## Server Execution Plane V1（2026-09-25）

- Cloud migration 已从 `community_0013_conversations` forward-only 升级到
  `community_0014_server_credentials` 与 `community_0015_cloud_runs`；真实 8772
  当前为 `community_0015_cloud_runs`，8771 为 `local_0031_project_artifact_sync_state`。
- Cloud Credential Vault 已完成 owner-scoped CRUD、no-generation validation、replace、
  enable/disable/default 和 Project/Agent binding。SQLite 只保存 metadata 与 AES-GCM
  ciphertext；production 必须配置 `VEYRA_CLOUD_CREDENTIAL_MASTER_KEY`，本机 development
  使用独立权限受限 master-key 文件。Settings Provider card 登录后优先走 Cloud API，
  没有 Cloud bridge 时保留 Local fallback；页面布局未重做。
- Cloud Runtime 只加载 exact immutable `agent_version`，校验 source/behavior/lock hashes；
  支持 Start/Model/Transform/Condition/Verifier/Output/HumanApproval。Tool 在 Cloud
  fail closed 为 `local_host_required`，Cloud File input 必须 owner/project scoped。
- Builder `create_agent` 的 waiting operation 仍由 Local Conversation durable 保存；选择
  Cloud credential 时先写入 Cloud Project `primary_model` binding，再以显式
  `credential_scope=cloud` 恢复同一个 operation，不把 Cloud secret 或 Platform key 交给
  Local Runtime。没有 Credential 时只显示添加/选择卡，不阻断普通 Chat。
- Cloud Run API 支持 create/get/list、durable events、SSE + `Last-Event-ID`、approval/
  reject、stop、retry child lineage、checkpoint resume 和 restart recovery。Run evidence
  只保存 provider/model、`credential_type=user`、alias 等安全 metadata。
- Focused execution **8 passed**；Cloud suite **27 passed**；最终 backend **767 passed / 399
  warnings**，Ruff/format/dependency lock、mypy **234 source files** 通过。Desktop **487
  passed / 66 files**，Community **23 passed / 4 files**；两端 typecheck/build PASS；
  Desktop build JS 1,202.14 kB、Web build JS 343.75 kB；Desktop large-chunk warning、jsdom Canvas stderr 和 Alembic
  `path_separator` warning 保留。
- 真实本机 mock acceptance：8771、8772、5173 均健康；Cloud mock Transform Run、SSE、
  8772 restart persistence、cleanup 通过。Real Provider acceptance：**NOT RUN**；真实
  Agent Model Run：**NOT RUN**。jsdom/API harness 不冒称真实 Browser acceptance。
- 5174 已从纯 Showcase 入口收口为 Web Workspace：登录、Projects、Cloud Conversation、
  Cloud Files、Cloud Runs、Community、Account、Cloud Credential Settings 使用同一 Server
  API；`#/showcase` 保留公开展示。Web 明确不提供 Local Working Copy、Finder、Git、Shell、
  MCP、Local Runtime 或 Device Credential。

## V1 Product Closure deployment/packaging audit（2026-09-25）

- Production Cloud deployment now starts `veyra_agent_platform.cloud.app:app` through
  `VEYRA_HOST_KIND=cloud`; the same authenticated Cloud Host exposes Account, Registry,
  Projects, Artifacts, Files, Conversations, Credentials, and Runs. Production requires
  PostgreSQL, S3-compatible object storage, `VEYRA_CLOUD_CREDENTIAL_MASTER_KEY`, auth HMAC,
  public origin, and explicit non-wildcard allowed origins. Secure cookies remain enabled in
  production; localhost development keeps its existing cookie behavior.
- Cloud Files support an S3-compatible adapter reusing the repository's signed S3 client seam;
  FilesystemBlobStore remains development/self-host only. `/api/v1/ready` now checks DB head,
  object storage, and Cloud credential cipher readiness. Backup/restore scripts document DB,
  blob-store, and master-key handling without writing secrets into the repository.
- Fresh Local and Cloud SQLite migrations from empty databases passed; copied current Local and
  Cloud databases upgraded to current heads. PostgreSQL migration SQL generation passed;
  live PostgreSQL integration: **NOT RUN** because Docker is unavailable in this environment.
- Desktop package static smoke: **PASS** (`static_contract=ok`). macOS arm64 package build:
  **NOT RUN** because Rust/Cargo tooling is unavailable in this environment. Signing and
  notarization: **SIGNING NOT RUN — Apple Developer credentials unavailable**.
- Golden-path API evidence: Build/Proposal/immutable Version foundations remain covered by the
  existing Local tests; mock Cloud Run path passed; Community Publisher A → Discover → Star →
  Download → Local Import Preview → no Project mutation before Confirm → Local Draft → Local
  mock-free Transform Run passed in an isolated two-account API harness. Web/Desktop shared
  Project/Conversation/Run IDs passed in an authenticated cross-client harness. Browser E2E:
  **NOT RUN**; Chrome debugger was unavailable, so API/jsdom evidence is not called Browser E2E.

## Community information architecture and visual refresh（2026-09-26，本地工作树）

- Community Desktop 首页从“注册表卡片列表”调整为开发者社区入口：深色社区 Hero、真实作品发现流、版本检查路径、收藏/发布下一步和讨论区预留；仍只读取真实 Registry / Star / Review 数据，不添加假帖子、假热度或假推荐。
- `#/community/mine` 调整为创作者工作台：发布 Agent 是主任务，发布前 Source/哈希/依赖/权限检查作为侧栏，真实已发布版本作为辅助列表；Plugin Pack 降级为可展开的第二层发布通道，避免空状态占据整块首屏。
- 保留原有发布预览、显式确认、导入预览、Star、版本详情、路由和 moderation 行为。页内“浏览作品/开始发布”使用真正的平滑滚动，不写入路由 hash。
- 讨论区当前仅展示产品方向和已可用的版本评价边界；creator follow、帖子、Feed、讨论 API 仍未实现，不能标记为社交社区闭环完成。
- 验证：Desktop 全量 `npm test --workspace=@veyra/desktop` **488 passed**；Web 全量 Desktop **488** + Community **23 passed**；Web typecheck 与 desktop/community production build 通过；保留 Desktop 既有大 chunk warning 与 jsdom Canvas stderr。
- 代码范围：`web/apps/desktop/src/pages/community.tsx`、`web/apps/desktop/src/features/community/community.css`、`web/packages/connected-account/src/styles.css`；未 stage、commit 或 push。

## Community flagship visual refinement（2026-09-26，本地工作树）

- 按四个真实页面截图继续收敛：Discover 的 Hero 改为轻量产品头部，Published 改为可扫描的版本记录行，Starred 增加独立标题/说明/正常空态，Mine 的创作者 Hero 和发布区减少营销式留白。
- 视觉系统保留 Veyra 的 teal/indigo token、深浅色和中文/英文，新增 GitHub 式底线导航、细边框记录、轻量 hover/淡入/轨道浮动动画；`prefers-reduced-motion` 关闭动画。
- 仍不添加假帖子、假数据、假热度或未实现资源类型；所有内容继续来自真实 Community Registry / Star / Review / publish/import flows。
- 验证：Desktop 全量 **488 passed**；Desktop typecheck；Web Desktop/Community production build 通过；既存 Desktop 大 chunk warning 与 jsdom Canvas stderr 保留；实际 Chrome 检查 Discover / Published / Starred / Mine。
- 本轮未 stage、commit 或 push。

## Community catalog view switch（2026-09-26，本地工作树）

- Discover / Starred 增加卡片 / 按行两种显示方式，默认卡片模式，偏好保存到浏览器本地；两种模式复用相同的真实 Registry 数据、Star 和版本详情路由。
- 列表模式使用紧凑 release row，适合快速扫描作者、版本、节点和操作；卡片模式保留推荐目录的视觉浏览体验。
- 修复当前工作树中重复的 `section === "mine"` 数据加载分支，使 Desktop typecheck 恢复通过。
- 验证：Community 页面定向测试 **3 passed**；Desktop 全量 **488 passed**；Desktop typecheck、Desktop production build 通过；Chrome 实际点击卡片/列表按钮并恢复默认卡片模式。
- 本轮未 stage、commit 或 push。

## Community reference design implementation（2026-09-26，本地工作树）

- 按用户提供的图 2 视觉稿落地 Community：Discover 增加 Community 标题区、几何装饰、搜索、资源类型胶囊、推荐区和 Agent graph preview；Published 增加四项状态统计、状态筛选胶囊和表格列；Starred 增加搜索/排序；Mine 改为 Creator Center，包含资源类型入口、四项统计、最近发布和草稿边界。
- 图 1 的卡片/列表切换保留在 Discover / Starred，列表模式复用同一真实 Registry 数据并以紧凑 release row 呈现；没有添加图片字段、假资源、假评分或假讨论。
- Workflow / Skill / Tool / Plugin Pack 在 Discover 中显示为真实能力边界：当前未开放的目录入口保持 disabled，并给出原因；Plugin Pack 的真实发布通道保留在 Creator Center。
- 验证：Desktop 全量 **488 passed**；`app.test.tsx` **59 passed**；Community 页面定向 **3 passed**；Web build（Desktop + Community）与 Desktop typecheck 通过；Chrome 实际检查四个社区页面、浅色/暗色与网格/列表切换。
- 本轮未 stage、commit 或 push。

## Community creator workspace correction（2026-09-27，本地工作树）

- `#/community/mine` 重组为 Creator workspace：状态概览只使用真实 Published / In review / Rejected / Star 数据；发布类型、来源选择、检查与确认统一在一块 Release Studio 背景内；不存在持久后端的 Community Draft 指标和草稿面板已移除。
- 页面按设计路线显示 Agent、Project、Workflow、Plugin Pack、Template、Component/Tool/standalone Skill。只有当前已有真实 Registry API 的 Agent 与 Plugin Pack 可操作；Project 只标明本地 export 已存在、Community 发布接口待接入，其余保持 planned，未增加假 API 或假发布结果。
- Discover / Published 的 version-bound Star 显示现在都由账户 `GET /api/v1/registry/starred` 集合恢复，修复同一 release 在 Discover 显示已收藏、Published 显示未收藏的问题；Starred 列表仍是自身权威状态。
- 验证：Desktop 全量 **66 files / 490 tests passed**；Community + App 定向 **64 passed**；Desktop typecheck、production build 与 `git diff --check` 通过。实际浏览器检查 Mine 浅色/暗色/窄 viewport、Agent/Plugin Pack 切换，以及 Discover/Published 同一 release 都显示已收藏。未执行发布、上传或 Star mutation。

## Connected Account workspace redesign（2026-09-27，本地工作树）

- `#/account` 改为账号身份摘要、公开资料、会话安全三层布局；保留头像、display name、handle、邮箱、资料保存、会话撤销和退出账号的原行为。
- 按原 Connected Account / Community 设计补入真实社区身份入口：Creator workspace、Published releases、Starred resources，以及已启用的 immutable publish、save/review、Fork lineage 能力；组织、计费和 private backup 仍是 later，不在页面伪装成可用。
- 本机边界以可见清单说明：Project / Agent / Workflow source、Run / approval / receipt、Secret values / host credentials 不因登录自动上传或按账号隔离，只有显式 Publish/Sync 才离开设备。
- 设备展示不再回显长 User-Agent；根据实际 user agent 归一浏览器/平台名称，同时保留有意义的显式 `device_name`。桌面端会话列表固定高度滚动，窄屏使用自然页面滚动。
- 页面明确 Community 只保存身份和发布元数据，Project / Agent / Run 仍在本机；退出登录不会删除本地 Project 或 Community release。未改后端契约或执行账号 mutation。
- 验证：Desktop 全量 **66 files / 490 tests passed**；Account/App 定向 **59 passed**；Desktop typecheck、production build 与 `git diff --check` 通过。实际浏览器以当前真实账号、Community route cards 和 17 个会话检查浅色、暗色与窄 viewport。保留既有大 chunk warning 与 jsdom Canvas stderr。
# 2026-10-09 — Generator convergence and CSV mainline (in progress)

Latest evidence: native CSV Tool 1.1 reads either a relative Project path or a
declared, validated Run file input by name. It reads immutable Artifact bytes without
copying private Run uploads into Project assets. Version 1.0 is retained. Six
scripted Factory/Runtime cases exercise both sources and approval/rejection paths,
real calculation/row evidence, source hashes, receipts, and report content reads.
The pre-real-test `make check` passed **1399** tests.

One real browser retry on the reloaded exact build failed at the Provider boundary
with HTTP429 `engine_overloaded_error`. Five receipted requests were made; no
candidate/Agent/Workflow was created. Earlier HTTP-success responses did not result
in a validated IR. The previous schema repair issue was not durable, so its exact
cause cannot be inferred. There are no persisted token/cost fields for this attempt.
Do not call this real-model success or treat bytes as token usage/cost.

After that attempt, pinned resource selection was corrected to return the entire
pinned descriptor rather than new-version metadata with an old ref/hash; safe local
validation issues now accompany later Provider failures. These post-attempt changes
passed 52 focused checks and are not yet loaded by the Local API. The next paid run
must follow local gates and a clear new evidence objective, not repeated overload.

The current priority is an ordinary-user Factory-to-committed-Run-to-deliverable
path, beginning with CSV reconciliation. Apply the user's architecture prompt
critically: retain exact supplied Skill selection and the existing bounded coverage
review; retain structured IR/redacted diagnostics instead of raw private responses.
Do not replace a successful Run or browser acceptance with static test counts.

Workflow value resolution now has one compiler module, `workflow_bindings.py`, for
AgentCall ports, human replies, final aliases and intermediate verifier subjects.
Composite Composer emits the Source graph; Runtime executes its explicit mappings
without requiring future final files during intermediate verification. Legacy
unmapped Source checks keep their prior behavior. The this-slice independent
verifier helper was folded into that cohesive module.

Repair retains duties and occurrences while allowing stage placement and qualified
port references to be corrected. It retains check contracts, conditions, decisions,
exact method pins and write limits. Actor capability guesses no longer become
permanent Skill dependencies; declared required Tool duties and real catalog
dependencies remain authoritative. `reports/` now participates in Project indexing,
content reads and archives.

Executable evidence: backend `make check` **1360 passed**, including a scripted
Factory HTTP → Apply → Commit → native CSV comparison → verifier → business and
Tool approvals → actual report → Project content-read fixture. Both rejection paths
preserve source hashes and produce no report. This proves compiler/HTTP/native
execution for that fixture, not arbitrary real-model generation or browser UX.

Pre-paid-test review found a remaining mainline input gap: ordinary Run uploads are
ArtifactRefs, while the existing CSV Tool accepts only Project paths. Work continues
at the native file-source boundary using selected Run input names and the existing
project-scoped, hash-checked Artifact byte reader. Preserve immutable Tool 1.0 pins;
do not silently copy private Run uploads into exportable Project assets. The Local
API has not yet been reloaded for these convergence changes. No new external model
request was made during this slice; later input changes require fresh checks.
