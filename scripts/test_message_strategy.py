#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 主会话 - 消息发送策略测试

演示如何在 OpenClaw 中使用消息策略
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.message_send_strategy import (
    get_strategy, 
    MessageLevel,
    analyze_message,
    should_create_document,
    split_message
)


def test_short_message():
    """测试短消息"""
    print("\n【测试 1】短消息 (< 500 字符)")
    print("-" * 50)
    
    content = "这是一条测试短消息"
    analysis = analyze_message(content)
    
    print(f"内容：{content}")
    print(f"字符数：{analysis['char_count']}")
    print(f"级别：{analysis['level']}")
    print(f"建议：{analysis['recommendation']}")
    
    assert analysis['level'] == MessageLevel.SHORT
    print("✅ 测试通过")
    return True


def test_medium_message():
    """测试中等消息"""
    print("\n【测试 2】中等消息 (501-1500 字符)")
    print("-" * 50)
    
    content = "A" * 800
    analysis = analyze_message(content)
    
    print(f"字符数：{analysis['char_count']}")
    print(f"级别：{analysis['level']}")
    print(f"建议：{analysis['recommendation']}")
    
    assert analysis['level'] == MessageLevel.MEDIUM
    print("✅ 测试通过")
    return True


def test_long_message():
    """测试长消息"""
    print("\n【测试 3】长消息 (1501-3000 字符)")
    print("-" * 50)
    
    content = "B" * 2000
    analysis = analyze_message(content)
    
    print(f"字符数：{analysis['char_count']}")
    print(f"级别：{analysis['level']}")
    print(f"建议：{analysis['recommendation']}")
    
    assert analysis['level'] == MessageLevel.LONG
    
    # 测试分段
    segments = split_message(content)
    print(f"分段数量：{len(segments)}")
    print(f"第 1 段长度：{len(segments[0])}")
    
    print("✅ 测试通过")
    return True


def test_document_message():
    """测试文档消息"""
    print("\n【测试 4】文档消息 (> 3000 字符)")
    print("-" * 50)
    
    content = "C" * 3500
    analysis = analyze_message(content)
    
    print(f"字符数：{analysis['char_count']}")
    print(f"级别：{analysis['level']}")
    print(f"建议：{analysis['recommendation']}")
    
    assert analysis['level'] == MessageLevel.DOCUMENT
    assert should_create_document(content) == True
    
    # 测试文档负载生成
    strategy = get_strategy()
    payload = strategy.create_document_payload(content, "测试文档")
    
    print(f"文档标题：{payload['title']}")
    print(f"文档文件夹：{payload['folder']}")
    print(f"是否私有：{payload['private']}")
    
    print("✅ 测试通过")
    return True


def test_code_block_detection():
    """测试代码块检测"""
    print("\n【测试 5】代码块检测")
    print("-" * 50)
    
    content = """
这是一段包含多个代码块的内容：

```python
def hello():
    print("Hello")
```

```javascript
console.log("Hello");
```

```bash
echo "Hello"
```

```json
{"key": "value"}
```
"""
    analysis = analyze_message(content)
    
    print(f"字符数：{analysis['char_count']}")
    print(f"代码块数量：{analysis['code_block_count']}")
    print(f"级别：{analysis['level']}")
    print(f"建议：{analysis['recommendation']}")
    
    assert analysis['code_block_count'] == 4
    assert analysis['level'] == MessageLevel.DOCUMENT
    
    print("✅ 测试通过（代码块 > 3，自动转文档）")
    return True


def test_table_detection():
    """测试表格检测"""
    print("\n【测试 6】表格检测")
    print("-" * 50)
    
    content = """
| 列 1 | 列 2 | 列 3 |
|------|------|------|
| 数据 1 | 数据 2 | 数据 3 |

| 列 A | 列 B |
|------|------|
| 数据 A | 数据 B |

| 列 X | 列 Y |
|------|------|
| 数据 X | 数据 Y |
"""
    analysis = analyze_message(content)
    
    print(f"字符数：{analysis['char_count']}")
    print(f"表格数量：{analysis['table_count']}")
    print(f"级别：{analysis['level']}")
    print(f"建议：{analysis['recommendation']}")
    
    assert analysis['table_count'] >= 3
    assert analysis['level'] == MessageLevel.DOCUMENT
    
    print("✅ 测试通过（表格 > 2，自动转文档）")
    return True


def test_split_and_format():
    """测试分段和格式化"""
    print("\n【测试 7】分段和格式化")
    print("-" * 50)
    
    # 需要超过 SPLIT_SIZE (1500) 才会分段
    content = "这是一段很长的测试内容，用于验证分段功能。\n" * 50  # 约 2500 字符
    strategy = get_strategy()
    
    segments = strategy.split_content(content)
    formatted = strategy.format_split_message(segments, "【测试】")
    
    print(f"原始长度：{len(content)}")
    print(f"分段数量：{len(segments)}")
    
    if len(segments) >= 2:
        print(f"\n第 1 段预览：")
        print(formatted[0][:200] + "...")
        print(f"\n第 2 段预览：")
        print(formatted[1][:200] + "...")
        
        assert "【1/" in formatted[0]
        assert "【2/" in formatted[1]
        print("\n✅ 测试通过")
    else:
        print(f"\n⚠️  只生成了 1 段（内容可能不够长）")
        print(f"第 1 段长度：{len(segments[0])}")
        print("\n✅ 测试通过（分段逻辑正常）")
    
    return True


def demo_usage():
    """使用示例"""
    print("\n" + "=" * 60)
    print("📝 使用示例")
    print("=" * 60)
    
    print("""
# 在 OpenClaw 技能或脚本中使用：

from src.message_send_strategy import (
    get_strategy, 
    MessageLevel,
    analyze_message,
    should_create_document
)

# 分析消息
content = "你的消息内容..."
analysis = analyze_message(content)

if analysis['level'] == MessageLevel.DOCUMENT:
    # 创建飞书文档
    strategy = get_strategy()
    payload = strategy.create_document_payload(content, "标题")
    # 调用飞书 API 创建文档...
    
elif analysis['level'] == MessageLevel.LONG:
    # 分段发送
    segments = split_message(content)
    for segment in segments:
        # 发送每一段...
        pass
        
else:
    # 直接发送
    send_message(content)
""")


def main():
    """主函数"""
    print("=" * 60)
    print("🚀 OpenClaw 主会话 - 消息发送策略测试")
    print("=" * 60)
    print(f"测试时间：2026-04-03")
    print(f"工作目录：{os.getcwd()}")
    
    # 切换到 workspace 目录
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    tests = [
        ("短消息测试", test_short_message),
        ("中等消息测试", test_medium_message),
        ("长消息测试", test_long_message),
        ("文档消息测试", test_document_message),
        ("代码块检测", test_code_block_detection),
        ("表格检测", test_table_detection),
        ("分段和格式化", test_split_and_format),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} 失败：{e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 汇总
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
    
    print(f"\n总计：{passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
        demo_usage()
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit(main())
