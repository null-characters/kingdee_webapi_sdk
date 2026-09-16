#!/usr/bin/env python3
"""
完整查看物料详情，探索附件信息
"""

import os
import sys

# 保证以 `python examples/view_material_full.py` 直接运行时可以导入 kingdee_sdk
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from kingdee_sdk import KingdeeClient, AuthType
from kingdee_sdk.config_loader import KINGDEE_CONFIG, validate_config

def create_client():
    return KingdeeClient(
        server_url=KINGDEE_CONFIG["server_url"],
        acct_id=KINGDEE_CONFIG["acct_id"],
        username=KINGDEE_CONFIG["username"],
        password=KINGDEE_CONFIG["password"],
        auth_type=KINGDEE_CONFIG.get("auth_type", AuthType.PASSWORD),
        lcid=KINGDEE_CONFIG.get("lcid", 2052),
        debug=False
    )

def main():
    missing = validate_config(KINGDEE_CONFIG)
    if missing:
        print(f"缺少配置项: {', '.join(missing)}")
        print("请设置环境变量（推荐）或复制 kingdee_sdk/config.example.py 为 kingdee_sdk/config.py")
        return

    client = create_client()
    client.login()
    
    print("=" * 80)
    print("完整查看物料详情")
    print("=" * 80)
    
    # 1. 查看物料详情（完整输出）
    print("\n1. 查看物料 3.R.C01.000006 详情...")
    try:
        result = client.view(
            form_id="BD_MATERIAL",
            data={"Number": "3.R.C01.000006"}
        )
        
        # 保存完整结果到文件
        with open('/Users/fengbing/svn/trunk/software/Code/code_update/material_detail.json', 'w') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print("  完整详情已保存到 material_detail.json")
        
        # 打印关键信息
        if 'Result' in result and 'Result' in result['Result']:
            material_data = result['Result']['Result']
            print(f"  物料 ID: {material_data.get('Id')}")
            print(f"  名称: {material_data.get('Name')}")
            
            # 查找附件相关字段
            attachment_keys = [k for k in material_data.keys() if 'attach' in k.lower() or 'file' in k.lower() or 'doc' in k.lower()]
            print(f"  附件相关字段: {attachment_keys}")
            
            # 打印所有字段名
            print(f"\n  所有字段名:")
            for key in sorted(material_data.keys()):
                value = material_data[key]
                if isinstance(value, (str, int, float, bool)) or value is None:
                    print(f"    {key}: {value}")
                elif isinstance(value, list) and len(value) < 5:
                    print(f"    {key}: [列表, {len(value)}项]")
                elif isinstance(value, dict):
                    print(f"    {key}: {type(value).__name__}")
                else:
                    print(f"    {key}: {type(value).__name__}")
            
    except Exception as e:
        print(f"  查询失败: {e}")
    
    # 2. 查询 BOS_Attachment 中 InterID 为物料 ID 的附件
    print("\n2. 查询物料 ID 1694737 的附件...")
    try:
        result = client.execute_bill_query(
            form_id="BOS_Attachment",
            field_keys="FID,FInterID,FATTACHMENTNAME,FBillNo,FBillType",
            filter_string=f"FInterID='{1694737}'",
            limit=10
        )
        print(f"  结果: {result}")
    except Exception as e:
        print(f"  查询失败: {e}")
    
    # 3. 尝试查询 BD_MATERIAL 附件分录
    print("\n3. 尝试查询物料附件分录...")
    try:
        # 尝试不同的分录表名
        entry_forms = [
            "BD_MATERIAL_Attachment",
            "BD_MATERIAL_AttachmentEntry",
            "BD_MATERIAL_Att",
            "BD_MATERIAL_File",
            "BD_MATERIAL_Doc",
            "BD_MATERIAL_BillFile",
            "BD_MATERIAL_Entry_Attachment",
        ]
        
        for form in entry_forms:
            try:
                result = client.execute_bill_query(
                    form_id=form,
                    field_keys="FID,FEntryID,FMaterialId,FFileName",
                    limit=1
                )
                print(f"  {form}: {result}")
            except Exception as e:
                error_msg = str(e)
                if "业务对象不存在" in error_msg:
                    print(f"  {form}: 不存在")
                else:
                    print(f"  {form}: {error_msg[:50]}")
        
    except Exception as e:
        print(f"  查询失败: {e}")
    
    # 4. 探索物料的其他可能附件字段
    print("\n4. 探索物料的其他可能附件字段...")
    
    # 金蝶物料通常有附件分录字段
    possible_fields = [
        "FMaterialID", "FNumber", "FName", "FSpecification",
        "FAttachmentEntry", "F_AttachmentEntry", "FATTACHMENTENTRY",
        "FBillFileEntry", "F_BillFileEntry", "FBILLFILEENTRY",
        "FFileEntry", "F_FileEntry", "FFILEENTRY",
        "FDocEntry", "F_DocEntry", "FDOCENTRY",
        "FExtBillEntry", "F_ExtBillEntry",
        "FEntity", "FEntity_Attachment",
    ]
    
    for field in possible_fields:
        try:
            result = client.execute_bill_query(
                form_id="BD_MATERIAL",
                field_keys=field,
                filter_string="FNumber='3.R.C01.000006'",
                limit=1
            )
            # 检查是否成功
            if isinstance(result, list) and len(result) > 0:
                first = result[0]
                if isinstance(first, dict) and 'Result' in first:
                    # 错误
                    pass
                else:
                    print(f"  ✓ {field}: {result}")
        except Exception as e:
            pass
    
    client.logout()

if __name__ == "__main__":
    main()