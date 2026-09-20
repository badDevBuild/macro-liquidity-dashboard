---
name: 宏观流动性观测台
description: 面向晨间手机阅读的可信宏观流动性决策支持界面
colors:
  observer-green: "oklch(48% 0.078 166)"
  observer-green-hover: "oklch(42% 0.079 166)"
  observer-wash: "oklch(91% 0.038 166)"
  morning-mist: "oklch(97.4% 0.009 166)"
  paper-surface: "oklch(99.2% 0.004 166)"
  quiet-mint: "oklch(94.8% 0.012 166)"
  structural-mint: "oklch(91.8% 0.017 166)"
  ink: "oklch(25% 0.024 166)"
  ink-soft: "oklch(43% 0.021 166)"
  ink-muted: "oklch(53% 0.018 166)"
  reed-border: "oklch(87% 0.018 166)"
  fed-blue: "oklch(50% 0.075 235)"
  fiscal-amber: "oklch(51% 0.08 75)"
  money-teal: "oklch(49% 0.072 166)"
  transmission-plum: "oklch(51% 0.058 315)"
  supportive-green: "oklch(49% 0.09 155)"
  caution-amber: "oklch(52% 0.105 72)"
  draining-red: "oklch(52% 0.13 28)"
  night-canvas: "oklch(18% 0.012 166)"
  night-surface: "oklch(22% 0.014 166)"
  night-surface-muted: "oklch(25.5% 0.016 166)"
  night-ink: "oklch(92.5% 0.012 166)"
  night-ink-soft: "oklch(78% 0.014 166)"
  night-ink-muted: "oklch(68% 0.014 166)"
  night-border: "oklch(34% 0.016 166)"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, Microsoft YaHei, Segoe UI, system-ui, sans-serif"
    fontSize: "2.25rem"
    fontWeight: 770
    lineHeight: 1
    letterSpacing: "-0.045em"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, Microsoft YaHei, Segoe UI, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 760
    lineHeight: 1.22
    letterSpacing: "-0.025em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, Microsoft YaHei, Segoe UI, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 730
    lineHeight: 1.22
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, Microsoft YaHei, Segoe UI, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, Microsoft YaHei, Segoe UI, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 720
    lineHeight: 1.5
    letterSpacing: "0.09em"
rounded:
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  pill: "999px"
spacing:
  2xs: "0.25rem"
  xs: "0.5rem"
  sm: "0.75rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"
  2xl: "3rem"
  3xl: "4rem"
components:
  button-primary:
    backgroundColor: "{colors.observer-green}"
    textColor: "{colors.paper-surface}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: "0 1rem"
    height: "2.75rem"
  button-primary-hover:
    backgroundColor: "{colors.observer-green-hover}"
    textColor: "{colors.paper-surface}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: "0 1rem"
    height: "2.75rem"
  filter-chip:
    backgroundColor: "{colors.paper-surface}"
    textColor: "{colors.ink-soft}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: "0 1rem"
    height: "2.75rem"
  filter-chip-selected:
    backgroundColor: "{colors.observer-wash}"
    textColor: "{colors.observer-green}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: "0 1rem"
    height: "2.75rem"
  trust-panel:
    backgroundColor: "{colors.paper-surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "1.5rem"
  nav-item-active:
    backgroundColor: "{colors.observer-wash}"
    textColor: "{colors.observer-green}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    height: "3.5rem"
---

# Design System: 宏观流动性观测台

## Overview

**Creative North Star: "晨间观测台"**

这是一个安静、精确、可核验的晨间工作台。视觉顺序始终是先回答环境与主要驱动，再展开公式、观测日期、历史和官方来源。它像一张整理清楚的观测桌，不像交易终端，也不借助行情氛围刺激决策。

系统以移动端单手阅读为起点，桌面端只增加对比空间，不改变叙事顺序。层级主要来自空间、对齐、字号、字重和少量表面差异；动效只解释状态变化。黑底霓虹、紫色渐变、玻璃拟态、金色财富模板和同尺寸卡片墙都被明确排除。

**Key Characteristics:**

