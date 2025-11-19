"""业务逻辑服务"""
from database import get_db, CodeFile, ReviewComment, KnowledgeBase, CodeReview
from milvus_client import milvus_client
from ollama_service import ollama_service
from code_parser import code_parser
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from sqlalchemy.orm import Session


class CodeReviewService:
    """代码审查服务"""
    
    def __init__(self):
        self.ollama = ollama_service
        self.milvus = milvus_client
    
    def review_code(self, code: str, language: str = "python", file_name: str = "code.py") -> dict:
        """审查代码"""
        # 1. 生成代码hash
        file_hash = hashlib.sha256(code.encode()).hexdigest()
        
        # 2. 解析代码结构（AST解析）
        ast_data = code_parser.parse_code(code, language)
        
        # 3. 查找相关历史案例
        related_cases = self._find_related_cases(code)
        
        # 4. AI生成审查建议（将AST信息传递给AI，帮助更好地理解代码）
        review_result = self.ollama.generate_code_review(code, related_cases, ast_info=ast_data)
        
        # 5. 保存代码文件（如果不存在）
        db = next(get_db())
        try:
            code_file = db.query(CodeFile).filter(CodeFile.file_hash == file_hash).first()
            if not code_file:
                code_file = CodeFile(
                    file_name=file_name,
                    file_content=code,
                    language=language,
                    file_hash=file_hash,
                    ast_json=ast_data  # 保存AST解析结果
                )
                db.add(code_file)
                db.commit()
                db.refresh(code_file)
            else:
                # 如果文件已存在但AST为空，更新AST
                if not code_file.ast_json:
                    code_file.ast_json = ast_data
                    db.commit()
            
            # 5. 保存审查记录
            matched_knowledge_ids = [case.get("id") for case in related_cases if case.get("id")]
            review_record = CodeReview(
                code_file_id=code_file.id,
                review_result=review_result,
                matched_knowledge_ids=matched_knowledge_ids,
                review_time_ms=review_result.get("review_time_ms", 0)
            )
            db.add(review_record)
            db.commit()
            
            # 6. 用户A功能：自动保存审查评论到知识库（如果审查发现问题）
            saved_comments = []
            for issue in review_result.get("issues", []):
                if issue.get("severity") in ["high", "medium"]:  # 只保存中高严重程度的问题
                    try:
                        comment = self.save_review_comment(
                            code_file_id=code_file.id,
                            comment_text=f"{issue.get('description', '')}\n建议: {issue.get('suggestion', '')}",
                            comment_type=issue.get("type", "general"),
                            severity=issue.get("severity", "medium"),
                            code_snippet=issue.get("code_snippet", "")
                        )
                        saved_comments.append(comment.get("id") if isinstance(comment, dict) else comment.id)
                    except Exception as e:
                        print(f"保存审查评论失败: {e}")
            
            return {
                "review_id": review_record.id,
                "file_id": code_file.id,
                "issues": review_result.get("issues", []),
                "related_cases": related_cases,
                "review_time_ms": review_result.get("review_time_ms", 0),
                "saved_comments": saved_comments,  # 用户A：保存的评论ID
                "ast_info": ast_data  # AST解析信息
            }
        finally:
            db.close()
    
    def get_code_history(self, code: str, top_k: int = 10) -> dict:
        """用户B功能：获取代码的历史问题和最佳实践"""
        # 1. 查找相关的历史审查案例
        related_cases = self._find_related_cases(code, top_k=top_k)
        
        # 2. 分类整理
        history_issues = []
        best_practices = []
        
        for case in related_cases:
            if case.get("type") == "review_comment":
                history_issues.append({
                    "id": case.get("id"),
                    "comment": case.get("comment_text", ""),
                    "type": case.get("comment_type", ""),
                    "severity": case.get("severity", ""),
                    "similarity": case.get("similarity", 0)
                })
            elif case.get("type") == "knowledge":
                best_practices.append({
                    "id": case.get("id"),
                    "title": case.get("title", ""),
                    "content": case.get("content", ""),
                    "category": case.get("category", ""),
                    "similarity": case.get("similarity", 0)
                })
        
        return {
            "history_issues": history_issues,
            "best_practices": best_practices,
            "total_found": len(related_cases)
        }
    
    def _find_related_cases(self, code: str, top_k: int = 5) -> list:
        """查找相关的历史案例"""
        # 1. 生成代码的embedding
        code_embedding = self.ollama.get_embedding(code)
        
        # 2. 在Milvus中搜索
        collection_name = "code_review_collection"
        if not milvus_client.get_collection(collection_name):
            return []
        
        try:
            results = self.milvus.search_vectors(collection_name, [code_embedding], top_k=top_k)
            
            if not results or len(results) == 0:
                return []
            
            # 3. 从MySQL获取完整信息
            db = next(get_db())
            related_cases = []
            try:
                for hit in results[0]:
                    entity_id = hit.entity.get("entity_id")
                    entity_type = hit.entity.get("entity_type")
                    
                    if entity_type == "review_comment":
                        comment = db.query(ReviewComment).filter(ReviewComment.id == entity_id).first()
                        if comment:
                            related_cases.append({
                                "id": comment.id,
                                "type": "review_comment",
                                "comment_text": comment.comment_text,
                                "comment_type": comment.comment_type,
                                "severity": comment.severity,
                                "similarity": hit.score
                            })
                    elif entity_type == "knowledge":
                        knowledge = db.query(KnowledgeBase).filter(KnowledgeBase.id == entity_id).first()
                        if knowledge:
                            related_cases.append({
                                "id": knowledge.id,
                                "type": "knowledge",
                                "title": knowledge.title,
                                "content": knowledge.content,
                                "category": knowledge.category,
                                "similarity": hit.score
                            })
            finally:
                db.close()
            
            return related_cases
        except Exception as e:
            print(f"查找相关案例失败: {e}")
            return []
    
    def save_review_comment(self, code_file_id: int, comment_text: str, 
                           comment_type: str, severity: str, code_snippet: str = ""):
        """保存审查评论"""
        db = next(get_db())
        try:
            # 创建评论
            comment = ReviewComment(
                code_file_id=code_file_id,
                comment_text=comment_text,
                comment_type=comment_type,
                severity=severity,
                code_snippet=code_snippet
            )
            db.add(comment)
            db.commit()
            db.refresh(comment)
            
            # 生成embedding并保存到Milvus
            embedding = self.ollama.get_embedding(comment_text)
            collection_name = "code_review_collection"
            
            # 确保集合存在
            dim = len(embedding)
            self.milvus.create_collection_if_not_exists(collection_name, dim)
            
            # 插入向量
            self.milvus.insert_vectors(
                collection_name=collection_name,
                embeddings=[embedding],
                entity_ids=[comment.id],
                entity_type="review_comment",
                metadata_list=[{
                    "comment_type": comment_type,
                    "severity": severity
                }]
            )
            
            # 在关闭会话前获取ID
            comment_id = comment.id
            
            # 更新milvus_id
            comment.milvus_id = str(comment_id)
            db.commit()
            
            # 在关闭会话前获取所有需要的属性
            result = {
                "id": comment_id,
                "code_file_id": comment.code_file_id,
                "comment_text": comment.comment_text,
                "comment_type": comment.comment_type,
                "severity": comment.severity,
                "code_snippet": comment.code_snippet,
                "milvus_id": comment.milvus_id
            }
            
            return result
        finally:
            db.close()


