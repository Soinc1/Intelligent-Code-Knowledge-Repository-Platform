"""FastAPI主应用"""
from fastapi import FastAPI, HTTPException, Depends, Request, status, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from services import code_review_service, knowledge_service
from database import init_db, get_db, User, CodeReview
from auth import (
    authenticate_user, create_access_token, get_current_active_user,
    require_admin, get_password_hash, require_auth, require_roles,
    APPROVER_ROLES, KNOWLEDGE_MANAGER_ROLES, ELEVATED_ROLES
)
from operation_log import operation_log_service
from statistics_service import statistics_service
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
import os
import time

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    try:
        init_db()
        print("数据库初始化完成")
    except Exception as e:
        print(f"数据库初始化失败: {e}")
    yield
    # 关闭时（如果需要清理资源）

app = FastAPI(title="智能代码知识沉淀平台", version="1.0.0", lifespan=lifespan)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求模型
class CodeReviewRequest(BaseModel):
    code: str
    language: str = "python"
    file_name: str = "code.py"


class FileUploadRequest(BaseModel):
    language: Optional[str] = None  # 如果为None，从文件扩展名推断


class KnowledgeRequest(BaseModel):
    title: str
    content: str
    category: Optional[str] = ""
    code_pattern: Optional[str] = ""
    best_practice: Optional[str] = ""
    status: Optional[str] = None
    tags: Optional[List[str]] = []
    review_notes: Optional[str] = ""
    source_comment_id: Optional[int] = None


class KnowledgeUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    code_pattern: Optional[str] = None
    best_practice: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    review_notes: Optional[str] = None
    source_comment_id: Optional[int] = None


class CodeHistoryRequest(BaseModel):
    code: str
    top_k: Optional[int] = 10


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = ""


# 路由
@app.get("/", response_class=HTMLResponse)
async def read_root():
    """返回前端HTML页面"""
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>前端页面未找到</h1>"


@app.post("/api/v1/auth/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    # 检查用户是否存在
    user_exists = db.query(User).filter(User.username == request.username).first()
    if not user_exists:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名不存在。默认账号：root，密码：123456",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 验证用户
    user = authenticate_user(db, request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="密码错误。默认账号：root，密码：123456",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.username})
    
    # 记录登录日志
    operation_log_service.log_operation(
        user_id=user.id,
        operation_type="login",
        operation_detail={"username": user.username}
    )
    
    return {
        "success": True,
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role
        }
    }


@app.post("/api/v1/auth/register")
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    # 创建新用户
    user = User(
        username=request.username,
        password_hash=get_password_hash(request.password),
        email=request.email,
        role="developer"  # 默认开发者角色
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 记录注册日志
    operation_log_service.log_operation(
        user_id=user.id,
        operation_type="register",
        operation_detail={"username": user.username}
    )
    
    return {
        "success": True,
        "message": "注册成功",
        "user": {
            "id": user.id,
            "username": user.username
        }
    }


@app.get("/api/v1/auth/me")
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """获取当前用户信息"""
    return {
        "success": True,
        "data": {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "role": current_user.role
        }
    }


@app.post("/api/v1/code/review")
async def review_code(
    request: CodeReviewRequest,
    current_user: User = Depends(require_auth),
    http_request: Request = None
):
    """代码审查接口"""
    try:
        result = code_review_service.review_code(
            code=request.code,
            language=request.language,
            file_name=request.file_name
        )
        
        # 记录操作历史
        operation_log_service.log_operation(
            user_id=current_user.id,
            operation_type="code_review",
            operation_detail={
                "file_name": request.file_name,
                "language": request.language,
                "review_id": result.get("review_id"),
                "issues_count": len(result.get("issues", []))
            },
            request=http_request
        )
        
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def detect_language_from_filename(filename: str) -> str:
    """从文件名推断编程语言"""
    ext_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'javascript',
        '.tsx': 'javascript',
        '.java': 'java',
        '.go': 'go',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.c': 'cpp',
        '.h': 'cpp',
        '.hpp': 'cpp'
    }
    for ext, lang in ext_map.items():
        if filename.lower().endswith(ext):
            return lang
    return 'python'  # 默认


