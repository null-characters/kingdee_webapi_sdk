"""
金蝶WebAPI客户端（改进版）
支持：多认证方式、附件上传下载、调试模式
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .auth import KingdeeAuth, AuthType
from .exceptions import KingdeeAPIError, AuthenticationError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KingdeeClient:
    """
    金蝶云星空WebAPI客户端（改进版）
    
    特性：多种认证方式、附件上传/下载（分块）、调试模式、自动登录
    
    使用示例:
        client = KingdeeClient(
            server_url="http://localhost/k3cloud",
            acct_id="账套ID",
            username="用户名",
            app_id="应用ID",
            app_secret="应用密钥",
            auth_type=AuthType.SIGN_SHA256,
            debug=True
        )
        client.login()
    """
    
    SERVICES = {
        "login": "Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginBySign.common.kdsvc",
        "validate_login": "Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc",
        "view": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.View.common.kdsvc",
        "save": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Save.common.kdsvc",
        "batch_save": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.BatchSave.common.kdsvc",
        "draft": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Draft.common.kdsvc",
        "submit": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Submit.common.kdsvc",
        "audit": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Audit.common.kdsvc",
        "unaudit": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.UnAudit.common.kdsvc",
        "delete": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.Delete.common.kdsvc",
        "execute_bill_query": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc",
        "attachment_upload": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.AttachmentUpload.common.kdsvc",
        "attachment_download": "Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.AttachmentDownLoad.common.kdsvc",
        "logout": "Kingdee.BOS.WebApi.ServicesStub.AuthService.Logout.common.kdsvc",
    }
    
    def __init__(
        self, 
        server_url: str, 
        acct_id: str,
        username: str,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        password: Optional[str] = None,
        auth_type: AuthType = AuthType.SIGN_SHA256,
        lcid: int = 2052,
        timeout: int = 60,
        max_retries: int = 3,
        debug: bool = False,
        auto_login: bool = True
    ):
        self.server_url = server_url.rstrip('/')
        self.acct_id = acct_id
        self.username = username
        self.app_id = app_id
        self.app_secret = app_secret
        self.password = password
        self.auth_type = auth_type
        self.lcid = lcid
        self.timeout = timeout
        self.debug = debug
        self.auto_login = auto_login
        
        self.auth = KingdeeAuth(auth_type)
        self.session_cookie = None
        self._is_logged_in = False
        
        # 调试信息存储
        self.last_request_info = {}
        
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        if debug:
            logging.getLogger().setLevel(logging.DEBUG)
    
    def _build_url(self, service_name: str) -> str:
        service_path = self.SERVICES.get(service_name, service_name)
        return f"{self.server_url}/{service_path}"
    
    def _request(self, service_name: str, data: Any, headers: Optional[Dict] = None) -> Any:
        url = self._build_url(service_name)
        request_headers = {'Content-Type': 'application/json; charset=UTF-8'}
        if headers:
            request_headers.update(headers)
        
        # Cookie由requests.Session自动管理，不再需要手动设置
        pass
        
        # 记录调试信息
        self.last_request_info = {
            'url': url,
            'headers': request_headers.copy(),
            'body': data
        }
        
        try:
            if self.debug:
                logger.debug(f"Request: POST {url}")
                logger.debug(f"Headers: {request_headers}")
                body_str = json.dumps(data, ensure_ascii=False)
                logger.debug(f"Body (repr): {repr(body_str)[:500]}...")
            
            # 金蝶WebAPI序列化规则：
            # - 单据操作接口(view/save/submit等): {"formId": "...", "data": {...}}
            # - 查询接口: {"data": "jsonString"}
            # - 登录接口: {"key": "value", ...}
            if isinstance(data, dict):
                request_body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            elif isinstance(data, list):
                request_body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            else:
                request_body = data
            
            response = self.session.post(
                url=url,
                data=request_body,
                headers=request_headers,
                timeout=self.timeout
            )
            
            # 保存登录后的session cookie
            if self.debug:
                logger.debug(f"Response cookies: {dict(response.cookies)}")
            
            # 优先从响应体获取WebAPI SessionId
            try:
                resp_data = response.json()
                context = resp_data.get('Context', {})
                if 'SessionId' in context:
                    self.session_cookie = context['SessionId']
                    if self.debug:
                        logger.debug(f"Saved WebAPI SessionId: {self.session_cookie}")
            except:
                # 备用：从HTTP Cookie获取
                session_id = response.cookies.get('ASP.NET_SessionId') or response.cookies.get('KDSVCSessionId')
                if session_id:
                    self.session_cookie = session_id
                    if self.debug:
                        logger.debug(f"Saved cookie-based session: {self.session_cookie}")
            
            result = self._handle_response(response)
            self.last_request_info['response'] = result
            return result
            
        except requests.exceptions.Timeout:
            raise KingdeeAPIError(f"请求超时（{self.timeout}秒）")
        except requests.exceptions.RequestException as e:
            raise KingdeeAPIError(f"网络请求失败: {e}")
    
    def _handle_response(self, response: requests.Response) -> Any:
        try:
            data = response.json()
        except json.JSONDecodeError:
            data = {"raw_response": response.text}
        
        if self.debug:
            logger.debug(f"Response: {response.status_code}")
            logger.debug(f"Body: {json.dumps(data, ensure_ascii=False)[:500]}...")
        
        if response.status_code != 200:
            raise KingdeeAPIError(f"HTTP错误: {response.status_code}", code=response.status_code, response_data=data)
        
        # 检查业务错误
        if isinstance(data, dict):
            response_status = data.get("Result", {}).get("ResponseStatus", {})
            if response_status.get("IsSuccess") == False:
                errors = response_status.get("Errors", [])
                error_msg = errors[0].get("Message", "业务错误") if errors else "业务处理失败"
                raise KingdeeAPIError(error_msg, response_data=data)
        
        return data
    
    def _check_login(self):
        if self.auto_login and not self._is_logged_in:
            self.login()
    
    def set_debug(self, debug: bool = True):
        """设置调试模式"""
        self.debug = debug
        if debug:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        else:
            logging.getLogger().setLevel(logging.INFO)
            logger.setLevel(logging.INFO)
    
    def get_debug_info(self) -> dict:
        """获取最后一次请求的调试信息"""
        return self.last_request_info.copy()
    
    def print_debug_info(self):
        """打印调试信息"""
        info = self.last_request_info
        print("=" * 60)
        print("调试信息:")
        print("=" * 60)
        print(f"URL: {info.get('url')}")
        print(f"Headers: {json.dumps(info.get('headers'), indent=2, ensure_ascii=False)}")
        print(f"Body: {json.dumps(info.get('body'), indent=2, ensure_ascii=False)[:1000]}")
        print(f"Response: {json.dumps(info.get('response'), indent=2, ensure_ascii=False)[:1000]}")
        print("=" * 60)
    
    def login(self) -> bool:
        """登录系统"""
        service_name = "validate_login" if self.auth_type == AuthType.PASSWORD else "login"
        
        auth_data, _ = self.auth.prepare_auth_data(
            acct_id=self.acct_id,
            username=self.username,
            app_id=self.app_id,
            app_secret=self.app_secret,
            password=self.password,
            lcid=self.lcid
        )
        
        result = self._request(service_name, auth_data)
        
        if isinstance(result, dict):
            login_result_type = result.get("LoginResultType")
            is_success = result.get("IsSuccessByAPI")
            
            if login_result_type == 1 or is_success:
                self._is_logged_in = True
                logger.info("登录成功")
                return True
            
            message = result.get("Message", "未知错误")
            raise AuthenticationError(f"登录失败: {message}")
        
        raise AuthenticationError(f"登录响应异常: {result}")
    
    def logout(self) -> bool:
        """登出系统"""
        self._check_login()
        self._request("logout", {})
        self._is_logged_in = False
        self.session_cookie = None
        logger.info("已登出")
        return True
    
    def view(self, form_id: str, data: Dict) -> Dict:
        """查看单据详情"""
        self._check_login()
        # 金蝶实际 API 格式: {"formId": "...", "data": {...}}
        return self._request("view", {"formId": form_id, "data": data})

    def save(self, form_id: str, data: Dict) -> Dict:
        """保存单据（创建或修改）"""
        self._check_login()
        return self._request("save", {"formId": form_id, "data": data})

    def batch_save(self, form_id: str, data: Dict) -> Dict:
        """批量保存单据"""
        self._check_login()
        return self._request("batch_save", {"formId": form_id, "data": data})

    def draft(self, form_id: str, data: Dict) -> Dict:
        """暂存单据"""
        self._check_login()
        return self._request("draft", {"formId": form_id, "data": data})

    def submit(self, form_id: str, data: Dict) -> Dict:
        """提交单据审批"""
        self._check_login()
        return self._request("submit", {"formId": form_id, "data": data})

    def audit(self, form_id: str, data: Dict) -> Dict:
        """审核单据"""
        self._check_login()
        return self._request("audit", {"formId": form_id, "data": data})

    def unaudit(self, form_id: str, data: Dict) -> Dict:
        """反审核单据"""
        self._check_login()
        return self._request("unaudit", {"formId": form_id, "data": data})

    def delete(self, form_id: str, data: Dict) -> Dict:
        """删除单据"""
        self._check_login()
        return self._request("delete", {"formId": form_id, "data": data})
    
    def execute_bill_query(
        self, form_id: str, field_keys: str,
        filter_string: Optional[str] = None,
        order_string: Optional[str] = None,
        top_row_count: int = 0,
        limit: int = 2000,
        start_row: int = 0
    ) -> List[List[Any]]:
        """执行单据查询
        
        Args:
            form_id: 表单ID，如 BD_MATERIAL
            field_keys: 字段列表，逗号分隔，如 FNumber,FName
            filter_string: 过滤条件，如 "FNumber like '%M%'"
            order_string: 排序条件，如 "FNumber DESC"
            top_row_count: 最大返回行数（0表示不限制）
            limit: 返回行数限制
            start_row: 开始行索引（用于分页）
            
        Returns:
            二维列表，每行是一条记录，每列是一个字段值
            
        Raises:
            KingdeeAPIError: 当查询失败时（字段不存在、表单不存在等）
        """
        self._check_login()
        
        # 构建查询参数对象
        query_params = {
            "FormId": form_id,
            "FieldKeys": field_keys,
            "TopRowCount": top_row_count,
            "Limit": limit,
            "StartRow": start_row
        }
        if filter_string:
            query_params["FilterString"] = filter_string
        if order_string:
            query_params["OrderString"] = order_string
        
        # 金蝶WebAPI要求: {"data": "json字符串"}
        inner_json = json.dumps(query_params, ensure_ascii=False)
        request_data = {"data": inner_json}
        
        result = self._request("execute_bill_query", request_data)
        
        # 检查结果中是否包含错误信息
        # 金蝶查询接口出错时不会返回 HTTP 错误，而是把错误体塞进结果里：[{}] 或 [[{}]]
        if isinstance(result, list) and len(result) > 0:
            candidates = result[0] if isinstance(result[0], (list, tuple)) else [result[0]]
            for item in candidates:
                if not isinstance(item, dict) or 'Result' not in item:
                    continue
                response_status = item.get('Result', {}).get('ResponseStatus', {})
                if response_status.get('IsSuccess') == False:
                    errors = response_status.get('Errors', [])
                    error_msg = errors[0].get('Message', '查询失败') if errors else '查询失败'
                    raise KingdeeAPIError(error_msg, response_data=item)
        
        return result
    
    def upload_attachment(
        self,
        file_path: str,
        form_id: Optional[str] = None,
        bill_no: Optional[str] = None,
        inter_id: Optional[str] = None,
        entry_key: Optional[str] = None,
        entry_inter_id: Optional[str] = None,
        alias_file_name: Optional[str] = None,
        file_id: Optional[str] = None,
        is_last: bool = True
    ) -> Dict:
        """
        上传附件（官方 AttachmentUpLoad 接口）

        官方参数说明（整文件一次性上传，该接口本身不支持分片）：
            FileName        文件名
            FormId          表单ID（BOS 业务对象标识，如 BD_MATERIAL，不能用数据库表名）
            InterId         单据内码
            BillNO          单据编号
            SendByte        Base64 编码的文件字节流（注意：不是 hex）
            IsLast          是否最后一次上传（单文件上传固定传 True）
            Entrykey        单据体标识（上传单据体附件时填写）
            EntryinterId    分录内码（单据头附件可不填或填 -1）
            AliasFileName   附件别名
            FileId          文件ID；分多次上传时，首次上传后必填

        Args:
            file_path: 本地文件路径
            form_id: 表单ID（官方要求必填）
            bill_no: 单据编号（官方要求必填）
            inter_id: 单据内码
            entry_key: 单据体标识（单据体附件）
            entry_inter_id: 分录内码
            alias_file_name: 附件别名
            file_id: 已有文件ID（续传/关联时用）
            is_last: 是否最后一次上传，默认 True

        Returns:
            上传结果（含 FileId）

        Note:
            大文件为 Base64 一次性读入内存上传，请留意内存占用。
        """
        self._check_login()

        if not os.path.exists(file_path):
            raise ValueError(f"文件不存在: {file_path}")

        import base64

        file_name = os.path.basename(file_path)
        with open(file_path, 'rb') as f:
            file_content = f.read()

        payload = {
            "FileName": file_name,
            "SendByte": base64.b64encode(file_content).decode('ascii'),
            "IsLast": is_last,
        }
        if form_id:
            payload["FormId"] = form_id
        if bill_no:
            payload["BillNO"] = bill_no
        if inter_id:
            payload["InterId"] = inter_id
        if entry_key:
            payload["Entrykey"] = entry_key
        if entry_inter_id is not None:
            payload["EntryinterId"] = entry_inter_id
        if alias_file_name:
            payload["AliasFileName"] = alias_file_name
        if file_id:
            payload["FileId"] = file_id

        # 金蝶 WebAPI 要求把这组参数包进 {"data": "<json字符串>"}（与 execute_bill_query 一致），
        # 直接放顶层会报“接口参数data不能为空”
        return self._request(
            "attachment_upload",
            {"data": json.dumps(payload, ensure_ascii=False)}
        )

    def download_attachment(
        self,
        file_id: str,
        save_path: Optional[str] = None,
        start_index: int = 0
    ) -> str:
        """
        下载附件
        
        Args:
            file_id: 文件ID，取自 BOS_Attachment 的 FFileId 字段（形如 Temp_xxx-xxx）；
                     首次上传返回的 FileId 也可直接使用
            save_path: 保存路径，默认使用附件原名
            start_index: 下载起始位置，默认为0（官方接口按 StartIndex 分片下载）

        Returns:
            保存的文件路径
        """
        self._check_login()

        import base64

        # 官方参数：FileId + StartIndex（StartIndex 为分片下载起始位置，首次传 0）
        param_str = '{"FileId":"' + str(file_id) + '","StartIndex":' + str(start_index) + '}'
        data = {"data": param_str}
        result = self._request("attachment_download", data)
        
        # 解析返回的文件内容
        result_data = result.get("Result", result)
        file_part = result_data.get("FilePart", "")
        file_name = result_data.get("FileName", f"attachment_{file_id}")
        is_last = result_data.get("IsLast", True)
        
        if not save_path:
            save_path = file_name
        
        # Base64解码并保存文件
        file_bytes = base64.b64decode(file_part) if file_part else b''
        
        # 如果不是最后一次，需要追加写入
        mode = 'wb' if start_index == 0 else 'ab'
        with open(save_path, mode) as f:
            f.write(file_bytes)
        
        # 如果文件较大需要分块下载
        if not is_last:
            next_index = result_data.get("StartIndex", start_index + len(file_bytes))
            return self.download_attachment(file_id, save_path, next_index)
        
        return save_path
