# §7 React 前端详细设计

> 版本: v1.0 | 日期: 2026-06-13 | 状态: 已批准
> 基于: `2026-06-13-acm-agent-design.md` §7 细化

---

## 1. 设计决策总览

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 设计语言 | Material Design 3 | 规范统一，组件丰富 |
| 组件库 | MUI 5 | MD3 风格，TypeScript 支持好 |
| 路由 | React Router v6 | 标准方案 |
| 状态管理 | Context + useReducer + 自定义 hooks | 轻量，适合中等规模 |
| HTTP 客户端 | axios + JWT 拦截器 | 拦截器处理 token 刷新 |
| 图表 | Recharts | 轻量，React 原生，配色跟随主题 |
| 代码分割 | React.lazy + Suspense | 按页面懒加载 |

---

## 2. 目录结构

```
frontend/src/
├── main.tsx
├── App.tsx
├── theme.ts                    # MD3 主题配置
├── routes.tsx                  # 路由配置
├── pages/
│   ├── Login.tsx
│   ├── Register.tsx
│   ├── Dashboard.tsx
│   ├── Problems.tsx
│   ├── ProblemDetail.tsx
│   ├── Records.tsx
│   ├── Profile.tsx
│   ├── Training.tsx
│   ├── TrainingRecommend.tsx
│   ├── Matching.tsx
│   ├── Teams.tsx
│   ├── TeamDetail.tsx
│   ├── Ranking.tsx
│   ├── Settings.tsx
│   └── admin/
│       ├── UserManagement.tsx
│       ├── UserDetail.tsx
│       ├── CrawlerManagement.tsx
│       └── BotConfig.tsx
├── components/
│   ├── layout/
│   │   ├── AppLayout.tsx       # 主布局（侧边栏 + 顶栏 + 内容区）
│   │   ├── Sidebar.tsx
│   │   └── TopBar.tsx
│   ├── common/
│   │   ├── DataTable.tsx       # 通用数据表格（分页+排序+筛选）
│   │   ├── SearchInput.tsx
│   │   ├── FilterPanel.tsx
│   │   ├── TagBadge.tsx        # 算法标签徽章
│   │   ├── DifficultyBadge.tsx # 难度徽章（颜色编码）
│   │   ├── VerdictBadge.tsx    # 判定结果徽章
│   │   ├── LoadingSpinner.tsx
│   │   ├── EmptyState.tsx
│   │   └── ConfirmDialog.tsx
│   ├── charts/
│   │   ├── SkillRadar.tsx      # 技能雷达图
│   │   ├── DailyTrend.tsx      # 每日趋势折线图
│   │   ├── DifficultyPie.tsx   # 难度分布饼图
│   │   ├── TagBar.tsx          # 标签柱状图
│   │   └── Heatmap.tsx         # 提交热力图
│   └── business/
│       ├── ProblemCard.tsx
│       ├── ProblemDetail.tsx
│       ├── CodeViewer.tsx
│       ├── ProfileOverview.tsx
│       ├── TrainingWeekView.tsx
│       ├── TeamCard.tsx
│       ├── MatchRecommendation.tsx
│       └── RankingTable.tsx
├── hooks/
│   ├── useAuth.ts              # 认证状态管理
│   ├── useApi.ts               # API 调用封装
│   ├── usePagination.ts        # 分页逻辑
│   └── useDebounce.ts          # 搜索防抖
├── services/
│   ├── api.ts                  # axios 实例 + 拦截器
│   ├── auth.ts                 # 登录/注册/刷新
│   ├── users.ts
│   ├── problems.ts
│   ├── records.ts
│   ├── profiles.ts
│   ├── training.ts
│   ├── matching.ts
│   ├── teams.ts
│   └── admin.ts
└── types/
    ├── user.ts
    ├── problem.ts
    ├── record.ts
    ├── profile.ts
    ├── training.ts
    └── team.ts
```

---

## 3. 主题配置

```typescript
// theme.ts
import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  palette: {
    primary: { main: '#1E40AF' },        // 信任蓝
    secondary: { main: '#3B82F6' },       // 亮蓝
    warning: { main: '#F59E0B' },         // 琥珀
    success: { main: '#10B981' },         // 翡翠绿 (AC)
    error: { main: '#EF4444' },           // 警示红 (WA)
    background: { default: '#F8FAFC' },   // 石板 50
    text: { primary: '#1E3A8A', secondary: '#475569' },
  },
  typography: {
    fontFamily: '"Fira Sans", "Noto Sans SC", sans-serif',
    h1: { fontWeight: 700 },
    h2: { fontWeight: 600 },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: { code: { fontFamily: '"Fira Code", monospace' } },
    },
  },
});
```

