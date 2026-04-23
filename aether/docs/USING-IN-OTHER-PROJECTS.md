# 把 Aether 装到其他项目 · 真实部署指南

> 你想在另一个 Cursor 项目(比如 OpenClaw / 工作仓库 / 任何 workspace)
> 启用 Aether 的 PROTOCOL 0 + 5-mode + reflex arc · 这是 step-by-step 指南。
>
> **30 秒读完 · 1 分钟装好 · 1 分钟测完**。
>
> **Day 8 末更新**:`install --global --apply` 顺手装 `aether` shell wrapper
> 到 PATH · **装好后任何终端任何目录都可直接 `aether daily` / `aether tasks add`** ·
> 不需要 cd 到 aether 目录或打长路径。

---

## 🎯 一句话决策树

| 场景 | 用哪个 |
|---|---|
| 想所有项目都自动用 Aether(推荐) | `--global` |
| 只让某一个项目用 | `<target>` (项目级 shared) |
| 把 Aether 打包发给陌生人 | `<target> --copy` |

---

## 0 · 你需要什么

- Cursor 已装(任意版本 · ≥ 3.x)
- Python 3.9+ 可用(确认:`python --version`)
- 当前 aether workspace 在原位(全局/shared 模式依赖它的绝对路径)
- (可选)一个具体项目路径(比如 `D:/OpenClaw/some-project`)

---

## 1 · 三种 scope · 选一个

### 🌍 全局(`--global`)· **Owner 推荐**

```powershell
python aether/bin/aether_install.py --global --apply
```

- ✅ **一次装好 · 任何项目自动用**(写 `~/.cursor/hooks.json`)
- ✅ **数据自动隔离**:hook 触发时按 `workspace_roots` 决定数据目录 · OpenClaw 的对话写到 `OpenClaw/.aether/` · 写小说项目的对话写到 `小说/.aether/`
- ✅ 中央 aether 改了 · 所有项目立即生效(共享代码)
- ❌ 移动/删除中央 aether/ → 全部 Cursor 会话 hook 报错(但 fail-open · 不阻塞)

### 📦 项目级(默认 · `<target>`)

```powershell
python aether/bin/aether_install.py "D:/path/to/project" --apply
```

- ✅ 1 KB 文件足迹(只装那个项目的 `.cursor/hooks.json`)
- ✅ 单项目精准控制 · 不影响其他项目
- ❌ N 个项目要装 N 次

### 📨 项目级 + 完整拷贝(`--copy`)· **分发给陌生人用**

```powershell
python aether/bin/aether_install.py "D:/path/to/project" --copy --apply
```

- ✅ target 完全自包含(94 文件 · 5 MB · 含 bin/ + 公开 fields)
- ✅ 不依赖你的 aether 路径 · 可被 git push 给别人
- ❌ 中央 aether 升级时 · 每个 target 要重装

**Owner 你当前测试场景 = `--global`**(装一次 · 所有项目用 · 数据自动隔离)
**Day 15 Pro launch 给陌生人 = `--copy`**

---

## 2 · 装

### 🌍 全局(推荐)

```powershell
# dry-run 看会做什么
python aether/bin/aether_install.py --global

# 真装
python aether/bin/aether_install.py --global --apply
```

输出像这样:

```
⟁ aether_install · GLOBAL mode · ~/.cursor/

  装到用户级别 · 所有 Cursor 会话 · 任何项目都会触发 Aether hooks
  数据按项目自动隔离 · 项目 A 的对话不污染项目 B

  · would create C:\Users\33116\.cursor\hooks.json (shared mode · ...)
  · would write .aether-install.json

applying...
  ✓ wrote ~/.cursor/hooks.json
  ✓ wrote .aether-install.json

next steps · 真实测试:
  1. 完全关闭 Cursor (File → Exit · 重新加载 ~/.cursor/hooks.json)
  2. 重新打开 Cursor · 任意打开一个之前没装过 Aether 的项目
  3. 新建 chat · 输入 "你好"
  4. AI 第一行应贴 "⟁ Aether · Day N/30 · ..." 状态行
  5. 看那个项目根 · 应出现 .aether/events.jsonl(数据隔离的证据)
```

### 📦 项目级 shared

```powershell
python aether/bin/aether_install.py "D:/path/to/project" --apply
```

### 📨 项目级 copy

```powershell
python aether/bin/aether_install.py "D:/path/to/project" --copy --apply
```

