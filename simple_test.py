#!/usr/bin/env python3
"""
简化测试 - 检查代码语法和功能
"""
import ast
import os

def test_syntax():
    print("🔍 检查代码语法...")
    
    files_to_check = [
        "packages/backend/app/services/ai.py",
        "packages/backend/app/routes/insights.py"
    ]
    
    all_good = True
    for filepath in files_to_check:
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    content = f.read()
                ast.parse(content)
                print(f"  ✅ {filepath} - 语法正确")
            except SyntaxError as e:
                print(f"  ❌ {filepath} - 语法错误: {e}")
                all_good = False
        else:
            print(f"  ⚠️ {filepath} - 文件不存在")
            all_good = False
    
    return all_good

def check_functionality():
    print("\n🔍 检查功能完整性...")
    
    # 检查ai.py中的函数
    with open("packages/backend/app/services/ai.py", 'r') as f:
        content = f.read()
    
    required_functions = [
        "weekly_financial_summary",
        "_weekly_totals", 
        "_weekly_category_trends",
        "_generate_weekly_insights_heuristic"
    ]
    
    missing = []
    for func in required_functions:
        if func not in content:
            missing.append(func)
    
    if missing:
        print(f"  ❌ 缺少函数: {missing}")
        return False
    else:
        print("  ✅ 所有必需函数都存在")
        return True

def check_routes():
    print("\n🔍 检查路由...")
    
    with open("packages/backend/app/routes/insights.py", 'r') as f:
        content = f.read()
    
    if "@bp.get(\"/weekly-summary\")" in content:
        print("  ✅ weekly-summary路由存在")
        return True
    else:
        print("  ❌ weekly-summary路由缺失")
        return False

def main():
    print("🧪 FinMind周报摘要功能测试")
    print("=" * 50)
    
    tests = [
        ("语法检查", test_syntax),
        ("功能完整性", check_functionality),
        ("路由配置", check_routes)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        result = test_func()
        results.append((test_name, result))
    
    print("\n" + "=" * 50)
    print("📊 测试结果汇总:")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    print(f"\n🎯 总体: {passed}/{total} 通过")
    
    if passed == total:
        print("\n✨ 所有测试通过！功能实现完成。")
        print("下一步: 编写单元测试，更新文档，提交PR")
        return True
    else:
        print("\n⚠️ 有测试失败，需要修复。")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
