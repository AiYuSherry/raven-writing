# 项目蒸馏参考流程

当用户要求把 GitHub 仓库、本地项目、工具库、框架、应用或 DevOps 项目蒸馏成 skill 时读取本文件。

## 1. 输入判断

支持两类输入：

- GitHub URL：先运行 `scripts/analyze-repo.sh <url> /tmp/skill-gen-<repo-name>`。
- 本地目录：直接读取项目根目录下的 README、配置文件、文档、示例和入口文件。

不要只看 README 就生成完整 skill。README 是起点，配置和源码入口用于核实命令真实性。

## 2. 项目画像

至少确认：

- 项目名、仓库地址、主要语言、许可证、stars、homepage。
- README 文件和 docs/examples 是否存在。
- 安装方式：pip、npm、go install、cargo、docker、二进制下载或源码构建。
- 核心入口：CLI 命令、库 API、HTTP 服务、插件、脚手架、workflow。
- 必需依赖：语言运行时、系统工具、API key、外部服务。

若 `project-profile.json` 存在，以它为结构化索引，但仍要用 README/docs/source 交叉验证。

## 3. 类型适配

### CLI

`SKILL.md` 重点：

- 最常用命令和参数组合。
- 输入/输出格式。
- 批量处理、下载、转换、检查等高频场景。

`guides/` 重点：

- 安装和版本检查。
- 从零完成一个真实任务。
- 常见参数组合。

### Library

`SKILL.md` 重点：

- API 核心对象、函数和调用顺序。
- 初始化、错误处理、返回值。
- 版本兼容和类型要求。

`guides/` 重点：

- 集成到现有项目。
- 最小可运行示例。
- 常见模式和反模式。

### Framework

`SKILL.md` 重点：

- 架构概念、扩展点、插件模型。
- 项目创建、配置、生命周期。

`guides/` 重点：

- 脚手架搭建。
- 插件/中间件配置。
- 开发、测试、构建流程。

### Web app

`SKILL.md` 重点：

- 本地开发、环境变量、端口、数据库或外部服务。
- 部署流程和运行健康检查。

`guides/` 重点：

- clone 后跑起来。
- 配置 `.env`。
- 常见启动失败和构建失败处理。

### DevOps

`SKILL.md` 重点：

- 支持平台、前置条件、配置文件、执行顺序。
- 安全边界、回滚和幂等性。

`guides/` 重点：

- 环境准备。
- dry-run/plan/validate。
- 部署和回滚。

## 4. 生成内容

项目 skill 默认结构：

```text
[repo-name]-skill/
├── SKILL.md
├── guides/
│   ├── 01-installation.md
│   ├── 02-quickstart.md
│   └── 03-advanced-usage.md    # 复杂项目才需要
└── troubleshooting.md
```

`SKILL.md` 必须包含：

- frontmatter：`name` 和 `description`。
- 技能概述：这个 skill 帮谁完成什么。
- 使用流程：4-6 步，偏执行而非介绍。
- 关键导航：指向 guides 和 troubleshooting。
- AI 助手能力：6-8 条可执行能力。
- 快速示例：3-5 个真实命令或代码片段。
- 安装要求和项目链接。

Guide 必须包含：

- 适用场景。
- 执行步骤。
- 命令或代码。
- 预期结果。
- 完成确认检查清单。
- 下一步。

Troubleshooting 至少包含：

- 安装问题。
- 使用问题。
- 环境或网络问题。

每个问题写清症状、常见原因、排查步骤和修复方式。

## 5. 事实核查

生成后必须检查：

- 命令是否真实存在。
- 参数是否来自 README、docs、help 输出或源码。
- 环境变量是否真实被项目读取。
- 示例输出是否不是臆造。
- 项目核心功能是否覆盖。
- 类型侧重点是否匹配项目画像。

找不到证据时，删除该命令或标成“需要用户确认”，不要伪造。

## 6. 质量门

用以下规则自评，满分 100：

- 10 分：`SKILL.md` 有 frontmatter，且含 `name` 和 `description`。
- 20 分：有概述、用法、示例三类段落。
- 20 分：`guides/` 有内容，核心 guide 足够完整。
- 20 分：`troubleshooting.md` 至少 3 条，极简项目至少 2 条。
- 15 分：代码块没有 `<placeholder>`、`<repo>`、`<your-xxx>` 之类占位符。
- 15 分：正文没有 `TBD`、`TODO`、`待补充`、独立 `xxx`。

低于 70 分必须修复后再交付；修复最多两轮。仍低于 70 分时，说明原因和剩余风险。

可用脚本：

```bash
bash scripts/validate-project-skill.sh /path/to/generated-skill
```

脚本偏结构检查，不能替代事实核查。
