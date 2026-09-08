# Git 操作指南（精简版）

> 个人定制：GitHub + Gitee 双平台，一条命令推送。

## 你的账号与仓库

| 平台 | 账号 | my_hub 的 SSH 地址 |
| --- | --- | --- |
| GitHub | `18728961140` | `git@github.com:18728961140/my_hub.git` |
| Gitee | `yhc`（路径 `yang-gengchun`） | `git@gitee.com:yang-gengchun/my_hub.git` |

> 注意：Gitee 网页显示 “yhc”，但真实路径是 `yang-gengchun`。GitHub 上的 `desktop-tutorial`、Gitee 上的 `my_project` 与本项目无关，别推错。

---

## 一、个人仓库：平时只需 4 条命令

```bash
git status            # 查看改动了什么
git add .             # 添加所有改动
git commit -m "说明"   # 提交
git push              # 同时推送到 GitHub 和 Gitee
```

---

## 二、企业/团队共用仓库：先更新，再上传（固定流程）

> 适用场景：多人共用的企业或团队远程仓库。核心原则：**上传前必须先更新**，把别人的最新代码先拉下来，避免冲突和被拒绝。

### 1. 添加企业远程仓库（只需一次）

```bash
# 把下面地址换成企业给你的真实仓库地址
git remote add company git@企业服务器:团队名/项目名.git

# 查看远程配置
git remote -v
```

### 2. 每次提交上传的固定流程

```bash
# ① 开工前：先把远程最新代码更新到本地
git pull company master

# ② 修改代码后：提交到本地
git add .
git commit -m "说明"

# ③ 上传前：再更新一次，把自己的提交接到最新代码后面（重要，不要省略）
git pull company master --rebase

# ④ 上传
git push company master
```

如果用的是 `main` 分支，把上面命令里的 `master` 换成 `main` 即可。

### 3. 更新时提示冲突怎么办

```bash
# 查看冲突文件
git status

# 打开冲突文件，手动保留需要的代码，然后：
git add 冲突文件
git rebase --continue

# 冲突解决完再上传
git push company master
```

### 4. 两个铁律

- **先 pull，再 push**：推送前没更新就直接 push，会被服务器拒绝；
- **有未提交的修改时不要 pull**：先 `git commit` 或保存好现场，再更新。

---

## 三、分支开发：在独立时间线上做功能

> 核心：分支 = 一条独立的提交时间线。`master` 是主时间线，功能分支从上面岔出去，互不干扰；做完后合并回 `master`，再推送。

```text
master:   A --- B（主时间线，稳定版）
              \
feature:       C --- D（新功能，做完合并回 master）
```

### 1. 动手前：先处理未提交的改动

未提交的改动**不属于任何分支**，切换分支时会跟着你走。开新分支前先定型：

```bash
git add .
git commit -m "说明"      # 把当前改动提交掉

# 或者临时放下手头的活：
git stash                 # 暂存改动，切回时用 git stash pop 恢复
```

### 2. 从主线拉出新分支

```bash
git switch master                  # 先回到主时间线
git switch -c feature/新功能名      # 创建并切换到功能分支
```

之后随时用 `git status` 或 `git branch` 查看当前在哪个分支。

### 3. 在分支上开发，多次提交

每完成一个逻辑单元就提交一次，提交信息写清楚做了什么：

```bash
git add .
git commit -m "feat: 增加搜索接口"
```

### 4. 推送到远程

```bash
git push -u origin feature/新功能名   # 第一次带 -u，GitHub 和 Gitee 会同时建分支
```

以后在该分支上只需 `git push`。

### 5. 合并回主线

```bash
git switch master                    # 回到主时间线
git pull                             # 先拉最新代码（只从 GitHub 拉）
git merge feature/新功能名            # 把功能分支并入 master
git push                             # 同时推送到 GitHub 和 Gitee
```

合并时提示冲突：打开冲突文件手动保留正确代码 → `git add 冲突文件` → `git commit` 收尾。

### 6. 删除用完的分支

```bash
git branch -d feature/新功能名              # 删本地
git push origin --delete feature/新功能名   # 删远程（两个平台一起删）
```

### 7. 三个要点

- 分支之间互不影响，但**未提交的改动会跟着切换走**：养成“先提交或 stash，再切分支”的习惯；
- `git pull` 只从 GitHub 收代码，推送才同时发 GitHub + Gitee；
- 新功能开分支，小修补可直接在 master 上提交（个人仓库从简）。

---

## 四、一次性配置（个人仓库 my_hub 已配好可跳过）

### 1. 设置身份

