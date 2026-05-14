# -*- coding: utf-8 -*-
"""编码测试脚本"""
import sys
import json

print(f"Python版本: {sys.version}")
print(f"默认编码: {sys.getdefaultencoding()}")
print(f"文件系统编码: {sys.getfilesystemencoding()}")
print(f"标准输出编码: {sys.stdout.encoding}")

# 测试数据
data = {
    "dbid": "your_acct_id",
    "user": "your_username",
    "pwd": "your_password",
    "lcid": 2052
}

# 测试JSON序列化
json_str = json.dumps(data, ensure_ascii=False)
print(f"\nJSON字符串: {json_str}")
print(f"JSON repr: {repr(json_str)}")

# 测试编码
encoded = json_str.encode('utf-8')
print(f"\nUTF-8编码后: {encoded}")
print(f"解码后: {encoded.decode('utf-8')}")

# 检查中文字节
print(f"\n'冯'的UTF-8字节: {'冯'.encode('utf-8')}")
print(f"'冰'的UTF-8字节: {'冰'.encode('utf-8')}")
