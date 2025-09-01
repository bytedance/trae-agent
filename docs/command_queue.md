# 命令队列功能使用指南

本文档介绍如何使用 Trae Agent 的命令队列功能，实现命令的缓存和顺序执行。

## 功能概述

命令队列功能允许您：
- 将多个命令添加到队列中，按顺序执行
- 在命令执行过程中继续添加新命令（实时入队）
- 持久化存储命令，避免命令丢失（默认存储于用户主目录）
- 查看队列状态与最近命令列表
- 取消待执行的命令
- 清理已完成/已取消/已失败的命令
- 手动启动队列处理器

## 基本使用

### 1) 添加命令到队列

使用 `--queue` 或 `-q` 选项将命令添加到队列：

```bash
# 添加第一个命令到队列
trae-cli run "Add tests for utils module" --working-dir /path/to/project --queue

# 继续添加更多命令
trae-cli run "Fix linting issues" --working-dir /path/to/project --queue
trae-cli run "Update documentation" --working-dir /path/to/project --queue
```

要点：
- 必须提供任务文本或通过 `--file` 指定任务文件（二选一）。
- 建议总是显式设置 `--working-dir` 为绝对路径。
- 支持与普通运行相同的全部参数（例如 `--provider`、`--model`、`--config-file`、`--must-patch`、`--trajectory-file`、`--patch-path`、`--console-type`、`--agent-type` 等）。这些选项会被一并持久化，执行时原样生效。

### 2) 查看队列状态

```bash
# 查看当前队列状态（命令：queue-status 或 queue_status 均可）
trae-cli queue-status
```

输出包含：
- 总计/待执行/执行中/已完成/失败 的数量
- 处理器是否在运行中
- 当前执行中的命令 ID（如有）
- 最近 10 条命令的简要信息（ID、状态、任务摘要、工作目录、创建时间）

### 3) 启动队列处理器

正常情况下，当您第一次以 `--queue` 入队且当前没有处理器在运行时，会自动启动处理器并开始执行。
如需手动启动或已停止时再次启动，可执行：

```bash
trae-cli process-queue
```

### 4) 取消待执行的命令

仅支持取消状态为“待执行”的命令：

```bash
trae-cli cancel-command <command_id>
```

取消后，该命令状态会标记为“已取消”，不会被处理器执行。

### 5) 清理已完成的命令

清理状态为“已完成/已取消/已失败”的命令，保留仍待执行的命令：

```bash
trae-cli clear-completed
```

## 可用命令与参数速览

- 入队执行（核心）：
  - `trae-cli run <TASK> [通用参数] --queue`
  - `trae-cli run --file <TASK_FILE> [通用参数] --queue`

- 队列管理：
  - 查看状态：`trae-cli queue-status`（或 `queue_status`）
  - 取消命令：`trae-cli cancel-command <command_id>`（或 `cancel_command`）
  - 清理完成：`trae-cli clear-completed`（或 `clear_completed`）
  - 手动处理：`trae-cli process-queue`（或 `process_queue`）

- 通用参数（与普通运行一致，均可随命令持久化）：
  - `--working-dir, -w` 绝对路径工作目录
  - `--provider, -p` 模型提供方
  - `--model, -m` 模型名称
  - `--model-base-url` 模型 API 基础地址
  - `--api-key, -k` API Key（也可通过环境变量）
  - `--max-steps` 最大执行步数
  - `--must-patch, -mp` 是否必须生成补丁
  - `--patch-path, -pp` 补丁输出路径
  - `--config-file` 配置文件路径（支持 .yaml/.yml；若不存在将回退到同名 .json）
  - `--trajectory-file, -t` 轨迹文件路径
  - `--console-type, -ct` 控制台类型：`simple`/`rich`
  - `--agent-type, -at` 代理类型：`trae_agent`

提示：命令名与选项使用短横线形式（如 `queue-status`、`clear-completed`、`process-queue`）更符合 CLI 习惯，亦兼容下划线形式。

## 执行原理（简述）

- 每条入队命令会被保存为一条记录，包含：任务、工作目录、原始 CLI 选项等。
- 队列处理器逐条取出“待执行”的命令，切换到命令的工作目录，按记录的选项创建并运行 Agent。
- 执行完成即标记“已完成”；发生异常则标记“失败”，并记录错误信息；取消则标记“已取消”。
- 处理器一次只处理一条命令，按入队顺序依次执行，期间可持续入队新命令。

## 持久化与文件位置

- 队列文件默认位于：用户主目录下的 `.trae_queue.json`。
- 应用启动时会自动加载该文件；若上次退出时存在“执行中”的命令，会重置为“待执行”，以避免中断后卡死。
- 注意：入队的选项会被原样写入该文件（包括可能的敏感信息如 `--api-key`）。请妥善保护本机文件权限，避免泄露。

## 最佳实践

- 总是使用绝对路径作为 `--working-dir`。
- 在处理器运行中入队不会打断当前执行，新增命令会排在后面顺序处理。
- 队列长期使用后建议定期执行 `clear-completed` 进行清理，保持文件体积可控。
- 若队列存在“待执行”但 `queue-status` 显示处理器未运行，可手动执行 `process-queue`。

## 常见问题（FAQ）

- 队列未自动启动怎么办？
  - 执行 `trae-cli process-queue` 手动启动。查看 `queue-status` 的“处理器运行中”标记，确认是否在运行。

- 能否同时执行多条命令？
  - 当前处理器以单实例串行方式工作，保证顺序与安全性。并行不在默认支持范围内。

- 取消命令无效？
  - 仅“待执行”状态可取消；对“执行中”命令不可强行终止。

- Windows 使用注意？
  - 请确保 `--working-dir` 使用绝对路径。若路径含空格，请加引号。

如需更多 CLI 功能，请参考 `trae-cli --help` 与普通运行模式文档。
