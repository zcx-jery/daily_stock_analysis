#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书通知测试脚本
"""

import os
import sys
import json
import requests
from datetime import datetime

# 加载环境变量
env_file = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

def test_feishu_notification():
    """测试飞书通知"""
    
    app_id = os.environ.get('FEISHU_APP_ID', '')
    app_secret = os.environ.get('FEISHU_APP_SECRET', '')
    chat_id = os.environ.get('FEISHU_CHAT_ID', '')
    
    print("=" * 60)
    print("📧 飞书通知测试")
    print("=" * 60)
    print()
    print(f"FEISHU_APP_ID: {app_id}")
    print(f"FEISHU_APP_SECRET: {app_secret[:10]}...")
    print(f"FEISHU_CHAT_ID: {chat_id}")
    print()
    
    if not all([app_id, app_secret, chat_id]):
        print("❌ 配置不完整，请检查 .env 文件")
        return False
    
    # 1. 获取 tenant_access_token
    print("📌 步骤 1: 获取 access_token...")
    token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    token_resp = requests.post(token_url, json={
        "app_id": app_id,
        "app_secret": app_secret
    }, timeout=10)
    
    if token_resp.status_code != 200:
        print(f"❌ HTTP 错误：{token_resp.status_code}")
        print(f"响应：{token_resp.text}")
        return False
    
    token_data = token_resp.json()
    if token_data.get('code') != 0:
        print(f"❌ 获取 token 失败：{token_data}")
        return False
    
    tenant_token = token_data.get('tenant_access_token', '')
    print(f"✅ Token 获取成功：{tenant_token[:20]}...")
    print()
    
    # 2. 发送测试消息
    print("📌 步骤 2: 发送测试消息...")
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    message_content = {
        "config": {
            "wide_screen_mode": True
        },
        "header": {
            "template": "green",
            "title": {
                "tag": "plain_text",
                "content": "✅ 飞书通知测试成功"
            }
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**测试时间**: {now}\n\n**配置状态**: ✅ 正常\n\n涨停股筛选系统飞书通知功能已就绪，可以正常使用 --notify 参数发送筛选结果。"
                }
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "📊 涨停股筛选系统 v2.0"
                    }
                ]
            }
        ]
    }
    
    send_url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    headers = {
        "Authorization": f"Bearer {tenant_token}",
        "Content-Type": "application/json"
    }
    
    send_resp = requests.post(
        send_url,
        headers=headers,
        json={
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(message_content)
        },
        timeout=10
    )
    
    if send_resp.status_code == 200:
        send_data = send_resp.json()
        if send_data.get('code') == 0:
            print("✅ 消息发送成功！")
            print()
            print("=" * 60)
            print("🎉 飞书通知配置完成，可以正常使用")
            print("=" * 60)
            return True
        else:
            print(f"❌ 发送失败：{send_data}")
            return False
    else:
        print(f"❌ HTTP 错误：{send_resp.status_code}")
        print(f"响应：{send_resp.text}")
        return False


if __name__ == "__main__":
    success = test_feishu_notification()
    sys.exit(0 if success else 1)
