# Markdown 组件测试指南

## 概述

本文档详细描述了前端 Markdown 组件的测试策略，基于具体功能场景提供测试逻辑，避免直接测试 CSS 文件内容。测试覆盖预处理函数、组件渲染、特殊场景处理和用户体验。

---

## 测试范围

### 核心功能模块
1. **预处理函数测试** - 文本清理和格式转换
2. **组件渲染测试** - 各种 Markdown 元素显示
3. **平台特定处理** - LeetCode/Codeforces/NowCoder 差异化处理
4. **用户体验测试** - 交互功能和无障碍访问

### 测试原则
- ❌ 不直接测试 CSS 属性值
- ✅ 测试视觉层次和结构语义
- ✅ 验证用户交互行为
- ✅ 确认跨平台一致性

---

## 预处理函数测试场景

### 1. 零宽字符清理 (`stripZeroWidthChars`)

#### 场景：NowCoder 内容去重处理
**测试逻辑**：
- 输入包含 U+200B 零宽字符的混合内容
- 验证处理后零宽字符完全移除
- 确认中文内容完整保留

**测试用例**：
```typescript
it("移除 NowCoder 零宽字符但保留中文", () => {
  const input = "a_i\n​\n和\nb_i\n​\n是两个碎片";
  const output = stripZeroWidthChars(input);
  expect(output).not.toContain("​");
  expect(output).toContain("和");
  expect(output).toContain("是两个碎片");
});
```

#### 场景：混合 Unicode 字符处理
**测试逻辑**：
- 验证 Unicode 数学符号正确保留
- 确认零宽字符不影响符号显示

### 2. MathJax 去重 (`dedupMathJax`)

#### 场景：数学符号三重重复去重
**测试逻辑**：
- 模拟 Codeforces/NowCoder 的数学符号重复模式
- 验证只保留最佳格式版本
- 确认代码块内容不被误处理

