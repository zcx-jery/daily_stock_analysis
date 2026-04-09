#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测演示脚本 - 使用模拟数据快速验证回测功能

说明：
- 使用随机生成的模拟数据
- 快速验证回测引擎和可视化功能
- 实际使用时请替换为真实历史数据
"""

import os
import sys
import json
import random
from datetime import datetime, timedelta

# 添加路径
SCRIPT_DIR = os.path.dirname(__file__)
sys.path.insert(0, SCRIPT_DIR)

from backtest import BacktestEngine, CACHE_DIR


class DemoBacktestEngine(BacktestEngine):
    """演示回测引擎（使用模拟数据）"""
    
    def get_historical_high_change_stocks(self, date: str, min_change_pct: float = 7.0) -> list:
        """模拟获取历史高涨幅股票"""
        # 生成 10-30 只模拟股票
        num_stocks = random.randint(10, 30)
        stocks = []
        
        stock_names = [
            "贵州茅台", "宁德时代", "比亚迪", "中国平安", "招商银行",
            "五粮液", "东方财富", "恒瑞医药", "中信证券", "兴业银行",
            "万科 A", "立讯精密", "美的集团", "海天味业", "药明康德",
        ]
        
        for i in range(num_stocks):
            code_prefix = random.choice(['sh600', 'sh601', 'sz000', 'sz002'])
            code_suffix = ''.join(random.choices('0123456789', k=3))
            
            stocks.append({
                'code': f"{code_prefix}{code_suffix}",
                'name': random.choice(stock_names),
                'change_pct': random.uniform(min_change_pct, 12.0),
                'price': random.uniform(10, 500),
                'date': date,
                'amount': random.uniform(10000, 500000),  # 万元
            })
        
        return stocks
    
    def get_next_day_return(self, code: str, date: str) -> float:
        """模拟次日收益率"""
        # 检查缓存
        cache_key = f"return_{code}_{date}".replace('/', '_')
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('return', 0)
        
        # 模拟收益率（正态分布，均值 0.5%，标准差 3%）
        next_day_return = random.gauss(0.5, 3.0)
        
        # 缓存
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({'return': next_day_return}, f)
        
        return next_day_return


def main():
    """演示回测主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='涨停股筛选系统 - 回测演示（模拟数据）')
    parser.add_argument('--start', type=str, default='2025-01-01',
                        help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2025-03-31',
                        help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--top', '-n', type=int, default=5,
                        help='每日买入 TOP N 只')
    parser.add_argument('--min-change', '-c', type=float, default=7.0,
                        help='最小涨幅%')
    parser.add_argument('--holding-days', type=int, default=1,
                        help='持仓天数')
    parser.add_argument('--stop-loss', type=float, default=-5.0,
                        help='止损%')
    parser.add_argument('--take-profit', type=float, default=10.0,
                        help='止盈%')
    parser.add_argument('--capital', type=float, default=1000000,
                        help='初始资金')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🎭 回测演示模式（使用模拟数据）")
    print("=" * 70)
    print()
    print(f"回测区间：{args.start} ~ {args.end}")
    print(f"初始资金：{args.capital:,.0f}")
    print()
    print("⚠️  注意：本演示使用模拟数据，实际收益请以真实回测为准")
    print()
    
    # 创建演示回测引擎
    engine = DemoBacktestEngine(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital
    )
    
    # 执行回测
    metrics = engine.run_backtest(
        top_n=args.top,
        min_change_pct=args.min_change,
        holding_days=args.holding_days,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit
    )
    
    # 生成报告
    report = engine.generate_report(metrics)
    print(report)
    
    # 保存结果
    output_file = os.path.join(CACHE_DIR, f"demo_backtest_result_{args.start}_{args.end}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"\n💾 回测结果已保存：{output_file}")
    
    # 提示可视化
    print()
    print("=" * 70)
    print("📊 可视化命令:")
    print("=" * 70)
    print(f"python3 visualize_backtest.py {output_file}")
    print()


if __name__ == "__main__":
    main()
