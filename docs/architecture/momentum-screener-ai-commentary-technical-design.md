# 强势筛选 AI 点评增强 技术开发文档

## 1. 文档信息

- 文档名称：强势筛选 AI 点评增强技术开发文档
- 英文名称：Momentum Screener AI Commentary Technical Design
- 所属系统：`daily_stock_analysis`
- 文档类型：技术开发文档 / 实现设计
- 当前状态：`draft v1.1`
- 最后更新：`2026-04-15`
- 关联文档：
  - [产品需求文档](./momentum-screener-ai-commentary-prd.md)
  - [二次决策技术开发](./momentum-screener-secondary-decision-technical-design.md)
  - [Agent API 设计](../api_spec.json)

---

## 2. 目标与范围

### 2.1 本次实现

在强势筛选页面新增四个 AI 点评入口，复用现有 Agent/LiteLLM 基础设施，实现：

- 候选股 AI 点评（个股维度拆解 → 自然语言深度分析）
- 二次决策 AI 综合建议（策略健康 + 组合 + 主线 → 操作指南）
- 盘中信号 AI 解读（实时价格 + 状态 → 盘中操作建议）
- 落选说明 AI 分析（淘汰原因标签 → 综合分析）

本次实现必须遵守一个前提：

> AI 点评是强势筛选的解释层与追问层，不是新的决策引擎。

因此实现范围还需要补两条边界：

1. 前端展示必须先呈现规则结论，再呈现 AI 解释
2. AI 输出不能覆盖 `今日不做`、`偏离过大`、固定顺序等规则风控边界

### 2.2 不复用的部分

- **不复用 `/agent/chat/stream` endpoint** — 因为它的 prompt 是为自由问答设计的，不适合结构化筛选数据
- **不复用 `agentChatStore`** — 强势筛选对话需要独立的 session 管理和上下文构造

### 2.3 复用的部分

| 组件 | 复用方式 |
|------|----------|
| `LLMToolAdapter` | 直接使用，零改动 |
| `build_agent_executor` | 用于构建带工具调用能力的 executor |
| Agent 工具集 | 行情、新闻、板块分析等工具全部可用 |
| SSE 流式输出 | 复用现有的 event generator 模式，但前台只展示“分析阶段”而不是详细 thinking |
| 会话存储 | 复用现有 agent chat session 数据库表，但前台列表只展示 screener 会话 |

---

## 3. 系统架构

### 3.1 高层架构

```
┌─────────────────────────────────────────────────────────────┐
│  前端 (apps/dsa-web)                                        │
│  ├── MomentumScreenerPage.tsx (现有)                        │
│  ├── ScreenerChatPanel.tsx (新增)                           │
│  ├── useScreenerChat.ts (新增 hook)                         │
│  └── screenerChatStore.ts (新增 store)                      │
└─────────────────────────────────────────────────────────────┘
                          │ REST + SSE
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  后端 (api/v1/endpoints)                                    │
│  ├── screener_ai.py (新增 endpoint)                         │
│  │   ├── POST /screener/momentum/ai-review/stream           │
│  │   ├── GET  /screener/momentum/ai-review/sessions         │
│  │   └── GET  /screener/momentum/ai-review/sessions/{id}    │
│  └── agent.py (现有，不改)                                  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  服务层 (src)                                               │
│  ├── agent/llm_adapter.py (现有，直接使用)                  │
│  ├── agent/factory.py (现有，build_agent_executor)          │
│  ├── agent/executor.py (现有，chat + progress_callback)     │
│  └── services/momentum_secondary_decision_service.py        │
│      (现有，提供评分数据)                                   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 数据流

```
用户点击"AI 点评"按钮
        │
        ▼
前端构造 prompt（组装评分数据 + 系统 prompt）
        │
        ▼
POST /api/v1/stocks/screener/momentum/ai-review/stream
   body: {
     review_type: "candidate_detail",  // or "secondary_decision", "intraday", "excluded"
     stock_code: "603026.SH",          // 候选股点评时必填
     profile: "aggressive",
     trade_date: "2026-04-14",
     screening_data: { ... },          // 完整的筛选数据快照
     intraday_data: { ... },           // 盘中点评时填
     refresh_mode: "resume" | "rerun"  // 默认 resume，主动点“重新分析”时才传 rerun
   }
        │
        ▼
