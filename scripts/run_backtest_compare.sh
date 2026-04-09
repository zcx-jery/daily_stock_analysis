#!/bin/bash
#
# 快速回测示例 - 测试不同参数组合
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_DIR="$SCRIPT_DIR/backtest_cache"

echo "=========================================="
echo "  涨停股筛选系统 - 参数回测对比"
echo "=========================================="
echo

# 创建输出目录
mkdir -p "$CACHE_DIR/compare_results"

# 参数组合
declare -a STRATEGIES=(
    "激进策略:--top 3 --min-change 9.0 --stop-loss -8.0 --take-profit 15.0"
    "稳健策略:--top 5 --min-change 7.0 --stop-loss -5.0 --take-profit 10.0"
    "保守策略:--top 10 --min-change 5.0 --stop-loss -3.0 --take-profit 8.0"
)

# 回测区间
START_DATE="2025-01-01"
END_DATE="2025-06-30"

echo "回测区间：$START_DATE ~ $END_DATE"
echo "策略数量：${#STRATEGIES[@]}"
echo

# 运行回测
results=()
for strategy_info in "${STRATEGIES[@]}"; do
    IFS=':' read -r name params <<< "$strategy_info"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 运行策略：$name"
    echo "   参数：$params"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    output_file="$CACHE_DIR/compare_results/backtest_${name// /_}.json"
    
    python3 "$SCRIPT_DIR/backtest.py" \
        --start "$START_DATE" \
        --end "$END_DATE" \
        $params \
        > "$CACHE_DIR/compare_results/report_${name// /_}.txt" 2>&1
    
    # 提取关键指标
    if [ -f "$output_file" ]; then
        total_return=$(python3 -c "import json; d=json.load(open('$output_file')); print(d.get('total_return', 'N/A'))")
        sharpe=$(python3 -c "import json; d=json.load(open('$output_file')); print(d.get('sharpe_ratio', 'N/A'))")
        max_dd=$(python3 -c "import json; d=json.load(open('$output_file')); print(d.get('max_drawdown', 'N/A'))")
        win_rate=$(python3 -c "import json; d=json.load(open('$output_file')); print(d.get('win_rate', 'N/A'))")
        
        results+=("$name|$total_return|$sharpe|$max_dd|$win_rate")
        echo "✅ 完成：总收益 ${total_return}%, 夏普 ${sharpe}, 回撤 ${max_dd}%"
    else
        echo "❌ 回测失败"
    fi
    echo
done

# 汇总对比
echo "=========================================="
echo "  📊 策略对比汇总"
echo "=========================================="
echo
printf "%-10s %12s %10s %12s %10s\n" "策略" "总收益%" "夏普" "最大回撤%" "胜率%"
echo "----------------------------------------------------------------------"

for result in "${results[@]}"; do
    IFS='|' read -r name total_return sharpe max_dd win_rate <<< "$result"
    printf "%-10s %12s %10s %12s %10s\n" "$name" "$total_return" "$sharpe" "$max_dd" "$win_rate"
done

echo
echo "=========================================="
echo "  ✅ 对比完成"
echo "=========================================="
echo
echo "详细报告保存在：$CACHE_DIR/compare_results/"
echo
