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
    
    # 变更（ERP 工程数据模块；本账套实测标识为 ENG_ECNOrder / ENG_ECRApply）
    ECO = "ENG_ECNOrder"      # 工程变更单
    ECN = "ENG_ECNOrder"      # 工程变更单（兼容旧名）
    ECR = "ENG_ECRApply"      # 工程变更申请单
    
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
        # 常用字段，避免使用可能不存在的字段
        fields = "FMaterialId,FNumber,FName,FSpecification,FMaterialGroup.FNumber,FGrossWeight,FNetWeight,FCreatorId.FName,FCreateDate,FDocumentStatus"
        
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
        bom_version: Optional[str] = None
    ) -> Optional[Dict]:
        """获取物料的BOM（查不到时返回 None）

        说明：ENG_BOM 的元数据中没有 FBomNo / FVersion 字段，
        BOM 编号就是 FNumber（形如 1.LE.CC.050010_V.0，版本信息包含在编号里）。
        因此不再按 FVersion 过滤；若传入 bom_version，则按编号后缀 "_<version>" 匹配。
        """
        try:
            fields = "FBomId,FNumber,FMaterialId.FNumber,FDocumentStatus,FDescription,FCreateDate"

            filters = [f"FMaterialId.FNumber = '{material_code}'"]
            if bom_version:
                filters.append(f"FNumber like '%_{bom_version}'")

            results = self.client.execute_bill_query(
                form_id=self.form_ids.BOM,
                field_keys=fields,
                filter_string=" and ".join(filters),
                limit=1
            )
            
            # 金蝶无匹配数据时会返回 [] / [[]] / [[None, ...]]，统一按“无 BOM”处理
            row = None
            for item in results or []:
                if isinstance(item, (list, tuple)) and any(v is not None for v in item):
                    row = item
                    break
            if not row:
                return None
            
            bom_no = row[1] if len(row) > 1 else row[0]
            if not bom_no:
                return None
            return self.client.view(self.form_ids.BOM, {"Number": bom_no})
        except KingdeeAPIError as e:
            logger.error(f"查询BOM失败: {e}")
            return None
    
    def create_bom(
        self,
        bom_no: str,
        parent_material_code: str,
        items: List[Dict],
        bom_name: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """创建BOM

        注意：ENG_BOM 元数据中没有 FBomNo / FVersion 字段，
        BOM 编号使用 FNumber，版本信息请直接包含在 bom_no 中
        （例如 "1.LE.CC.050010_V.0"）。
        """
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
                "FNumber": bom_no,
                "FMaterialID": {"FNumber": parent_material_code},
                "FDescription": bom_name,
                "FEntity": entries
            }
        }
        
        for key, value in kwargs.items():
            if key not in ["creator"]:
                data["Model"][key] = value
        
        return self.client.save(self.form_ids.BOM, data)
    
    def batch_create_boms(self, boms: List[Dict]) -> Dict:
        """批量创建BOM（版本请并入 bom_no，ENG_BOM 没有 FVersion 字段）"""
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
                "FNumber": bom["bom_no"],
                "FMaterialID": {"FNumber": bom["parent_material_code"]},
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
        """获取待审批的工程变更单（ENG_ECNOrder）
        
        FDocumentStatus: A=创建(暂存) / B=待审核 / C=已审核
        注意：如果账套未启用工程变更（对象不存在），返回空列表而不是报错
        """
        fields = "FBillNo,FBillTypeID.FName,FCreateDate,FCreatorId.FName,FDocumentStatus,FDescription"
        filter_str = "FDocumentStatus = 'B'"
        
        try:
            return self.client.execute_bill_query(
                form_id=self.form_ids.ECO,
                field_keys=fields,
                filter_string=filter_str,
                limit=limit
            )
        except KingdeeAPIError as e:
            # 如果业务对象不存在，返回空列表而不是报错
            if "业务对象不存在" in str(e):
                logger.warning(f"{self.form_ids.ECO} 业务对象不存在，可能未启用工程变更")
                return []
            raise
    
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
        bill_no: Optional[str] = None
    ) -> Dict:
        """
        上传图纸（先走官方附件上传接口，再保存图纸单据）

        注意：需要账套安装 PLM 图纸单据（PLM_DRAWING）；未安装的账套会在保存图纸时
        报“业务对象不存在”。官方附件接口为整文件上传，不支持分片。

        Args:
            file_path: 文件路径
            material_code: 关联物料编码
            version: 图纸版本
            description: 描述（同时作为附件别名）
            bill_no: 关联的图纸单据编号（官方附件接口要求，有则传）

        Returns:
            上传结果，包含附件ID
        """
        if not os.path.exists(file_path):
            raise ValueError(f"文件不存在: {file_path}")
        
        # 先上传附件（官方 AttachmentUpLoad：FileName/FormId/BillNO/SendByte/IsLast）
        upload_result = self.client.upload_attachment(
            file_path=file_path,
            form_id=self.form_ids.DRAWING,
            bill_no=bill_no,
            alias_file_name=description
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
        """查询图纸
        
        注意：如果账套未安装 PLM 模块，PLM_DRAWING 业务对象可能不存在
        """
        fields = "FDocId,FDocNo,FDocName,FVersion,FMaterialID.FNumber,FFileName,FAttachmentID,FCreateDate"
        
        filters = []
        if material_code:
            filters.append(f"FMaterialID.FNumber = '{material_code}'")
        if doc_name:
            filters.append(f"FDocName like '%{doc_name}%'")
        
        filter_string = " and ".join(filters) if filters else None
        
        try:
            return self.client.execute_bill_query(
                form_id=self.form_ids.DRAWING,
                field_keys=fields,
                filter_string=filter_string,
                limit=limit
            )
        except KingdeeAPIError as e:
            if "业务对象不存在" in str(e):
                logger.warning(f"PLM_DRAWING 业务对象不存在，可能未安装 PLM 模块")
                return []
            raise
    
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
