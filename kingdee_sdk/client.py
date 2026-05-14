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
            
            # 金蝶WebAPI使用JSON格式 - 手动序列化以确保中文字符正确处理
            if isinstance(data, (dict, list)):
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
        self._check_login()
        return self._request("view", [form_id, json.dumps(data, ensure_ascii=False)])
    
    def save(self, form_id: str, data: Dict) -> Dict:
        self._check_login()
        return self._request("save", [form_id, json.dumps(data, ensure_ascii=False)])
    
    def batch_save(self, form_id: str, data: Dict) -> Dict:
        self._check_login()
        return self._request("batch_save", [form_id, json.dumps(data, ensure_ascii=False)])
    
    def draft(self, form_id: str, data: Dict) -> Dict:
        self._check_login()
        return self._request("draft", [form_id, json.dumps(data, ensure_ascii=False)])
    
    def submit(self, form_id: str, data: Dict) -> Dict:
        self._check_login()
        return self._request("submit", [form_id, json.dumps(data, ensure_ascii=False)])
    
    def audit(self, form_id: str, data: Dict) -> Dict:
        self._check_login()
        return self._request("audit", [form_id, json.dumps(data, ensure_ascii=False)])
    
    def unaudit(self, form_id: str, data: Dict) -> Dict:
        self._check_login()
        return self._request("unaudit", [form_id, json.dumps(data, ensure_ascii=False)])
    
    def delete(self, form_id: str, data: Dict) -> Dict:
        self._check_login()
        return self._request("delete", [form_id, json.dumps(data, ensure_ascii=False)])
    
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
        
        return self._request("execute_bill_query", request_data)
    
    def upload_attachment(
        self,
        file_path: str,
        form_id: Optional[str] = None,
        bill_no: Optional[str] = None,
        entry_id: Optional[str] = None,
        row_id: Optional[str] = None,
        chunk_size: int = 1024 * 1024  # 1MB分块
    ) -> Dict:
        """
        上传附件（支持分块上传大文件）
        
        Args:
            file_path: 文件路径
            form_id: 表单ID（可选）
            bill_no: 单据编号（可选）
            entry_id: 分录ID（可选）
            row_id: 行ID（可选）
            chunk_size: 分块大小，默认1MB
            
        Returns:
            上传结果
        """
        self._check_login()
        
        if not os.path.exists(file_path):
            raise ValueError(f"文件不存在: {file_path}")
        
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        # 小文件直接上传
        if file_size <= chunk_size:
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            data = {
                "FileName": file_name,
                "FileContent": file_content.hex() if isinstance(file_content, bytes) else file_content
            }
            if form_id:
                data["FormId"] = form_id
            if bill_no:
                data["BillNo"] = bill_no
            
            return self._request("attachment_upload", data)
        
        # 大文件分块上传
        return self._upload_attachment_chunked(file_path, file_name, form_id, bill_no, chunk_size)
    
    def _upload_attachment_chunked(
        self,
        file_path: str,
        file_name: str,
        form_id: Optional[str],
        bill_no: Optional[str],
        chunk_size: int
    ) -> Dict:
        """分块上传附件"""
        file_size = os.path.getsize(file_path)
        chunks = []
        
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
        
        total_chunks = len(chunks)
        results = []
        
        for i, chunk in enumerate(chunks):
            data = {
                "FileName": file_name,
                "FileContent": chunk.hex(),
                "ChunkIndex": i,
                "TotalChunks": total_chunks,
                "IsLastChunk": (i == total_chunks - 1)
            }
            if form_id:
                data["FormId"] = form_id
            if bill_no:
                data["BillNo"] = bill_no
            
            result = self._request("attachment_upload", data)
            results.append(result)
            
            if self.debug:
                logger.debug(f"上传分块 {i+1}/{total_chunks}")
        
        return results[-1] if results else {}
    
    def download_attachment(
        self,
        attachment_id: str,
        save_path: Optional[str] = None
    ) -> str:
        """
        下载附件
        
        Args:
            attachment_id: 附件ID
            save_path: 保存路径，默认使用附件原名
            
        Returns:
            保存的文件路径
        """
        self._check_login()
        
        data = {"AttachmentId": attachment_id}
        result = self._request("attachment_download", data)
        
        # 解析返回的文件内容
        file_content = result.get("FileContent", "")
        file_name = result.get("FileName", f"attachment_{attachment_id}")
        
        if not save_path:
            save_path = file_name
        
        # 保存文件
        with open(save_path, 'wb') as f:
            f.write(bytes.fromhex(file_content) if isinstance(file_content, str) else file_content)
        
        return save_path
