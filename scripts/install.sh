#!/bin/bash
#
# 涨停股筛选系统 - 安装脚本
# 功能：配置 cron 定时任务、环境变量、日志轮转
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(dirname "$SCRIPT_DIR")"
CONF_FILE="$SCRIPT_DIR/screen_limit_up_stocks.conf"
LOG_DIR="/var/log/stock-screen"
LOG_FILE="$LOG_DIR/screen.log"

echo "=========================================="
echo "  涨停股筛选系统 - 安装配置"
echo "=========================================="
echo

# 1. 检查 Python 依赖
echo "📦 检查 Python 依赖..."
python3 -c "import akshare" 2>/dev/null || {
    echo "   安装 akshare..."
    pip3 install akshare -q
}
python3 -c "import requests" 2>/dev/null || {
    echo "   安装 requests..."
    pip3 install requests -q
}
python3 -c "import pandas" 2>/dev/null || {
    echo "   安装 pandas..."
    pip3 install pandas -q
}
echo "   ✅ Python 依赖检查完成"
echo

# 2. 创建日志目录
echo "📁 创建日志目录..."
if [ ! -d "$LOG_DIR" ]; then
    sudo mkdir -p "$LOG_DIR"
    sudo chmod 755 "$LOG_DIR"
    echo "   创建：$LOG_DIR"
fi
if [ ! -f "$LOG_FILE" ]; then
    sudo touch "$LOG_FILE"
    sudo chmod 644 "$LOG_FILE"
    echo "   创建：$LOG_FILE"
fi
echo "   ✅ 日志目录配置完成"
echo

# 3. 配置环境变量
echo "🔧 配置环境变量..."
ENV_FILE="$WORKSPACE_DIR/.env"

# 读取配置文件
if [ -f "$CONF_FILE" ]; then
    echo "   读取配置：$CONF_FILE"
    
    # 提取飞书配置
    FEISHU_APP_ID=$(grep "^FEISHU_APP_ID=" "$CONF_FILE" | cut -d'=' -f2)
    FEISHU_APP_SECRET=$(grep "^FEISHU_APP_SECRET=" "$CONF_FILE" | cut -d'=' -f2)
    FEISHU_CHAT_ID=$(grep "^FEISHU_CHAT_ID=" "$CONF_FILE" | cut -d'=' -f2)
    
    # 写入 .env 文件
    cat > "$ENV_FILE" << EOF
# 飞书通知配置
FEISHU_APP_ID=$FEISHU_APP_ID
FEISHU_APP_SECRET=$FEISHU_APP_SECRET
FEISHU_CHAT_ID=$FEISHU_CHAT_ID

# 筛选参数
TOP_N=5
MIN_CHANGE_PCT=7.0
FEISHU_NOTIFY=true
EOF
    echo "   写入：$ENV_FILE"
else
    echo "   ⚠️  配置文件不存在：$CONF_FILE"
    echo "   请手动创建 $ENV_FILE 并配置飞书参数"
fi
echo "   ✅ 环境变量配置完成"
echo

# 4. 配置 cron 定时任务
echo "⏰ 配置 cron 定时任务..."

# 检查 cron 服务
if ! command -v crontab &> /dev/null; then
    echo "   ⚠️  crontab 未安装，跳过定时任务配置"
else
    # 备份现有 cron
    crontab -l > /tmp/cron_backup.$$.txt 2>/dev/null || true
    
    # 检查是否已存在任务
    if crontab -l 2>/dev/null | grep -q "screen_limit_up_stocks.py"; then
        echo "   ⚠️  定时任务已存在，跳过"
    else
        # 添加新任务
        CRON_JOB="30 15 * * 1-5 cd $WORKSPACE_DIR && source $ENV_FILE && python3 $SCRIPT_DIR/screen_limit_up_stocks.py --notify >> $LOG_FILE 2>&1"
        (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
        echo "   添加任务：$CRON_JOB"
    fi
    echo "   ✅ Cron 配置完成"
    
    # 显示当前 cron 列表
    echo
    echo "   当前 cron 任务列表:"
    crontab -l | grep "screen_limit" || echo "   (无)"
fi
echo

# 5. 配置日志轮转
echo "📋 配置日志轮转..."
LOGROTATE_CONF="/etc/logrotate.d/stock-screen"

if [ ! -f "$LOGROTATE_CONF" ]; then
    sudo cat > "$LOGROTATE_CONF" << EOF
$LOG_FILE {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
EOF
    echo "   创建：$LOGROTATE_CONF"
else
    echo "   ✅ 日志轮转已配置"
fi
echo

# 6. 测试运行
echo "🧪 测试运行..."
cd "$WORKSPACE_DIR"
if python3 "$SCRIPT_DIR/screen_limit_up_stocks.py" --no-detail > /dev/null 2>&1; then
    echo "   ✅ 测试运行成功"
else
    echo "   ⚠️  测试运行失败，请检查网络和依赖"
fi
echo

# 完成
echo "=========================================="
echo "  ✅ 安装配置完成"
echo "=========================================="
echo
echo "📌 下一步:"
echo "   1. 编辑 $CONF_FILE 配置飞书参数"
echo "   2. 运行 crontab -e 确认定时任务"
echo "   3. 查看日志：tail -f $LOG_FILE"
echo
echo "🚀 手动运行:"
echo "   cd $WORKSPACE_DIR"
echo "   python3 $SCRIPT_DIR/screen_limit_up_stocks.py --notify"
echo
