"""初始化Milvus集合脚本"""
import sys
import os

# 添加父目录到路径，确保能导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from milvus_client import milvus_client
from ollama_service import ollama_service

def init_milvus():
    """初始化Milvus集合"""
    print("开始初始化Milvus...")
    
    # 获取一个示例embedding来确定维度
    try:
        sample_embedding = ollama_service.get_embedding("sample text")
        dim = len(sample_embedding)
        print(f"✓ Embedding维度: {dim}")
    except Exception as e:
        print(f"获取embedding失败，使用默认维度1024: {e}")
        dim = 1024
    
    # 创建集合
    collection_name = "code_review_collection"
    milvus_client.create_collection_if_not_exists(collection_name, dim)
    print(f"✓ Milvus集合 '{collection_name}' 初始化完成")

if __name__ == "__main__":
    init_milvus()