- 默认日间模式使用带青绿色倾向的浅色表面；夜间模式使用同色相的深灰表面，不使用纯黑。
- 首屏结论明确，但任何代理都附带公式与证据边界。
- 首屏必须出现真实时间序列；单个最新值不能替代变化趋势。
- 事实、确定性计算、Agent 分析和未知事项严格分层。
- 手机点击目标至少 44×44 CSS 像素，桌面布局不牺牲阅读顺序。
- 正常、降级、阻止分析、缓存与冲突都是正式产品状态。

## Colors

主色像安静的观测仪器，而不是行情信号灯。青绿色只用于交互、选择和焦点；联储、财政、货币市场、市场传导拥有低饱和度分层色，正负语义只用于公式已经确认的支持或抽水贡献。

### Primary

- **深观测绿（observer-green）：** 主要操作、当前导航、链接和图表主线。它必须稀少，不能成为装饰底色。
- **观测洗色（observer-wash）：** 选择态与轻量强调，保持文字对比度和表面安静感。

### Secondary

- **联储蓝（fed-blue）：** 联储资产负债表层级编号与识别。
- **财政琥珀（fiscal-amber）：** 财政现金层级编号与识别。
- **货币市场青（money-teal）：** 货币市场层级编号与识别。
- **传导梅紫（transmission-plum）：** 市场传导层级编号与识别。

### Neutral

- **晨雾（morning-mist）：** 全局画布。
- **纸面（paper-surface）：** 独立、可操作或需要核验的表面。
- **静薄荷（quiet-mint）与结构薄荷（structural-mint）：** 说明区、骨架和轨道。
- **观测墨（ink）及其软化层级：** 正文、次级文字和元数据。
- **芦苇边线（reed-border）：** 分组、表格和页面节奏。

### Day and Night Modes

- 首次访问跟随设备外观；用户手动切换后记住选择。
- 顶部切换按钮是 44×44 像素的标准图标按钮，图标表示将要切换到的模式，并提供完整辅助标签。
- 夜间画布使用 `night-canvas`，可操作表面使用 `night-surface`。层级来自同色相亮度差，不使用纯黑、发光边框或高饱和霓虹。
- 日间与夜间共享相同的信息结构、状态含义和图表线型。所有正文、弱化文字、链接与状态组合都必须达到 WCAG 2.2 AA。
- 切换只过渡背景、文字、边线与环境阴影，时长 180ms；系统要求减少动态效果时取消过渡。

### Named Rules

**The Rare Accent Rule.** 深观测绿只承担操作、选中和焦点，单屏视觉重量不得超过约 10%。

**The Meaning Before Color Rule.** 原始指标上涨或下跌不得自动着绿或着红；只有明确公式中的支持与抽水才使用 supportive-green 与 draining-red，并同时显示符号和文字。

## Typography

**Display Font:** 原生系统无衬线字体栈

**Body Font:** 原生系统无衬线字体栈

**Character:** 中文优先、加载即时、接近原生设备。全界面只使用一个字体家族，通过固定字号、字重、颜色与留白建立层级；所有指标启用等宽数字特性。

### Hierarchy

- **Display**（770，2.25rem，1）：只用于首要代理变化，不能把普通指标放大成英雄数字。
- **Headline**（760，1.75rem，1.22）：页面标题和首屏环境判断。
- **Title**（730，1.25rem，1.22）：主要内容区和分层标题。
- **Body**（400，1rem，1.5）：正文与解释，说明文字最大行长保持在约 65ch。
- **Label**（720，0.75rem，0.09em）：眉题与证据标签；普通中文按钮使用 0.875rem，避免全大写习惯直接套到中文。

### Named Rules

**The Fixed Dashboard Scale Rule.** 看板字号使用固定 rem 层级，不使用随视口流动的标题字号；响应式变化来自结构重排。

**The Tabular Evidence Rule.** 金额、利率、日期、比例和图表坐标必须使用 tabular numbers，确保纵向核验时对齐。

## Elevation

系统默认是平的。深度主要由晨雾画布、纸面表面、静薄荷说明区、细边线和空间节奏建立；阴影只出现在移动端固定导航等必须从内容上抬起的层，不用于普通卡片。

### Shadow Vocabulary

- **固定导航环境影（shadow-sticky）：** 低透明度、大扩散范围，只用于移动底栏，提示它悬浮在滚动内容之上。

### Named Rules

**The Flat-by-Default Rule.** 如果普通面板的阴影一眼可见，阴影就过重；先用背景、边线和留白解决层级。

## Components