后端：
  1. 校验请求参数
  2. 构造 system prompt + user prompt
  3. build_agent_executor(config)  ← 复用问股的 executor
  4. executor.chat(message, session_id, progress_callback)
  5. SSE 流式输出 event（stage / tool_start / tool_done / chunk / done）
        │
        ▼
前端 SSE 客户端接收 event，实时渲染
        │
        ▼
对话持久化到数据库（agent chat session 表，与问股共用）
        │
        ▼
用户可以继续追问（后续追问走同一个 session_id）
        │
        ▼
面板顶部展示 trust bar
（规则日期 / profile / 行情时间 / 已调用工具 / 当前规则总闸门）
```

---

## 4. 后端设计

### 4.1 新增 API Endpoint

**文件**：`api/v1/endpoints/screener_ai.py`

#### 4.1.1 流式点评接口

```
POST /api/v1/stocks/screener/momentum/ai-review/stream
Content-Type: application/json
Accept: text/event-stream

Request Body:
{
  "review_type": "candidate_detail" | "secondary_decision" | "intraday" | "excluded",
  "profile": "standard" | "aggressive",
  "trade_date": "2026-04-14",
  "stock_code": "603026.SH",          // candidate_detail 时必填
  "screening_data": { ... },          // 筛选数据快照
  "intraday_data": { ... },           // intraday 时填
  "excluded_stocks": [ ... ],         // excluded 时填
  "refresh_mode": "resume" | "rerun", // 默认 resume，主动重分析时才传 rerun
  "session_id": "可选，不传则后端生成"
}

Response: text/event-stream (SSE)
Event types:
  - stage: { type: "stage", code: "loading_context" | "fetching_tools" | "analyzing" | "generating", message: "..." }
  - tool_start: { type: "tool_start", tool: "...", display_name: "..." }
  - tool_done: { type: "tool_done", tool: "...", success: true, duration: 1.2 }
  - chunk: { type: "chunk", content: "..." }
  - done: {
      type: "done",
      content: "...",
      success: true,
      session_id: "...",
      context_meta: {
        trade_date: "2026-04-14",
        profile: "aggressive",
        market_data_as_of: "2026-04-15T10:32:00+08:00",
        tools_used: ["quote", "news", "sector"],
        rule_guardrail: "今日不做"
      },
      suggested_questions: ["这只票最大风险是什么？", "什么情况下直接放弃？"]
    }
  - error: { type: "error", message: "..." }
```

#### 4.1.2 会话列表接口

```
GET /api/v1/stocks/screener/momentum/ai-review/sessions?profile=aggressive&limit=10

Response:
{
  "sessions": [
    {
      "session_id": "uuid",
      "title": "石大胜华 AI 点评 · 2026-04-14",
      "review_type": "candidate_detail",
      "stock_code": "603026.SH",
      "message_count": 3,
      "created_at": "2026-04-15T10:30:00Z",
      "last_active": "2026-04-15T10:32:00Z"
    },
    ...
  ]
}
```

#### 4.1.3 会话消息接口

```
GET /api/v1/stocks/screener/momentum/ai-review/sessions/{session_id}?limit=50