class KnowledgeService:
    """知识库服务"""
    
    def __init__(self):
        self.ollama = ollama_service
        self.milvus = milvus_client
    
    def auto_extract_knowledge_from_review(self, review_comment_id: int) -> dict:
        """用户C功能：自动将审查评论转化为知识库"""
        db = next(get_db())
        try:
            # 获取审查评论
            comment = db.query(ReviewComment).filter(ReviewComment.id == review_comment_id).first()
            if not comment:
                raise ValueError("审查评论不存在")
            
            # 检查评论内容是否为空
            if not comment.comment_text or not comment.comment_text.strip():
                raise ValueError(f"评论 {review_comment_id} 的内容为空，无法提取知识")
            
            # 使用AI提取知识
            prompt = f"""请将以下代码审查评论转化为结构化的知识库条目。

审查评论：
{comment.comment_text}

代码片段：
{comment.code_snippet or '无'}

请提取以下信息：
1. 知识标题（简洁描述问题）
2. 知识内容（详细说明）
3. 代码模式（如果有）
4. 最佳实践建议

请以JSON格式输出：
{{
  "title": "知识标题",
  "content": "知识内容",
  "code_pattern": "代码模式",
  "best_practice": "最佳实践"
}}"""
            
            try:
                # 使用Ollama服务生成响应
                try:
                    response = self.ollama.ollama_client.generate(
                        model=self.ollama.llm_model,
                        prompt=prompt,
                        options={"temperature": 0.3}
                    )
                except Exception as ollama_error:
                    print(f"Ollama服务调用失败: {ollama_error}")
                    raise ollama_error
                
                # 解析响应
                import json
                import re
                # 处理不同格式的响应
                if isinstance(response, dict):
                    response_text = response.get("response", "")
                elif hasattr(response, "response"):
                    response_text = response.response
                elif hasattr(response, "__iter__") and not isinstance(response, str):
                    # 处理流式响应
                    response_text = ""
                    for chunk in response:
                        if isinstance(chunk, dict):
                            response_text += chunk.get("response", "")
                        elif hasattr(chunk, "response"):
                            response_text += chunk.response
                        else:
                            response_text += str(chunk)
                else:
                    response_text = str(response)
                
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    try:
                        knowledge_data = json.loads(json_match.group())
                    except json.JSONDecodeError as json_error:
                        print(f"JSON解析失败: {json_error}, 使用默认值")
                        knowledge_data = {
                            "title": f"代码审查建议: {comment.comment_type}",
                            "content": comment.comment_text,
                            "code_pattern": comment.code_snippet or "",
                            "best_practice": "请参考审查建议进行改进"
                        }
                else:
                    # 如果无法解析，使用默认值
                    knowledge_data = {
                        "title": f"代码审查建议: {comment.comment_type}",
                        "content": comment.comment_text,
                        "code_pattern": comment.code_snippet or "",
                        "best_practice": "请参考审查建议进行改进"
                    }
                
                # 创建知识库条目
                knowledge = self.add_knowledge(
                    title=knowledge_data.get("title", f"审查建议: {comment.comment_type}"),
                    content=knowledge_data.get("content", comment.comment_text),
                    category=comment.comment_type or "general",
                    code_pattern=knowledge_data.get("code_pattern", comment.code_snippet or ""),
                    best_practice=knowledge_data.get("best_practice", ""),
                    source_comment_id=comment.id
                )
                
                return knowledge
            except Exception as e:
                print(f"AI提取知识失败，使用简化版本: {e}")
                import traceback
                traceback.print_exc()
                # 如果AI失败，直接使用评论内容创建知识
                knowledge = self.add_knowledge(
                    title=f"代码审查建议: {comment.comment_type}",
                    content=comment.comment_text,
                    category=comment.comment_type or "general",
                    code_pattern=comment.code_snippet or "",
                    best_practice="请参考审查建议进行改进",
                    source_comment_id=comment.id
                )
                return knowledge
        finally:
            db.close()
    
    def batch_extract_knowledge(self, min_severity: str = "medium") -> dict:
        """批量将审查评论转化为知识库"""
        db = None
        try:
            print(f"开始批量提取知识，严重度: {min_severity}")
            db = next(get_db())
            
            # 获取符合条件的评论（未转化为知识的）
            severity_filter = ["high", "medium"] if min_severity == "medium" else ["high"]
            print(f"查询严重度为 {severity_filter} 的评论...")
            
            comments = db.query(ReviewComment).filter(
                ReviewComment.severity.in_(severity_filter)
            ).all()
            
            print(f"找到 {len(comments)} 条符合条件的评论")
            
            extracted_count = 0
            failed_count = 0
            skipped_count = 0
            error_messages = []
            
            for idx, comment in enumerate(comments, 1):
                try:
                    print(f"处理评论 {idx}/{len(comments)}: ID={comment.id}")
                    
                    # 跳过没有评论内容的记录
                    if not comment.comment_text or not comment.comment_text.strip():
                        print(f"跳过评论 {comment.id}: 评论内容为空")
                        skipped_count += 1
                        continue
                    
                    # 检查是否已经转化为知识（通过检查是否有相同内容的知识）
                    comment_preview = comment.comment_text[:50] if len(comment.comment_text) > 50 else comment.comment_text
                    existing = db.query(KnowledgeBase).filter(
                        KnowledgeBase.content.like(f"%{comment_preview}%")
                    ).first()
                    
                    if existing:
                        print(f"评论 {comment.id} 已存在相关知识，跳过")
                        skipped_count += 1
                        continue
                    
                    # auto_extract_knowledge_from_review 会创建自己的数据库会话，所以这里不需要传递db
                    print(f"开始提取评论 {comment.id} 的知识...")
                    self.auto_extract_knowledge_from_review(comment.id)
                    extracted_count += 1
                    print(f"成功提取评论 {comment.id} 的知识")
                    
                except Exception as e:
                    error_msg = f"提取评论 {comment.id} 失败: {str(e)}"
                    print(f"错误: {error_msg}")
                    import traceback
                    traceback.print_exc()
                    failed_count += 1
                    if len(error_messages) < 5:  # 只保存前5个错误信息
                        error_messages.append(error_msg)
            
            result = {
                "total_comments": len(comments),
                "extracted": extracted_count,
                "failed": failed_count,
                "skipped": skipped_count
            }
            
            print(f"批量提取完成: 总计={len(comments)}, 成功={extracted_count}, 失败={failed_count}, 跳过={skipped_count}")
            
            # 如果有错误，在结果中包含错误信息（用于调试）
            if error_messages:
                result["error_samples"] = error_messages
            
            return result
        except Exception as e:
            import traceback
            error_detail = f"批量提取过程出错: {str(e)}"
            print(f"严重错误: {error_detail}")
            traceback.print_exc()
            raise ValueError(error_detail)
        finally:
            if db:
                try:
                    db.close()
                except:
                    pass
    
    def add_knowledge(
        self,
        title: str,
        content: str,
        category: str = "",
        code_pattern: str = "",
        best_practice: str = "",
        status: str = "pending_review",
        tags: list = None,
        created_by: int = None,
        review_notes: str = "",
        source_comment_id: int = None
    ):
        """添加知识"""
        db = next(get_db())
        try:
            if tags is None:
                tags = []
            # 先保存到MySQL
            knowledge = KnowledgeBase(
                title=title,
                content=content,
                category=category,
                code_pattern=code_pattern,
                best_practice=best_practice,
                status=status,
                tags=tags,
                created_by=created_by,
                review_notes=review_notes,
                source_comment_id=source_comment_id
            )
            db.add(knowledge)
            db.commit()
            db.refresh(knowledge)
            
            # 在关闭会话前获取ID（避免DetachedInstanceError）
            knowledge_id = knowledge.id
            
            # 生成embedding并保存到Milvus（如果失败不影响MySQL数据）
            try:
                text_for_embedding = f"{title}\n{content}"
                embedding = self.ollama.get_embedding(text_for_embedding)
                collection_name = "code_review_collection"
                
                # 确保集合存在
                dim = len(embedding)
                self.milvus.create_collection_if_not_exists(collection_name, dim)
                
                # 插入向量
                self.milvus.insert_vectors(
                    collection_name=collection_name,
                    embeddings=[embedding],
                    entity_ids=[knowledge_id],
                    entity_type="knowledge",
                    metadata_list=[{
                        "category": category,
                        "title": title
                    }]
                )
                
                # 更新milvus_id（可选，不影响功能）
                try:
                    knowledge.milvus_id = str(knowledge_id)
                    db.commit()
                except Exception as e:
                    print(f"警告: 更新milvus_id失败: {e}")
                    db.rollback()
            except Exception as e:
                print(f"警告: Milvus向量插入失败，但知识已保存到MySQL: {e}")
                import traceback
                traceback.print_exc()
            
            # 在关闭会话前获取所有需要的属性
            return self._serialize_knowledge(knowledge)
        except Exception as e:
            db.rollback()
            print(f"添加知识失败: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            db.close()
    
    def get_all_knowledge(self, status: str = None, keyword: str = None, page: int = 1, page_size: int = 10):
        """获取所有知识，支持状态和关键字过滤，支持分页"""
        db = next(get_db())
        try:
            query = db.query(KnowledgeBase)
            if status and status not in ["all", ""]:
                query = query.filter(KnowledgeBase.status == status)
            if keyword:
                like_pattern = f"%{keyword}%"
                query = query.filter(KnowledgeBase.title.like(like_pattern) | KnowledgeBase.content.like(like_pattern))
            
            # 计算总数
            total = query.count()
            
            # 分页
            offset = (page - 1) * page_size
            knowledge_list = query.order_by(KnowledgeBase.updated_at.desc()).offset(offset).limit(page_size).all()
            
            return {
                "items": [self._serialize_knowledge(k) for k in knowledge_list],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 1
            }
        finally:
            db.close()

    def get_knowledge_by_id(self, knowledge_id: int) -> dict:
        db = next(get_db())
        try:
            knowledge = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_id).first()
            if not knowledge:
                return None
            return self._serialize_knowledge(knowledge)
        finally:
            db.close()

    def update_knowledge(self, knowledge_id: int, data: dict, reviewer_id: int = None) -> dict:
        db = next(get_db())
        try:
            knowledge = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_id).first()
            if not knowledge:
                raise ValueError("知识条目不存在")
            
            updatable_fields = ["title", "content", "category", "code_pattern", "best_practice", "status", "tags", "review_notes", "source_comment_id"]
            for field in updatable_fields:
                if field in data and data[field] is not None:
                    setattr(knowledge, field, data[field])
            
            if reviewer_id:
                knowledge.last_reviewed_by = reviewer_id
            knowledge.updated_at = datetime.now()
            
            db.commit()
            db.refresh(knowledge)
            
            # 更新向量
            try:
                text_for_embedding = f"{knowledge.title}\n{knowledge.content}"
                embedding = self.ollama.get_embedding(text_for_embedding)
                self.milvus.insert_vectors(
                    collection_name="code_review_collection",
                    embeddings=[embedding],
                    entity_ids=[knowledge.id],
                    entity_type="knowledge",
                    metadata_list=[{
                        "category": knowledge.category,
                        "title": knowledge.title,
                        "status": knowledge.status
                    }]
                )
            except Exception as e:
                print(f"更新知识向量失败: {e}")
            
            return self._serialize_knowledge(knowledge)
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def delete_knowledge(self, knowledge_id: int):
        db = next(get_db())
        try:
            knowledge = db.query(KnowledgeBase).filter(KnowledgeBase.id == knowledge_id).first()
            if not knowledge:
                raise ValueError("知识条目不存在")
            
            db.delete(knowledge)
            db.commit()
            
            try:
                self.milvus.delete_vectors("code_review_collection", [knowledge_id])
            except Exception as e:
                print(f"删除Milvus向量失败: {e}")
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    def get_knowledge_graph(self, limit: int = 30) -> dict:
        """构建知识图谱数据"""
        db = next(get_db())
        try:
            nodes = {}
            edges = []

            def add_node(entity_id: int, node_type: str, label: str, sub_label: str = "", meta: dict = None):
                node_key = f"{node_type}_{entity_id}"
                if node_key not in nodes:
                    nodes[node_key] = {
                        "id": node_key,
                        "entity_id": entity_id,
                        "type": node_type,
                        "label": label,
                        "sub_label": sub_label,
                        "meta": meta or {},
                        "level": {"code_file": 0, "review_comment": 1, "knowledge": 2}.get(node_type, 1)
                    }
                return node_key

            recent_reviews = db.query(CodeReview).order_by(CodeReview.created_at.desc()).limit(limit).all()
            if not recent_reviews:
                return {"nodes": [], "edges": []}

            code_files = []
            code_file_ids = set()
            for review in recent_reviews:
                if review.code_file:
                    code_files.append(review.code_file)
                    code_file_ids.add(review.code_file.id)

            if not code_files:
                return {"nodes": [], "edges": []}

            # 代码文件节点
            for cf in code_files:
                add_node(
                    cf.id,
                    "code_file",
                    cf.file_name or f"文件 {cf.id}",
                    cf.language or "unknown",
                    {"created_at": cf.created_at.isoformat() if cf.created_at else None}
                )

            # 获取相关的评论
            comments = db.query(ReviewComment).filter(ReviewComment.code_file_id.in_(code_file_ids)).limit(limit * 5).all()
            comment_map = {}
            for comment in comments:
                node_id = add_node(
                    comment.id,
                    "review_comment",
                    (comment.comment_text or "")[:40] + ("..." if comment.comment_text and len(comment.comment_text) > 40 else ""),
                    comment.comment_type or "general",
                    {"severity": comment.severity}
                )
                comment_map[comment.id] = node_id
                cf_node = f"code_file_{comment.code_file_id}"
                edges.append({
                    "source": cf_node,
                    "target": node_id,
                    "type": "review"
                })

            # 知识节点
            matched_ids = set()
            for review in recent_reviews:
                if review.matched_knowledge_ids:
                    ids = review.matched_knowledge_ids
                    if isinstance(ids, str):
                        try:
                            parsed = json.loads(ids)
                            if isinstance(parsed, list):
                                ids = parsed
                        except json.JSONDecodeError:
                            ids = [ids]
                    if isinstance(ids, list):
                        for kid in ids:
                            try:
                                matched_ids.add(int(kid))
                            except (TypeError, ValueError):
                                continue

            knowledge_query = db.query(KnowledgeBase)
            filter_conditions = []
            if comment_map:
                filter_conditions.append(KnowledgeBase.source_comment_id.in_(comment_map.keys()))
            if matched_ids:
                filter_conditions.append(KnowledgeBase.id.in_(matched_ids))

            if filter_conditions:
                from sqlalchemy import or_
                knowledge_records = knowledge_query.filter(or_(*filter_conditions)).all()
            else:
                knowledge_records = []

            knowledge_nodes = {}
            for knowledge in knowledge_records:
                node_id = add_node(
                    knowledge.id,
                    "knowledge",
                    knowledge.title,
                    knowledge.category or "general",
                    {"status": knowledge.status}
                )
                knowledge_nodes[knowledge.id] = node_id

                if knowledge.source_comment_id and knowledge.source_comment_id in comment_map:
                    edges.append({
                        "source": comment_map[knowledge.source_comment_id],
                        "target": node_id,
                        "type": "derived"
                    })

            # 代码文件与知识的直接关联（基于CodeReview匹配结果）
            for review in recent_reviews:
                if not review.code_file_id:
                    continue
                if review.matched_knowledge_ids:
                    ids = review.matched_knowledge_ids
                    if isinstance(ids, str):
                        try:
                            parsed = json.loads(ids)
                            if isinstance(parsed, list):
                                ids = parsed
                        except json.JSONDecodeError:
                            ids = [ids]
                    if isinstance(ids, list):
                        for kid in ids:
                            try:
                                kid_int = int(kid)
                            except (TypeError, ValueError):
                                continue
                            node_id = knowledge_nodes.get(kid_int)
                            if node_id:
                                edges.append({
                                    "source": f"code_file_{review.code_file_id}",
                                    "target": node_id,
                                    "type": "reference"
                                })

            return {
                "nodes": list(nodes.values()),
                "edges": edges
            }
        finally:
            db.close()

    def _serialize_knowledge(self, knowledge: KnowledgeBase) -> dict:
        return {
            "id": knowledge.id,
            "title": knowledge.title,
            "content": knowledge.content,
            "category": knowledge.category,
            "code_pattern": knowledge.code_pattern,
            "best_practice": knowledge.best_practice,
            "status": knowledge.status,
            "tags": knowledge.tags or [],
            "review_notes": knowledge.review_notes,
            "created_by": knowledge.created_by,
            "last_reviewed_by": knowledge.last_reviewed_by,
            "source_comment_id": knowledge.source_comment_id,
            "created_at": knowledge.created_at.isoformat() if knowledge.created_at else None,
            "updated_at": knowledge.updated_at.isoformat() if knowledge.updated_at else None
        }


# 全局服务实例
code_review_service = CodeReviewService()
knowledge_service = KnowledgeService()

