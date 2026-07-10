import sys
import os
import unittest

# 强行在首行导入 tests 模块以触发 tests/__init__.py 部署的原生类大清洗和离线物理拦截
import tests

if __name__ == "__main__":
    print("[run_tests] 正在启动全量离线回归测试流程...")
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir="tests", pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