---

## 4. 路由与权限

```typescript
// routes.tsx
const routes = [
  { path: '/login', element: <Login />, public: true },
  { path: '/register', element: <Register />, public: true },
  { path: '/dashboard', element: <Dashboard /> },
  { path: '/problems', element: <Problems /> },
  { path: '/problems/:id', element: <ProblemDetail /> },
  { path: '/records', element: <Records /> },
  { path: '/profile/:userId', element: <Profile /> },
  { path: '/training', element: <Training /> },
  { path: '/training/recommend', element: <TrainingRecommend /> },
  { path: '/matching', element: <Matching /> },
  { path: '/teams', element: <Teams /> },
  { path: '/teams/:id', element: <TeamDetail /> },
  { path: '/ranking', element: <Ranking /> },
  { path: '/settings', element: <Settings /> },
  // Admin 路由
  { path: '/admin/users', element: <UserManagement />, roles: ['admin'] },
  { path: '/admin/users/:id', element: <UserDetail />, roles: ['admin'] },
  { path: '/admin/crawler', element: <CrawlerManagement />, roles: ['admin'] },
  { path: '/admin/bot', element: <BotConfig />, roles: ['admin'] },
];
```

---

## 5. 核心页面设计

### 5.1 Dashboard（仪表盘）

```
┌─────────────────────────────────────────────────┐
│  仪表盘                                          │
├──────────┬──────────┬──────────┬────────────────┤
│  今日 AC  │ 本周 AC  │ 连续天数 │  团队排名      │
│    12     │    45    │    7     │    #3          │
├──────────┴──────────┴──────────┴────────────────┤
│  ┌─────────────────┐  ┌─────────────────────┐  │
│  │  每日提交趋势     │  │  技能雷达图          │  │
│  │  (折线图, 30天)   │  │  (SkillRadar)       │  │
│  └─────────────────┘  └─────────────────────┘  │
├─────────────────────────────────────────────────┤
│  最近 AC 记录                                     │
│  ┌───────────────────────────────────────────┐  │
│  │ P1001 A+B Problem    洛谷   入门   2min前  │  │
│  │ P1002 过河卒         洛谷   普及   1h前    │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

**数据源**: `GET /api/records/stats/summary` + `GET /api/profiles/:userId`

### 5.2 Problems（题库浏览）

```
┌─────────────────────────────────────────────────┐
│  题库                              [语义搜索 🔍]  │
├──────────┬──────────────────────────────────────┤
│ 筛选面板  │  题目列表                              │
│          │                                       │
│ 平台:    │  ┌─────────────────────────────────┐ │
│ □ 洛谷   │  │ P1001  A+B Problem  入门  模拟   │ │
│ □ 力扣   │  │ P1002  过河卒       普及  DP     │ │
│ □ CF     │  │ P1003  栈          普及  栈      │ │
│          │  └─────────────────────────────────┘ │
│ 难度:    │                                       │
│ [1──10]  │  分页: < 1 2 3 ... 50 >              │
│          │                                       │
│ 标签:    │                                       │
│ [搜索..] │                                       │
└──────────┴──────────────────────────────────────┘
```

**功能**: 筛选（平台/难度/标签）+ 语义搜索 + 列表展示 + 分页

### 5.3 Profile（用户画像）

```
┌─────────────────────────────────────────────────┐
│  用户画像 - 张三                                  │
├─────────────────────────────────────────────────┤
│  ┌──────────────┐  综合评分: 0.72                │
│  │  技能雷达图    │  难度天花板: 7.2 (中级)        │
│  │  (SkillRadar) │  解题效率: 0.65               │
│  │               │  学习风格: 均衡型              │
│  │               │  趋势: 📈 进步中              │
│  └──────────────┘                               │
├─────────────────────────────────────────────────┤
│  💪 强项                          🎯 待提升       │
│  ├─ DP (0.85)                    ├─ 图论 (0.35) │
│  ├─ 二叉树 (0.80)                ├─ 字符串 (0.40)│
│  └─ 贪心 (0.75)                  └─ 数论 (0.42) │
├─────────────────────────────────────────────────┤
│  📝 AI 总结                                      │
│  该同学整体处于中级水平，擅长 DP 和二叉树算法，     │
│  但在图论和字符串方面需要加强...                    │
├─────────────────────────────────────────────────┤
│  难度分布 (饼图)    │  标签分布 (柱状图)           │
└─────────────────────────────────────────────────┘
```

### 5.4 Training（训练计划）

```
┌─────────────────────────────────────────────────┐
│  训练计划               [生成新计划] [快速推荐]     │
├─────────────────────────────────────────────────┤
│  阶段: 专题突破期  │  目标: 图论, 字符串            │
│  进度: 15/35 题   │  难度曲线: ─────╱────╲──     │
├─────────────────────────────────────────────────┤
│  ┌─── Day 1 (周一) ──────────────────────────┐  │
│  │ 🔴 CF1234 图论基础   [推荐理由: 补基础]     │  │
│  │ 🟡 LC200  岛屿数量   [推荐理由: DFS模板]    │  │
│  │ 🟢 P1002  过河卒     [复习]                 │  │
│  │ 🟡 CF5678 最短路     [推荐理由: Dijkstra]   │  │
│  │ 🔴 LC743  网络延迟   [推荐理由: 综合]       │  │
│  └───────────────────────────────────────────┘  │
│  ┌─── Day 2 (周二) ──────────────────────────┐  │
│  │ ...                                        │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 5.5 Matching（队友匹配）