Response:
{
  "session_id": "uuid",
  "messages": [
    { "id": "...", "role": "user", "content": "..." },
    { "id": "...", "role": "assistant", "content": "...", "thinking_steps": [...] }
  ]
}
```

### 4.2 Prompt 组装服务

**文件**：`src/services/screener_ai_prompt_service.py`（新增）

```python
class ScreenerAIPromptService:
    """组装强势筛选 AI 点评的 prompt。"""

    def build_candidate_review_prompt(
        self,
        stock_code: str,
        name: str,
        profile: str,
        trade_date: str,
        screening_data: Dict[str, Any],
    ) -> Tuple[str, str]:
        """返回 (system_prompt, user_prompt)。"""
        system = "你是一个短线交易助手。请基于以下强势筛选数据..."
        user = self._format_candidate_review_input(...)
        return system, user

    def build_secondary_decision_prompt(
        self,
        profile: str,
        trade_date: str,
        decision_data: Dict[str, Any],
    ) -> Tuple[str, str]:
        ...

    def build_intraday_prompt(
        self,
        profile: str,
        trade_date: str,
        intraday_data: Dict[str, Any],
    ) -> Tuple[str, str]:
        ...

    def build_excluded_analysis_prompt(
        self,
        profile: str,
        trade_date: str,
        excluded_data: Dict[str, Any],
    ) -> Tuple[str, str]:
        ...
```

Prompt 组装时要把产品侧的“回答合同”固化进去：

1. 每类点评都先输出规则结论，再输出 AI 解释
2. 盘中点评显式写入不能重排顺序、不能推翻 `今日不做`、不能对“偏离过大”给追入建议
3. 落选分析默认限制为“最可惜落选 Top3”

### 4.3 Endpoint 实现要点

```python
@router.post("/screener/momentum/ai-review/stream")
async def screener_ai_review_stream(request: ScreenerAIReviewRequest):
    config = get_config()
    session_id = request.session_id or str(uuid.uuid4())

    # 1. 组装 prompt
    prompt_service = ScreenerAIPromptService()
    system_prompt, user_prompt = prompt_service.build_prompt_for_type(request)

    # 2. 构造首条消息
    initial_message = f"{system_prompt}\n\n{user_prompt}"

    # 3. 构建 executor（复用问股的）
    executor = build_agent_executor(config)

    # 4. 流式输出
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def progress_callback(event: dict):
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    def run_sync():
        result = executor.chat(
            message=initial_message,
            session_id=session_id,
            progress_callback=progress_callback,
        )
        asyncio.run_coroutine_threadsafe(
            queue.put({
                "type": "done",
                "success": result.success,
                "content": result.content,
                "session_id": session_id,
            }),
            loop,
        )

    # SSE event generator（复用 agent.py 中的模式）
    async def event_generator():
        fut = loop.run_in_executor(None, run_sync)
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=300.0)
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if event.get("type") in ("done", "error"):
                    break
        finally:
            try:
                await asyncio.wait_for(fut, timeout=5.0)
            except asyncio.TimeoutError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

### 4.4 会话存储

**方案**：直接复用现有 agent chat session 数据库表，不需要新建。

在 session title 中加前缀区分来源：
- 强势筛选会话：`[Screener] 石大胜华 AI 点评 · 2026-04-14`
- 问股会话：不带前缀

后端仍然可以复用同一张表，但产品层必须保持前台隔离：

1. 强势筛选页面只读取 `[Screener]` 前缀会话
2. 问股页面默认不展示 `[Screener]` 会话
3. 最近对话列表是“围绕某次筛选任务的历史”，不是自由问股历史

### 4.5 Schema 定义

**文件**：`api/v1/schemas/stocks.py`（扩展）

```python
class ScreenerAIReviewRequest(BaseModel):
    review_type: Literal["candidate_detail", "secondary_decision", "intraday", "excluded"]
    profile: Literal["standard", "aggressive"]
    trade_date: str
    stock_code: Optional[str] = None          # candidate_detail 时必填
    screening_data: Optional[Dict[str, Any]] = None
    intraday_data: Optional[Dict[str, Any]] = None
    excluded_stocks: Optional[List[Dict[str, Any]]] = None
    refresh_mode: Literal["resume", "rerun"] = "resume"
    session_id: Optional[str] = None

class ScreenerChatSessionItem(BaseModel):
    session_id: str
    title: str
    review_type: str
    stock_code: Optional[str] = None
    message_count: int
    created_at: Optional[str] = None
    last_active: Optional[str] = None

class ScreenerAIContextMeta(BaseModel):
    trade_date: str
    profile: Literal["standard", "aggressive"]
    market_data_as_of: Optional[str] = None
    tools_used: List[str] = []
    rule_guardrail: Optional[str] = None
```