### Buttons

- **Shape:** 主要与筛选操作使用胶囊形；图标按钮使用圆形。所有可点击目标最小高度 2.75rem。
- **Primary:** 深观测绿底、纸面文字，用于重试等明确行动。
- **Hover / Focus:** hover 只在精细指针设备出现；键盘焦点使用 0.1875rem 高对比外环和 0.1875rem 间距；active 轻微缩放反馈。
- **Disabled / Loading:** 降低透明度并保留原有尺寸；刷新图标可以旋转，但布局不能跳动。

### Chips

- **Style:** 未选中为纸面底与细边线，选中为观测洗色、深观测绿文字和同色边线。
- **State:** 最小高度 2.75rem，使用 `aria-pressed`；手机允许横向滚动并露出下一项提示可继续浏览。

### Cards / Containers

- **Corner Style:** 说明与图表使用 0.75rem；独立可信度和错误面板使用 1rem。
- **Background:** 只有独立核验区使用纸面，叙事主轴依靠留白和分隔线，不把每块内容包成卡片。
- **Shadow Strategy:** 普通容器无阴影。
- **Border:** 1px 芦苇边线；禁止粗侧边色条。
- **Internal Padding:** 手机 1rem 至 1.5rem，桌面保持相同节奏而不是无止境放大。

### Navigation

手机使用固定底部四入口，兼容安全区；桌面在 64rem 以上转为左侧粘性导航。默认态为柔和墨色，当前项使用观测洗色和深观测绿，并同时设置 `aria-current="page"`。

传导页在内容顶部提供四个页内跳转：联储财政、短端融资、市场定价和加密管道。它们只缩短长页面的阅读路径，不增加第五个全局入口；跳转目标必须保留足够的粘性页眉偏移。

### Disclosure Rows

账本和来源使用原生 `details/summary`。摘要至少 4.75rem 高，右侧显示值或质量状态；展开后直接出现定义、历史、日期与来源，不使用模态框。焦点、展开箭头和空历史说明必须完整。

### Trend Charts

总览主图使用单根观测绿折线，手机阅读顺序固定为“结论 → 真实趋势 → 组成证据”，默认显示 1 年周度数据，并可切换 3 个月、5 年和全部历史。图表必须显示起止日期、最高与最低刻度、最新点和不同窗口的精确变化；不用面积填充、渐变、平滑曲线或双 Y 轴。

四条交叉检查线使用同一根色系的微型折线，但原始涨跌保持中性色文字。指标详情默认显示 1 年历史，并把 1 周、1 月、3 月、1 年变化直接列在图表之前。

### Status Pills

状态胶囊同时包含圆点和文字。绿色代表通过，琥珀代表降级或过期，红色代表阻止分析、不可用或来源冲突；不能只靠颜色传递状态。

“本次数据能否使用”和“连续运行是否达到 14 天稳定性门槛”是两个独立状态：前者只描述当前一轮，后者显示观察进度。一次更新成功不能用绿色状态替代长期稳定性结论。

## Do's and Don'ts

### Do:

- **Do** 让首屏先回答环境、方向和主要驱动，并在一次操作内到达公式、观测日期和来源。
- **Do** 把缺失、缓存、过期、冲突和离线作为正式状态；null 永远显示为“不可用”，不显示为 0。
- **Do** 只在支持或抽水含义已由公式确定时使用绿红语义，原始涨跌保持中性。
- **Do** 使用 4pt 间距系统、至少 1rem 正文和至少 44×44 CSS 像素的手机触控目标。
- **Do** 在 390px、768px 和 1024px 以上分别验证结构，不把桌面简单缩小成手机。

### Don't:

- **Don't** 做黑底霓虹、紫色渐变和发光边框式的加密行情页面。
- **Don't** 做海军蓝加金色的传统财富管理模板。
- **Don't** 做由大量同尺寸指标卡片组成的通用 SaaS 看板，也不要在卡片内继续嵌套卡片。
- **Don't** 使用玻璃拟态、渐变文字或装饰性动效制造“高级感”。
- **Don't** 把单一流动性代理包装成确定的买卖信号。
- **Don't** 隐藏数据缺失、观测日期差异、缓存和来源冲突。
- **Don't** 使用粗侧边色条、明显阴影、模态框优先交互或颜色作为唯一状态信号。
