#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
涨停股筛选工具 - 按 4 步筛选法
1. 题材分析（含 300/688）→ 找出市场最强题材
2. 股票筛选（排除 300/688）→ 只选主板
3. 强题材优先 → 在强题材中选主板龙头
4. 量价配合评分 → 涨幅 + 量能 + 换手综合排序
"""

import requests
import re
from typing import List, Dict, Tuple

# 腾讯行情 API
TENCENT_API = "http://qt.gtimg.cn/q="

# 股票池（示例：热门股票，实际使用时应替换为当日涨幅榜/涨停股列表）
STOCK_POOL = [
    # 主板股票（600/601/603/605/000/001/002/003）
    "sh600519",  # 贵州茅台
    "sh603629",  # 利通电子
    "sz002384",  # 东山精密
    "sz000001",  # 平安银行
    "sh601318",  # 中国平安
    "sh600030",  # 中信证券
    "sh601166",  # 兴业银行
    "sz000063",  # 中兴通讯
    "sh600271",  # 航天信息
    "sz002594",  # 比亚迪
    "sh601888",  # 中国中免
    "sh603259",  # 药明康德
    # 创业板（300开头）- 用于题材分析
    "sz300750",  # 宁德时代
    # 科创板（688 开头）- 用于题材分析
    "sh688981",  # 中芯国际
]

# 主板前缀
MAIN_BOARD_PREFIXES = ["sh600", "sh601", "sh603", "sh605", "sz000", "sz001", "sz002", "sz003"]


def parse_tencent_data(raw_text: bytes) -> List[Dict]:
    """解析腾讯 API 返回的数据"""
    stocks = []
    # 先按 GBK 解码整个响应
    text = raw_text.decode('gbk', errors='ignore')
    lines = text.strip().split("\n")
    
    for line in lines:
        if not line.startswith("v_"):
            continue
        
        # 提取引号内的数据
        match = re.search(r'"([^"]+)"', line)
        if not match:
            continue
        
        values = match.group(1).split("~")
        if len(values) < 35:
            continue
        
        # 提取关键字段
        try:
            code_raw = values[2]
            # 添加前缀
            if code_raw.startswith('6') or code_raw.startswith('9'):
                code = f'sh{code_raw}'
            else:
                code = f'sz{code_raw}'
            name = values[1]
            current_price = float(values[3])
            prev_close = float(values[4])
            # 腾讯 API 字段解析（修正版）
            # 31:涨跌额 32:涨跌幅% 33:最高 34:最低 37:成交额 (万元) 38:量比 43:换手率%
            high = float(values[33]) if len(values) > 33 and values[33] else current_price
            low = float(values[34]) if len(values) > 34 and values[34] else current_price
            volume = int(values[36]) if len(values) > 36 and values[36] else 0  # 成交量（手）
            amount = float(values[37]) if len(values) > 37 and values[37] else 0  # 成交金额（万元）
            
            # 涨跌幅和涨跌额
            change = float(values[31]) if len(values) > 31 and values[31] else (current_price - prev_close)
            change_percent = float(values[32]) if len(values) > 32 and values[32] else ((current_price - prev_close) / prev_close * 100)
            
            # 换手率（直接读取）
            turnover_rate = float(values[43]) if len(values) > 43 and values[43] else 0
            
            # 量比
            volume_ratio = float(values[41]) if len(values) > 41 and values[41] else 1.0
            
            stocks.append({
                "code": code,
                "name": name,
                "price": current_price,
                "change": change,
                "change_percent": change_percent,
                "high": high,
                "low": low,
                "volume": volume,
                "amount": amount,
                "turnover_rate": turnover_rate,
                "volume_ratio": volume_ratio,
            })
        except (ValueError, IndexError) as e:
            print(f"解析失败 {line[:50]}: {e}")
            continue
    
    return stocks


def is_main_board(code: str) -> bool:
    """判断是否为主板股票（排除 300/688）"""
    code_lower = code.lower()
    for prefix in MAIN_BOARD_PREFIXES:
        if code_lower.startswith(prefix):
            return True
    return False


def calculate_score(stock: Dict) -> float:
    """
    量价配合评分
    评分维度：
    1. 涨幅（30%）- 今日涨幅
    2. 量能（30%）- 成交额
    3. 换手（20%）- 换手率
    4. 量比（20%）- 量比
    """
    # 涨幅评分（0-10 分）
    change_score = min(abs(stock["change_percent"]) / 10 * 10, 10)
    
    # 量能评分（0-10 分）- 以 10 亿为满分
    amount_score = min(stock["amount"] / 100000 * 10, 10)
    
    # 换手评分（0-10 分）- 5%-15% 为最佳
    turnover = stock["turnover_rate"]
    if 5 <= turnover <= 15:
        turnover_score = 10
    elif turnover < 5:
        turnover_score = turnover / 5 * 10
    else:
        turnover_score = max(10 - (turnover - 15) / 10 * 10, 0)
    
    # 量比评分（0-10 分）- 1.5-3.0 为最佳
    volume_ratio = stock["volume_ratio"]
    if 1.5 <= volume_ratio <= 3.0:
        volume_ratio_score = 10
    elif volume_ratio < 1.5:
        volume_ratio_score = volume_ratio / 1.5 * 10
    else:
        volume_ratio_score = max(10 - (volume_ratio - 3.0) / 5 * 10, 0)
    
    # 加权总分
    total_score = (
        change_score * 0.3 +
        amount_score * 0.3 +
        turnover_score * 0.2 +
        volume_ratio_score * 0.2
    )
    
    return round(total_score, 2)


def screen_stocks(stock_pool: List[str] = None) -> List[Dict]:
    """执行筛选"""
    if stock_pool is None:
        stock_pool = STOCK_POOL
    
    # 批量获取数据
    query = ",".join(stock_pool)
    url = f"{TENCENT_API}{query}"
    
    print(f"正在获取 {len(stock_pool)} 只股票数据...")
    response = requests.get(url, timeout=10)
    
    if response.status_code != 200:
        print(f"获取数据失败：{response.status_code}")
        return []
    
    # 解析数据（使用原始 bytes，避免编码问题）
    stocks = parse_tencent_data(response.content)
    print(f"成功获取 {len(stocks)} 只股票数据")
    
    # 步骤 1&2: 题材分析（全市场）+ 筛选主板
    main_board_stocks = [s for s in stocks if is_main_board(s["code"])]
    print(f"主板股票：{len(main_board_stocks)} 只")
    
    # 步骤 3: 强题材优先（这里简化为按行业/概念筛选，实际需要题材数据）
    # 暂按涨幅排序，取前 50%
    main_board_stocks.sort(key=lambda x: x["change_percent"], reverse=True)
    strong_stocks = main_board_stocks[:max(len(main_board_stocks) // 2, 1)]
    print(f"强势股票：{len(strong_stocks)} 只")
    
    # 步骤 4: 量价配合评分
    for stock in strong_stocks:
        stock["score"] = calculate_score(stock)
    
    # 按评分排序
    strong_stocks.sort(key=lambda x: x["score"], reverse=True)
    
    return strong_stocks


def main():
    """主函数"""
    print("=" * 70)
    print("A 股涨停股筛选工具 - 4 步筛选法")
    print("=" * 70)
    print()
    
    # 执行筛选
    results = screen_stocks()
    
    if not results:
        print("筛选结果为空")
        return
    
    # 输出前 5 只
    print()
    print("=" * 70)
    print("📊 明日可能涨停股票 TOP5")
    print("=" * 70)
    print()
    
    for i, stock in enumerate(results[:5], 1):
        print(f"{i}. {stock['name']}（{stock['code']}）")
        print(f"   当前价：¥{stock['price']:.2f}")
        print(f"   涨跌幅：{stock['change_percent']:+.2f}%")
        print(f"   成交额：{stock['amount']/10000:.2f}亿")
        print(f"   换手率：{stock['turnover_rate']:.2f}%")
        print(f"   量比：{stock['volume_ratio']:.2f}")
        print(f"   综合评分：{stock['score']:.2f}")
        print()
    
    # 完整表格
    print("=" * 70)
    print("📋 完整筛选结果")
    print("=" * 70)
    print()
    print(f"{'排名':<4} {'代码':<8} {'名称':<10} {'价格':>8} {'涨幅%':>8} {'成交额亿':>10} {'换手%':>8} {'量比':>6} {'评分':>6}")
    print("-" * 70)
    
    for i, stock in enumerate(results, 1):
        print(f"{i:<4} {stock['code']:<8} {stock['name']:<10} {stock['price']:>8.2f} {stock['change_percent']:>+8.2f} {stock['amount']/10000:>10.2f} {stock['turnover_rate']:>8.2f} {stock['volume_ratio']:>6.2f} {stock['score']:>6.2f}")


if __name__ == "__main__":
    main()
