#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
涨停股筛选系统 - 历史回测模块（DSA API 增强版）

使用 DSA API 获取历史数据，速度更快、数据更准确
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import requests

# 添加路径
sys.path.insert(0, os.path.dirname(__file__))
from backtest import BacktestEngine, CACHE_DIR

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# DSA API 配置
DSA_BASE_URL = "http://localhost:8001"
DSA_COOKIE_FILE = '/tmp/dsa_cookies.txt'


def load_dsa_cookie() -> str:
    """加载 DSA Cookie"""
    if os.path.exists(DSA_COOKIE_FILE):
        with open(DSA_COOKIE_FILE, 'r') as f:
            content = f.read()
            for line in content.split('\n'):
                if 'dsa_session' in line:
                    return line.split('\t')[-1]
    return ''


class DSABacktestEngine(BacktestEngine):
    """使用 DSA API 的回测引擎"""
    
    def __init__(self, start_date: str, end_date: str, initial_capital: float = 1000000):
        super().__init__(start_date, end_date, initial_capital)
        self.dsa_cookie = load_dsa_cookie()
        self.dsa_session = requests.Session()
        if self.dsa_cookie:
            self.dsa_session.cookies.set('dsa_session', self.dsa_cookie, domain='localhost')
            logger.info(f"DSA Cookie 加载成功：{self.dsa_cookie[:20]}...")
        else:
            logger.warning("未找到 DSA Cookie，部分接口可能无法访问")
    
    def get_stock_history_from_dsa(self, code: str, end_date: str, days: int = 90) -> List[Dict]:
        """
        从 DSA API 获取股票历史行情
        
        Args:
            code: 股票代码（不含前缀）
            end_date: 结束日期 (YYYY-MM-DD)
            days: 获取天数
        
        Returns:
            历史行情列表
        """
        try:
            # 检查缓存
            cache_key = f"dsa_hist_{code}_{end_date}_{days}".replace('/', '_')
            cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            
            # 调用 DSA API
            url = f"{DSA_BASE_URL}/api/v1/stocks/{code}/history"
            params = {
                'period': 'daily',
                'days': days
            }
            
            response = self.dsa_session.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.debug(f"DSA API 返回错误：{response.status_code}")
                return []
            
            data = response.json()
            
            if 'error' in data:
                logger.debug(f"DSA API 错误：{data['error']}")
                return []
            
            history_data = data.get('data', [])
            
            # 缓存
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, ensure_ascii=False)
            
            return history_data
            
        except Exception as e:
            logger.debug(f"获取{code}历史数据失败：{e}")
            return []
    
    def get_all_stocks_list(self) -> List[Dict]:
        """
        获取 A 股股票列表（主板）
        
        Returns:
            股票列表（代码、名称）
        """
        # 缓存股票列表
        cache_file = os.path.join(CACHE_DIR, "stock_list.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # 主板股票代码范围（简化版，实际应从 DSA 获取完整列表）
        stock_list = []
        
        # 沪市主板：600xxx, 601xxx, 603xxx, 605xxx
        for prefix in ['600', '601', '603', '605']:
            for i in range(1000):
                code = f"{prefix}{i:03d}"
                stock_list.append({
                    'code': code,
                    'full_code': f'sh{code}'
                })
        
        # 深市主板：000xxx, 001xxx, 002xxx, 003xxx
        for prefix in ['000', '001', '002', '003']:
            for i in range(1000):
                code = f"{prefix}{i:03d}"
                stock_list.append({
                    'code': code,
                    'full_code': f'sz{code}'
                })
        
        # 缓存
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(stock_list, f, ensure_ascii=False)
        
        logger.info(f"股票列表已加载：{len(stock_list)} 只")
        return stock_list
    
    def get_high_change_stocks_for_date(self, date: str, min_change_pct: float = 7.0) -> List[Dict]:
        """
        获取指定日期涨幅>=min_change_pct% 的股票
        
        Args:
            date: 日期 (YYYY-MM-DD)
            min_change_pct: 最小涨幅
        
        Returns:
            符合条件的股票列表
        """
        # 检查缓存
        cache_file = os.path.join(CACHE_DIR, f"hist_{date}.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        try:
            logger.info(f"获取 {date} 历史数据...")
            
            # 获取股票列表
            stock_list = self.get_all_stocks_list()
            
            # 采样测试（前 100 只，避免超时）
            # 实际使用应遍历全部股票
            sample_size = min(100, len(stock_list))
            test_stocks = stock_list[:sample_size]
            
            high_change_stocks = []
            
            for stock_info in test_stocks:
                code = stock_info['code']
                full_code = stock_info['full_code']
                
                # 获取历史数据（包含指定日期）
                history = self.get_stock_history_from_dsa(code, date, days=2)
                
                if not history or len(history) < 1:
                    continue
                
                # 查找指定日期的数据
                target_data = None
                for record in history:
                    if record.get('date') == date:
                        target_data = record
                        break
                
                if not target_data:
                    continue
                
                change_percent = target_data.get('change_percent', 0)
                
                # 筛选涨幅>=阈值的股票
                if change_percent >= min_change_pct:
                    high_change_stocks.append({
                        'code': full_code,
                        'name': target_data.get('stock_name', ''),
                        'price': target_data.get('close', 0),
                        'change_pct': change_percent,
                        'amount': target_data.get('amount', 0) / 10000,  # 转为万元
                        'turnover_rate': 0,  # DSA API 未提供，后续补充
                        'volume_ratio': 1.0,  # DSA API 未提供，后续补充
                        'date': date,
                    })
            
            # 保存到缓存
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(high_change_stocks, f, ensure_ascii=False)
            
            logger.info(f"获取到 {len(high_change_stocks)} 只涨幅>={min_change_pct}% 的股票")
            return high_change_stocks
            
        except Exception as e:
            logger.error(f"获取历史数据失败：{e}")
            return []
    
    def run_backtest(self, top_n: int = 5, min_change_pct: float = 7.0,
                     holding_days: int = 1, stop_loss_pct: float = -5.0,
                     take_profit_pct: float = 10.0, use_sample: bool = True) -> Dict:
        """
        执行回测（DSA API 版本）
        
        Args:
            use_sample: 是否使用采样模式（仅测试前 100 只股票）
        """
        logger.info(f"开始回测（DSA API）：TOP{top_n}, 涨幅>={min_change_pct}%, 持仓{holding_days}天")
        
        dates = self._generate_trading_dates(self.start_date, self.end_date)
        logger.info(f"交易日数：{len(dates)}")
        
        daily_returns = []
        win_count = 0
        loss_count = 0
        total_trades = 0
        
        for i, date in enumerate(dates[:-holding_days]):
            logger.info(f"回测进度：{i+1}/{len(dates)} - {date}")
            
            # 获取当日高涨幅股票
            stocks = self.get_high_change_stocks_for_date(date, min_change_pct)
            
            if len(stocks) < top_n:
                continue
            
            # 评分并排序（简化版）
            for stock in stocks:
                stock['score'] = self.calculate_score(stock)
            stocks.sort(key=lambda x: x['score'], reverse=True)
            
            # 买入 TOP N
            selected_stocks = stocks[:top_n]
            
            # 计算次日收益
            day_returns = []
            for stock in selected_stocks:
                # 获取次日数据
                next_date = self._get_next_trading_date(date)
                next_return = self._get_return_for_date(stock['code'], date, next_date)
                
                # 止损止盈处理
                if next_return <= stop_loss_pct:
                    actual_return = stop_loss_pct
                elif next_return >= take_profit_pct:
                    actual_return = take_profit_pct
                else:
                    actual_return = next_return
                
                day_returns.append(actual_return)
                
                total_trades += 1
                if actual_return > 0:
                    win_count += 1
                else:
                    loss_count += 1
                
                self.trades.append({
                    'date': date,
                    'code': stock['code'],
                    'name': stock['name'],
                    'return': actual_return,
                })
            
            if day_returns:
                avg_return = sum(day_returns) / len(day_returns)
                daily_returns.append({
                    'date': date,
                    'return': avg_return,
                })
        
        return self._calculate_metrics(daily_returns, win_count, loss_count, total_trades)
    
    def _get_next_trading_date(self, date: str) -> str:
        """获取下一个交易日（简化版，跳过周末）"""
        current = datetime.strptime(date, '%Y-%m-%d')
        while True:
            current += timedelta(days=1)
            if current.weekday() < 5:  # 周一到周五
                return current.strftime('%Y-%m-%d')
    
    def _get_return_for_date(self, code: str, start_date: str, end_date: str) -> float:
        """获取某股票在两个日期之间的收益率"""
        try:
            pure_code = code.replace('sh', '').replace('sz', '')
            history = self.get_stock_history_from_dsa(pure_code, end_date, days=5)
            
            if len(history) < 2:
                return 0
            
            # 查找起始和结束价格
            start_price = None
            end_price = None
            
            for record in history:
                if record.get('date') == start_date:
                    start_price = record.get('close', 0)
                if record.get('date') == end_date:
                    end_price = record.get('close', 0)
            
            if start_price and end_price and start_price > 0:
                return (end_price - start_price) / start_price * 100
            
            return 0
            
        except Exception as e:
            logger.debug(f"计算收益率失败：{e}")
            return 0


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='涨停股筛选系统 - DSA API 回测')
    parser.add_argument('--start', type=str, default='2025-10-01',
                        help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default='2025-10-31',
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
    parser.add_argument('--sample', action='store_true',
                        help='采样模式（仅测试前 100 只股票）')
    
    args = parser.parse_args()
    
    # 创建 DSA 回测引擎
    engine = DSABacktestEngine(
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
        take_profit_pct=args.take_profit,
        use_sample=args.sample
    )
    
    # 生成报告
    report = engine.generate_report(metrics)
    print(report)
    
    # 保存结果
    output_file = os.path.join(CACHE_DIR, f"dsa_backtest_result_{args.start}_{args.end}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"\n💾 回测结果已保存：{output_file}")


if __name__ == "__main__":
    main()