---

## 5. 前端设计

### 5.1 新增文件

| 文件 | 说明 |
|------|------|
| `apps/dsa-web/src/components/screener/ScreenerChatPanel.tsx` | 对话面板组件 |
| `apps/dsa-web/src/stores/screenerChatStore.ts` | Zustand store |
| `apps/dsa-web/src/api/screenerAi.ts` | API 客户端 |
| `apps/dsa-web/src/types/screenerAi.ts` | TypeScript 类型定义 |
| `apps/dsa-web/src/hooks/useScreenerChat.ts` | 对话逻辑 hook |

### 5.2 API 客户端

```typescript
// apps/dsa-web/src/api/screenerAi.ts
export const screenerAiApi = {
  async reviewStream(payload: ScreenerAIReviewRequest): Promise<Response> {
    return fetch('/api/v1/stocks/screener/momentum/ai-review/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  async getSessions(profile: string, limit = 10): Promise<ScreenerChatSessionItem[]> {
    const res = await apiClient.get('/api/v1/stocks/screener/momentum/ai-review/sessions', {
      params: { profile, limit },
    });
    return res.data.sessions;
  },

  async getSessionMessages(sessionId: string): Promise<ChatMessage[]> {
    const res = await apiClient.get(`/api/v1/stocks/screener/momentum/ai-review/sessions/${sessionId}`);
    return res.data.messages;
  },
};
```

### 5.3 Zustand Store

```typescript
// apps/dsa-web/src/stores/screenerChatStore.ts
interface ScreenerChatState {
  // 面板状态
  panelOpen: boolean;
  panelTitle: string;
  currentReviewType: string | null;

  // 对话数据
  messages: Message[];
  loading: boolean;
  analysisStages: ProgressStep[];
  sessionId: string;
  contextMeta: ScreenerAIContextMeta | null;
  suggestedQuestions: string[];

  // 最近对话列表
  recentSessions: ScreenerChatSessionItem[];

  // 操作
  openPanel: (title: string, reviewType: string, initData: any) => void;
  closePanel: () => void;
  startStream: (payload: ScreenerAIReviewRequest) => Promise<void>;
  rerunAnalysis: () => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  switchSession: (sessionId: string) => Promise<void>;
  loadRecentSessions: () => Promise<void>;
}
```

### 5.4 组件集成点

在 `MomentumScreenerPage.tsx` 中集成：

```tsx
// 1. 引入面板组件
import { ScreenerChatPanel } from '../components/screener/ScreenerChatPanel';

// 2. 在页面根组件中渲染
function MomentumScreenerPage() {
  // ... 现有逻辑

  return (
    <div className="flex h-full">
      {/* 现有筛选内容 */}
      <div className="flex-1">
        {/* 筛选参数、结果表格等 */}
      </div>

      {/* 新增：对话面板 */}
      <ScreenerChatPanel />
    </div>
  );
}
```

### 5.5 触发集成

V1 触发集成要按优先级区分：

1. **主入口**：候选股点评、二次决策建议
2. **次入口**：盘中信号解读、落选分析

**候选股点评**（详情抽屉内，主入口）：

```tsx
// 在详情抽屉组件中
<button
  onClick={() => {
    openPanel(
      `AI 点评 · ${stock.name} (${stock.tsCode})`,
      'candidate_detail',
      { stockCode: stock.tsCode, screeningData: stock.screeningData }
    );
  }}
>
  🤖 AI 点评
</button>
```

**二次决策建议**（主入口）：

```tsx
<button
  onClick={() => {
    openPanel(
      `AI 综合建议 · 二次决策 (${profile})`,
      'secondary_decision',
      { decisionData }
    );
  }}
>
  🤖 AI 建议
</button>
```

**盘中信号解读**（次入口）：

```tsx
<button
  onClick={() => {
    openPanel(
      `AI 盘中解读 · ${tradeDate}`,
      'intraday',
      { intradayData }
    );
  }}
>
  🤖 AI 盘中解读
</button>
```

**落选分析**（次入口）：

