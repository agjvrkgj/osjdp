#!/bin/bash

# ==========================================
# Stream Notify Bot - 一键安装/卸载脚本
# ==========================================

GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
RESET="\033[0m"

INSTALL_DIR="/opt/stream-notify-bot"
SERVICE_FILE="/etc/systemd/system/stream-notify.service"

echo -e "${GREEN}====================================${RESET}"
echo -e "${GREEN}   Stream Notify Bot 一键管理脚本   ${RESET}"
echo -e "${GREEN}====================================${RESET}"
echo "1. 安装/更新 机器人"
echo "2. 卸载 机器人"
echo "0. 退出"
read -p "请输入数字选择 [0-2]: " choice

if [[ "$choice" == "0" ]]; then
    exit 0
fi

if [[ "$choice" == "2" ]]; then
    echo -e "\n${YELLOW}正在卸载...${RESET}"
    systemctl stop stream-notify >/dev/null 2>&1
    systemctl disable stream-notify >/dev/null 2>&1
    rm -f $SERVICE_FILE
    systemctl daemon-reload
    rm -rf $INSTALL_DIR
    echo -e "${GREEN}卸载完成！${RESET}"
    exit 0
fi

if [[ "$choice" == "1" ]]; then
    echo -e "\n${YELLOW}正在安装依赖并配置环境...${RESET}"
    
    # 检查 python3 和 venv
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}未找到 Python3，正在尝试安装...${RESET}"
        apt-get update && apt-get install -y python3 python3-venv || { echo -e "${RED}安装 Python3 失败，请手动安装！${RESET}"; exit 1; }
    fi
    
    # 创建目录
    mkdir -p $INSTALL_DIR
    
    # 下载核心文件 (假设从 GitHub raw 下载，后续替换为真实地址)
    echo -e "${YELLOW}下载机器人文件...${RESET}"
    curl -s -L "https://raw.githubusercontent.com/agjvrkgj/osjdp/main/main.py" -o $INSTALL_DIR/main.py
    curl -s -L "https://raw.githubusercontent.com/agjvrkgj/osjdp/main/requirements.txt" -o $INSTALL_DIR/requirements.txt
    
    # 检查是否下载成功
    if [ ! -s "$INSTALL_DIR/main.py" ]; then
         echo -e "${RED}下载失败，请检查网络或 GitHub 仓库地址！${RESET}"
         exit 1
    fi
    
    # 初始化配置
    if [ ! -f "$INSTALL_DIR/config.json" ]; then
        echo -e "\n${YELLOW}请填写机器人的配置信息:${RESET}"
        read -p "👉 1. 请输入 Telegram Bot Token (联系 @BotFather 获取): " bot_token
        read -p "👉 2. 请输入你的 Telegram Chat ID (联系 @userinfobot 获取): " chat_id
        
        cat > $INSTALL_DIR/config.json <<EOF
{
  "telegram_bot_token": "$bot_token",
  "telegram_chat_id": "$chat_id",
  "allowed_chat_ids": ["$chat_id"],
  "check_interval_seconds": 60
}
EOF
    else
        echo -e "${GREEN}配置文件已存在，跳过配置。${RESET}"
    fi
    
    # 设置 Python 虚拟环境
    echo -e "${YELLOW}正在安装 Python 依赖...${RESET}"
    cd $INSTALL_DIR
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt -q
    
    # 创建 systemd 服务
    cat > $SERVICE_FILE <<EOF
[Unit]
Description=Streamer Notification Bot (PandaLive & SOOP)
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable stream-notify >/dev/null 2>&1
    systemctl restart stream-notify

    # 设置 Telegram Bot 快捷菜单命令
    echo -e "${YELLOW}正在注册 Telegram 快捷菜单...${RESET}"
    curl -s -X POST "https://api.telegram.org/bot$bot_token/setMyCommands" \
         -H "Content-Type: application/json" \
         -d '{
            "commands": [
                {"command": "add", "description": "添加监控 (/add 平台 ID 别名)"},
                {"command": "del", "description": "删除监控 (/del 平台 ID)"},
                {"command": "list", "description": "查看列表和在线状态"},
                {"command": "check", "description": "立即检查一次在线状态"},
                {"command": "status", "description": "查看机器人运行状态"},
                {"command": "help", "description": "显示命令使用帮助"}
            ]
         }' > /dev/null

    
    echo -e "\n${GREEN}✅ 安装并启动成功！${RESET}"
    echo -e "你可以去 Telegram 向你的机器人发送 ${YELLOW}/help${RESET} 查看命令了。"
    echo -e "查看运行日志命令: ${YELLOW}journalctl -u stream-notify -f${RESET}"
fi
