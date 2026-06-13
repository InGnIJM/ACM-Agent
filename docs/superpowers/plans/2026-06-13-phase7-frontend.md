# Phase 7: React 前端 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans

**Goal:** 实现完整 React SPA（17 页面 + 布局 + 图表 + 图表组件），90% 测试覆盖率通过后进入 Phase 8

**Architecture:** Vite + React 18 + TypeScript + MUI 5 (MD3) + React Router v6 + Recharts + Vitest + React Testing Library

**Tech Stack:** React 18, TypeScript, Vite 5, MUI 5, Recharts, React Router v6, axios, Vitest, @testing-library/react

---

## 文件结构

```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── theme.ts              # MD3 主题（Analytics Blue）
│   ├── routes.tsx
│   ├── services/
│   │   ├── api.ts            # axios + JWT 拦截器
│   │   ├── auth.ts, users.ts, problems.ts, records.ts, profiles.ts, training.ts, matching.ts, teams.ts, admin.ts
│   ├── hooks/
│   │   ├── useAuth.ts, useApi.ts, usePagination.ts, useDebounce.ts
│   ├── components/
│   │   ├── layout/ (AppLayout, Sidebar, TopBar)
│   │   ├── common/ (DataTable, SearchInput, FilterPanel, TagBadge, DifficultyBadge, VerdictBadge, LoadingSpinner, EmptyState, ConfirmDialog)
│   │   ├── charts/ (SkillRadar, DailyTrend, DifficultyPie, TagBar, Heatmap)
│   │   └── business/ (ProblemCard, ProfileOverview, TrainingWeekView, TeamCard, MatchRecommendation, RankingTable)
│   ├── pages/ (Login, Register, Dashboard, Problems, ProblemDetail, Records, Profile, Training, TrainingRecommend, Matching, Teams, TeamDetail, Ranking, Settings)
│   │   └── admin/ (UserManagement, UserDetail, CrawlerManagement, BotConfig)
│   └── types/ (user.ts, problem.ts, record.ts, profile.ts, training.ts, team.ts)
├── test/
│   ├── setup.ts
│   ├── components/ (DataTable.test.tsx, TagBadge.test.tsx, SkillRadar.test.tsx, ...)
│   └── pages/ (Login.test.tsx, Dashboard.test.tsx, ...)
```

---

## Task 1: Project Setup + Theme + API Service

**Files:** Create `frontend/`

- [ ] **Step 1: 初始化**

```bash
cd E:/code/ACM-Agent
npm create vite@latest frontend -- --template react-ts
cd frontend
npm i @mui/material @emotion/react @emotion/styled @mui/icons-material
npm i react-router-dom axios recharts
npm i -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

- [ ] **Step 2: 配置 vite.config.ts**

```typescript
// frontend/vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:3000' } },
  test: { globals: true, environment: 'jsdom', setupFiles: './test/setup.ts' },
});
```

- [ ] **Step 3: 写测试 — Theme 渲染**

```typescript
// frontend/test/components/Theme.test.tsx
import { render, screen } from '@testing-library/react';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { theme } from '../../src/theme';

function TestComponent() {
  return <ThemeProvider theme={theme}><CssBaseline /><button>test</button></ThemeProvider>;
}

describe('Theme', () => {
  it('should use primary color', () => {
    render(<TestComponent />);
    const button = screen.getByText('test');
    expect(button).toBeInTheDocument();
  });

  it('should have correct primary main', () => {
    expect(theme.palette.primary.main).toBe('#1E40AF');
  });

  it('should have correct font family', () => {
    expect(theme.typography.fontFamily).toContain('Fira Sans');
  });
});
```

- [ ] **Step 4: 实现 theme.ts + api.ts**

```typescript
// frontend/src/theme.ts
import { createTheme } from '@mui/material/styles';
export const theme = createTheme({
  palette: {
    primary: { main: '#1E40AF' }, secondary: { main: '#3B82F6' },
    warning: { main: '#F59E0B' }, success: { main: '#10B981' }, error: { main: '#EF4444' },
    background: { default: '#F8FAFC' },
    text: { primary: '#1E3A8A', secondary: '#475569' },
  },
  typography: { fontFamily: '"Fira Sans", "Noto Sans SC", sans-serif', h1: { fontWeight: 700 }, h2: { fontWeight: 600 } },
});
```

```typescript
// frontend/src/services/api.ts
import axios from 'axios';
const api = axios.create({ baseURL: '/api' });
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
api.interceptors.response.use((r) => r, async (error) => {
  if (error.response?.status === 401) {
    const refresh = localStorage.getItem('refresh_token');
    if (refresh) {
      const { data } = await axios.post('/api/auth/refresh', { refresh_token: refresh });
      localStorage.setItem('access_token', data.access_token);
      error.config.headers.Authorization = `Bearer ${data.access_token}`;
      return api(error.config);
    }
    window.location.href = '/login';
  }
  return Promise.reject(error);
});
export default api;
```

- [ ] **Step 5: 运行测试**

```bash
cd frontend && npx vitest run
# 预期: Theme test PASS
git add frontend/
git commit -m "feat(frontend): scaffold project with MUI theme and API service"
```

---

## Task 2: Layout + Common Components

- [ ] **Step 1: 写测试 — DataTable, TagBadge, DifficultyBadge, LoadingSpinner, EmptyState**

```typescript
// frontend/test/components/common.test.tsx
import { render, screen } from '@testing-library/react';
import { TagBadge } from '../../src/components/common/TagBadge';
import { DifficultyBadge } from '../../src/components/common/DifficultyBadge';
import { LoadingSpinner } from '../../src/components/common/LoadingSpinner';
import { EmptyState } from '../../src/components/common/EmptyState';
import { ThemeProvider } from '@mui/material';
import { theme } from '../../src/theme';

