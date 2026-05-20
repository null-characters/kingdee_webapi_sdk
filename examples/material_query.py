# -*- coding: utf-8 -*-
"""
物料查询控制台程序
简单的交互式物料查询工具
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kingdee_sdk import KingdeeClient, AuthType
from kingdee_sdk.config import KINGDEE_CONFIG


class MaterialQuery:
    """物料查询工具"""
    
    def __init__(self):
        self.client = None
        self.logged_in = False
        
    def login(self):
        """登录系统"""
        try:
            print("\n正在连接金蝶系统...")
            self.client = KingdeeClient(
                server_url=KINGDEE_CONFIG["server_url"],
                acct_id=KINGDEE_CONFIG["acct_id"],
                username=KINGDEE_CONFIG["username"],
                password=KINGDEE_CONFIG["password"],
                auth_type=AuthType.PASSWORD
            )
            self.client.login()
            self.logged_in = True
            print("登录成功!")
            return True
        except Exception as e:
            print(f"登录失败: {e}")
            return False
    
    def logout(self):
        """登出系统"""
        if self.client and self.logged_in:
            try:
                self.client.logout()
            except:
                pass
        self.logged_in = False
    
    def query_by_number(self, number):
        """按物料编号查询"""
        if not self.logged_in:
            print("请先登录!")
            return
        
        try:
            result = self.client.execute_bill_query(
                form_id="BD_MATERIAL",
                field_keys="FMaterialID,FNumber,FName,FSpecification",
                filter_string=f"FNumber = '{number}'",
                limit=10
            )
            self._display_result(result)
        except Exception as e:
            print(f"查询出错: {e}")
    
    def query_by_name(self, name):
        """按物料名称模糊查询"""
        if not self.logged_in:
            print("请先登录!")
            return
        
        try:
            result = self.client.execute_bill_query(
                form_id="BD_MATERIAL",
                field_keys="FMaterialID,FNumber,FName,FSpecification",
                filter_string=f"FName like '%{name}%'",
                limit=20
            )
            self._display_result(result)
        except Exception as e:
            print(f"查询出错: {e}")
    
    def query_all(self, limit=20):
        """查询所有物料"""
        if not self.logged_in:
            print("请先登录!")
            return
        
        try:
            result = self.client.execute_bill_query(
                form_id="BD_MATERIAL",
                field_keys="FMaterialID,FNumber,FName,FSpecification",
                limit=limit
            )
            self._display_result(result)
        except Exception as e:
            print(f"查询出错: {e}")
    
    def _display_result(self, result):
        """显示查询结果"""
        if not result:
            print("未找到记录")
            return
        
        # 检查是否是错误响应
        if isinstance(result, list) and len(result) == 1:
            first_item = result[0]
            if isinstance(first_item, dict) and 'Result' in first_item:
                error_info = first_item['Result'].get('ResponseStatus', {})
                if error_info.get('IsSuccess') == False:
                    errors = error_info.get('Errors', [])
                    msg = errors[0].get('Message', '未知错误') if errors else '未知错误'
                    print(f"查询失败: {msg}")
                    return
        
        # 正常结果显示
        print(f"\n找到 {len(result)} 条记录:")
        print("-" * 90)
        print(f"{'序号':<4} {'物料ID':<10} {'物料编号':<20} {'物料名称':<25} {'规格型号':<30}")
        print("-" * 90)
        
        for i, row in enumerate(result, 1):
            # row 格式: [FMaterialID, FNumber, FName, FSpecification]
            if not isinstance(row, list):
                continue
                
            material_id = str(row[0]) if len(row) > 0 else ""
            number = str(row[1]) if len(row) > 1 else ""
            name = str(row[2]) if len(row) > 2 else ""
            spec = str(row[3]) if len(row) > 3 else ""
            
            # 截断过长的字段
            number = number[:18] + ".." if len(number) > 20 else number
            name = name[:23] + ".." if len(name) > 25 else name
            spec = spec[:28] + ".." if len(spec) > 30 else spec
            
            print(f"{i:<4} {material_id:<10} {number:<20} {name:<25} {spec:<30}")
        print("-" * 90)


def show_menu():
    """显示菜单"""
    print("\n" + "=" * 50)
    print("        物料查询系统")
    print("=" * 50)
    print("  1. 查询所有物料 (前20条)")
    print("  2. 按物料编号查询")
    print("  3. 按物料名称模糊查询")
    print("  4. 重新登录")
    print("  0. 退出")
    print("=" * 50)


def main():
    """主程序"""
    app = MaterialQuery()
    
    print("\n欢迎使用物料查询系统")
    
    # 自动登录
    if not app.login():
        print("初始化失败，请检查配置后重试")
        try:
            input("按回车键退出...")
        except:
            pass
        return
    
    while True:
        try:
            show_menu()
            choice = input("\n请选择操作 [0-4]: ").strip()
            
            if choice == "0":
                print("\n正在退出...")
                app.logout()
                print("再见!")
                break
            
            elif choice == "1":
                limit_input = input("显示条数 (默认20): ").strip()
                limit = int(limit_input) if limit_input.isdigit() else 20
                app.query_all(limit)
            
            elif choice == "2":
                number = input("请输入物料编号: ").strip()
                if number:
                    app.query_by_number(number)
                else:
                    print("编号不能为空")
            
            elif choice == "3":
                name = input("请输入物料名称(支持模糊查询): ").strip()
                if name:
                    app.query_by_name(name)
                else:
                    print("名称不能为空")
            
            elif choice == "4":
                app.logout()
                app.login()
            
            else:
                print("无效选择，请重新输入")
            
            try:
                input("\n按回车键继续...")
            except:
                pass
                
        except KeyboardInterrupt:
            print("\n\n正在退出...")
            app.logout()
            print("再见!")
            break
        except EOFError:
            app.logout()
            break
        except Exception as e:
            print(f"\n发生错误: {e}")
            try:
                input("按回车键继续...")
            except:
                pass


if __name__ == "__main__":
    main()