```tsx
<button
  onClick={() => {
    openPanel(
      'AI 综合分析 · 落选说明',
      'excluded',
      { excludedStocks }
    );
  }}
>
  🤖 AI 综合分析
</button>
```

### 5.6 SSE 流式渲染

复用问股页面已有的 SSE 解析逻辑，但前端展示层需要改成“分析阶段 + 信任条”，而不是直接展示详细 thinking：

```typescript
// screenerChatStore.ts 中的 startStream
const response = await screenerAiApi.reviewStream(payload);
const reader = response.body!.getReader();
const decoder = new TextDecoder();
let buf = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buf += decoder.decode(value, { stream: true });
  const lines = buf.split('\n');
  buf = lines.pop() ?? '';

  for (const line of lines) {
    processLine(line);  // 复用 event 解析逻辑，但只渲染 stage/tool/chunk/done
  }
}
```

---

## 6. 数据库变更

### 6.1 无需新建表

直接复用现有 agent chat 会话表：

| 表 | 用途 |
|----|------|
| `chat_sessions` | 会话列表（通过 title 前缀 `[Screener]` 区分来源） |
| `chat_messages` | 消息记录 |

### 6.2 Session ID 生成策略

```python
# 后端生成 session_id 的规则
def generate_screener_session_id(review_type: str, object_id: str, trade_date: str, profile: str) -> str:
    """
    为强势筛选对话生成稳定的 session_id。
    同一只票同一天同一个 profile 的点评共享一个 session。
    """
    key = f"screener_{review_type}_{object_id}_{trade_date}_{profile}"
    return hashlib.md5(key.encode()).hexdigest()[:16]
```

前端首次触发时不传 `session_id`，后端自动生成并返回。后续追问时前端携带该 `session_id`。

产品对 reopen / rerun 的技术要求是：

1. `refresh_mode=resume`
   - 默认行为，读取已有 session，并继续在原会话里追问
2. `refresh_mode=rerun`
   - 用户主动点击“基于最新数据重新分析”时使用
   - 保留同一个逻辑 session，但新增一轮 assistant 响应，并带新的 `context_meta`

这样既能保持会话连续性，也能让用户明确区分“旧分析”和“基于最新数据的新分析”。

---

## 7. 配置与依赖

### 7.1 无需新增配置项

| 配置项 | 来源 |
|--------|------|
| LLM 模型 | 复用 `LLMToolAdapter(config)` |
| API Key | 复用项目现有配置 |
| 温度参数 | 代码中硬编码 0.3 |
| 超时时间 | 代码中硬编码 120s |
| 最大 token | 代码中硬编码 1500 |

### 7.2 依赖检查

- `litellm` — 已有
- `fastapi.responses.StreamingResponse` — 已有
- Agent executor 和工具集 — 已有
- 无需安装新依赖

---

## 8. 错误处理与降级

### 8.1 LLM 调用失败

| 错误类型 | 处理方式 |
|----------|----------|
| Agent 未配置（`is_agent_available()` 返回 false） | 面板顶部显示 InlineAlert：「AI 点评功能需要配置 LLM 模型，请前往系统设置」 |
| LLM API 调用失败 | SSE event 发送 `error` 类型，面板显示「AI 点评暂时不可用：错误信息」 |
| 超时（120s） | SSE event 发送 `error`，面板显示「AI 分析超时，请稍后重试」 |
| 网络异常 | 同超时处理 |
| 外部数据时间过旧 | trust bar 显示「行情/新闻数据可能已过期」，但不阻塞规则结论展示 |

### 8.2 前端降级

- LLM 加载期间显示骨架屏，不阻塞用户操作其他区域
- 面板可以正常关闭，不中断后台 LLM 调用
- 追问输入框在 LLM 生成完成前保持 disabled 状态

---

## 9. 测试策略

### 9.1 后端测试