**测试用例**：
```typescript
it("正确去重数学符号但保留代码块", () => {
  const input = [
    "text",
    "p_i",
    "p_i", 
    "p_i",
    "```",
    "5",
    "2 2",
    "```",
    "more text"
  ].join("\n");
  
  const output = dedupMathJax(input);
  expect(output.split("\n").filter(line => line.trim() === "p_i").length).toBe(1);
  expect((output.match(/```/g) || []).length).toBe(2);
});
```

#### 场景：多行样本数据保护
**测试逻辑**：
- 测试实际 OJ 题目的样本输入输出数据
- 验证短行数字内容不被压缩
- 确认代码围栏完整性

### 3. 章节预处理 (`preprocessSections`)

#### 场景：中文标签转换
**测试逻辑**：
- 验证所有标准中文标签正确转换
- 确认转换后的格式正确
- 测试多章节连续转换

**测试用例**：
```typescript
it("批量转换标准中文标签", () => {
  const input = "[描述]\n内容\n[输入]\ndata\n[输出]\nresult";
  const output = preprocessSections(input);
  expect(output).toContain("## 题目描述");
  expect(output).toContain("## 输入格式");
  expect(output).toContain("## 输出格式");
});
```

### 4. 平台特定预处理

#### 场景：LeetCode 格式化
**测试逻辑**：
- 验证示例标题转换为三级标题
- 确认输入输出标签加粗显示
- 测试中英文标签同时处理

**测试重点**：
- "示例 1：" → "### 示例 1："
- "输入：" → "**输入：**"
- "Input:" → "**Input:**"

#### 场景：Codeforces 特殊处理
**测试逻辑**：
- 验证段落边界恢复（空行插入）
- 确认数学符号包装（$...$）
- 测试显示数学隔离（$$...$$ 独立行）

#### 场景：NowCoder 特殊处理
**测试逻辑**：
- 验证 Setext 标题防护（转义等号/横线）
- 确认 LaTeX 命令转换（\le → ≤）
- 测试零宽字符完全清理

---

## 组件渲染测试场景

### 1. 标题层级和图标

#### 场景：二级标题图标显示
**测试逻辑**：
- 验证不同类型标题显示对应图标
- 确认图标与文字的对齐和间距
- 测试无匹配标题时的默认显示

**测试用例**：
```typescript
it("描述标题显示描述图标", () => {
  const { container } = render(
    <Markdown content="## 描述\n这是题目描述" />
  );
  const heading = container.querySelector("h5");
  expect(heading?.textContent).toContain("描述");
  // 验证图标存在（通过文本包含图标Unicode字符）
});
```

#### 场景：三级标题图标显示
**测试逻辑**：
- 验证三级标题正确显示图标
- 确认层级缩进关系正确

### 2. 段落处理

#### 场景：脚注段落识别
**测试逻辑**：
- 验证 Codeforces 脚注正确识别
- 确认脚注显示为小字号
- 测试多个脚注的独立显示

**测试重点**：
- 脚注标记 `∗`/`†` → `data-footnote="true"`
- 字体大小为 `caption`
- 每个脚注为独立段落

#### 场景：普通段落恢复
**测试逻辑**：
- 验证粘连段落正确分割
- 确认分割后的段落语义完整

### 3. 代码处理

#### 场景：代码块复制功能
**测试逻辑**：
- 模拟用户点击复制按钮
- 验证复制成功状态显示
- 确认复制内容准确性

**测试用例**：
```typescript
it("代码块复制功能", async () => {
  const { container } = render(
    <Markdown content="```\nconsole.log('hello');\n```" />
  );
  
  const copyButton = container.querySelector("button");
  expect(copyButton).toBeInTheDocument();
  
  // 模拟复制操作
  await user.click(copyButton);
  
  // 验证复制成功状态
  const successIcon = container.querySelector(".MuiIcon-success");
  expect(successIcon).toBeInTheDocument();
});
```

#### 场景：内联代码样式
**测试逻辑**：
- 验证内联代码与块级代码的视觉区分
- 确认语法高亮类名正确传递
- 测试无语言标识的代码块处理

### 4. 数学公式渲染

#### 场景：行内数学公式
**测试逻辑**：
- 验证 $...$ 格式正确渲染
- 确认与周围文本的正确间距
- 测试复杂公式渲染完整性

#### 场景：显示数学公式
**测试逻辑**：
- 验证 $$...$$ 独立行显示
- 确认居中对齐效果
- 测试多公式并列显示

### 5. 表格处理

#### 场景：响应式表格
**测试逻辑**：
- 验证表格在小屏幕上正确滚动
- 确认表头样式应用正确
- 测试表格内容换行处理

### 6. 链接处理

#### 场景：外部链接
**测试逻辑**：
- 验证链接在新标签页打开
- 确认 rel="noopener noreferrer" 属性
- 测试长链接换行处理

---

## 平台特定测试场景

### 1. Codeforces 特殊处理

#### 场景：脚注分离处理
**测试逻辑**：
- 模拟真实的 CF 内容格式
- 验证脚注正确分离到独立段落
- 确认主体文本不受影响

**测试用例**：
```typescript
it("CF 脚注正确分离", () => {
  const cfContent = "that are ideal.$^{\\ast}lcm$ — least common multiple.";
  const { container } = render(
    <Markdown content={cfContent} sourcePlatform="codeforces" />
  );
  
  const footnotes = container.querySelectorAll('[data-footnote="true"]');
  expect(footnotes.length).toBe(1);
  expect(footnotes[0].tagName).toBe("P"); // 确认为块级元素
});
```

#### 场景：段落恢复
**测试逻辑**：
- 验证粘连段落正确分割
- 确认分割点准确（句号+大写字母）
- 测试代码块内内容不受影响

### 2. NowCoder 特殊处理

#### 场景：Setext 标题防护
**测试逻辑**：
- 验证等号线被正确转义
- 确认不会意外创建一级标题
- 测试转义后的正常显示

**测试重点**：
- `"=\n"` → `"\\="`
- 避免生成 `<h1>` 标签

### 3. LeetCode 特殊处理

#### 场景：示例格式化
**测试逻辑**：
- 验证中英文示例标题转换
- 确认输入输出标签加粗
- 测试约束条件转换

---

## 边界条件和错误处理

### 1. 空内容处理

#### 场景：空输入显示
**测试逻辑**：
- 验证空内容显示占位符
- 确认占位符样式正确
- 测试 undefined/null 处理

### 2. 格式错误处理

#### 场景：不完整 Markdown
**测试逻辑**：
- 测试不闭合的代码块
- 验证不匹配的标题标记
- 确认错误不会导致渲染崩溃

#### 场景：特殊字符处理
**测试逻辑**：
- 测试 Unicode 字符正确显示
- 验证 HTML 转义字符
- 确认零宽字符正确清理

---

## 用户体验测试

### 1. 复制功能测试

#### 场景：代码块复制
**测试逻辑**：
- 模拟用户点击复制按钮
- 验证复制成功反馈
- 确认复制内容准确性

#### 场景：复制状态管理
**测试逻辑**：
- 验证复制状态自动重置
- 确认重复点击的正确处理
- 测试多代码块复制互不影响

### 2. 无障碍访问测试

#### 场景：键盘导航
**测试逻辑**：
- 验证复制按钮可通过 Tab 聚焦
- 确认按钮有正确的 ARIA 标签
- 测试键盘操作反馈

#### 场景：屏幕阅读器
**测试逻辑**：
- 验证标题层级语义正确
- 确认代码块有适当的描述
- 测试数学公式的可访问性

### 3. 响应式设计测试

#### 场景：移动端显示
**测试逻辑**：
- 验证小屏幕下的内容布局
- 确认表格正确滚动
- 测试代码块换行处理

---

## 性能测试

### 1. 大文件处理

#### 场景：长题目内容
**测试逻辑**：
- 测试 10KB+ 内容的渲染性能
- 验证预处理器处理速度
- 确认内存使用合理

### 2. 实时更新

#### 场景：内容动态更新
**测试逻辑**：
- 验证内容更新时的重新渲染
- 确认更新过程平滑无卡顿
- 测试频繁更新的性能表现

---

## 集成测试场景

### 1. 完整题目渲染

#### 场景：完整 OJ 题目
**测试逻辑**：
- 使用真实 OJ 题目数据端到端测试
- 验证所有元素正确显示
- 确认平台特定处理生效

**测试用例**：
```typescript
it("完整 Codeforces 题目渲染", () => {
  const cfProblem = getRealCFProblemData(); // 真实 CF 题目数据
  const { container } = render(
    <Markdown content={cfProblem} sourcePlatform="codeforces" />
  );
  
  // 验证所有关键元素存在
  expect(container.querySelector("h5")).toBeInTheDocument(); // 标题
  expect(container.querySelector("pre")).toBeInTheDocument(); // 代码块
  expect(container.querySelector(".katex")).toBeInTheDocument(); // 数学公式
  expect(container.querySelector("blockquote")).toBeInTheDocument(); // 引用
});
```

### 2. 跨平台一致性

#### 场景：相同内容不同平台
**测试逻辑**：
- 验证相同内容在不同平台的一致性
- 确认平台特定差异正确应用
- 测试平台切换的平滑过渡

---

## 测试数据建议

### 1. 测试数据集

#### 真实题目数据
- Codeforces 2236F2 "GCD Groups"
- LeetCode "Two Sum"
- NowCoder 算法题目

#### 边界情况数据
- 包含特殊字符的内容
- 超长行内容
- 混合语言内容
- 不完整 Markdown

### 2. 测试工具配置

#### 测试框架
- Vitest + React Testing Library
- MSW 用于 API 模拟
- Jest 无头浏览器测试

#### 持续集成
- 自动化测试套件
- 性能监控
- 回归测试