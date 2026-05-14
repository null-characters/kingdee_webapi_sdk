"""
PLM业务工具封装（改进版）
支持附件上传、更多业务操作
"""

import os
import logging
from typing import List, Dict, Optional, Any, Tuple
from .client import KingdeeClient
from .exceptions import KingdeeAPIError

logger = logging.getLogger(__name__)


class PLMFormIds:
    """PLM模块常用表单ID"""
    # 基础资料
    MATERIAL = "BD_MATERIAL"
    MATERIAL_GROUP = "BD_MATERIALGROUP"
    UNIT = "BD_UNIT"
    
    # BOM
    BOM = "ENG_BOM"
    BOM_VERSION = "ENG_BOMVERSION"
    
    # 变更
    ECO = "ENG_ECO"
    ECN = "ENG_ECN"
    
    # 文档/图纸
    DOC = "PLM_DOC"
    DRAWING = "PLM_DRAWING"
    
    # 项目
    PROJECT = "PLM_PROJECT"
    TASK = "PLM_TASK"
    
    # 工艺
    ROUTE = "ENG_ROUTE"


class PLMTools:
    """
    PLM业务工具类（改进版）
    封装PLM常用业务操作，支持附件处理
    """
    
    def __init__(self, client: KingdeeClient):
        self.client = client
        self.form_ids = PLMFormIds()
    
    # ==================== 物料操作 ====================
    
    def query_material_by_code(self, material_code: str) -> Optional[Dict]:
        """根据编码查询物料"""
        try:
            result = self.client.view(
                self.form_ids.MATERIAL,
                {"Number": material_code}
            )
            return result.get("Result", {}).get("Result") if isinstance(result, dict) else None
        except KingdeeAPIError as e:
            logger.error(f"查询物料失败: {e}")
            return None
    
    def search_materials(
        self,
        keyword: Optional[str] = None,
        material_group: Optional[str] = None,
        limit: int = 100,
        start_row: int = 0
    ) -> List[List[Any]]:
        """模糊搜索物料"""
        fields = "FMaterialId,FNumber,FName,FSpecification,FMaterialGroup.FNumber,FUnitID.FNumber,FGrossWeight,FNetWeight,FCreatorId.FName,FCreateDate,FDocumentStatus"
        
        filters = []
        if keyword:
            filters.append(f"FName like '%{keyword}%'")
        if material_group:
            filters.append(f"FMaterialGroup.FNumber = '{material_group}'")
        
        filter_string = " and ".join(filters) if filters else None
        
        return self.client.execute_bill_query(
            form_id=self.form_ids.MATERIAL,
            field_keys=fields,
            filter_string=filter_string,
            limit=limit,
            start_row=start_row
        )
    
    def create_material(
        self,
        material_code: str,
        material_name: str,
        specification: Optional[str] = None,
        material_group: str = "",
        unit: str = "Pcs",
        **kwargs
    ) -> Dict:
        """创建物料"""
        data = {
            "Creator": kwargs.get("creator", self.client.username),
            "NeedUpDateFields": [],
            "Model": {
                "FNumber": material_code,
                "FName": material_name,
                "FSpecification": specification or "",
                "FMaterialGroup": {"FNumber": material_group},
                "FUnitID": {"FNumber": unit}
            }
        }
        for key, value in kwargs.items():
            if key not in ["creator"]:
                data["Model"][key] = value
        
        return self.client.save(self.form_ids.MATERIAL, data)
    
    def batch_create_materials(self, materials: List[Dict]) -> Dict:
        """
        批量创建物料
        
        Args:
            materials: 物料列表，每个元素包含创建参数
        """
        models = []
        for mat in materials:
            model = {
                "FNumber": mat["material_code"],
                "FName": mat["material_name"],
                "FSpecification": mat.get("specification", ""),
                "FMaterialGroup": {"FNumber": mat.get("material_group", "")},
                "FUnitID": {"FNumber": mat.get("unit", "Pcs")}
            }
            models.append(model)
        
        data = {
            "Creator": self.client.username,
            "NeedUpDateFields": [],
            "BatchCount": str(len(models)),
            "Model": models
        }
        
        return self.client.batch_save(self.form_ids.MATERIAL, data)
    
    # ==================== BOM操作 ====================
    
    def get_bom_by_material(
        self,
        material_code: str,
        bom_version: str = "V1.0"
    ) -> Optional[Dict]:
        """获取物料的BOM"""
        try:
            fields = "FBomId,FBomNo,FMaterialId.FNumber,FVersion,FDescription,FCreateDate"
            filter_str = f"FMaterialId.FNumber = '{material_code}' and FVersion = '{bom_version}'"
            
            results = self.client.execute_bill_query(
                form_id=self.form_ids.BOM,
                field_keys=fields,
                filter_string=filter_str,
                limit=1
            )
            
            if results and len(results) > 0:
                bom_no = results[0][1]
                return self.client.view(self.form_ids.BOM, {"Number": bom_no})
            return None
        except KingdeeAPIError as e:
            logger.error(f"查询BOM失败: {e}")
            return None
    
    def create_bom(
        self,
        bom_no: str,
        parent_material_code: str,
        items: List[Dict],
        version: str = "V1.0",
        bom_name: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """创建BOM"""
        bom_name = bom_name or f"{parent_material_code} BOM"
        
        entries = []
        for i, item in enumerate(items, 1):
            entry = {
                "FEntryID": 0,
                "FSeq": item.get("seq", i),
                "FMaterialID": {"FNumber": item["material_code"]},
                "FQty": item.get("qty", 1),
                "FLossRate": item.get("loss_rate", 0),
                "FPositionNo": item.get("position", "")
            }
            entries.append(entry)
        
        data = {
            "Creator": kwargs.get("creator", self.client.username),
            "NeedUpDateFields": [],
            "Model": {
                "FBomNo": bom_no,
                "FMaterialID": {"FNumber": parent_material_code},
                "FVersion": version,
                "FDescription": bom_name,
                "FEntity": entries
            }
        }
        
        for key, value in kwargs.items():
            if key not in ["creator"]:
                data["Model"][key] = value
        
        return self.client.save(self.form_ids.BOM, data)
    
    def batch_create_boms(self, boms: List[Dict]) -> Dict:
        """批量创建BOM"""
        models = []
        for bom in boms:
            items = []
            for i, item in enumerate(bom.get("items", []), 1):
                items.append({
                    "FSeq": i,
                    "FMaterialID": {"FNumber": item["material_code"]},
                    "FQty": item.get("qty", 1),
                    "FLossRate": item.get("loss_rate", 0)
                })
            
            model = {
                "FBomNo": bom["bom_no"],
                "FMaterialID": {"FNumber": bom["parent_material_code"]},
                "FVersion": bom.get("version", "V1.0"),
                "FDescription": bom.get("bom_name", bom["bom_no"]),
                "FEntity": items
            }
            models.append(model)
        
        data = {
            "Creator": self.client.username,
            "NeedUpDateFields": [],
            "BatchCount": str(len(models)),
            "Model": models
        }
        
        return self.client.batch_save(self.form_ids.BOM, data)
    
    # ==================== 变更单操作 ====================
    
    def get_pending_ecos(self, limit: int = 100) -> List[List[Any]]:
        """获取待审批的工程变更单"""
        fields = "FBillNo,FBillType,FCreateDate,FCreatorId.FName,FBillStatus,FDescription"
        filter_str = "FBillStatus = 'A'"
        
        return self.client.execute_bill_query(
            form_id=self.form_ids.ECO,
            field_keys=fields,
            filter_string=filter_str,
            limit=limit
        )
    
    def get_eco_detail(self, bill_no: str) -> Optional[Dict]:
        """获取变更单详情"""
        try:
            result = self.client.view(self.form_ids.ECO, {"Number": bill_no})
            return result.get("Result", {}).get("Result") if isinstance(result, dict) else None
        except KingdeeAPIError as e:
            logger.error(f"查询变更单失败: {e}")
            return None
    
    def approve_eco(self, bill_no: str) -> Dict:
        """审批工程变更单"""
        return self.client.audit(self.form_ids.ECO, {"Numbers": [bill_no]})
    
    def reject_eco(self, bill_no: str) -> Dict:
        """驳回工程变更单（执行反审核）"""
        return self.client.unaudit(self.form_ids.ECO, {"Numbers": [bill_no]})
    
    def batch_approve_ecos(self, bill_nos: List[str]) -> Tuple[List[str], List[Dict]]:
        """批量审批变更单"""
        success, failed = [], []
        for bill_no in bill_nos:
            try:
                self.approve_eco(bill_no)
                success.append(bill_no)
            except KingdeeAPIError as e:
                failed.append({"bill_no": bill_no, "error": str(e)})
        return success, failed
    
    # ==================== 图纸/附件操作 ====================
    
    def upload_drawing(
        self,
        file_path: str,
        material_code: Optional[str] = None,
        version: str = "V1.0",
        description: Optional[str] = None,
        chunk_size: int = 1024 * 1024
    ) -> Dict:
        """
        上传图纸（使用附件上传接口）
        
        Args:
            file_path: 文件路径
            material_code: 关联物料编码
            version: 图纸版本
            description: 描述
            chunk_size: 分块大小
            
        Returns:
            上传结果，包含附件ID
        """
        if not os.path.exists(file_path):
            raise ValueError(f"文件不存在: {file_path}")
        
        # 先上传附件
        upload_result = self.client.upload_attachment(
            file_path=file_path,
            form_id=self.form_ids.DRAWING,
            chunk_size=chunk_size
        )
        
        attachment_id = upload_result.get("AttachmentId")
        
        # 再保存图纸记录
        file_name = os.path.basename(file_path)
        model = {
            "FDocName": file_name,
            "FVersion": version,
            "FFileName": file_name,
            "FAttachmentID": attachment_id
        }
        
        if material_code:
            model["FMaterialID"] = {"FNumber": material_code}
        if description:
            model["FDescription"] = description
        
        data = {
            "Creator": self.client.username,
            "NeedUpDateFields": [],
            "Model": model
        }
        
        save_result = self.client.save(self.form_ids.DRAWING, data)
        
        return {
            "upload_result": upload_result,
            "save_result": save_result,
            "attachment_id": attachment_id
        }
    
    def download_drawing(
        self,
        attachment_id: str,
        save_dir: str = "."
    ) -> str:
        """
        下载图纸
        
        Args:
            attachment_id: 附件ID
            save_dir: 保存目录
            
        Returns:
            保存的文件路径
        """
        save_path = os.path.join(save_dir, f"drawing_{attachment_id}")
        return self.client.download_attachment(attachment_id, save_path)
    
    def query_drawings(
        self,
        material_code: Optional[str] = None,
        doc_name: Optional[str] = None,
        limit: int = 100
    ) -> List[List[Any]]:
        """查询图纸"""
        fields = "FDocId,FDocNo,FDocName,FVersion,FMaterialID.FNumber,FFileName,FAttachmentID,FCreateDate"
        
        filters = []
        if material_code:
            filters.append(f"FMaterialID.FNumber = '{material_code}'")
        if doc_name:
            filters.append(f"FDocName like '%{doc_name}%'")
        
        filter_string = " and ".join(filters) if filters else None
        
        return self.client.execute_bill_query(
            form_id=self.form_ids.DRAWING,
            field_keys=fields,
            filter_string=filter_string,
            limit=limit
        )
    
    # ==================== 辅助方法 ====================
    
    def get_form_id_list(self) -> List[str]:
        """获取支持的表单ID列表"""
        return [getattr(self.form_ids, attr) for attr in dir(self.form_ids) if not attr.startswith('_')]
    
    def test_connection(self) -> bool:
        """测试连接是否成功"""
        try:
            self.client.login()
            return True
        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return False