会拷 ~94 个文件(bin/* + 9 个公开 fields + 文档 + 模板),约 5 MB。

**Privacy 保证**(适用于 copy 模式):
- 你 Owner 的私有数据(coll/mirror/handover/registry/critique/persona)永远**不会**被 copy 模式拷过去
- 详见 `aether/bin/aether_install.py` 的 `COPY_INCLUDE` 白名单

---

## 3 · 真实测试(关键这 4 步)

1. **关闭 Cursor**(确保 hooks.json 重新加载)
2. **重启 Cursor** · 用它打开目标项目目录
3. **新建一个 chat** · 输入随便什么(`你好` / `hi` / `?`)
4. **AI 第一行**应该贴这一行:

   ```
   ⟁ Aether · Day N/30 · 100/100 (28 ok · 0 warn · 0 fail) · handover: day-N-handover.md
   ```

如果出了 → install 成功 · Aether 在那个项目里全功能工作。

如果没出 → 见 §5 排错。

---

## 4 · 看状态 / 卸载

### 看是否已装

```powershell
# 全局
python aether/bin/aether_install.py --global --check

# 项目级
python aether/bin/aether_install.py "D:/path/to/target/project" --check
```

输出:

```
⟁ aether_install · check · D:\path\to\target\project

  ✓ Aether installed · mode=shared
     installed_at: 2026-04-19T12:03:13.273837+00:00
     central aether: C:\Users\33116\OneDrive\桌面\制作skills的skiils
     hooks.json present · 3385 bytes
```

### 卸载(干净撤除)

```powershell
# 全局
python aether/bin/aether_install.py --global --uninstall --apply

# 项目级
python aether/bin/aether_install.py "D:/path/to/target/project" --uninstall --apply
```

会:
- 删 `.cursor/hooks.json`(我们装的那份)
- 删 `.aether-install.json`(manifest)
- 如 copy 模式 · 删 `target/aether/`
- 如装时 backup 了你原有的 hooks.json · 自动恢复

---

## 5 · 排错

### 5.1 · 状态行没出

**最常见原因**:Cursor 没重启 · hooks.json 还是旧的。
**修**:完全关闭 Cursor(File → Exit) · 重新打开。

**其次**:Python 路径不对。
**查**:看 target 的 `.cursor/hooks.json` · 第一个 hook 的 `command` 字段 · 应该是绝对路径如 `"C:\\Python39\\python.exe" "C:\\..\\aether\\bin\\aether_hook.py" --event sessionStart`。
**修**:
- 如果 python 路径是错的 · uninstall 后用正确的 Python 重装
- 如果 aether 路径错(你移动过 workspace)· uninstall + 重装

### 5.2 · 看 hook 真触发了没

打开 Cursor Settings → Hooks tab(就在 settings 搜索 "hooks" 找)· 看 OUTPUT log。
应该看到 `sessionStart` hook 的 stdout 输出 JSON · 包含 `additional_context`。

### 5.3 · target 里出现奇怪文件夹

shared 模式下 hook 会写 events 到中央 `.aether/` · target 自己不出现 .aether/ 目录(除非中央 aether 跑了 indexer 写 target 数据)。
copy 模式下 target 会有 `.aether/` 出现 · 这是正常的(target 自己的数据库)。

### 5.4 · 我的 target 已有 .cursor/hooks.json 怎么办

aether_install.py 会**自动备份**你已有的 hooks.json 到 `hooks.json.bak`(或带时间戳),然后写我们的。
uninstall 时如有 backup · 会自动恢复。

---

## 6 · 数据隔离 · 它怎么工作的(看一眼就懂)

**全局 / shared 模式都已自动隔离**(Day 8 末实现)。逻辑如下:

```
hook 触发(Cursor 给 payload)
    ↓
payload 里有 workspace_roots = ["/c:/path/to/openclaw/x"]
    ↓
aether_events.resolve_data_dir(payload)
    ↓
events / transcripts / agent-responses → /c:/path/to/openclaw/x/.aether/
```

环境变量 `AETHER_DATA_DIR=<path>` 可强制覆盖(高级用法)。

**结果**:
- OpenClaw 项目的 AI shell 调用 → 写到 OpenClaw 自己的 `.aether/events.jsonl`
- 写小说项目的 AI 思考 → 写到小说项目自己的 `.aether/`
- 你的中央 aether 数据库 → 仍只装中央 aether 的事(不被污染)

如果你想跨项目查统计 · 跑 `python aether/bin/aether_query.py --stats` 看的是中央数据。
跨项目聚合查询 = Day 9 P3 候选(目前未实现)。

---

## 7 · 拷粘贴一行 cheat sheet

```powershell
# 全局(推荐 · 装一次终身)
python aether/bin/aether_install.py --global --apply
python aether/bin/aether_install.py --global --check
python aether/bin/aether_install.py --global --uninstall --apply

# 项目级
python aether/bin/aether_install.py "<TARGET>" --apply
python aether/bin/aether_install.py "<TARGET>" --copy --apply
python aether/bin/aether_install.py "<TARGET>" --check
python aether/bin/aether_install.py "<TARGET>" --uninstall --apply
```

把 `<TARGET>` 替换成项目绝对路径。完。

**Owner 你现在跑这一行 · 装到全局**:
```powershell
python aether/bin/aether_install.py --global --apply
```
然后重启 Cursor · 打开任何项目 · 新 chat 输入 "你好" · 看 AI 第一行是否贴状态行。