```
┌─────────────────────────────────────────────────┐
│  队友匹配推荐                                     │
├─────────────────────────────────────────────────┤
│  为 张三 推荐的最佳队友组合:                        │
│                                                   │
│  ┌─── 推荐 #1 (综合分: 0.85) ───────────────┐   │
│  │  👤 李四 (兼容性: 0.82)                    │   │
│  │     强项: 图论, 字符串  风格: 精研型         │   │
│  │  👤 王五 (兼容性: 0.78)                    │   │
│  │     强项: 数据结构, 数学  风格: 题海型       │   │
│  │  [创建队伍]                                 │   │
│  └───────────────────────────────────────────┘   │
│  ┌─── 推荐 #2 (综合分: 0.79) ───────────────┐   │
│  │  ...                                       │   │
│  └───────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

---

## 6. API 服务层

```typescript
// services/api.ts
import axios from 'axios';

const api = axios.create({ baseURL: '/api' });

// JWT 拦截器
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Token 刷新拦截器
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const refresh_token = localStorage.getItem('refresh_token');
      if (refresh_token) {
        const { data } = await axios.post('/api/auth/refresh', { refresh_token });
        localStorage.setItem('access_token', data.access_token);
        error.config.headers.Authorization = `Bearer ${data.access_token}`;
        return api(error.config);
      }
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
```

---

## 7. 响应式布局

```typescript
// components/layout/AppLayout.tsx
function AppLayout({ children }) {
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  return (
    <Box sx={{ display: 'flex' }}>
      {isMobile ? <NavigationBar /> : <Sidebar />}
      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <TopBar />
        {children}
      </Box>
    </Box>
  );
}
```

| 断点 | 导航方式 | 列数 |
|------|---------|------|
| < 600px | 底部 NavigationBar | 4 |
| 600-839px | NavigationRail | 8 |
| ≥ 840px | NavigationDrawer | 12 |

---

## 8. 关键组件接口

### 8.1 DataTable

```typescript
interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  data: T[];
  loading: boolean;
  pagination: { page: number; limit: number; total: number };
  onPageChange: (page: number) => void;
  onSort?: (field: string, order: 'asc' | 'desc') => void;
  onFilter?: (filters: Record<string, any>) => void;
  onRowClick?: (row: T) => void;
}
```

### 8.2 SkillRadar

```typescript
interface SkillRadarProps {
  data: { tag: string; score: number }[];
  maxValue?: number;  // 默认 1
  size?: number;      // 默认 300
  color?: string;     // 默认 primary.main
}
```

### 8.3 DifficultyBadge

```typescript
interface DifficultyBadgeProps {
  difficulty: number;  // 1~10
  variant?: 'chip' | 'dot' | 'text';
}
// 颜色映射: 1-3 绿色, 4-5 黄色, 6-7 橙色, 8-10 红色
```
