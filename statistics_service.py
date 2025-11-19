"""数据统计服务"""
from database import get_db, ReviewComment, KnowledgeBase, CodeReview, OperationLog
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from typing import Dict, List
from collections import Counter


class StatisticsService:
    """统计数据服务"""
    
    def get_top_issues(self, limit: int = 10) -> List[Dict]:
        """获取高频问题Top10"""
        db = next(get_db())
        try:
            # 统计审查评论中的问题类型和严重程度
            results = db.query(
                ReviewComment.comment_type,
                ReviewComment.severity,
                func.count(ReviewComment.id).label('count')
            ).group_by(
                ReviewComment.comment_type,
                ReviewComment.severity
            ).order_by(desc('count')).limit(limit * 2).all()
            
            # 按问题类型聚合
            issue_counter = Counter()
            for result in results:
                # 处理 None 值，将其转换为 'general'
                comment_type = result.comment_type if result.comment_type else 'general'
                severity = result.severity if result.severity else 'medium'
                issue_key = f"{comment_type}_{severity}"
                issue_counter[issue_key] += result.count
            
            # 转换为列表格式
            top_issues = []
            for (issue_key, count) in issue_counter.most_common(limit):
                parts = issue_key.split('_', 1)  # 只分割一次，保留后面的下划线
                issue_type = parts[0] if len(parts) > 0 and parts[0] else 'general'
                severity = parts[1] if len(parts) > 1 and parts[1] else 'medium'
                
                # 处理 None 值
                if issue_type.lower() in ['none', 'null']:
                    issue_type = 'general'
                
                top_issues.append({
                    "type": issue_type,
                    "severity": severity,
                    "count": count,
                    "label": self._get_issue_label(issue_type, severity)
                })
            
            return top_issues
        finally:
            db.close()
    
    def get_knowledge_trend(self, days: int = 30) -> Dict:
        """获取知识沉淀趋势"""
        db = next(get_db())
        try:
            # 获取最近N天的知识库增长趋势
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 按日期统计知识库新增数量
            results = db.query(
                func.date(KnowledgeBase.created_at).label('date'),
                func.count(KnowledgeBase.id).label('count')
            ).filter(
                KnowledgeBase.created_at >= start_date
            ).group_by(
                func.date(KnowledgeBase.created_at)
            ).order_by('date').all()
            
            # 按日期统计审查评论数量（作为知识来源）
            comment_results = db.query(
                func.date(ReviewComment.review_date).label('date'),
                func.count(ReviewComment.id).label('count')
            ).filter(
                ReviewComment.review_date >= start_date
            ).group_by(
                func.date(ReviewComment.review_date)
            ).order_by('date').all()
            
            # 构建日期范围
            date_list = []
            knowledge_data = []
            comment_data = []
            
            current_date = start_date.date()
            while current_date <= end_date.date():
                date_str = current_date.strftime('%Y-%m-%d')
                date_list.append(date_str)
                
                # 查找对应日期的数据
                knowledge_count = next((r.count for r in results if str(r.date) == date_str), 0)
                comment_count = next((r.count for r in comment_results if str(r.date) == date_str), 0)
                
                knowledge_data.append(knowledge_count)
                comment_data.append(comment_count)
                
                current_date += timedelta(days=1)
            
            # 计算知识沉淀率（知识库条目数 / 审查评论数）
            total_knowledge = sum(knowledge_data)
            total_comments = sum(comment_data)
            knowledge_rate = (total_knowledge / total_comments * 100) if total_comments > 0 else 0
            
            return {
                "dates": date_list,
                "knowledge_count": knowledge_data,
                "comment_count": comment_data,
                "total_knowledge": total_knowledge,
                "total_comments": total_comments,
                "knowledge_rate": round(knowledge_rate, 2)
            }
        finally:
            db.close()
    
    def get_review_statistics(self) -> Dict:
        """获取审查统计"""
        db = next(get_db())
        try:
            # 总审查次数
            total_reviews = db.query(func.count(CodeReview.id)).scalar() or 0
            
            # 总代码文件数
            total_files = db.query(func.count(CodeReview.code_file_id.distinct())).scalar() or 0
            
            # 总问题数（从审查结果中统计）
            total_issues = 0
            reviews = db.query(CodeReview.review_result).all()
            for review in reviews:
                if review.review_result and isinstance(review.review_result, dict):
                    issues = review.review_result.get('issues', [])
                    total_issues += len(issues)
            
            # 平均审查时间
            avg_review_time = db.query(func.avg(CodeReview.review_time_ms)).scalar() or 0
            
            # 按严重程度统计问题
            severity_stats = db.query(
                ReviewComment.severity,
                func.count(ReviewComment.id).label('count')
            ).group_by(ReviewComment.severity).all()
            
            severity_distribution = {
                "high": 0,
                "medium": 0,
                "low": 0
            }
            for stat in severity_stats:
                if stat.severity in severity_distribution:
                    severity_distribution[stat.severity] = stat.count
            
            # 知识库统计
            total_knowledge = db.query(func.count(KnowledgeBase.id)).scalar() or 0
            
            # 知识复用率（有匹配到历史案例的审查比例）
            reviews_with_matches = db.query(func.count(CodeReview.id)).filter(
                CodeReview.matched_knowledge_ids.isnot(None)
            ).scalar() or 0
            reuse_rate = (reviews_with_matches / total_reviews * 100) if total_reviews > 0 else 0
            
            return {
                "total_reviews": total_reviews,
                "total_files": total_files,
                "total_issues": total_issues,
                "total_knowledge": total_knowledge,
                "avg_review_time_ms": round(avg_review_time, 2),
                "severity_distribution": severity_distribution,
                "knowledge_reuse_rate": round(reuse_rate, 2)
            }
        finally:
            db.close()
    
    def get_dashboard_data(self) -> Dict:
        """获取完整看板数据"""
        return {
            "top_issues": self.get_top_issues(10),
            "knowledge_trend": self.get_knowledge_trend(30),
            "review_statistics": self.get_review_statistics()
        }
    
    def get_issue_details(self, issue_type: str, severity: str, limit: int = 20) -> List[Dict]:
        """获取特定类型和严重度的问题详情"""
        db = next(get_db())
        try:
            # 处理 None 或空字符串的情况
            from sqlalchemy import or_
            
            # 构建查询条件
            filters = [ReviewComment.severity == severity]
            
            # 处理问题类型
            if issue_type and issue_type.lower() not in ['none', 'null', '']:
                # 如果 issue_type 是 'unknown' 或 'general'，查询 comment_type 为 None 或空字符串的记录
                if issue_type.lower() in ['unknown', 'general', 'none']:
                    filters.append(or_(
                        ReviewComment.comment_type.is_(None),
                        ReviewComment.comment_type == '',
                        ReviewComment.comment_type == 'general'
                    ))
                else:
                    filters.append(ReviewComment.comment_type == issue_type)
            else:
                # 如果没有指定类型，查询所有类型
                filters.append(or_(
                    ReviewComment.comment_type.is_(None),
                    ReviewComment.comment_type == '',
                    ReviewComment.comment_type == issue_type
                ))
            
            comments = db.query(ReviewComment).filter(
                *filters
            ).order_by(desc(ReviewComment.review_date)).limit(limit).all()
            
            details = []
            for comment in comments:
                details.append({
                    "id": comment.id,
                    "comment_text": comment.comment_text,
                    "code_snippet": comment.code_snippet,
                    "review_date": comment.review_date.isoformat() if comment.review_date else None,
                    "code_file_id": comment.code_file_id,
                    "comment_type": comment.comment_type or "general"
                })
            
            return details
        finally:
            db.close()
    
    def get_severity_issues(self, severity: str, limit: int = 20) -> List[Dict]:
        """获取特定严重度的问题列表"""
        db = next(get_db())
        try:
            comments = db.query(ReviewComment).filter(
                ReviewComment.severity == severity
            ).order_by(desc(ReviewComment.review_date)).limit(limit).all()
            
            issues = []
            for comment in comments:
                issues.append({
                    "id": comment.id,
                    "comment_text": comment.comment_text,
                    "comment_type": comment.comment_type,
                    "code_snippet": comment.code_snippet,
                    "review_date": comment.review_date.isoformat() if comment.review_date else None,
                    "code_file_id": comment.code_file_id
                })
            
            return issues
        finally:
            db.close()
    
    def _get_issue_label(self, issue_type: str, severity: str) -> str:
        """获取问题标签"""
        type_labels = {
            "security": "安全性",
            "performance": "性能",
            "style": "代码规范",
            "best_practice": "最佳实践",
            "general": "一般问题"
        }
        severity_labels = {
            "high": "高",
            "medium": "中",
            "low": "低"
        }
        type_label = type_labels.get(issue_type, issue_type)
        severity_label = severity_labels.get(severity, severity)
        return f"{type_label} ({severity_label}严重度)"


# 全局实例
statistics_service = StatisticsService()

