# geekbench-local-lens

让 Geekbench **完全跑在自己机器上**：本地测试、本地出结果、不依赖厂商的结果浏览器。

[English](README.md) · [实现原理](docs/how-it-works.md) · [跨平台](docs/platforms.md) · [踩坑记录](docs/pitfalls.md) · [Agent 用法](docs/agent-usage.md)

---

## 为什么需要它

Geekbench 7 免费版有两个特性，让"本地测试"这件事变得别扭：

1. 必须联网，且**自动上传**结果到 Geekbench Browser（`--no-upload` 是 Pro 专属）。
2. **结果窗口本身就是那个网页**——分数表由服务器渲染，客户端本地不渲染。

所以"把上传掐掉"的结果是：跑分正常，然后弹一句
*Unable to display benchmark results*。

本项目反过来做：让上传"成功"，但目标是 `127.0.0.1`。客户端满意，数据不出本机，
结果在本地渲染成网页。

```
Geekbench 7（补丁副本）
   │  POST http://127.0.0.1:8080/   multipart: document + hash
   ▼
gblens serve  ──►  results/<id>.json            原始上传
                ──►  results/<id>.document.json  抽出的结果
                ──►  results/<id>.html           本地渲染页
```

## 安装

```bash
git clone https://github.com/<you>/geekbench-local-lens.git
cd geekbench-local-lens
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
gblens doctor          # 环境自检；加 --json 给机器读
```

依赖：macOS、Python ≥ 3.9、Xcode 命令行工具（`codesign`、`PlistBuddy`）。无第三方库。

## 三步跑起来

```bash
# 1. 起本地端点
gblens serve --results ./results --http-port 8080 --open

# 2. 克隆并打补丁（生成 ~/Applications/Geekbench 7 Local.app）
gblens patch \
  --app "/Applications/Geekbench 7.app" \
  --out "$HOME/Applications/Geekbench 7 Local.app"

# 3. 打开副本，点 Run CPU Benchmark
open "$HOME/Applications/Geekbench 7 Local.app"
```

跑完 `results/<时间戳>.html` 会自动弹出，所有东西都在自己磁盘上。

不打补丁也能用渲染器：`gblens view` 支持 `.gb6` / `.gb7` / `.json`，
包括你从 Geekbench Browser 另存的结果文件。

```bash
gblens view ~/Downloads/result.gb7 --open
```

## 补丁到底改了什么

| 改动 | 位置 | 作用 |
| --- | --- | --- |
| `browser.geekbench.com` → `127.0.0.1:8080` | 主二进制字符串表 | 上传打本机 |
| `b.ne` → `b` | URL 构造处，`movk #0x3a73`（`https://` 里的 `s:`）之前 | 强制走 `http://` 分支，不需要信任自签证书 |
| `SUFeedURL` 置无效、关闭自动更新 | `Contents/Info.plist` | 副本不会自己更新回原版 |
| ad-hoc 重签（`--options linker-signed`） | 整个 bundle | 改了代码段后必须重签 |

补丁做在**副本**上，`/Applications` 里的原件一个字节都不动。

## CLI

```
gblens serve   --results DIR [--http-port 8080] [--https-port 8443 --cert C --key K] [--open]
gblens view    FILE [--html OUT] [--open]
gblens patch   [--app APP] [--out DIR] [--host 127.0.0.1:8080] [--keep-https]
gblens info    [--app APP]
gblens doctor  [--app APP] [--results DIR] [--http-port 8080]
```

所有子命令都接受 `--json`，只输出一个 JSON 文档。
退出码：`0` 成功、`1` 校验失败、`2` 版本结构不支持。

## 给 agent 用

设计上就是给 agent 无人值守调用的：

```bash
gblens --json doctor                       # 环境事实
gblens --json patch --out /tmp/gb.app      # {"ok":true,"host_hits":2,...}
gblens --json view results/x.gb7           # {"single":{...},"multi":{...}}
gblens serve --results ./results --json    # 打印 {"listening":...} 后常驻
```

调用顺序、需要断言的不变量、哪些失败该重试、哪些该上报，见 [AGENTS.md](AGENTS.md)。

## 已知限制

- **客户端自己的结果窗口仍然打不开**（`Unable to display benchmark results`）。
  假端点返回了一个超集 JSON，但客户端校验的字段还没定位。此时上传已经落盘，
  以本地 HTML 为准。
- CLI 的 `--no-upload` / `--json` / `--save` 是 Pro 开关，本项目不破解授权。
- HTTPS 模式需要**客户端信任**的 CA。新版 macOS 上非图形会话里的
  `security add-trusted-cert` 会被静默拒绝，走 Keychain GUI，或者直接用 HTTP 分支。
- scheme 补丁依赖当前版本（7.1.0）的指令序列。新版本上 `gblens patch` 会明确失败
  （exit 2），而不是产出一个坏二进制。

各种「不上传」路线的完整对比（黑洞、代理、Hook、响应格式逆向、Pro）见 [docs/approaches.md](docs/approaches.md)。

## 跨平台

**Unix 优先**：macOS 已端到端验证；Linux 的 CLI 版本预期无需改代码即可适用
（同样的字节模式，且不需要代码签名）。Windows 欢迎作为社区贡献——渲染器和服务端
本来就能跑，缺的只是补丁验证。

分层是刻意的，让移植工作足够小：`render.py` 与 `server.py` 是纯 Python；
`patch.py` 做字节级操作，格式无关（Mach-O / ELF / PE）；唯一与系统相关的是签名
（macOS 用 `codesign`，其他平台空操作）。

- `gblens scan <binary>` 先判断一个构建能不能打补丁，再动手
- 状态矩阵见 [docs/platforms.md](docs/platforms.md)
- 想用 agent 加一个平台：看 [docs/extending.md](docs/extending.md) 和
  [docs/agent-extension-prompt.md](docs/agent-extension-prompt.md)

## 开发

```bash
python3 -m pytest tests/ -q
python3 -m gblens.cli view examples/results/sample-macbook-air-m5.gb7.json
```

目录：

```
gblens/render.py    容错的结果渲染器（终端 + HTML）
gblens/server.py    本地上传端点（HTTP，可选 HTTPS）
gblens/patch.py     host/scheme 补丁与重签
gblens/cli.py       参数、JSON 输出、退出码
docs/               原理、坑、agent 配方
```

欢迎贡献：新的结果结构（Geekbench 5/6/7、AI、Compute）、Windows/Linux 的补丁实现。

## 致谢

本项目在 **DeepSeek Harness** 中完成，使用 **DeepSeek Purge** 插件。整个过程由
agent 实际操作机器：跑分、读 `log show`、打补丁、验证每一步，而不是停留在
"你可以试试"。详见 [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md)。

## 声明

只在你拥有或获授权测试的机器上使用。补丁修改的是商业软件的本地副本，用于本地互操作；
不重新分发软件本体，不绕过授权，不解除 Pro 功能。

MIT License。
