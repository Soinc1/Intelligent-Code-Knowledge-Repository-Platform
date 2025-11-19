"""操作历史记录服务"""
from database import get_db, OperationLog, User
from sqlalchemy.orm import Session
from typing import Optional
from fastapi import Request


class OperationLogService:
    """操作日志服务"""
    
    @staticmethod
    def log_operation(
        user_id: int,
        operation_type: str,
        operation_detail: dict,
        request: Optional[Request] = None
    ):
        """记录操作历史"""
        db = next(get_db())
        try:
            # 获取IP和User-Agent
            ip_address = None
            user_agent = None
            if request:
                ip_address = request.client.host if request.client else None
                user_agent = request.headers.get("user-agent")
            
            log = OperationLog(
                user_id=user_id,
                operation_type=operation_type,
                operation_detail=operation_detail,
                ip_address=ip_address,
                user_agent=user_agent
            )
            db.add(log)
            db.commit()
        except Exception as e:
            print(f"记录操作日志失败: {e}")
            db.rollback()
        finally:
            db.close()
    
    @staticmethod
    def get_user_logs(user_id: int, limit: int = 50):
        """获取用户操作日志"""
        db = next(get_db())
        try:
            logs = db.query(OperationLog).filter(
                OperationLog.user_id == user_id
            ).order_by(OperationLog.created_at.desc()).limit(limit).all()
            
            return [{
                "id": log.id,
                "operation_type": log.operation_type,
                "operation_detail": log.operation_detail,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat() if log.created_at else None
            } for log in logs]
        finally:
            db.close()
    
    @staticmethod
    def get_all_logs(limit: int = 100):
        """获取所有操作日志（管理员）"""
        db = next(get_db())
        try:
            logs = db.query(OperationLog).order_by(
                OperationLog.created_at.desc()
            ).limit(limit).all()
            
            return [{
                "id": log.id,
                "user_id": log.user_id,
                "operation_type": log.operation_type,
                "operation_detail": log.operation_detail,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat() if log.created_at else None
            } for log in logs]
        finally:
            db.close()


# 全局实例
operation_log_service = OperationLogService()