@app.post("/api/v1/code/upload")
async def upload_code_file(
    file: UploadFile = File(...),
    language: Optional[str] = None,
    current_user: User = Depends(require_auth),
    http_request: Request = None
):
    """文件上传接口"""
    try:
        # 读取文件内容
        content = await file.read()
        code = content.decode('utf-8')
        
        # 确定语言
        if not language:
            language = detect_language_from_filename(file.filename)
        
        # 使用文件名
        file_name = file.filename or "uploaded_code.txt"
        
        # 进行代码审查
        result = code_review_service.review_code(
            code=code,
            language=language,
            file_name=file_name
        )
        
        # 记录操作历史
        operation_log_service.log_operation(
            user_id=current_user.id,
            operation_type="code_upload",
            operation_detail={
                "file_name": file_name,
                "language": language,
                "file_size": len(content),
                "review_id": result.get("review_id"),
                "issues_count": len(result.get("issues", []))
            },
            request=http_request
        )
        
        return {
            "success": True,
            "data": {
                **result,
                "file_name": file_name,
                "file_size": len(content),
                "language": language
            }
        }
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码错误，请使用UTF-8编码的文件")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@app.get("/api/v1/code/{file_id}/history")
async def get_code_history(file_id: int):
    """获取代码审查历史"""
    from database import get_db, CodeFile, CodeReview
    db = next(get_db())
    try:
        code_file = db.query(CodeFile).filter(CodeFile.id == file_id).first()
        if not code_file:
            raise HTTPException(status_code=404, detail="代码文件不存在")
        
        reviews = db.query(CodeReview).filter(CodeReview.code_file_id == file_id).all()
        
        return {
            "success": True,
            "data": {
                "file_info": {
                    "id": code_file.id,
                    "file_name": code_file.file_name,
                    "language": code_file.language,
                    "created_at": code_file.created_at.isoformat() if code_file.created_at else None
                },
                "review_history": [{
                    "id": r.id,
                    "review_result": r.review_result,
                    "review_time_ms": r.review_time_ms,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                } for r in reviews]
            }
        }
    finally:
        db.close()