const wrap = (ui: React.ReactNode) => <ThemeProvider theme={theme}>{ui}</ThemeProvider>;

describe('TagBadge', () => {
  it('renders tag text', () => { render(wrap(<TagBadge label="dp" />)); expect(screen.getByText('dp')).toBeInTheDocument(); });
  it('uses MUI Chip', () => { render(wrap(<TagBadge label="graph" />)); expect(screen.getByText('graph').closest('.MuiChip-root')).toBeInTheDocument(); });
});

describe('DifficultyBadge', () => {
  it('renders difficulty 5 as correct number', () => {
    render(wrap(<DifficultyBadge difficulty={5} />));
    expect(screen.getByText('5').closest('.MuiChip-root')).toBeInTheDocument();
  });
  it('renders difficulty 7 as string', () => {
    render(wrap(<DifficultyBadge difficulty={7} variant="text" />));
    expect(screen.getByText('7')).toBeInTheDocument();
  });
});

describe('LoadingSpinner', () => {
  it('renders CircularProgress', () => { render(wrap(<LoadingSpinner />)); expect(document.querySelector('.MuiCircularProgress-root')).toBeInTheDocument(); });
});

describe('EmptyState', () => {
  it('renders message and icon', () => {
    render(wrap(<EmptyState message="暂无数据" />));
    expect(screen.getByText('暂无数据')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 实现 Common Components**（TagBadge/MuiChip, DifficultyBadge 颜色映射 1-10, DataTable/MuiTable, SearchInput, FilterPanel, VerifyBadge, ConfirmDialog）
- [ ] **Step 3: 实现 Layout**（AppLayout + Sidebar 导航 + TopBar + 响应式断点）
- [ ] **Step 4: 运行测试**

```bash
npx vitest run
git commit -m "feat(frontend): add layout and common components"
```

---

## Task 3: Chart Components

- [ ] **Step 1: 写测试 — SkillRadar**

```typescript
// frontend/test/components/charts.test.tsx
import { render } from '@testing-library/react';
import { SkillRadar } from '../../src/components/charts/SkillRadar';

const radarData = [{ tag: 'dp', score: 0.8 }, { tag: 'graph', score: 0.4 }];

describe('SkillRadar', () => {
  it('renders without crash', () => {
    const { container } = render(<SkillRadar data={radarData} />);
    expect(container.querySelector('.recharts-wrapper')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 实现 SkillRadar, DailyTrend, DifficultyPie, TagBar, Heatmap**（全用 Recharts）
- [ ] **Step 3: 运行测试**

```bash
npx vitest run
git commit -m "feat(frontend): add chart components (Radar, Trend, Pie, Bar, Heatmap)"
```

---

## Task 4: Pages (17 pages)

- [ ] **Step 1: 实现 Login + Register + Dashboard**
- [ ] **Step 2: 实现 Problems + ProblemDetail + Records**
- [ ] **Step 3: 实现 Profile + Training + TrainingRecommend**
- [ ] **Step 4: 实现 Matching + Teams + TeamDetail + Ranking + Settings**
- [ ] **Step 5: 实现 Admin 页面** (UserManagement, UserDetail, CrawlerManagement, BotConfig)
- [ ] **Step 6: React.lazy 代码分割**

```typescript
// frontend/src/routes.tsx
import { lazy, Suspense } from 'react';
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Problems = lazy(() => import('./pages/Problems'));
// ... 全部 17 页面

export const routes = [
  { path: '/login', element: <Login />, public: true },
  { path: '/dashboard', element: <Dashboard /> },
  // ...
];
```

- [ ] **Step 7: 运行全部测试 + 覆盖率**

```bash
npx vitest run --coverage
# 预期: 全部 PASS + ≥ 90%
git commit -m "feat(frontend): add all 17 pages with lazy loading"
```

---

## Phase 7 Gate

| 检查项 | 标准 |
|--------|------|
| 主题 | MD3 颜色 + Fira 字体 |
| JWT 拦截器 | 自动刷新 token |
| 布局 | 响应式 NavigationDrawer/NavigationBar |
| DataTable | 分页 + 排序 + 行点击 |
| 图表 | SkillRadar/DailyTrend/DifficultyPie/TagBar/Heatmap |
| 17 页面 | 全部可渲染 |
| 代码分割 | React.lazy |
| 覆盖率 | ≥ 90% |
