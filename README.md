# Stream Notify Bot

一个轻量级的跨平台直播开播提醒 Telegram 机器人。

## 🌟 功能

- **多平台支持**
  - **PandaLive (PandaTV)**：支持查询全站主播（**包括 19禁 成人频道**），推送带免登录代理播放地址及 M3U8 流地址。
  - **SOOP (原 AfreecaTV)**：调用官方无限制 API，支持实时人数和状态查询。
- **全命令交互**：无需修改配置文件，直接在 Telegram 聊天框内发命令添加、删除主播。
- **极简部署**：只需运行一行命令即可完成环境安装、配置填写和守护进程设置。

## 🚀 一键安装 / 卸载

在你的 Linux 终端（Ubuntu/Debian/CentOS）中运行以下命令：

```bash
bash <(curl -sL https://raw.githubusercontent.com/USER/stream-notify-bot/main/install.sh)
```

*(请将链接中的 `USER` 替换为你的 GitHub 用户名)*

运行后会弹出交互菜单：
1. **安装/更新**（会提示你输入 Bot Token 和你的 Chat ID）
2. **卸载**

## 💬 机器人使用说明

在 Telegram 中向你的机器人发送命令：

- `/add panda siyun12476 诗允` 👉 监控 PandaTV 的 siyun12476，取别名为"诗允"
- `/add soop lshooooo 이상호` 👉 监控 SOOP 的 lshooooo
- `/del panda siyun12476` 👉 取消监控
- `/list` 👉 查看当前监控的所有主播和在线状态（开播显示 🟢，未播显示 ⚫）
- `/status` 👉 查看机器人运行日志和轮询状态

*(注意：机器人默认只回复你在配置文件中绑定的 Chat ID，其他人私聊机器人会被拒绝，保证隐私安全。)*

## 🛠 手动管理

服务以 systemd 形式运行在后台。

**查看实时日志：**
```bash
journalctl -u stream-notify -f
```

**重启服务：**
```bash
systemctl restart stream-notify
```

**停止服务：**
```bash
systemctl stop stream-notify
```

**修改配置 / 主播数据：**
所有数据储存在 `/opt/stream-notify-bot` 目录下：
- `config.json`：基础配置
- `streamers.json`：监控的主播列表
修改完 `config.json` 后需重启服务，修改 `streamers.json` 不需要重启。