```bash
git config --global user.name "yhc"
git config --global user.email "18728961140@163.com"
```

### 2. 配置远端

```bash
git remote remove origin
git remote add origin git@github.com:18728961140/my_hub.git
git remote set-url --add --push origin git@gitee.com:yang-gengchun/my_hub.git

# 确认：fetch 只有 GitHub，push 有 GitHub + Gitee 两个地址
git remote -v
```

正确效果：

```text
origin  git@github.com:18728961140/my_hub.git (fetch)
origin  git@gitee.com:yang-gengchun/my_hub.git (push)
origin  git@github.com:18728961140/my_hub.git (push)
```

### 3. 首次推送

```bash
git push -u origin master
```

如果第一次推送提示 “rejected / fetch first”，说明远端有自动生成的模板 README，追加 `--force` 覆盖一次即可（只影响模板占位内容）：

```bash
git push -u origin master --force
```

以后只需 `git push`。

---

## 五、其他常用指令

```bash
git log --oneline          # 查看提交历史
git branch                 # 查看分支
git checkout -b 新分支名    # 新建并切换分支
git pull                   # 拉取远程更新
git clone <仓库地址>        # 克隆仓库
```

> `git reset --hard` 会丢掉提交，非必要不要用。

---

## 六、SSH 密钥（一次性）

密钥位置：`C:\Users\yhc\.ssh\id_rsa`（私钥，勿外传）和 `id_rsa.pub`（公钥）。

查看公钥并添加到平台：

```powershell
Get-Content C:\Users\yhc\.ssh\id_rsa.pub
```

- GitHub：Settings → SSH and GPG keys → New SSH key
- Gitee：设置 → 安全设置 → SSH 公钥

测试连接：

```powershell
ssh -T git@github.com
ssh -T git@gitee.com
```

若报 “Permissions ... too open”，修复：

```powershell
icacls "C:\Users\yhc\.ssh\id_rsa" /inheritance:r
icacls "C:\Users\yhc\.ssh\id_rsa" /grant:r "%USERNAME%:R"
```

---

## 七、报错速查

| 报错 | 原因 | 解决 |
| --- | --- | --- |
| `Permission denied (publickey)` | 公钥未添加或私钥权限过宽 | 添加公钥；执行上面的 `icacls` |
| `Repository not found` / `404` | 地址写错或仓库不存在 | 用真实地址重配 `origin` 或 `company` |
| 推送被拒绝 `fetch first` | 远端有别人新提交的代码 | 先 `git pull ... --rebase`，再 push |
| 合并/变基冲突 | 你和别人改了同一处代码 | 手动解决冲突后 `git add` + `git rebase --continue` |
| GitHub HTTPS 连接被重置 | 国内网络问题 | 一律使用 SSH 地址 |

---

## 附录：SSH 公钥备份

```text
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDT+I77yg565189QV8nwTdH6i4pTCxY3Oj45x3ZOruKhknhYnqkq5MMPmFudnLabxjcLcVqrE41d7IQaXXXdUEVfUWr5ETB7X/+CvG1y5TRUQD6lb/4Y/OnB+FTYc4cgqnLsWhYJLEFSfzZUfic4wAGt0ATkmgE2S1yhgiS0riOo9MBe+L4xMst6oHhNf2MDY4QgHgdZ2AHgPKfvMQNZ6bhRyvR6C6Y64xSstA/0rr+6t4JYKse4eLWsvenu/2izLajB9zp/3LrYMK2yaTExMZM+vak9cXWJKwf5bqnUAqv/GE041WIV/TyhaRqX1OUdTtHrD7p/bA9SPyC5FtyxOg+yI9L9YaSY2Se2Y+fvi6iTIJEkeCRKKMqUMr1k/4cIIdB5/BGgRv5basi4HNe701vfYwkzj/HMhKI9aDc2AD9vSbgKGhkqWaQvQYaXERNawFrsqvBjOoGZUQiP4n22HsiwM663vVD5iFU/RqXlsMyb9moGHFGQag0ltNk4T3Vv5zGxARh/OnoLI3GXud79IgsnMJVILth6uMOGztexAlvk+gwSYEfTutdwoqtfAR2DjYVV3nYrsDtx3oo9PbnhF86Q8vxE6UeoDM1k09M+64d0ZFtGPILW9SGm2EvkyQuhnW/blB6WEe0x46m/RmBqTRqhy6slH0Zlk5cwEPwJBNoBQ== 18728961140@163.com
```

> 公钥可以公开；私钥 `id_rsa` 绝不能泄露。
