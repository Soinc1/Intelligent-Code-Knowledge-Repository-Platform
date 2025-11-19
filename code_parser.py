"""代码解析模块 - AST解析和代码结构提取"""
import ast
import json
from typing import Dict, List, Optional, Any
import re


class CodeParser:
    """代码解析器"""
    
    def __init__(self):
        self.supported_languages = {
            'python': self._parse_python,
            'javascript': self._parse_javascript,
            'java': self._parse_java,
            'go': self._parse_go,
            'cpp': self._parse_cpp
        }
    
    def parse_code(self, code: str, language: str = "python") -> Dict[str, Any]:
        """解析代码，提取结构信息"""
        language = language.lower()
        
        if language in self.supported_languages:
            parser_func = self.supported_languages[language]
            try:
                return parser_func(code)
            except Exception as e:
                print(f"解析{language}代码失败: {e}")
                return self._parse_generic(code, language)
        else:
            return self._parse_generic(code, language)
    
    def _parse_python(self, code: str) -> Dict[str, Any]:
        """解析Python代码"""
        try:
            tree = ast.parse(code)
            
            functions = []
            classes = []
            imports = []
            variables = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # 处理装饰器
                    decorators = []
                    for d in node.decorator_list:
                        if isinstance(d, ast.Name):
                            decorators.append(d.id)
                        elif isinstance(d, ast.Attribute):
                            decorators.append(f"{d.attr}")
                        else:
                            decorators.append(str(type(d).__name__))
                    
                    functions.append({
                        "name": node.name,
                        "line": node.lineno,
                        "args": [arg.arg for arg in node.args.args],
                        "decorators": decorators
                    })
                elif isinstance(node, ast.ClassDef):
                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                    # 处理基类
                    bases = []
                    for b in node.bases:
                        if isinstance(b, ast.Name):
                            bases.append(b.id)
                        elif isinstance(b, ast.Attribute):
                            bases.append(b.attr)
                        else:
                            bases.append(str(type(b).__name__))
                    
                    classes.append({
                        "name": node.name,
                        "line": node.lineno,
                        "methods": methods,
                        "bases": bases
                    })
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append({
                            "module": alias.name,
                            "alias": alias.asname
                        })
                elif isinstance(node, ast.ImportFrom):
                    imports.append({
                        "module": node.module or "",
                        "names": [alias.name for alias in node.names]
                    })
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            variables.append({
                                "name": target.id,
                                "line": node.lineno
                            })
            
            return {
                "language": "python",
                "functions": functions,
                "classes": classes,
                "imports": imports,
                "variables": variables,
                "function_count": len(functions),
                "class_count": len(classes),
                "import_count": len(imports),
                "structure": {
                    "has_main": any(f["name"] == "__main__" or f["name"] == "main" for f in functions),
                    "has_classes": len(classes) > 0,
                    "has_functions": len(functions) > 0
                }
            }
        except SyntaxError as e:
            return {
                "language": "python",
                "error": f"语法错误: {str(e)}",
                "functions": [],
                "classes": [],
                "imports": [],
                "variables": []
            }
    
    def _parse_javascript(self, code: str) -> Dict[str, Any]:
        """解析JavaScript代码（简单正则匹配）"""
        functions = []
        classes = []
        imports = []
        
        # 匹配函数定义
        function_pattern = r'(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:\([^)]*\)\s*=>|function)|(\w+)\s*:\s*function)'
        for match in re.finditer(function_pattern, code):
            func_name = match.group(1) or match.group(2) or match.group(3)
            if func_name:
                functions.append({"name": func_name, "line": code[:match.start()].count('\n') + 1})
        
        # 匹配类定义
        class_pattern = r'class\s+(\w+)'
        for match in re.finditer(class_pattern, code):
            classes.append({"name": match.group(1), "line": code[:match.start()].count('\n') + 1})
        
        # 匹配import
        import_pattern = r'(?:import\s+(?:\{[^}]*\}|\w+|\*\s+as\s+\w+)\s+from\s+[\'"]([^\'"]+)[\'"]|require\s*\([\'"]([^\'"]+)[\'"]\))'
        for match in re.finditer(import_pattern, code):
            module = match.group(1) or match.group(2)
            if module:
                imports.append({"module": module})
        
        return {
            "language": "javascript",
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "function_count": len(functions),
            "class_count": len(classes),
            "import_count": len(imports),
            "structure": {
                "has_classes": len(classes) > 0,
                "has_functions": len(functions) > 0
            }
        }
    
    def _parse_java(self, code: str) -> Dict[str, Any]:
        """解析Java代码（简单正则匹配）"""
        classes = []
        methods = []
        imports = []
        
        # 匹配类定义
        class_pattern = r'(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)'
        for match in re.finditer(class_pattern, code):
            classes.append({"name": match.group(1), "line": code[:match.start()].count('\n') + 1})
        
        # 匹配方法定义
        method_pattern = r'(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\([^)]*\)'
        for match in re.finditer(method_pattern, code):
            methods.append({"name": match.group(1), "line": code[:match.start()].count('\n') + 1})
        
        # 匹配import
        import_pattern = r'import\s+(?:static\s+)?([\w.]+)'
        for match in re.finditer(import_pattern, code):
            imports.append({"module": match.group(1)})
        
        return {
            "language": "java",
            "functions": methods,
            "classes": classes,
            "imports": imports,
            "function_count": len(methods),
            "class_count": len(classes),
            "import_count": len(imports),
            "structure": {
                "has_classes": len(classes) > 0,
                "has_functions": len(methods) > 0
            }
        }
    
    def _parse_go(self, code: str) -> Dict[str, Any]:
        """解析Go代码（简单正则匹配）"""
        functions = []
        imports = []
        
        # 匹配函数定义
        func_pattern = r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\([^)]*\)'
        for match in re.finditer(func_pattern, code):
            functions.append({"name": match.group(1), "line": code[:match.start()].count('\n') + 1})
        
        # 匹配import
        import_pattern = r'import\s+(?:\(([^)]+)\)|"([^"]+)")'
        for match in re.finditer(import_pattern, code):
            if match.group(1):
                # 多行import
                for imp in match.group(1).split('\n'):
                    imp = imp.strip().strip('"')
                    if imp:
                        imports.append({"module": imp})
            elif match.group(2):
                imports.append({"module": match.group(2)})
        
        return {
            "language": "go",
            "functions": functions,
            "classes": [],
            "imports": imports,
            "function_count": len(functions),
            "class_count": 0,
            "import_count": len(imports),
            "structure": {
                "has_functions": len(functions) > 0
            }
        }
    
    def _parse_cpp(self, code: str) -> Dict[str, Any]:
        """解析C++代码（简单正则匹配）"""
        classes = []
        functions = []
        includes = []
        
        # 匹配类定义
        class_pattern = r'class\s+(\w+)'
        for match in re.finditer(class_pattern, code):
            classes.append({"name": match.group(1), "line": code[:match.start()].count('\n') + 1})
        
        # 匹配函数定义
        func_pattern = r'(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*\{'
        for match in re.finditer(func_pattern, code):
            func_name = match.group(1)
            if func_name not in ['if', 'for', 'while', 'switch']:
                functions.append({"name": func_name, "line": code[:match.start()].count('\n') + 1})
        
        # 匹配include
        include_pattern = r'#include\s+[<"]([^>"]+)[>"]'
        for match in re.finditer(include_pattern, code):
            includes.append({"module": match.group(1)})
        
        return {
            "language": "cpp",
            "functions": functions[:20],  # 限制数量
            "classes": classes,
            "imports": includes,
            "function_count": len(functions),
            "class_count": len(classes),
            "import_count": len(includes),
            "structure": {
                "has_classes": len(classes) > 0,
                "has_functions": len(functions) > 0
            }
        }
    
    def _parse_generic(self, code: str, language: str) -> Dict[str, Any]:
        """通用解析（基于代码行数和基本统计）"""
        lines = code.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        
        return {
            "language": language,
            "functions": [],
            "classes": [],
            "imports": [],
            "variables": [],
            "total_lines": len(lines),
            "non_empty_lines": len(non_empty_lines),
            "structure": {
                "code_length": len(code),
                "line_count": len(lines)
            }
        }


# 全局实例
code_parser = CodeParser()

