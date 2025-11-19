"""Ollama服务封装"""
import ollama
from config import OLLAMA_HOST, OLLAMA_PORT, OLLAMA_EMBEDDING_MODEL, OLLAMA_LLM_MODEL
import time


class OllamaService:
    """Ollama服务封装类"""
    
    def __init__(self):
        # 根据ollama库版本，尝试不同的初始化方式
        # 错误信息显示base_url参数冲突，说明新版本可能使用不同的参数
        try:
            # 方式1: 尝试使用host参数（不带http://）
            self.ollama_client = ollama.Client(host=f"{OLLAMA_HOST}:{OLLAMA_PORT}")
            print(f"Ollama客户端已连接: {OLLAMA_HOST}:{OLLAMA_PORT}")
        except (TypeError, Exception) as e1:
            try:
                # 方式2: 尝试使用host参数（带http://）
                self.ollama_client = ollama.Client(host=f"http://{OLLAMA_HOST}:{OLLAMA_PORT}")
                print(f"Ollama客户端已连接: http://{OLLAMA_HOST}:{OLLAMA_PORT}")
            except (TypeError, Exception) as e2:
                try:
                    # 方式3: 尝试直接传递host和port作为关键字参数
                    self.ollama_client = ollama.Client(host=OLLAMA_HOST, port=OLLAMA_PORT)
                    print(f"Ollama客户端已连接: {OLLAMA_HOST}:{OLLAMA_PORT}")
                except (TypeError, Exception) as e3:
                    # 方式4: 使用环境变量设置，然后使用默认连接
                    import os
                    os.environ['OLLAMA_HOST'] = f"{OLLAMA_HOST}:{OLLAMA_PORT}"
                    self.ollama_client = ollama.Client()
                    print(f"警告: 使用默认Ollama连接，已设置环境变量OLLAMA_HOST={OLLAMA_HOST}:{OLLAMA_PORT}")
        
        self.embedding_model = OLLAMA_EMBEDDING_MODEL
        self.llm_model = OLLAMA_LLM_MODEL
    
    def get_embedding(self, text: str) -> list:
        """获取文本的embedding向量"""
        try:
            # Ollama embeddings API
            response = self.ollama_client.embeddings(
                model=self.embedding_model,
                prompt=text
            )
            # 处理不同的响应格式
            if isinstance(response, dict):
                # 字典格式
                if "embedding" in response:
                    return response["embedding"]
            elif hasattr(response, "embedding"):
                # 对象格式（EmbeddingsResponse）
                return response.embedding
            elif isinstance(response, list):
                # 列表格式
                return response
            else:
                # 尝试获取embedding属性
                try:
                    return getattr(response, "embedding", None) or list(response)
                except:
                    raise ValueError(f"意外的响应格式: {type(response)}")
        except Exception as e:
            print(f"获取embedding失败: {e}")
            # 如果失败，返回一个默认维度的零向量（bge-m3通常是1024维）
            print("返回默认零向量")
            return [0.0] * 1024
    
    def get_embeddings_batch(self, texts: list) -> list:
        """批量获取embeddings"""
        embeddings = []
        for text in texts:
            embedding = self.get_embedding(text)
            embeddings.append(embedding)
        return embeddings
    
    def generate_code_review(self, code: str, related_cases: list = None, ast_info: dict = None) -> dict:
        """生成代码审查建议"""
        # 构建提示词
        prompt = self._build_review_prompt(code, related_cases, ast_info)
        
        try:
            start_time = time.time()
            response = self.ollama_client.generate(
                model=self.llm_model,
                prompt=prompt,
                options={
                    "temperature": 0.3,
                    "top_p": 0.9,
                }
            )
            elapsed_time = int((time.time() - start_time) * 1000)
            
            # 解析响应 - 处理流式和非流式响应
            if isinstance(response, dict):
                review_text = response.get("response", "")
            elif hasattr(response, "response"):
                review_text = response.response
            else:
                # 如果是生成器（流式响应），收集所有内容
                review_text = ""
                for chunk in response:
                    if isinstance(chunk, dict):
                        review_text += chunk.get("response", "")
                    elif hasattr(chunk, "response"):
                        review_text += chunk.response
            issues = self._parse_review_response(review_text)
            
            return {
                "issues": issues,
                "raw_response": review_text,
                "review_time_ms": elapsed_time
            }
        except Exception as e:
            print(f"生成代码审查失败: {e}")
            raise
    
    def _build_review_prompt(self, code: str, related_cases: list = None, ast_info: dict = None) -> str:
        """构建审查提示词"""
        prompt = """你是一个资深的代码审查专家。请分析以下代码，并基于历史审查案例和代码结构提供建议。

代码:
```{language}
{code}
```

""".format(
            code=code,
            language=ast_info.get("language", "python") if ast_info else "python"
        )
        
        # 添加代码结构信息
        if ast_info:
            structure_info = []
            if ast_info.get("function_count", 0) > 0:
                structure_info.append(f"包含 {ast_info['function_count']} 个函数: {', '.join([f['name'] for f in ast_info.get('functions', [])[:5]])}")
            if ast_info.get("class_count", 0) > 0:
                structure_info.append(f"包含 {ast_info['class_count']} 个类: {', '.join([c['name'] for c in ast_info.get('classes', [])[:5]])}")
            if ast_info.get("import_count", 0) > 0:
                imports = ast_info.get("imports", [])
                if imports:
                    import_names = [imp.get("module", "") for imp in imports[:5]]
                    structure_info.append(f"导入了 {ast_info['import_count']} 个模块: {', '.join(import_names)}")
            
            if structure_info:
                prompt += "代码结构信息:\n"
                prompt += "\n".join(f"- {info}" for info in structure_info)
                prompt += "\n\n"
        
        if related_cases:
            prompt += "历史相关案例:\n"
            for i, case in enumerate(related_cases[:3], 1):  # 最多3个案例
                prompt += f"{i}. {case.get('comment_text', case.get('content', ''))}\n"
            prompt += "\n"
        
        prompt += """请从以下角度审查:
1. 安全性 (SQL注入、XSS、权限控制等)
2. 性能 (算法复杂度、资源泄漏等)
3. 代码规范 (命名、结构、可读性等)
4. 最佳实践 (设计模式、架构合理性等)

请以JSON格式输出，格式如下:
{
  "issues": [
    {
      "type": "security/performance/style/best_practice",
      "severity": "high/medium/low",
      "description": "问题描述",
      "suggestion": "修复建议",
      "code_snippet": "相关代码片段"
    }
  ]
}

如果代码没有问题，返回空的issues数组。
"""
        return prompt
    
    def _parse_review_response(self, response_text: str) -> list:
        """解析审查响应"""
        import json
        import re
        
        # 尝试提取JSON
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group())
                return result.get("issues", [])
            except:
                pass
        
        # 如果无法解析JSON，返回原始文本作为单个问题
        return [{
            "type": "general",
            "severity": "medium",
            "description": response_text[:500],
            "suggestion": "请查看详细审查意见",
            "code_snippet": ""
        }]


# 全局Ollama服务实例
ollama_service = OllamaService()

