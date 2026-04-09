#!/usr/bin/env python3
"""
获取全市场涨幅大于 X% 的 TopN 股票
使用腾讯财经 API（免 Token）
"""

import requests
import json
import sys
from datetime import datetime

# 扩展 A 股代码列表（沪深 300+ 部分热门股票）
A_STOCKS = [
    # 沪市主板
    *[f"sh{code}" for code in [
        "600519", "603629", "600036", "601318", "600030", "601888", "601012", "600276", 
        "600887", "601166", "600000", "601398", "600900", "601668", "600588", "603986",
        "600031", "600048", "600050", "600104", "600276", "600309", "600346", "600436",
        "600519", "600547", "600585", "600588", "600690", "600745", "600809", "600887",
        "600900", "600905", "600919", "601012", "601088", "601166", "601211", "601288",
        "601318", "601336", "601390", "601398", "601601", "601628", "601668", "601688",
        "601728", "601766", "601857", "601888", "601898", "601899", "601919", "601988",
        "601995", "601998", "603259", "603260", "603288", "603501", "603629", "603899",
    ]],
    # 深市主板/创业板
    *[f"sz{code}" for code in [
        "000001", "000002", "000063", "000100", "000157", "000333", "000538", "000568",
        "000596", "000625", "000651", "000661", "000725", "000858", "000895", "002001",
        "002007", "002027", "002049", "002129", "002142", "002179", "002230", "002236",
        "002241", "002252", "002271", "002304", "002352", "002415", "002460", "002466",
        "002475", "002507", "002594", "002601", "002714", "002897", "300001", "300002",
        "300003", "300012", "300014", "300015", "300033", "300059", "300122", "300124",
        "300142", "300274", "300316", "300347", "300363", "300408", "300413", "300433",
        "300450", "300498", "300522", "300601", "300628", "300661", "300750", "300759",
        "300760", "300782", "300896", "300957", "300979", "300999", "301000",
    ]],
]

def get_quotes(codes):
    """批量获取行情（每次最多 60 只）"""
    results = []
    batch_size = 60
    
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        code_list = ','.join(batch)
        url = f"https://qt.gtimg.cn/q={code_list}"
        try:
            resp = requests.get(url, timeout=10)
            resp.encoding = 'gbk'
            content = resp.text
            for line in content.strip().split('\n'):
                if '=' in line:
                    parts = line.split('~')
                    if len(parts) >= 50:
                        code = parts[2]
                        name = parts[1]
                        price = float(parts[3]) if parts[3] else 0
                        prev_close = float(parts[4]) if parts[4] else 0
                        if prev_close > 0:
                            change_pct = (price - prev_close) / prev_close * 100
                        else:
                            change_pct = 0
                        results.append({
                            'code': code,
                            'name': name,
                            'price': price,
                            'prev_close': prev_close,
                            'change_pct': change_pct
                        })
        except Exception as e:
            print(f"Error fetching batch: {e}", file=sys.stderr)
    
    return results

def main():
    min_pct = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    print(f"📡 正在获取全市场{len(A_STOCKS)}只股票行情...\n")
    
    quotes = get_quotes(A_STOCKS)
    
    # 筛选涨幅大于 min_pct 的股票
    gainers = [q for q in quotes if q['change_pct'] >= min_pct]
    
    # 按涨幅排序
    gainers.sort(key=lambda x: x['change_pct'], reverse=True)
    
    # 取 TopN
    top_gainers = gainers[:top_n]
    
    print(f"# 📈 全市场涨幅榜 Top{len(top_gainers)}（涨幅≥{min_pct}%）\n")
    print(f"**数据源**: 腾讯财经 API  ")
    print(f"**样本**: {len(quotes)}只股票  ")
    print(f"**更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**\n")
    
    if not top_gainers:
        print(f"❌ 暂无涨幅大于 {min_pct}% 的股票\n")
        print("💡 提示：当前市场可能较为平淡，建议降低阈值查看")
        return
    
    print("| 排名 | 代码 | 名称 | 现价 | 涨幅% |")
    print("|------|------|------|------|-------|")
    
    for i, stock in enumerate(top_gainers, 1):
        print(f"| {i} | `{stock['code']}` | {stock['name']} | {stock['price']:.2f} | **+{stock['change_pct']:.2f}%** |")
    
    print("\n## 详细列表\n")
    for i, stock in enumerate(top_gainers, 1):
        print(f"{i}. **{stock['name']}** ({stock['code']}) - 现价 ¥{stock['price']:.2f}, 涨幅 +{stock['change_pct']:.2f}%")

if __name__ == '__main__':
    main()
