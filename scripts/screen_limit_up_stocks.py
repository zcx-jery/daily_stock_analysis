#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
涨停股筛选工具 - 调用 DSA 的 Akshare 数据源
按 4 步筛选法筛选明日可能涨停的股票

需求更新：
1. TOP N 改为动态参数，由用户输入
2. 第 1 步改为获取当日涨幅>=7% 的股票（原为涨停股）
"""

import sys
import os
sys.path.insert(0, '/root/.openclaw/workspace/stock/daily_stock')

import logging
import requests
from typing import List, Dict
import argparse
import json
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# DSA Cookie 文件
DSA_COOKIE_FILE = '/tmp/dsa_cookies.txt'
DSA_BASE = 'http://localhost:8001'

# 腾讯行情 API（用于批量获取实时数据）
TENCENT_API = "http://qt.gtimg.cn/q="

# 主板前缀
MAIN_BOARD_PREFIXES = ["sh600", "sh601", "sh603", "sh605", "sz000", "sz001", "sz002", "sz003"]


def load_dsa_cookie() -> str:
    """加载 DSA Cookie"""
    if os.path.exists(DSA_COOKIE_FILE):
        with open(DSA_COOKIE_FILE, 'r') as f:
            content = f.read()
            for line in content.split('\n'):
                if 'dsa_session' in line:
                    return line.split('\t')[-1]
    return ''


def get_high_change_stocks(min_change_pct: float = 7.0) -> List[Dict]:
    """
    获取当日涨幅>=min_change_pct% 的股票列表
    默认获取涨幅>=7% 的股票（原为涨停股）
    
    Args:
        min_change_pct: 最小涨幅百分比，默认 7.0
    """
    try:
        import akshare as ak
        import pandas as pd
        
        logger.info(f"正在获取全市场股票数据（涨幅>={min_change_pct}%）...")
        df = ak.stock_zh_a_spot_em()
        
        if df is None or df.empty:
            logger.error("获取股票数据失败")
            return []
        
        high_change_stocks = []
        
        for idx, row in df.iterrows():
            try:
                code = str(row.get('代码', ''))
                name = str(row.get('名称', ''))
                current_price = row.get('最新价', 0)
                pre_close = row.get('昨收', 0)
                change_percent = row.get('涨跌幅', 0)
                
                # 跳过无效数据
                if pd.isna(current_price) or pd.isna(pre_close) or current_price <= 0:
                    continue
                
                # 筛选涨幅>=min_change_pct 的股票
                if pd.isna(change_percent) or float(change_percent) < min_change_pct:
                    continue
                
                # 添加前缀
                if code.startswith('6') or code.startswith('9'):
                    full_code = f'sh{code}'
                elif code.startswith('0') or code.startswith('3'):
                    full_code = f'sz{code}'
                else:
                    full_code = code
                
                high_change_stocks.append({
                    'code': full_code,
                    'name': name,
                    'price': float(current_price),
                    'change_pct': float(change_percent),
                    'pre_close': float(pre_close),
                })
                    
            except Exception as e:
                continue
        
        logger.info(f"获取到 {len(high_change_stocks)} 只涨幅>={min_change_pct}% 的股票")
        return high_change_stocks
        
    except Exception as e:
        logger.error(f"获取高涨幅股票失败：{e}")
        return []


def get_sector_rankings() -> tuple:
    """
    获取板块涨跌榜
    Returns:
        (top_sectors, bottom_sectors): 涨幅前 10 和跌幅后 10
    """
    try:
        import akshare as ak
        
        logger.info("正在获取板块排行...")
        df = ak.stock_board_industry_name_em()
        
        if df is None or df.empty:
            return [], []
        
        # 涨幅前 10
        top_sectors = df.nlargest(10, '涨跌幅')[['板块名称', '涨跌幅']].to_dict('records')
        # 跌幅后 10
        bottom_sectors = df.nsmallest(10, '涨跌幅')[['板块名称', '涨跌幅']].to_dict('records')
        
        return top_sectors, bottom_sectors
        
    except Exception as e:
        logger.error(f"获取板块排行失败：{e}")
        return [], []


def get_stock_concept(code: str) -> List[str]:
    """
    获取个股所属概念板块
    
    Args:
        code: 股票代码（不含前缀）
    
    Returns:
        概念板块名称列表
    """
    try:
        import akshare as ak
        
        # 去除前缀
        pure_code = code.replace('sh', '').replace('sz', '')
        
        df = ak.stock_individual_info_em(symbol=pure_code)
        if df is None or df.empty:
            return []
        
        # 提取概念板块信息
        concepts = []
        for _, row in df.iterrows():
            if '概念' in str(row.get('item', '')):
                value = row.get('value', '')
                if value:
                    concepts.extend([c.strip() for c in str(value).split(',') if c.strip()])
        
        return concepts[:5]  # 最多返回 5 个概念
        
    except Exception as e:
        logger.debug(f"获取{code}概念失败：{e}")
        return []


def match_sector_strength(stock: Dict, top_sectors: List[Dict]) -> Dict:
    """
    匹配个股与最强题材，计算题材强度分
    
    Args:
        stock: 股票信息字典
        top_sectors: 涨幅前 10 板块列表
    
    Returns:
        包含题材匹配信息的字典
    """
    try:
        pure_code = stock['code'].replace('sh', '').replace('sz', '')
        concepts = get_stock_concept(pure_code)
        
        if not concepts:
            return {
                'concepts': [],
                'matched_sectors': [],
                'sector_score': 0,
                'strongest_sector': None,
            }
        
        # 匹配涨停股所属板块与最强题材
        matched_sectors = []
        for sector in top_sectors:
            sector_name = sector.get('板块名称', '')
            sector_change = sector.get('涨跌幅', 0)
            
            for concept in concepts:
                if concept in sector_name or sector_name in concept:
                    matched_sectors.append({
                        'sector': sector_name,
                        'change_pct': sector_change,
                        'concept': concept,
                    })
                    break
        
        # 计算题材强度分（0-10 分）
        sector_score = 0
        strongest_sector = None
        if matched_sectors:
            # 取匹配板块中涨幅最高的
            strongest = max(matched_sectors, key=lambda x: x['change_pct'])
            strongest_sector = strongest['sector']
            # 板块涨幅转换为分数（板块涨 10% 得 10 分）
            sector_score = min(abs(strongest['change_pct']) / 10 * 10, 10)
        
        return {
            'concepts': concepts,
            'matched_sectors': matched_sectors,
            'sector_score': round(sector_score, 2),
            'strongest_sector': strongest_sector,
        }
        
    except Exception as e:
        logger.debug(f"题材匹配失败：{e}")
        return {
            'concepts': [],
            'matched_sectors': [],
            'sector_score': 0,
            'strongest_sector': None,
        }


def get_batch_quotes(codes: List[str]) -> List[Dict]:
    """批量获取股票实时行情（腾讯 API）"""
    if not codes:
        return []
    
    # 分批请求，每批 50 只
    all_stocks = []
    batch_size = 50
    
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        query = ",".join(batch)
        url = f"{TENCENT_API}{query}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                continue
            
            # 解析数据
            text = response.content.decode('gbk', errors='ignore')
            
            for line in text.strip().split('\n'):
                if not line.startswith('v_'):
                    continue
                
                import re
                match = re.search(r'"([^"]+)"', line)
                if not match:
                    continue
                
                values = match.group(1).split('~')
                if len(values) < 45:
                    continue
                
                try:
                    code_raw = values[2]
                    code = f'sh{code_raw}' if code_raw.startswith('6') or code_raw.startswith('9') else f'sz{code_raw}'
                    name = values[1]
                    current_price = float(values[3])
                    prev_close = float(values[4])
                    
                    # 成交额（万元）、换手率、量比
                    amount = float(values[37]) if len(values) > 37 else 0
                    turnover_rate = float(values[43]) if len(values) > 43 else 0
                    volume_ratio = float(values[41]) if len(values) > 41 else 1.0
                    
                    # 涨跌幅
                    change_percent = float(values[32]) if len(values) > 32 else ((current_price - prev_close) / prev_close * 100)
                    
                    all_stocks.append({
                        'code': code,
                        'name': name,
                        'price': current_price,
                        'change_percent': change_percent,
                        'amount': amount,  # 万元
                        'turnover_rate': turnover_rate,
                        'volume_ratio': volume_ratio,
                    })
                except Exception:
                    continue
                    
        except Exception as e:
            logger.warning(f"批量获取行情失败：{e}")
    
    return all_stocks


def is_main_board(code: str) -> bool:
    """判断是否为主板股票"""
    code_lower = code.lower()
    return any(code_lower.startswith(p) for p in MAIN_BOARD_PREFIXES)


def calculate_score(stock: Dict, include_sector: bool = True) -> float:
    """
    量价配合评分 + 题材强度
    基础评分：涨幅 30% + 量能 30% + 换手 20% + 量比 20%
    题材加成：额外 0-2 分（强题材股票）
    
    Args:
        stock: 股票信息字典
        include_sector: 是否包含题材评分
    
    Returns:
        综合评分（0-12 分）
    """
    try:
        # 涨幅评分（涨停为 10 分）
        change_pct = stock.get('change_pct', 0)
        change_score = min(abs(change_pct) / 10 * 10, 10)
        
        # 量能评分（以 10 亿为满分，amount 单位是万元）
        amount = stock.get('amount', 0)
        amount_score = min(amount / 100000 * 10, 10)
        
        # 换手评分（5%-15% 为最佳）
        turnover = stock.get('turnover_rate', 0)
        if 5 <= turnover <= 15:
            turnover_score = 10
        elif turnover < 5:
            turnover_score = turnover / 5 * 10
        else:
            turnover_score = max(10 - (turnover - 15) / 10 * 10, 0)
        
        # 量比评分（1.5-3.0 为最佳）
        volume_ratio = stock.get('volume_ratio', 1.0)
        if 1.5 <= volume_ratio <= 3.0:
            volume_ratio_score = 10
        elif volume_ratio < 1.5:
            volume_ratio_score = volume_ratio / 1.5 * 10
        else:
            volume_ratio_score = max(10 - (volume_ratio - 3.0) / 5 * 10, 0)
        
        # 基础评分（0-10 分）
        base_score = (
            change_score * 0.3 +
            amount_score * 0.3 +
            turnover_score * 0.2 +
            volume_ratio_score * 0.2
        )
        
        # 题材加成（0-2 分）
        sector_bonus = 0
        if include_sector:
            sector_score = stock.get('sector_score', 0)
            # 题材分>=7 分的股票，额外加 1-2 分
            if sector_score >= 7:
                sector_bonus = 2
            elif sector_score >= 5:
                sector_bonus = 1
        
        total_score = base_score + sector_bonus
        
        return round(total_score, 2)
    except Exception as e:
        print(f"评分计算失败：{e}, stock={stock}")
        return 0.0


def calculate_buy_point(stock: Dict) -> None:
    """
    计算买入点、仓位管理、止损止盈
    
    基于技术位 + 评分综合决策：
    - 买入点：涨停价附近支撑位（分 3 批）
    - 仓位：根据评分动态分配
    - 止损：技术位 + 固定比例双重保护
    - 止盈：阶梯式止盈
    """
    try:
        price = stock.get('price', 0)
        score = stock.get('score', 0)
        change_pct = stock.get('change_pct', 0)
        turnover = stock.get('turnover_rate', 0)
        
        # ==================== 1. 技术位计算 ====================
        # 涨停价作为强支撑
        limit_up_price = price  # 当前已是涨停价
        
        # 支撑位计算（基于涨停价）
        support_1 = round(limit_up_price * 0.98, 2)   # 第一支撑：-2%
        support_2 = round(limit_up_price * 0.95, 2)   # 第二支撑：-5%
        support_3 = round(limit_up_price * 0.90, 2)   # 第三支撑：-10%
        
        # 压力位计算（基于涨停价）
        resistance_1 = round(limit_up_price * 1.03, 2)  # 第一压力：+3%
        resistance_2 = round(limit_up_price * 1.05, 2)  # 第二压力：+5%
        resistance_3 = round(limit_up_price * 1.10, 2)  # 第三压力：+10%（连板）
        
        # ==================== 2. 买入点策略 ====================
        # 评分越高，买入越积极
        if score >= 9.0:
            # 强烈推荐：3 批建仓，较重仓位
            buy_1_price = limit_up_price  # 涨停价附近
            buy_1_percent = 40
            buy_2_price = support_1       # -2%
            buy_2_percent = 35
            buy_3_price = support_2       # -5%
            buy_3_percent = 25
            target_position = 30  # 目标仓位 30%
        elif score >= 8.0:
            # 重点关注：3 批建仓，中等仓位
            buy_1_price = limit_up_price
            buy_1_percent = 35
            buy_2_price = support_1
            buy_2_percent = 35
            buy_3_price = support_2
            buy_3_percent = 30
            target_position = 20  # 目标仓位 20%
        elif score >= 7.0:
            # 一般关注：2 批建仓，较轻仓位
            buy_1_price = support_1
            buy_1_percent = 50
            buy_2_price = support_2
            buy_2_percent = 50
            buy_3_price = 0
            buy_3_percent = 0
            target_position = 15  # 目标仓位 15%
        else:
            # 观察为主：1 批建仓，轻仓试探
            buy_1_price = support_2
            buy_1_percent = 100
            buy_2_price = 0
            buy_2_percent = 0
            buy_3_price = 0
            buy_3_percent = 0
            target_position = 10  # 目标仓位 10%
        
        # ==================== 3. 止损策略 ====================
        # 技术位止损 + 固定比例止损 双重保护
        # 评分越高，止损越宽松（给予更大波动空间）
        if score >= 9.0:
            stop_loss_percent = 8    # -8% 止损
            stop_loss_price = round(limit_up_price * 0.92, 2)
        elif score >= 8.0:
            stop_loss_percent = 7    # -7% 止损
            stop_loss_price = round(limit_up_price * 0.93, 2)
        elif score >= 7.0:
            stop_loss_percent = 6    # -6% 止损
            stop_loss_price = round(limit_up_price * 0.94, 2)
        else:
            stop_loss_percent = 5    # -5% 止损
            stop_loss_price = round(limit_up_price * 0.95, 2)
        
        # ==================== 4. 止盈策略 ====================
        # 阶梯式止盈，评分越高目标越高
        if score >= 9.0:
            take_profit_1 = round(limit_up_price * 1.08, 2)  # +8% 减仓 30%
            take_profit_2 = round(limit_up_price * 1.15, 2)  # +15% 减仓 30%
            take_profit_3 = round(limit_up_price * 1.25, 2)  # +25% 清仓
        elif score >= 8.0:
            take_profit_1 = round(limit_up_price * 1.06, 2)  # +6% 减仓 30%
            take_profit_2 = round(limit_up_price * 1.12, 2)  # +12% 减仓 30%
            take_profit_3 = round(limit_up_price * 1.20, 2)  # +20% 清仓
        else:
            take_profit_1 = round(limit_up_price * 1.05, 2)  # +5% 减仓 30%
            take_profit_2 = round(limit_up_price * 1.10, 2)  # +10% 减仓 30%
            take_profit_3 = round(limit_up_price * 1.15, 2)  # +15% 清仓
        
        # ==================== 5. 写入股票字典 ====================
        stock['buy_point'] = {
            'buy_1': {'price': buy_1_price, 'percent': buy_1_percent},
            'buy_2': {'price': buy_2_price, 'percent': buy_2_percent},
            'buy_3': {'price': buy_3_price, 'percent': buy_3_percent},
            'target_position': target_position,
        }
        stock['stop_loss'] = {
            'price': stop_loss_price,
            'percent': stop_loss_percent,
        }
        stock['take_profit'] = {
            'tp_1': take_profit_1,
            'tp_2': take_profit_2,
            'tp_3': take_profit_3,
        }
        stock['support'] = [support_1, support_2, support_3]
        stock['resistance'] = [resistance_1, resistance_2, resistance_3]
        
    except Exception as e:
        print(f"买入点计算失败：{e}, stock={stock}")
        # 设置默认值
        stock['buy_point'] = {'buy_1': {'price': 0, 'percent': 0}, 'buy_2': {'price': 0, 'percent': 0}, 'buy_3': {'price': 0, 'percent': 0}, 'target_position': 0}
        stock['stop_loss'] = {'price': 0, 'percent': 0}
        stock['take_profit'] = {'tp_1': 0, 'tp_2': 0, 'tp_3': 0}
        stock['support'] = [0, 0, 0]
        stock['resistance'] = [0, 0, 0]


def send_feishu_notification(results: List[Dict], top_n: int, min_change_pct: float) -> bool:
    """
    发送筛选结果到飞书群
    
    Args:
        results: 筛选结果列表
        top_n: TOP N 数量
        min_change_pct: 最小涨幅阈值
    
    Returns:
        是否发送成功
    """
    try:
        # 从环境变量读取飞书配置
        app_id = os.environ.get('FEISHU_APP_ID', '')
        app_secret = os.environ.get('FEISHU_APP_SECRET', '')
        chat_id = os.environ.get('FEISHU_CHAT_ID', '')
        
        if not all([app_id, app_secret, chat_id]):
            logger.warning("飞书配置不完整，跳过通知发送")
            return False
        
        # 获取 tenant_access_token
        token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        token_resp = requests.post(token_url, json={
            "app_id": app_id,
            "app_secret": app_secret
        }, timeout=10)
        
        if token_resp.status_code != 200:
            logger.error(f"获取飞书 token 失败：{token_resp.text}")
            return False
        
        token_data = token_resp.json()
        if token_data.get('code') != 0:
            logger.error(f"获取飞书 token 失败：{token_data}")
            return False
        
        tenant_token = token_data.get('tenant_access_token', '')
        
        # 构建消息内容
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        top_stocks = results[:top_n]
        
        # 构建股票列表文本
        stock_lines = []
        for i, stock in enumerate(top_stocks, 1):
            name = stock.get('name', '')
            code = stock.get('code', '')
            price = stock.get('price', 0)
            change_pct = stock.get('change_pct', 0)
            score = stock.get('score', 0)
            concepts = stock.get('concepts', [])
            strongest_sector = stock.get('strongest_sector', None)
            bp = stock.get('buy_point', {})
            position = bp.get('target_position', 0)
            
            line = f"{i}. **{name}** ({code})\n"
            line += f"   价格：¥{price:.2f} | 涨幅：{change_pct:+.1f}% | 评分：{score:.2f}\n"
            if concepts:
                line += f"   概念：{', '.join(concepts[:3])}\n"
            if strongest_sector:
                line += f"   🏆 最强题材：{strongest_sector}\n"
            if position > 0:
                line += f"   💰 建议仓位：{position}%\n"
            stock_lines.append(line)
        
        stock_text = "\n".join(stock_lines)
        
        # 构建富文本消息
        message_content = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": f"📊 高涨幅股票筛选结果 (TOP{top_n})"
                }
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**筛选时间**: {now}\n**筛选条件**: 涨幅≥{min_change_pct}% | 主板股票\n**最强题材**: {top_stocks[0].get('strongest_sector', 'N/A') if top_stocks else 'N/A'}"
                    }
                },
                {
                    "tag": "divider"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": stock_text
                    }
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "⚠️ 投资有风险，以上结果仅供参考"
                        }
                    ]
                }
            ]
        }
        
        # 发送消息
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
                logger.info("飞书通知发送成功")
                return True
            else:
                logger.error(f"飞书通知发送失败：{send_data}")
                return False
        else:
            logger.error(f"飞书通知发送失败：{send_resp.text}")
            return False
            
    except Exception as e:
        logger.error(f"发送飞书通知失败：{e}")
        return False


def screen_limit_up_stocks(top_n: int = 5, min_change_pct: float = 7.0) -> List[Dict]:
    """
    执行 4 步筛选
    
    Args:
        top_n: 输出 TOP N 只股票，默认 5
        min_change_pct: 最小涨幅百分比，默认 7.0%
    """
    print("=" * 70)
    print(f"A 股高涨幅股票筛选工具 - 4 步筛选法 (TOP{top_n}, 涨幅>={min_change_pct}%)")
    print("=" * 70)
    print()
    
    # 步骤 1: 获取涨幅>=min_change_pct% 的股票列表（包含 300/688）
    high_change_stocks = get_high_change_stocks(min_change_pct=min_change_pct)
    if not high_change_stocks:
        print(f"❌ 未获取到涨幅>={min_change_pct}% 的股票数据")
        return []
    
    print(f"✅ 第 1 步：获取到 {len(high_change_stocks)} 只涨幅>={min_change_pct}% 的股票")
    
    # 步骤 2: 排除 300/688，只留主板
    main_board_stocks = [s for s in high_change_stocks if is_main_board(s['code'])]
    print(f"✅ 第 2 步：主板股票 {len(main_board_stocks)} 只（排除创业板/科创板）")
    
    if not main_board_stocks:
        print("❌ 没有符合条件的主板股票")
        return []
    
    # 步骤 3: 获取板块排行，找出最强题材
    top_sectors, bottom_sectors = get_sector_rankings()
    if top_sectors:
        print(f"✅ 第 3 步：今日最强题材 - {top_sectors[0].get('板块名称', '未知')} (+{top_sectors[0].get('涨跌幅', 0):.2f}%)")
    
    # 步骤 4: 批量获取量价数据并评分
    print("✅ 第 4 步：获取量价数据并评分...")
    codes = [s['code'] for s in main_board_stocks]
    quotes = get_batch_quotes(codes)
    
    # 合并数据
    quote_map = {q['code']: q for q in quotes}
    for stock in main_board_stocks:
        try:
            quote = quote_map.get(stock['code'], {})
            stock['amount'] = quote.get('amount', 0)
            stock['turnover_rate'] = quote.get('turnover_rate', 0)
            stock['volume_ratio'] = quote.get('volume_ratio', 1.0)
            
            # 题材匹配分析
            stock['sector_analysis'] = match_sector_strength(stock, top_sectors)
            stock['sector_score'] = stock['sector_analysis'].get('sector_score', 0)
            stock['concepts'] = stock['sector_analysis'].get('concepts', [])
            stock['strongest_sector'] = stock['sector_analysis'].get('strongest_sector', None)
            
            # 综合评分（含题材加成）
            stock['score'] = calculate_score(stock, include_sector=True)
        except Exception as e:
            stock['score'] = 0
            stock['sector_analysis'] = {}
            stock['concepts'] = []
            stock['strongest_sector'] = None
    
    # 按评分排序
    main_board_stocks.sort(key=lambda x: x['score'], reverse=True)
    
    # 步骤 5: 计算买入点、仓位、止损止盈
    print("✅ 第 5 步：计算买入点 + 仓位管理 + 止损止盈...")
    for stock in main_board_stocks:
        calculate_buy_point(stock)
    
    return main_board_stocks


def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='A 股高涨幅股票筛选工具 - 4 步筛选法')
    parser.add_argument('--top', '-n', type=int, default=5, 
                        help='输出 TOP N 只股票，默认 5')
    parser.add_argument('--min-change', '-c', type=float, default=7.0,
                        help='最小涨幅百分比，默认 7.0%%')
    parser.add_argument('--notify', action='store_true',
                        help='发送结果到飞书群')
    parser.add_argument('--no-detail', action='store_true',
                        help='仅输出简表，不显示详细分析')
    args = parser.parse_args()
    
    results = screen_limit_up_stocks(top_n=args.top, min_change_pct=args.min_change)
    
    if not results:
        print("\n筛选结果为空")
        return
    
    # 发送飞书通知（如果启用）
    if args.notify:
        print("\n📤 正在发送飞书通知...")
        if send_feishu_notification(results, args.top, args.min_change):
            print("✅ 飞书通知发送成功")
        else:
            print("❌ 飞书通知发送失败")
    
    # 如果仅输出简表，跳过详细分析
    if args.no_detail:
        print("\n✅ 筛选完成（简表模式）")
        return
    
    # 输出前 N 只（含买入点分析）
    print()
    print("=" * 70)
    print(f"📊 明日可能连板/涨停股票 TOP{args.top}")
    print("=" * 70)
    print()
    
    for i, stock in enumerate(results[:args.top], 1):
        print(f"{i}. {stock['name']}（{stock['code']}）")
        print(f"   当前价：¥{stock['price']:.2f}  |  涨跌幅：{stock['change_pct']:+.1f}%  |  评分：{stock['score']:.2f}")
        print(f"   成交额：{stock['amount']/10000:.2f}亿  |  换手率：{stock['turnover_rate']:.2f}%  |  量比：{stock['volume_ratio']:.2f}")
        
        # 题材信息
        concepts = stock.get('concepts', [])
        strongest_sector = stock.get('strongest_sector', None)
        sector_score = stock.get('sector_score', 0)
        if concepts:
            print(f"   概念：{', '.join(concepts[:3])}")
        if strongest_sector:
            print(f"   🏆 最强题材：{strongest_sector} (题材分：{sector_score:.1f})")
        print()
        
        # 买入点
        bp = stock.get('buy_point', {})
        print(f"   🟢 建仓方案（目标仓位 {bp.get('target_position', 0)}%）:")
        if bp.get('buy_1', {}).get('price', 0) > 0:
            print(f"      第 1 批：{bp['buy_1']['percent']}% @ ¥{bp['buy_1']['price']:.2f}")
        if bp.get('buy_2', {}).get('price', 0) > 0:
            print(f"      第 2 批：{bp['buy_2']['percent']}% @ ¥{bp['buy_2']['price']:.2f}")
        if bp.get('buy_3', {}).get('price', 0) > 0:
            print(f"      第 3 批：{bp['buy_3']['percent']}% @ ¥{bp['buy_3']['price']:.2f}")
        print()
        
        # 支撑/压力
        support = stock.get('support', [])
        resistance = stock.get('resistance', [])
        print(f"   📏 技术位:")
        print(f"      支撑位：¥{support[0]:.2f} → ¥{support[1]:.2f} → ¥{support[2]:.2f}")
        print(f"      压力位：¥{resistance[0]:.2f} → ¥{resistance[1]:.2f} → ¥{resistance[2]:.2f}")
        print()
        
        # 止损止盈
        sl = stock.get('stop_loss', {})
        tp = stock.get('take_profit', {})
        print(f"   🔴 止损：¥{sl.get('price', 0):.2f} (-{sl.get('percent', 0)}%)")
        print(f"   🟡 止盈：¥{tp.get('tp_1', 0):.2f} → ¥{tp.get('tp_2', 0):.2f} → ¥{tp.get('tp_3', 0):.2f}")
        print()
        print("-" * 70)
        print()
    
    # 完整表格（简化版）
    print("=" * 70)
    print(f"📋 完整筛选结果（共{len(results)}只）")
    print("=" * 70)
    print()
    print(f"{'排名':<4} {'代码':<8} {'名称':<10} {'价格':>8} {'涨幅%':>7} {'成交额亿':>10} {'换手%':>8} {'量比':>6} {'评分':>6} {'题材分':>6} {'仓位':>6}")
    print("-" * 70)
    
    for i, stock in enumerate(results, 1):
        bp = stock.get('buy_point', {})
        position = bp.get('target_position', 0)
        sector_score = stock.get('sector_score', 0)
        print(f"{i:<4} {stock['code']:<8} {stock['name']:<10} {stock['price']:>8.2f} {stock['change_pct']:>7.1f} {stock['amount']/10000:>10.2f} {stock['turnover_rate']:>8.2f} {stock['volume_ratio']:>6.2f} {stock['score']:>6.2f} {sector_score:>6.1f} {position:>5}%")


if __name__ == "__main__":
    main()
