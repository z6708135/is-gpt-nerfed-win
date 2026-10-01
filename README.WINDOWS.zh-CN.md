# Windows 移植：默认只做本地被动检查

本移植基于 **kiyoakii** 的 [is-gpt-nerfed](https://github.com/kiyoakii/is-gpt-nerfed)，固定上游提交为 [`ff0d7c0c8fdc8713273b6570b1ada1838eaad84c`](https://github.com/kiyoakii/is-gpt-nerfed/tree/ff0d7c0c8fdc8713273b6570b1ada1838eaad84c)，Windows 版本为 `0.5.3-windows.2`。上游作者、MIT 许可及 ModelTrace 归属均保留；修改范围和英文说明见 [WINDOWS-PORT.md](docs/WINDOWS-PORT.md)。这不是上游作者发布的官方 Windows 版本。

`0.5.3-windows.2` 为已审阅的 Windows hook 调度命令添加安全编码，并抑制 PowerShell 首次加载模块时的进度输出；调度操作和权限保持不变。可读源码及确定性生成器位于 [tools/build_windows_hooks.py](tools/build_windows_hooks.py)。修改源码不会更新已安装的 `0.5.3-windows.1` 或其受信任 hook 哈希。隔离离线模拟检查不能证明 hook 已在真实 Codex 会话中自然触发。

这里只移植原生 Windows CLI、本地 hooks、安装和卸载流程。上游 [中文 README](https://github.com/kiyoakii/is-gpt-nerfed/blob/ff0d7c0c8fdc8713273b6570b1ada1838eaad84c/README.zh-CN.md) 中的 macOS 菜单栏 App、通知和安装脚本没有移植。

默认检查**当前明确指定的本地 Codex 会话**中的模型、推理强度、服务优先级和上下文窗口元数据变化。默认不发起模型请求，不读取 `auth.json`，不自动发现其他会话，不运行后台探测，不查询更新，也不记录工具命令正文。

## 当前验证状态

本分支 20 项隔离测试已通过：18 项 Windows 回归和 2 项计算一致性检查。五种 hook 命令经过真实外层 Windows PowerShell 5.1 和 pwsh，以合成会话数据完成测试。被动扫描器也成功读取一次明确指定的真实本地会话，没有启动模型推理或指纹探针。

在已审阅的本地安装中，五个更新定义均已启用并受信任。这是安装元数据，不等于自然执行证据；CLI 与桌面生命周期的原生自动调度尚未观察到，仍待验证，桌面会话的编排模式也未确定。其他安装需要自行审阅并信任定义。本地项目目录或后端版本不能单独证明桌面支持 hooks。

## 运行边界与版本

开发时使用了原生 Windows `codex-cli 0.159.2`，其 Authenticode 状态为 `Valid`，签名者为 `OpenAI OpCo, LLC`。这不保证其他 CLI 版本具有相同插件、hooks 或 rollout 格式。需要 Python 3 和原生 `codex.exe`；Python 的实际版本请以所选解释器的 `--version` 为准，不能根据安装目录名推断。

OpenAI 的 [Hooks 文档](https://learn.chatgpt.com/docs/hooks) 说明 hooks 支持 `commandWindows`，非托管 hooks 需要审核并信任当前内容哈希。安装插件不会自动授予 hook 信任；代码变化后应重新审核。

本地 Codex 和 dot 云端对话具有不同执行环境。[Plugins 文档](https://learn.chatgpt.com/docs/plugins) 明确说明云端编排的 ChatGPT Work 不支持插件 hooks；网页安装也不会把这些脚本部署到执行电脑。即使 dot 可以把某项工作委派给本机，也不能据此声称本插件监测 dot 云端模型。Synced Work 的管理员 MCP hooks 是另一套机制。

## 默认保护与修改

| 配置 | Windows 默认值 | 行为 |
| --- | --- | --- |
| `frequency` / `fresh_frequency` | `manual` / `manual` | 不定期发起探测 |
| `mode` | `nudge` | 提示已记录的元数据变化 |
| `active_probes` | `false` | CLI 和 app-server 拒绝主动创建会话、fork 和模型回合 |
| `background_probes` / `auto_retries` | `false` / `false` | 不安排后台探测和自动重试 |
| `account_metadata` | `false` | 在读取凭据文件前返回未知账号 |
| `discover_sessions` | `false` | 不扫描近期或其他会话 |
| `record_tool_commands` | `false` | 工具记录使用 `[command omitted]` |
| `check_updates` | `false` | 不发起更新检查；macOS 更新安装入口在 Windows 上拒绝执行 |
| `passive` | `true` | Stop 时检查当前经过验证的本地 rollout |
| `notify` / `sound` / `halt_on_mismatch` | `false` | 不使用 macOS 通知或声音，不默认打断工作 |

Windows 锁使用 `msvcrt`，进程存活检查使用 `OpenProcess` 查询，替代不适用于 Windows 的 `fcntl` 和 `os.kill(pid, 0)`。后者在 Windows 上可能终止目标进程，参见 Python 的 [os.kill 文档](https://docs.python.org/3/library/os.html#os.kill)。子进程使用原生可执行文件，不通过 shell，不弹出控制台窗口；保留 `CODEX_SANDBOX*` 环境限制。

Windows hook 只有在以下条件全部满足时才检查 rollout：路径解析后位于所配置的 `CODEX_HOME\sessions` 中，扩展名为 `.jsonl`，文件名包含完整会话 ID，首条 `session_meta.payload.id` 与 hook 会话 ID 相同。缺失或非法 ID、路径不符或头部不匹配时跳过，不猜测父会话或扫描其他会话。这可能降低对新格式的覆盖率；应针对格式变化修补，而非放宽会话范围。

统计指纹的 MATCH 增加了置信度、样本数和候选差距要求，但仍然只是统计归类。MATCH、模型名称和无变化记录都不是服务端模型身份、权重或路由未变的证明。

## 审查、离线验证与安装

先审查所选提交与 Windows 补丁，再执行已获授权的阶段。不要运行上游 `install.sh`、`install-app.sh`、`uninstall.sh`，也不要把远程脚本直接管道给 shell。Windows 安装不需要这些脚本、WSL、Git Bash、管理员权限、修改 PATH 或持久登录授权。

以下示例使用环境变量和本机程序发现，不包含某台电脑的用户目录。若 Codex 安装在其他位置，请将 `$nerfedCodexExe` 改为已核实的原生可执行文件绝对路径。

```powershell
$nerfedCodexDir = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$nerfedCodexExe = Join-Path $nerfedCodexDir '.sandbox-bin\codex.exe'
$nerfedPythonExe = (Get-Command python.exe -CommandType Application -ErrorAction Stop).Source
```

从 checkout 根目录执行专用离线测试：

```powershell
& $nerfedPythonExe -I -B -m unittest discover -s tests -p test_windows.py -v
```

测试使用临时 `CODEX_HOME` / `NERFED_HOME`、固定合成 UUID 和受控 Python 子进程 fixture；检查凭据读取、网络和非预期子进程没有发生。它不需要真实会话或账号。不要通过整个仓库的测试发现误运行其他可能包含主动逻辑的检查。测试通过只能证明被测路径，不能证明服务端模型身份或所有自然 hook 事件都触发。

检查安装预览；确认具体安装目标后执行安装：

```powershell
.\install-windows.ps1 -CodexPath $nerfedCodexExe -PythonPath $nerfedPythonExe -CodexHome $nerfedCodexDir -WhatIf
.\install-windows.ps1 -CodexPath $nerfedCodexExe -PythonPath $nerfedPythonExe -CodexHome $nerfedCodexDir
```

安装器检查 Codex 的有效 OpenAI Authenticode 签名，拒绝 `.cmd` / `.bat` 包装器、已有同名安装和目标路径上的重解析点；复制已审查源码，备份现有 Codex 配置，再注册独立 marketplace 与插件。它不自动信任 hooks、不启动后台守护进程，也不运行主动检测。

只有在用户已批准运行这些具体被动 hooks 后，才在本地 Codex 的 `/hooks` 中审核并信任当前定义。重新启动本地客户端以确认加载。验证时使用专用验收会话或合成输入，区分「已信任」「合成 hook 调用成功」和「客户端自然事件触发」；每类证据只能支持对应结论。不要用历史会话、`doctor --fork`、主动指纹检测或新的模型请求替代被动安装验收。

如果 CLI 在临时目录遇到沙箱权限错误，应确认拒绝的具体路径和操作；不要因此修改全局 HOME、放宽整个用户目录的 ACL 或关闭 Windows 沙箱。参见 [Windows sandbox 文档](https://learn.chatgpt.com/docs/windows/windows-sandbox)。

## 安装位置、权限与隐私

独立 marketplace 为 `is-gpt-nerfed-windows`，插件 ID 为 `is-gpt-nerfed@is-gpt-nerfed-windows`。默认 Codex home 为 `%USERPROFILE%\.codex`，可由 `CODEX_HOME` 或显式 `-CodexHome` 选择。

```text
<CodexHome>\is-gpt-nerfed\
  config.json                         被动默认配置
  windows-install-state.json          安装阶段、绝对路径与备份记录
  windows-backups\                    安装前 config.toml 的字节副本
  windows-marketplace\
    .agents\plugins\marketplace.json  独立本地 marketplace
    plugin\                          已审查的插件源码
    bin\nerfed.ps1                   本地 CLI 包装器
    uninstall-windows.ps1             管理式卸载入口
  sessions\、events.jsonl、log.jsonl 等本地证据
```

Codex 另行维护插件缓存。安装生成的 `windows-runtime.json` 将 Python、Codex home 和证据目录绑定到本机绝对路径；wrapper 和 hook 使用这些值，并恢复原环境。运行时文件、配置备份、日志和会话证据属于本机私有数据，不应提交到公开仓库。

安装会写入所选用户目录，通过已安装 Codex 注册和移除这一独立 marketplace/plugin，并由 Codex 修改该用户配置。被动 hooks 需要读取当前明确匹配的 rollout 和模型缓存，写入自己的证据目录。它不申请新的账号登录、持久网络连接或管理员权限。

`account_metadata=false` 阻止插件直接读取 `auth.json`；这属于程序保护，不能撤销该进程原本拥有的文件系统权限。被动使用时保持该配置关闭。已安装 Codex 自身可能按正常方式使用登录状态，插件不复制凭据。

本地证据仍可能包含会话 ID、工作目录、rollout 路径、时间、模型名称、服务优先级、prompt 长度和工具名称；默认省略工具命令正文。扫描当前 rollout 会读取其中的内容。`hide_titles` 只影响显示，不能把存储内容匿名化。目录沿用本机 ACL；分享日志前应审查并脱敏。

## 上游主动功能的风险

固定上游原件默认 `30m/auto/queries=3`，使用已有账号的 Codex app-server fork 临时会话并发起真实模型回合。副本可能接触源会话历史，不能将「临时」解释成没有上下文、服务端状态或额度消耗。

「3 个回答」不是请求上限。原件每题可重试，超时可补题，副本创建也可重试；按源码可得保守上界为 **12 次模型回合启动**，开启 `confirm_uncertain` 时可达 **18 次**，不包含 Codex 内部重试。周期性重复运行没有全局每日额度上限。Windows 默认关闭主动、后台和自动重试，所以被动安装不运行这些回合。

上游账号标记会读取整个 `auth.json`，解析 JWT 中的账号、邮箱和计划，必要时对 API key 哈希，并写入截断哈希与账号元数据。截断哈希可以关联记录，不等于匿名；邮箱域和计划也可能识别组织。本移植默认在该读取入口前返回。

上游 MATCH 仅比较排名第一的候选与预期模型，原件可能在低置信度或少量回答时显示匹配。本移植加强阈值仍不能将有限指纹库中的统计相似度变成身份认证。

上游主动 probe 的「不使用工具」提示和拒绝审批不能单独保证工具绝不运行。新增主动入口保护和请求限制没有经过真实主动请求验收；主动功能需要针对会话副本、上下文暴露、工具权限和额度的新明确批准。批准安装或被动 hooks 不授权主动探测、账号读取或更新。不能用其他模型、dot 云端回合或 subagent 冒充当前本地模型检测。

## 卸载与回滚

先预览同一安装目标，再执行管理式卸载：

```powershell
$nerfedUninstall = Join-Path $nerfedCodexDir 'is-gpt-nerfed\windows-marketplace\uninstall-windows.ps1'
& $nerfedUninstall -CodexHome $nerfedCodexDir -WhatIf
& $nerfedUninstall -CodexHome $nerfedCodexDir
```

卸载核对安装记录、固定目标路径和当前 marketplace 注册，移除这一独立插件与 marketplace，并在自己的状态目录内归档安装文件与记录。保持原样的被动配置也会归档；用户修改过的配置、ledger 和安装前备份保留，不递归删除整个用户目录。若操作中途失败，保留记录并核对实际注册状态后继续；重新启动 Codex 以卸载已加载的 hooks。

安装前 `config.toml` 字节备份供人工审核恢复。如果用户随后修改了其他配置，不应直接用旧备份覆盖当前文件；应只合并撤销本次注册的必要差异。删除保留的证据、备份或归档需要明确选择目标。不要使用上游 macOS 卸载脚本或清空 marketplace 目录来卸载此 Windows 安装。

## 验证结论的范围

公开验证说明见 [WINDOWS-PORT.md](docs/WINDOWS-PORT.md)。离线测试、安装/卸载和合成 hook 验证分别覆盖自己的路径，不能相互替代。实际自然 hook 生命周期、CLI 格式与版本变化应由对应客户端的验收结果证明；没有观察到的事件应写为未验证。

主动 fork、模型请求、账号追踪、跨会话发现和更新功能不在被动验收范围。无论本地安装是否成功，都不能据此认定 dot 云端对话加载了本地插件 hooks。
