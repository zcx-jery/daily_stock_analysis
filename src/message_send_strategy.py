# -*- coding: utf-8 -*-
"""
OpenClaw 主会话 - 消息发送策略

基于 daily_stock 项目 v1.0 版本
用于 OpenClaw 主会话的消息发送优化
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


# ==================== 配置参数 ====================

class MessageStrategyConfig:
    """消息发送策略配置"""
    
    # 长度阈值（字符数）
    SHORT_MAX = 500             # SHORT: 0-500
    MEDIUM_MAX = 1500           # MEDIUM: 501-1500
    LONG_MAX = 3000             # LONG: 1501-3000
    DOC_THRESHOLD = 3000        # DOCUMENT: > 3000
    
    # 分段设置
    ENABLE_SPLIT = True
    SPLIT_SIZE = 1500
    SPLIT_OVERLAP = 50
    
    # 文档设置
    DOC_ENABLED = True
    DOC_FOLDER_NAME = "OpenClaw/技术文档"
    DOC_PRIVATE = True
    DOC_PREFIX = "【OpenClaw】"
    
    # 特殊场景阈值
    CODE_BLOCK_THRESHOLD = 3
    TABLE_THRESHOLD = 2
    LINE_THRESHOLD = 50


# ==================== 消息级别枚举 ====================

class MessageLevel:
    """消息级别"""
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"
    DOCUMENT = "document"


# ==================== 核心策略类 ====================

class MessageSendStrategy:
    """消息发送策略管理器"""
    
    def __init__(self, config: Optional[MessageStrategyConfig] = None):
        self.config = config or MessageStrategyConfig()
        logger.info("OpenClaw 消息发送策略初始化完成")
    
    def analyze_content(self, content: str) -> Dict[str, Any]:
        """分析内容特征"""
        char_count = len(content)
        line_count = content.count('\n') + 1
        
        # 统计代码块
        code_block_count = content.count('```') // 2
        
        # 统计表格
        table_lines = [line for line in content.split('\n') if line.count('|') >= 2]
        table_count = len(table_lines) // 3
        
        # 统计代码行数
        code_lines = 0
        in_code = False
        for line in content.split('\n'):
            if line.strip().startswith('```'):
                in_code = not in_code
            elif in_code:
                code_lines += 1
        
        # 判断消息级别
        level = self._determine_level(
            char_count, code_block_count, table_count, code_lines
        )
        
        recommendation = self._get_recommendation(level, char_count)
        
        return {
            "char_count": char_count,
            "line_count": line_count,
            "code_block_count": code_block_count,
            "table_count": table_count,
            "code_lines": code_lines,
            "level": level,
            "recommendation": recommendation
        }
    
    def _determine_level(
        self, 
        char_count: int, 
        code_block_count: int,
        table_count: int,
        code_lines: int
    ) -> str:
        """确定消息级别"""
        
        # 特殊场景：优先文档
        if code_block_count > self.config.CODE_BLOCK_THRESHOLD:
            return MessageLevel.DOCUMENT
        if table_count > self.config.TABLE_THRESHOLD:
            return MessageLevel.DOCUMENT
        if code_lines > self.config.LINE_THRESHOLD:
            return MessageLevel.DOCUMENT
        
        # 按长度判断
        if char_count > self.config.LONG_MAX:
            return MessageLevel.DOCUMENT
        elif char_count > self.config.MEDIUM_MAX:
            return MessageLevel.LONG
        elif char_count > self.config.SHORT_MAX:
            return MessageLevel.MEDIUM
        else:
            return MessageLevel.SHORT
    
    def _get_recommendation(self, level: str, char_count: int) -> str:
        """获取推荐处理方式"""
        recommendations = {
            MessageLevel.SHORT: "直接发送",
            MessageLevel.MEDIUM: "直接发送",
            MessageLevel.LONG: "分段发送（2-3 段）",
            MessageLevel.DOCUMENT: "创建飞书文档"
        }
        return recommendations.get(level, "直接发送")
    
    def split_content(self, content: str) -> list:
        """分段发送"""
        if len(content) <= self.config.SPLIT_SIZE:
            return [content]
        
        segments = []
        current = ""
        
        for line in content.split('\n'):
            if len(current) + len(line) + 1 > self.config.SPLIT_SIZE:
                if current:
                    segments.append(current)
                current = line
            else:
                if current:
                    current += '\n' + line
                else:
                    current = line
        
        if current:
            segments.append(current)
        
        logger.info(f"内容分段完成：{len(segments)} 段")
        return segments
    
    def format_split_message(self, segments: list, prefix: str = "") -> list:
        """为分段消息添加标记"""
        total = len(segments)
        formatted = []
        
        for i, segment in enumerate(segments, 1):
            marker = f"【{i}/{total}】"
            if prefix:
                marker = f"{prefix} {marker}"
            formatted.append(f"{marker}\n\n{segment}")
        
        return formatted
    
    def create_document_payload(
        self, 
        content: str, 
        title: str,
        summary: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建飞书文档负载"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        full_title = f"{self.config.DOC_PREFIX}{title} - {date_str}"
        
        if not summary:
            summary = content[:300].replace('\n', ' ')
            if len(content) > 300:
                summary += "..."
        
        doc_content = f"""# {full_title}

## 📋 核心摘要

{summary}

---

## 📊 详细内容

{content}

---

📅 创建时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
🤖 生成方式：OpenClaw 自动创建
"""
        
        return {
            "title": full_title,
            "content": doc_content,
            "folder": self.config.DOC_FOLDER_NAME,
            "private": self.config.DOC_PRIVATE
        }
    
    def format_doc_message(
        self, 
        doc_title: str, 
        doc_link: str, 
        summary: str
    ) -> str:
        """格式化文档链接消息"""
        return f"""📄 详细内容已写入飞书文档：

**{doc_title}**
🔗 {doc_link}

【核心摘要】
{summary}

如需查看完整内容，请点击上方链接。"""


# ==================== 便捷函数 ====================

_global_strategy: Optional[MessageSendStrategy] = None


def get_strategy() -> MessageSendStrategy:
    """获取全局消息策略实例"""
    global _global_strategy
    if _global_strategy is None:
        _global_strategy = MessageSendStrategy()
    return _global_strategy


def analyze_message(content: str) -> Dict[str, Any]:
    """分析消息内容"""
    return get_strategy().analyze_content(content)


def should_create_document(content: str) -> bool:
    """判断是否需要创建文档"""
    analysis = analyze_message(content)
    return analysis["level"] == MessageLevel.DOCUMENT


def split_message(content: str) -> list:
    """分段消息"""
    strategy = get_strategy()
    segments = strategy.split_content(content)
    return strategy.format_split_message(segments)


# ==================== 测试代码 ====================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    strategy = MessageSendStrategy()
    
    # 测试
    print("=== OpenClaw 消息发送策略测试 ===\n")
    
    short_msg = "这是一条短消息"
    print(f"短消息：{strategy.analyze_content(short_msg)}")
    
    long_msg = "这是一条长消息\n" * 500
    print(f"长消息：级别={strategy.analyze_content(long_msg)['level']}")
    
    segments = strategy.split_content(long_msg)
    print(f"分段数量：{len(segments)}")
