#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测结果可视化

功能：
1. 绘制收益曲线
2. 月度收益分布
3. 年度收益对比
4. 回撤曲线
"""

import os
import sys
import json
import argparse
from datetime import datetime

# 检查 matplotlib
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("⚠️  未安装 matplotlib，使用文本模式输出")
    print("   安装：pip3 install matplotlib")


def load_backtest_result(file_path: str) -> dict:
    """加载回测结果"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def plot_text_mode(metrics: dict):
    """文本模式输出（无 matplotlib）"""
    daily_returns = metrics.get('daily_returns', [])
    
    if not daily_returns:
        print("❌ 无每日收益数据")
        return
    
    print("\n" + "=" * 70)
    print("📈 收益曲线（文本版）")
    print("=" * 70)
    
    # 计算累计收益
    cumulative = [1.0]
    for d in daily_returns:
        cumulative.append(cumulative[-1] * (1 + d['return']/100))
    
    # 采样显示（最多 50 个点）
    step = max(1, len(cumulative) // 50)
    sampled = cumulative[::step][:50]
    
    # 找到最大最小值
    max_val = max(sampled)
    min_val = min(sampled)
    range_val = max_val - min_val if max_val != min_val else 1
    
    # 绘制 ASCII 图表
    height = 15
    width = 60
    
    print()
    for row in range(height, -1, -1):
        threshold = min_val + (row / height) * range_val
        line = f"{threshold:7.2f} │"
        for val in sampled[:width]:
            if val >= threshold:
                line += "█"
            else:
                line += " "
        print(line)
    
    # X 轴
    print(" " * 8 + "└" + "─" * min(len(sampled), width))
    print(" " * 8 + f"  {daily_returns[0]['date']} {' ' * 40} {daily_returns[-1]['date']}")


def plot_charts(metrics: dict, output_dir: str):
    """绘制图表（需要 matplotlib）"""
    os.makedirs(output_dir, exist_ok=True)
    
    daily_returns = metrics.get('daily_returns', [])
    if not daily_returns:
        print("❌ 无每日收益数据")
        return
    
    # 设置中文字体
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    
    # 1. 收益曲线
    fig, ax = plt.subplots(figsize=(12, 6))
    
    dates = [d['date'] for d in daily_returns]
    returns = [d['return'] for d in daily_returns]
    
    # 累计收益
    cumulative = [1.0]
    for r in returns:
        cumulative.append(cumulative[-1] * (1 + r/100))
    
    ax.plot(dates, cumulative[1:], linewidth=1.5, color='#2196F3')
    ax.fill_between(dates, cumulative[1:], alpha=0.3, color='#2196F3')
    
    ax.set_title('累计收益曲线', fontsize=14, fontweight='bold')
    ax.set_xlabel('日期')
    ax.set_ylabel('累计收益率')
    ax.grid(True, alpha=0.3)
    
    # 旋转日期标签
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    output_file = os.path.join(output_dir, 'cumulative_return.png')
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ 收益曲线已保存：{output_file}")
    
    # 2. 月度收益分布
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # 月度收益
    monthly_returns = {}
    for d in daily_returns:
        month = d['date'][:7]  # YYYY-MM
        if month not in monthly_returns:
            monthly_returns[month] = []
        monthly_returns[month].append(d['return'])
    
    monthly_avg = {k: sum(v)/len(v) for k, v in monthly_returns.items()}
    
    ax1 = axes[0]
    months = list(monthly_avg.keys())
    values = list(monthly_avg.values())
    
    colors = ['#4CAF50' if v > 0 else '#F44336' for v in values]
    ax1.bar(range(len(months)), values, color=colors, alpha=0.7)
    ax1.set_title('月度平均收益', fontsize=12, fontweight='bold')
    ax1.set_xlabel('月份')
    ax1.set_ylabel('收益率%')
    ax1.set_xticks(range(len(months)))
    ax1.set_xticklabels(months, rotation=45)
    ax1.grid(True, alpha=0.3, axis='y')
    
    # 收益分布直方图
    ax2 = axes[1]
    ax2.hist(returns, bins=30, color='#9C27B0', alpha=0.7, edgecolor='black')
    ax2.axvline(x=0, color='red', linestyle='--', linewidth=2)
    ax2.set_title('日收益分布', fontsize=12, fontweight='bold')
    ax2.set_xlabel('收益率%')
    ax2.set_ylabel('频数')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    output_file = os.path.join(output_dir, 'monthly_distribution.png')
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ 月度分布图已保存：{output_file}")
    
    # 3. 回撤曲线
    fig, ax = plt.subplots(figsize=(12, 5))
    
    # 计算回撤
    cumulative = [1.0]
    for r in returns:
        cumulative.append(cumulative[-1] * (1 + r/100))
    
    drawdowns = []
    peak = cumulative[0]
    for value in cumulative:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak * 100
        drawdowns.append(drawdown)
    
    ax.fill_between(range(len(drawdowns)), 0, drawdowns[1:], color='#F44336', alpha=0.5)
    ax.set_title('回撤曲线', fontsize=14, fontweight='bold')
    ax.set_xlabel('交易日')
    ax.set_ylabel('回撤%')
    ax.grid(True, alpha=0.3)
    
    output_file = os.path.join(output_dir, 'drawdown.png')
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ 回撤曲线已保存：{output_file}")


def main():
    parser = argparse.ArgumentParser(description='回测结果可视化')
    parser.add_argument('result_file', type=str, help='回测结果 JSON 文件')
    parser.add_argument('--output', '-o', type=str, default='backtest_charts',
                        help='输出目录')
    parser.add_argument('--text', action='store_true',
                        help='仅文本模式（不使用 matplotlib）')
    
    args = parser.parse_args()
    
    # 加载结果
    print(f"📂 加载回测结果：{args.result_file}")
    metrics = load_backtest_result(args.result_file)
    
    if 'error' in metrics:
        print(f"❌ 回测结果错误：{metrics['error']}")
        return
    
    # 输出目录
    output_dir = args.output
    
    if args.text or not HAS_MATPLOTLIB:
        # 文本模式
        plot_text_mode(metrics)
    else:
        # 图表模式
        print(f"📊 生成图表...")
        plot_charts(metrics, output_dir)
        print(f"\n✅ 图表已保存到：{output_dir}/")
    
    # 显示关键指标
    print("\n" + "=" * 70)
    print("📊 关键指标速览")
    print("=" * 70)
    print(f"总收益率：    {metrics.get('total_return', 0):>10.2f}%")
    print(f"年化收益：    {metrics.get('annual_return', 0):>10.2f}%")
    print(f"最大回撤：    {metrics.get('max_drawdown', 0):>10.2f}%")
    print(f"夏普比率：    {metrics.get('sharpe_ratio', 0):>10.2f}")
    print(f"胜率：        {metrics.get('win_rate', 0):>10.2f}%")
    print(f"盈亏比：      {metrics.get('profit_loss_ratio', 0):>10.2f}")
    print("=" * 70)


if __name__ == "__main__":
    main()
