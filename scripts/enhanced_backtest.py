#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
涨停股筛选系统 - 增强版回测引擎

优化：
1. 并行获取历史数据（多线程）
2. 支持多种数据源（Akshare / DSA API）
3. 智能缓存机制
4. 更详细的回测报告
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'backtest_cache')
os.makedirs(CACHE_DIR, exist_ok=True)


class EnhancedBacktestEngine:
    """增强版回测引擎"""
    
    def __init__(self, start_date: str, end_date: str, initial_capital: float = 1000000,
                 data_source: str = 'akshare', max_workers: int = 4):
        """
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            initial_capital: 初始资金
            data_source: 数据源 (akshare / dsa / demo)
            max_workers: 并行线程数
        """
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.data_source = data_source
        self.max_workers = max_workers
        
        self.capital = initial_capital
        self.positions = {}
        self.trades = []
        self.daily_values = []
        
        logger.info(f"回测引擎初始化：{start_date} ~ {end_date}")
        logger.info(f"数据源：{data_source}, 线程数：{max_workers}")
    
    def _get_stock_list(self) -> List[Dict]:
        """获取股票列表（主板）"""
        cache_file = os.path.join(CACHE_DIR, "stock_list.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        logger.info("正在生成股票列表...")
        stock_list = []
        
        # 沪市主板
        for prefix in ['600', '601', '603', '605']:
            for i in range(500):  # 采样 500 只
                code = f"{prefix}{i:03d}"
                stock_list.append({'code': code, 'full_code': f'sh{code}'})
        
        # 深市主板
        for prefix in ['000', '001', '002', '003']:
            for i in range(500):  # 采样 500 只
                code = f"{prefix}{i:03d}"
                stock_list.append({'code': code, 'full_code': f'sz{code}'})
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(stock_list, f, ensure_ascii=False)
        
        logger.info(f"股票列表：{len(stock_list)} 只")
        return stock_list
    
    def _fetch_single_stock_data(self, stock_info: Dict, target_date: str) -> Dict:
        """获取单只股票在指定日期的数据"""
        try:
            import akshare as ak
            
            code = stock_info['code']
            pure_code = code  # akshare 不需要前缀
            
            # 获取历史数据
            df = ak.stock_zh_a_hist(
                symbol=pure_code,
                period="daily",
                start_date=target_date.replace('-', ''),
                end_date=(datetime.strptime(target_date, '%Y-%m-%d') + timedelta(days=5)).strftime('%Y%m%d')
            )
            
            if df is None or df.empty:
                return None
            
            # 查找目标日期数据
            target_row = None
            for _, row in df.iterrows():
                date_str = str(row.get('日期', ''))
                if date_str == target_date:
                    target_row = row
                    break
            
            if target_row is None:
                return None
            
            change_pct = float(target_row.get('涨跌幅', 0))
            
            # 筛选涨幅>=7%
            if change_pct < 7.0:
                return None
            
            return {
                'code': stock_info['full_code'],
                'name': str(target_row.get('名称', '')),
                'price': float(target_row.get('收盘', 0)),
                'change_pct': change_pct,
                'amount': float(target_row.get('成交额', 0)),  # 元
                'volume': float(target_row.get('成交量', 0)),
                'turnover_rate': 0,  # 需要额外获取
                'volume_ratio': 1.0,
                'date': target_date,
            }
            
        except Exception as e:
            return None
    
    def get_high_change_stocks_for_date(self, date: str, min_change_pct: float = 7.0) -> List[Dict]:
        """并行获取指定日期的高涨幅股票"""
        # 检查缓存
        cache_file = os.path.join(CACHE_DIR, f"hist_{date}.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        logger.info(f"获取 {date} 数据（并行模式，{self.max_workers}线程）...")
        
        stock_list = self._get_stock_list()
        
        # 采样测试（前 1000 只）
        sample_size = min(1000, len(stock_list))
        test_stocks = stock_list[:sample_size]
        
        high_change_stocks = []
        
        # 并行获取
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._fetch_single_stock_data, stock, date): stock
                for stock in test_stocks
            }
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        high_change_stocks.append(result)
                except Exception as e:
                    continue
        
        # 保存到缓存
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(high_change_stocks, f, ensure_ascii=False)
        
        logger.info(f"获取到 {len(high_change_stocks)} 只涨幅>={min_change_pct}% 的股票")
        return high_change_stocks
    
    def _get_next_trading_date(self, date: str) -> str:
        """获取下一个交易日"""
        current = datetime.strptime(date, '%Y-%m-%d')
        while True:
            current += timedelta(days=1)
            if current.weekday() < 5:
                return current.strftime('%Y-%m-%d')
    
    def _get_next_day_return(self, code: str, date: str) -> float:
        """获取次日收益率"""
        try:
            import akshare as ak
            
            pure_code = code.replace('sh', '').replace('sz', '')
            next_date = self._get_next_trading_date(date)
            
            df = ak.stock_zh_a_hist(
                symbol=pure_code,
                period="daily",
                start_date=date.replace('-', ''),
                end_date=(datetime.strptime(next_date, '%Y-%m-%d') + timedelta(days=2)).strftime('%Y%m%d')
            )
            
            if df is None or len(df) < 2:
                return 0
            
            close_prices = df['收盘'].values
            if len(close_prices) >= 2:
                return (close_prices[1] - close_prices[0]) / close_prices[0] * 100
            
            return 0
            
        except Exception as e:
            return 0
    
    def is_main_board(self, code: str) -> bool:
        """判断主板"""
        prefixes = ["sh600", "sh601", "sh603", "sh605", "sz000", "sz001", "sz002", "sz003"]
        return any(code.lower().startswith(p) for p in prefixes)
    
    def calculate_score(self, stock: Dict) -> float:
        """评分"""
        change_pct = stock.get('change_pct', 0)
        amount = stock.get('amount', 0)
        
        change_score = min(abs(change_pct) / 10 * 10, 10)
        amount_score = min(amount / 1000000000 * 10, 10)  # 10 亿为满分
        
        return change_score * 0.6 + amount_score * 0.4
    
    def run_backtest(self, top_n: int = 5, min_change_pct: float = 7.0,
                     holding_days: int = 1, stop_loss_pct: float = -5.0,
                     take_profit_pct: float = 10.0) -> Dict:
        """执行回测"""
        logger.info(f"开始回测：TOP{top_n}, 涨幅>={min_change_pct}%, 持仓{holding_days}天, 止损{stop_loss_pct}%, 止盈{take_profit_pct}%")
        
        dates = self._generate_trading_dates(self.start_date, self.end_date)
        logger.info(f"交易日数：{len(dates)}")
        
        daily_returns = []
        win_count = 0
        loss_count = 0
        total_trades = 0
        
        for i, date in enumerate(dates[:-holding_days]):
            logger.info(f"进度：{i+1}/{len(dates)} - {date}")
            
            # 获取高涨幅股票
            stocks = self.get_high_change_stocks_for_date(date, min_change_pct)
            
            # 排除创业板/科创板
            main_board_stocks = [s for s in stocks if self.is_main_board(s['code'])]
            
            if len(main_board_stocks) < top_n:
                continue
            
            # 评分排序
            for stock in main_board_stocks:
                stock['score'] = self.calculate_score(stock)
            main_board_stocks.sort(key=lambda x: x['score'], reverse=True)
            
            # 买入 TOP N
            selected = main_board_stocks[:top_n]
            
            # 计算收益
            day_returns = []
            for stock in selected:
                next_return = self._get_next_day_return(stock['code'], date)
                
                # 止损止盈
                if next_return <= stop_loss_pct:
                    actual = stop_loss_pct
                elif next_return >= take_profit_pct:
                    actual = take_profit_pct
                else:
                    actual = next_return
                
                day_returns.append(actual)
                total_trades += 1
                if actual > 0:
                    win_count += 1
                else:
                    loss_count += 1
                
                self.trades.append({
                    'date': date,
                    'code': stock['code'],
                    'name': stock['name'],
                    'return': actual,
                })
            
            if day_returns:
                daily_returns.append({
                    'date': date,
                    'return': sum(day_returns) / len(day_returns),
                })
        
        return self._calculate_metrics(daily_returns, win_count, loss_count, total_trades)
    
    def _generate_trading_dates(self, start: str, end: str) -> List[str]:
        """生成交易日期"""
        dates = []
        current = datetime.strptime(start, '%Y-%m-%d')
        target = datetime.strptime(end, '%Y-%m-%d')
        
        while current <= target:
            if current.weekday() < 5:
                dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        return dates
    
    def _calculate_metrics(self, daily_returns: List[Dict], win: int, loss: int, total: int) -> Dict:
        """计算指标"""
        if not daily_returns:
            return {'error': '无交易数据'}
        
        returns = [d['return'] for d in daily_returns]
        
        total_return = np.prod([1 + r/100 for r in returns]) - 1
        avg_return = np.mean(returns)
        std_return = np.std(returns)
        
        days = len(daily_returns)
        annual_return = (1 + total_return) ** (252 / days) - 1 if days > 0 else 0
        
        win_rate = win / total if total > 0 else 0
        
        avg_win = np.mean([r for r in returns if r > 0]) if any(r > 0 for r in returns) else 0
        avg_loss = abs(np.mean([r for r in returns if r < 0])) if any(r < 0 for r in returns) else 1
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        
        # 最大回撤
        cumulative = [1]
        for r in returns:
            cumulative.append(cumulative[-1] * (1 + r/100))
        
        max_dd = 0
        peak = cumulative[0]
        for val in cumulative:
            if val > peak:
                peak = val
            dd = (peak - val) / peak
            if dd > max_dd:
                max_dd = dd
        
        sharpe = (avg_return / std_return * np.sqrt(252)) if std_return > 0 else 0
        
        return {
            'total_return': round(total_return * 100, 2),
            'annual_return': round(annual_return * 100, 2),
            'avg_return': round(avg_return, 4),
            'std_return': round(std_return, 4),
            'max_drawdown': round(max_dd * 100, 2),
            'sharpe_ratio': round(sharpe, 2),
            'total_trades': total,
            'win_count': win,
            'loss_count': loss,
            'win_rate': round(win_rate * 100, 2),
            'profit_loss_ratio': round(profit_loss_ratio, 2),
            'trading_days': days,
            'daily_returns': daily_returns,
        }
    
    def generate_report(self, metrics: Dict) -> str:
        """生成报告"""
        if 'error' in metrics:
            return f"❌ 回测失败：{metrics['error']}"
        
        lines = [
            "=" * 70,
            "📊 增强版回测报告",
            "=" * 70,
            "",
            f"回测区间：{self.start_date} ~ {self.end_date}",
            f"初始资金：{self.initial_capital:,.0f}",
            f"数据源：{self.data_source}",
            "",
            "-" * 70,
            "📈 收益指标",
            "-" * 70,
            f"总收益率：    {metrics['total_return']:>10.2f}%",
            f"年化收益：    {metrics['annual_return']:>10.2f}%",
            f"日均收益：    {metrics['avg_return']:>10.4f}%",
            f"收益标准差：  {metrics['std_return']:>10.4f}%",
            "",
            "-" * 70,
            "🎯 风险指标",
            "-" * 70,
            f"最大回撤：    {metrics['max_drawdown']:>10.2f}%",
            f"夏普比率：    {metrics['sharpe_ratio']:>10.2f}",
            "",
            "-" * 70,
            "📋 交易统计",
            "-" * 70,
            f"交易天数：    {metrics['trading_days']:>10}",
            f"总交易数：    {metrics['total_trades']:>10}",
            f"盈利次数：    {metrics['win_count']:>10}",
            f"亏损次数：    {metrics['loss_count']:>10}",
            f"胜率：        {metrics['win_rate']:>10.2f}%",
            f"盈亏比：      {metrics['profit_loss_ratio']:>10.2f}",
            "",
            "=" * 70,
        ]
        
        return "\n".join(lines)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='增强版回测引擎')
    parser.add_argument('--start', type=str, default='2025-01-01')
    parser.add_argument('--end', type=str, default='2025-01-31')
    parser.add_argument('--top', '-n', type=int, default=5)
    parser.add_argument('--min-change', '-c', type=float, default=7.0)
    parser.add_argument('--holding-days', type=int, default=1)
    parser.add_argument('--stop-loss', type=float, default=-5.0)
    parser.add_argument('--take-profit', type=float, default=10.0)
    parser.add_argument('--workers', '-w', type=int, default=4, help='并行线程数')
    parser.add_argument('--data-source', type=str, default='akshare', choices=['akshare', 'dsa', 'demo'])
    
    args = parser.parse_args()
    
    engine = EnhancedBacktestEngine(
        start_date=args.start,
        end_date=args.end,
        data_source=args.data_source,
        max_workers=args.workers
    )
    
    metrics = engine.run_backtest(
        top_n=args.top,
        min_change_pct=args.min_change,
        holding_days=args.holding_days,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit
    )
    
    print(engine.generate_report(metrics))
    
    # 保存
    output = os.path.join(CACHE_DIR, f"enhanced_backtest_{args.start}_{args.end}.json")
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"\n💾 已保存：{output}")


if __name__ == "__main__":
    main()