| 测试 | 类型 |
|------|------|
| Prompt 组装正确性 | 单元测试 — `test_screener_ai_prompt_service.py` |
| API endpoint 参数校验 | 单元测试 — `test_screener_ai_endpoint.py` |
| SSE 流式输出格式 | 集成测试 |
| Session 持久化 | 集成测试 |
| LLM 调用失败降级 | 集成测试（mock LLM 异常） |
| trust bar 元信息正确性 | 集成测试 |
| `resume / rerun` 行为一致性 | 集成测试 |

### 9.2 前端测试

| 测试 | 类型 |
|------|------|
| 面板打开/关闭 | 单元测试 — `ScreenerChatPanel.test.tsx` |
| SSE 事件解析 | 单元测试 — `screenerChatStore.test.ts` |
| 最近对话列表渲染 | 单元测试 |
| 追问消息发送 | 集成测试 |
| 移动端全屏 | E2E 测试 |
| 快捷追问 chips | 单元测试 |
| 信任条渲染 | 单元测试 |

### 9.3 手动验证清单

- [ ] 四个窗口的 AI 点评按钮均可触发
- [ ] 流式输出正常显示（thinking → tool → generating → done）
- [ ] 追问功能正常
- [ ] 最近对话列表正确显示
- [ ] 切换对话正常
- [ ] LLM 调用失败时展示降级提示
- [ ] 移动端全屏弹出正常
- [ ] 关闭面板不中断 LLM 调用
- [ ] 默认 reopen 为 resume，点击“基于最新数据重新分析”才触发 rerun
- [ ] 问股页面不会混入 screener 最近对话

---

## 10. 风险与注意事项

| 风险 | 应对措施 |
|------|----------|
| LLM 输出与规则引擎结论矛盾 | 在 system prompt 中明确要求"基于以下数据给出建议"，不允许凭空判断 |
| 工具调用超时影响体验 | executor 已有超时控制，前端 120s 后展示超时提示 |
| Session 数据量增长 | 7 天自动清理 + 每类型最多 10 个 session |
| 与问股页面会话混淆 | session title 加 `[Screener]` 前缀，且前台列表严格按来源隔离 |
| 多 profile 会话冲突 | session_id 包含 profile，Standard 和 Aggressive 的点评独立 |
| 用户过度相信 AI | trust bar 必显 + 回答结构固定为“规则结论优先” + 盘中边界硬限制 |
| 旧会话与新数据混淆 | `resume / rerun` 分离 + 每轮回答带 `context_meta` |

## 11. V1.3 Decision Intelligence Sync

第四阶段后，实际实现以 `src/services/momentum_screener_ai_commentary_service.py` 为准。AI 点评服务继续作为解释层，不替代规则引擎，但角色从普通点评助手升级为 `Short-term Trading Auditor / Logic Auditor`。

### 11.1 Prompt Contract

系统 Prompt 必须固定要求输出：

- `[Core Logic]`：复述规则层结论，并解释主线、强度、角色与 `Mainline_Intensity`。
- `[Risk Audit]`：列出 `Risk_Stack_Check` 已触发因子，并对每只默认 Top3 执行一次 Devil's Advocate 审计。
- `[Execution Guard]`：落到 V1.3 可交易合同，尤其是 `T+1 Open >= T0 Close * 0.99`；不满足时只能放弃或仅观察。
- `[External Check]`：工具调用只作为外部验证，不能覆盖规则层结论。

### 11.2 Context Injection

`_build_review_context()` 必须注入 `decision_intelligence`：

- `top3_audit[]`：包含每个槽位的 `risk_stack`、触发风险因子、`mainline_intensity`、Devil's Advocate 候选背离项和 `execution_guard`。
- `adaptive_gate`：透出动态总闸门状态，说明是否进入弱市收口。
- `required_output_sections`：给 LLM 明确结构约束，避免生成泛泛摘要。

### 11.3 Test Coverage

`tests/test_momentum_screener_ai_commentary_service.py` 需要覆盖：

- Prompt 中包含 `Risk Stack` / `Mainline Intensity` / Devil's Advocate 要求。
- 规则上下文中能看到 `risk_stack_triggered_factors`。
- `[Risk Audit]` 与 `T+1 Open >= T0 Close * 0.99` 执行守卫不会从 Prompt 中丢失。
