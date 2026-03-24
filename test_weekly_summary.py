#!/usr/bin/env python3
"""
测试周报摘要功能
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'packages/backend'))

from app.services.ai import weekly_financial_summary

# 模拟测试数据
def test_weekly_summary():
    print("🧪 测试周报摘要功能...")
    
    # 测试数据
    test_uid = 1
    start_date = "2026-02-24"
    end_date = "2026-03-01"
    
    try:
        # 调用周报摘要函数
        result = weekly_financial_summary(
            uid=test_uid,
            start_date=start_date,
            end_date=end_date,
            gemini_api_key=None,
            persona=None
        )
        
        print("✅ 测试成功！")
        print(f"测试期间: {start_date} 到 {end_date}")
        print(f"收入: ${result['totals']['income']}")
        print(f"支出: ${result['totals']['expenses']}")
        print(f"净现金流: ${result['totals']['net_flow']}")
        print(f"储蓄率: {result['totals']['savings_rate']}%")
        
        print("\n📊 趋势分析:")
        print(f"收入变化: {result['trends']['income_change_pct']}%")
        print(f"支出变化: {result['trends']['expenses_change_pct']}%")
        print(f"最高支出日: {result['trends']['max_spend_day']}")
        
        print("\n💡 关键洞察:")
        for insight in result['insights']['key_insights']:
            print(f"  • {insight}")
            
        print("\n🎯 建议:")
        for rec in result['insights']['recommendations']:
            print(f"  • {rec}")
            
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_weekly_summary()
    sys.exit(0 if success else 1)