@app.get("/api/v1/knowledge")
async def get_knowledge_list(
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(require_auth)
):
    """获取知识库列表（支持分页）"""
    try:
        result = knowledge_service.get_all_knowledge(status=status, keyword=keyword, page=page, page_size=page_size)
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/knowledge")
async def add_knowledge(
    request: KnowledgeRequest,
    current_user: User = Depends(require_auth),
    http_request: Request = None
):
    """添加知识"""
    try:
        normalized_tags = request.tags or []
        normalized_tags = [tag.strip() for tag in normalized_tags if tag and tag.strip()]
        can_approve = current_user.role in APPROVER_ROLES
        if can_approve:
            desired_status = request.status or "published"
        else:
            desired_status = "draft" if request.status == "draft" else "pending_review"
        review_notes = request.review_notes if can_approve else ""
        
        knowledge_data = knowledge_service.add_knowledge(
            title=request.title,
            content=request.content,
            category=request.category,
            code_pattern=request.code_pattern,
            best_practice=request.best_practice,
            status=desired_status,
            tags=normalized_tags,
            created_by=current_user.id,
            review_notes=review_notes,
            source_comment_id=request.source_comment_id
        )
        
        # 记录操作历史
        operation_log_service.log_operation(
            user_id=current_user.id,
            operation_type="knowledge_add",
            operation_detail={
                "knowledge_id": knowledge_data.get("id"),
                "title": request.title,
                "category": request.category
            },
            request=http_request
        )
        
        return {
            "success": True,
            "data": knowledge_data
        }
    except Exception as e:
        import traceback
        error_detail = str(e)
        print(f"添加知识API错误: {error_detail}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"添加知识失败: {error_detail}")


@app.put("/api/v1/knowledge/{knowledge_id}")
async def update_knowledge(
    knowledge_id: int,
    request: KnowledgeUpdateRequest,
    current_user: User = Depends(require_auth),
    http_request: Request = None
):
    """更新知识条目"""
    existing = knowledge_service.get_knowledge_by_id(knowledge_id)
    if not existing:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    
    if current_user.role != "admin" and existing.get("created_by") not in [None, current_user.id]:
        raise HTTPException(status_code=403, detail="无权限编辑该知识")
    
    if request.status and current_user.role != "admin":
        if request.status not in ["draft", "pending_review"]:
            raise HTTPException(status_code=403, detail="非管理员无法设置该状态")
    
    try:
        payload = request.dict(exclude_unset=True)
        if "tags" in payload and payload["tags"] is not None:
            payload["tags"] = [tag.strip() for tag in payload["tags"] if tag and tag.strip()]
        if "review_notes" in payload and current_user.role not in APPROVER_ROLES:
            payload.pop("review_notes", None)
        if "status" in payload and payload["status"] is not None and current_user.role not in APPROVER_ROLES:
            if payload["status"] not in ["draft", "pending_review"]:
                raise HTTPException(status_code=403, detail="无权限设置该状态")
        if "status" not in payload and current_user.role not in APPROVER_ROLES:
            payload.pop("status", None)
        updated = knowledge_service.update_knowledge(
            knowledge_id,
            payload,
            reviewer_id=current_user.id if current_user.role in APPROVER_ROLES else None
        )
        
        operation_log_service.log_operation(
            user_id=current_user.id,
            operation_type="knowledge_update",
            operation_detail={"knowledge_id": knowledge_id},
            request=http_request
        )
        
        return {
            "success": True,
            "data": updated
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ApproveRequest(BaseModel):
    review_notes: Optional[str] = None


class RejectRequest(BaseModel):
    review_notes: str


@app.post("/api/v1/knowledge/{knowledge_id}/approve")
async def approve_knowledge(
    knowledge_id: int,
    approve_request: ApproveRequest,
    current_user: User = Depends(require_roles(list(APPROVER_ROLES))),
    http_request: Request = None
):
    """快速审核：批准知识条目"""
    existing = knowledge_service.get_knowledge_by_id(knowledge_id)
    if not existing:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    
    try:
        updated = knowledge_service.update_knowledge(
            knowledge_id,
            {"status": "published", "review_notes": approve_request.review_notes or ""},
            reviewer_id=current_user.id
        )
        
        operation_log_service.log_operation(
            user_id=current_user.id,
            operation_type="knowledge_approve",
            operation_detail={"knowledge_id": knowledge_id},
            request=http_request
        )
        
        return {
            "success": True,
            "data": updated,
            "message": "知识已批准并发布"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/knowledge/{knowledge_id}/reject")
async def reject_knowledge(
    knowledge_id: int,
    reject_request: RejectRequest,
    current_user: User = Depends(require_roles(list(APPROVER_ROLES))),
    http_request: Request = None
):
    """快速审核：驳回知识条目"""
    existing = knowledge_service.get_knowledge_by_id(knowledge_id)
    if not existing:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    
    if not reject_request.review_notes or not reject_request.review_notes.strip():
        raise HTTPException(status_code=400, detail="驳回时必须填写审核备注")
    
    try:
        updated = knowledge_service.update_knowledge(
            knowledge_id,
            {"status": "draft", "review_notes": reject_request.review_notes.strip()},
            reviewer_id=current_user.id
        )
        
        operation_log_service.log_operation(
            user_id=current_user.id,
            operation_type="knowledge_reject",
            operation_detail={"knowledge_id": knowledge_id},
            request=http_request
        )
        
        return {
            "success": True,
            "data": updated,
            "message": "知识已驳回"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/knowledge/{knowledge_id}")
async def delete_knowledge(
    knowledge_id: int,
    current_user: User = Depends(require_auth),
    http_request: Request = None
):
    """删除知识条目"""
    existing = knowledge_service.get_knowledge_by_id(knowledge_id)
    if not existing:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    
    if current_user.role != "admin" and existing.get("created_by") not in [None, current_user.id]:
        raise HTTPException(status_code=403, detail="无权限删除该知识")
    
    try:
        knowledge_service.delete_knowledge(knowledge_id)
        operation_log_service.log_operation(
            user_id=current_user.id,
            operation_type="knowledge_delete",
            operation_detail={"knowledge_id": knowledge_id},
            request=http_request
        )
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/knowledge/graph")
async def get_knowledge_graph_data(
    limit: int = 30,
    current_user: User = Depends(require_auth)
):
    """获取知识图谱数据"""
    try:
        data = knowledge_service.get_knowledge_graph(limit=limit)
        return {
            "success": True,
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/code/history")
async def get_code_history(
    request: CodeHistoryRequest,
    current_user: User = Depends(require_auth),
    http_request: Request = None
):
    """用户B功能：获取代码的历史问题和最佳实践"""
    try:
        result = code_review_service.get_code_history(
            code=request.code,
            top_k=request.top_k or 10
        )
        
        # 记录操作历史
        operation_log_service.log_operation(
            user_id=current_user.id,
            operation_type="history_query",
            operation_detail={
                "total_found": result.get("total_found", 0),
                "history_issues_count": len(result.get("history_issues", [])),
                "best_practices_count": len(result.get("best_practices", []))
            },
            request=http_request
        )
        
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/knowledge/auto-extract/{comment_id}")
async def auto_extract_knowledge(
    comment_id: int,
    current_user: User = Depends(require_roles(list(APPROVER_ROLES))),
    http_request: Request = None
):
    """用户C功能：自动将审查评论转化为知识库"""
    try:
        knowledge = knowledge_service.auto_extract_knowledge_from_review(comment_id)
        return {
            "success": True,
            "data": knowledge,
            "message": "知识已自动提取并保存"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/knowledge/batch-extract")
async def batch_extract_knowledge(
    min_severity: str = "medium",
    current_user: User = Depends(require_roles(["admin", "reviewer", "curator"])),
    http_request: Request = None
):
    """用户C功能：批量将审查评论转化为知识库（需要管理员权限）"""
    try:
        result = knowledge_service.batch_extract_knowledge(min_severity=min_severity)
        
        # 记录操作历史
        try:
            operation_log_service.log_operation(
                user_id=current_user.id,
                operation_type="knowledge_extract",
                operation_detail={
                    "min_severity": min_severity,
                    "total_comments": result.get("total_comments", 0),
                    "extracted": result.get("extracted", 0),
                    "failed": result.get("failed", 0)
                },
                request=http_request
            )
        except Exception as log_error:
            # 日志记录失败不影响主流程
            print(f"记录操作日志失败: {log_error}")
        
        return {
            "success": True,
            "data": result,
            "message": f"已提取 {result['extracted']} 条知识"
        }
    except Exception as e:
        import traceback
        error_detail = str(e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"批量提取失败: {error_detail}")


@app.get("/api/v1/operation-logs")
async def get_operation_logs(
    current_user: User = Depends(require_auth),
    limit: int = 50
):
    """获取操作日志"""
    if current_user.role == "admin":
        # 管理员可以查看所有日志
        logs = operation_log_service.get_all_logs(limit=limit)
    else:
        # 普通用户只能查看自己的日志
        logs = operation_log_service.get_user_logs(current_user.id, limit=limit)
    
    return {
        "success": True,
        "data": logs
    }


@app.get("/api/v1/statistics/dashboard")
async def get_dashboard(
    current_user: User = Depends(require_auth)
):
    """获取数据看板（需要登录）"""
    try:
        data = statistics_service.get_dashboard_data()
        return {
            "success": True,
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/statistics/top-issues")
async def get_top_issues(
    limit: int = 10,
    current_user: User = Depends(require_auth)
):
    """获取高频问题TopN"""
    try:
        issues = statistics_service.get_top_issues(limit)
        return {
            "success": True,
            "data": issues
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/statistics/knowledge-trend")
async def get_knowledge_trend(
    days: int = 30,
    current_user: User = Depends(require_auth)
):
    """获取知识沉淀趋势"""
    try:
        trend = statistics_service.get_knowledge_trend(days)
        return {
            "success": True,
            "data": trend
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/statistics/review-stats")
async def get_review_statistics(
    current_user: User = Depends(require_auth)
):
    """获取审查统计"""
    try:
        stats = statistics_service.get_review_statistics()
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/statistics/issue-details")
async def get_issue_details(
    issue_type: str,
    severity: str,
    limit: int = 20,
    current_user: User = Depends(require_auth)
):
    """获取问题详情列表"""
    try:
        # 清理参数，移除可能的特殊字符
        issue_type = issue_type.strip()
        severity = severity.strip()
        
        # 验证参数
        if not issue_type or not severity:
            raise HTTPException(status_code=400, detail="参数不完整")
        
        # 如果issue_type包含斜杠，只取第一部分
        if '/' in issue_type:
            issue_type = issue_type.split('/')[0]
        
        details = statistics_service.get_issue_details(issue_type, severity, limit)
        return {
            "success": True,
            "data": details
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"获取问题详情失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取问题详情失败: {str(e)}")


@app.get("/api/v1/statistics/severity-issues")
async def get_severity_issues(
    severity: str,
    limit: int = 20,
    current_user: User = Depends(require_auth)
):
    """获取特定严重度的问题列表"""
    try:
        # 清理参数
        severity = severity.strip()
        
        # 验证参数
        if not severity:
            raise HTTPException(status_code=400, detail="严重度参数不能为空")
        
        # 验证严重度值
        if severity not in ['high', 'medium', 'low']:
            raise HTTPException(status_code=400, detail=f"无效的严重度值: {severity}")
        
        issues = statistics_service.get_severity_issues(severity, limit)
        return {
            "success": True,
            "data": issues
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"获取严重度问题列表失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取严重度问题列表失败: {str(e)}")


class ChatRequest(BaseModel):
    question: str
    context: Optional[str] = ""  # 审查建议上下文
    review_id: Optional[int] = None  # 关联的审查ID


@app.post("/api/v1/chat")
async def chat_with_ai(
    request: ChatRequest,
    current_user: User = Depends(require_auth),
    http_request: Request = None
):
    """智能追问功能：基于审查建议进行对话"""
    try:
        from ollama_service import ollama_service
        
        # 构建上下文提示
        context_prompt = ""
        if request.context:
            context_prompt = f"\n审查建议上下文：\n{request.context}\n"
        
        # 如果有review_id，获取更多上下文
        if request.review_id:
            db = next(get_db())
            try:
                review = db.query(CodeReview).filter(CodeReview.id == request.review_id).first()
                if review and review.review_result:
                    issues = review.review_result.get('issues', [])
                    if issues:
                        context_prompt += f"\n相关问题：\n"
                        for issue in issues[:3]:  # 只取前3个问题
                            context_prompt += f"- {issue.get('description', '')}\n"
            finally:
                db.close()
        
        # 构建完整提示
        full_prompt = f"""你是一个代码审查助手。用户针对代码审查建议提出了问题，请基于上下文给出详细、专业的回答。

{context_prompt}

用户问题：{request.question}

请用中文回答，回答要：
1. 准确理解用户的问题
2. 基于审查建议上下文给出具体建议
3. 如果涉及代码问题，提供改进方案
4. 回答要简洁明了，不超过200字"""
        
        # 调用Ollama生成回答
        try:
            start_time = time.time()
            response = ollama_service.ollama_client.generate(
                model=ollama_service.llm_model,
                prompt=full_prompt,
                options={"temperature": 0.7}
            )
            
            # 解析响应 - 处理流式和非流式响应
            answer = ""
            if isinstance(response, dict):
                answer = response.get("response", "")
            elif hasattr(response, "response"):
                answer = response.response
            elif hasattr(response, "__iter__") and not isinstance(response, str):
                # 如果是生成器（流式响应），收集所有内容
                for chunk in response:
                    if isinstance(chunk, dict):
                        answer += chunk.get("response", "")
                    elif hasattr(chunk, "response"):
                        answer += chunk.response
                    else:
                        answer += str(chunk)
            else:
                answer = str(response)
            
            # 如果没有得到答案，返回默认消息
            if not answer or answer.strip() == "":
                answer = "抱歉，我暂时无法回答这个问题。请尝试重新提问或提供更多上下文信息。"
        except Exception as e:
            print(f"调用Ollama生成回答失败: {e}")
            import traceback
            traceback.print_exc()
            answer = f"生成回答时出错: {str(e)}"
        
        # 记录操作日志
        operation_log_service.log_operation(
            user_id=current_user.id,
            operation_type="chat_question",
            operation_detail={
                "question": request.question,
                "review_id": request.review_id
            },
            request=http_request
        )
        
        return {
            "success": True,
            "data": {
                "answer": answer,
                "question": request.question
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "message": "服务运行正常"}


if __name__ == "__main__":
    import uvicorn
    from config import APP_HOST, APP_PORT
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)

