# 📚 生词本 · ShengCiBen

一个极简的个人背单词 / 记好句网站：单词、短语、句子三个板块，注册账号密码登录，复习时用「回忆式卡片」连续抽题。响应式布局，手机浏览器也能正常使用。

- 后端：Flask + SQLite（标准库，零额外数据库依赖）
- 前端：原生 HTML / CSS / JS
- 密码：werkzeug 哈希存储（不存明文）

## 功能

- 注册 / 登录 / 退出
- **单词板块**：录入生词（单词 + 释义，例句可选）、列表、删除、熟练度展示（●○○○○）
- **短语板块**：录入短语 / 固定搭配（短语 + 释义，例句可选）、列表、删除
- **句子板块**：写作 / 翻译用的例句 + 解释，按**自定义分类**（如并列句、复杂句、倒装句）分开存
  - 分类管理：新建 / 改名 / 删除（删除分类会连带删除其中所有句子）、上移 / 下移排序
- **批量导入**：单词、短语、句子都支持一次粘贴多行
- **回忆式复习**，三种模式：
  - 复习单词：看到单词 + 挖空例句 → 回忆意思
  - 复习短语：看到短语 + 挖空例句 → 回忆意思
  - 复习句子：看到分类 + 解释 → 回想原句
  - 点「显示答案」后自评「记得 / 不记得」
- 内置轻量 Leitner 记忆法：记得的熟练度上升、被抽到概率降低；不记得的下降、更容易再出现

## 本地运行

```bash
# 1. 建虚拟环境（可选但推荐）
python -m venv .venv
# Windows 激活：
.venv\Scripts\activate
# macOS / Linux 激活：
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动
python app.py
```

打开浏览器访问 http://127.0.0.1:5000 即可。数据会存在项目目录下的 `vocab.db` 文件里。

## 部署到网上

### 通用准备

数据库路径和密钥都通过环境变量配置，部署时务必设置：

| 环境变量 | 说明 |
| --- | --- |
| `SECRET_KEY` | 会话签名密钥，必须设一个长随机串 |
| `DATABASE_PATH` | 数据库文件路径（用于挂载持久磁盘） |

生成随机密钥：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 部署到 Render（推荐，有免费套餐）

1. 把代码推到 GitHub 仓库。
2. 在 Render 建一个 **Web Service**，连接该仓库。
3. 构建命令：`pip install -r requirements.txt`；启动命令：`gunicorn app:app`。
4. 环境变量里加 `SECRET_KEY`。
5. 若要数据不丢失，新建一个 **Disk** 挂载到 `/data`，并把 `DATABASE_PATH` 设为 `/data/vocab.db`。

> 注意：Render 免费套餐的磁盘在重启时会清空，只有挂载 Disk 才能持久保存数据。

### 部署到 Railway

1. 推仓库后在 Railway 新建项目（会自动识别 `requirements.txt` 和 `Procfile`）。
2. 添加环境变量 `SECRET_KEY`。
3. 在「Volumes」里挂载一个持久卷，并设 `DATABASE_PATH` 指向卷内路径（如 `/app/data/vocab.db`）。

## 项目结构

```
app.py               # 全部后端逻辑（认证 / 单词与句子增删 / 分类管理 / 复习 API / 数据库）
templates/           # 页面模板（index 单词、phrases 短语、sentences 句子、review 复习等）
static/style.css     # 样式
static/app.js        # 复习卡片交互
requirements.txt     # 依赖
Procfile             # 线上启动命令
```

## 开源协议

MIT License，详见 [LICENSE](LICENSE)。

## 后续可以加

- 发音（TTS）
- 选择题模式
- 间隔重复曲线（如 SM-2）
