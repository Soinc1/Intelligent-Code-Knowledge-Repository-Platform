"""Milvus向量数据库客户端"""
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
from config import MILVUS_HOST, MILVUS_PORT, MILVUS_ALIAS
import uuid


class MilvusClient:
    """Milvus客户端封装"""
    
    def __init__(self):
        self.connected = False
        self.connect()
    
    def connect(self):
        """连接Milvus"""
        if not self.connected:
            try:
                connections.connect(
                    alias=MILVUS_ALIAS,
                    host=MILVUS_HOST,
                    port=MILVUS_PORT
                )
                self.connected = True
                print(f"已连接到Milvus: {MILVUS_HOST}:{MILVUS_PORT}")
            except Exception as e:
                print(f"连接Milvus失败: {e}")
                raise
    
    def create_collection_if_not_exists(self, collection_name: str, dim: int = 1024):
        """创建集合（如果不存在）"""
        if utility.has_collection(collection_name):
            print(f"集合 {collection_name} 已存在")
            return Collection(collection_name)
        
        # 定义字段
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
            FieldSchema(name="entity_id", dtype=DataType.INT64),  # 对应MySQL中的ID
            FieldSchema(name="entity_type", dtype=DataType.VARCHAR, max_length=50),  # review_comment/knowledge
            FieldSchema(name="metadata", dtype=DataType.JSON)
        ]
        
        # 创建集合
        schema = CollectionSchema(fields, description=f"{collection_name} collection")
        collection = Collection(collection_name, schema)
        
        # 创建索引
        index_params = {
            "metric_type": "COSINE",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 1024}
        }
        collection.create_index("embedding", index_params)
        
        print(f"已创建集合: {collection_name}")
        return collection
    
    def insert_vectors(self, collection_name: str, embeddings: list, entity_ids: list, 
                       entity_type: str, metadata_list: list = None):
        """插入向量"""
        collection = Collection(collection_name)
        
        if metadata_list is None:
            metadata_list = [{}] * len(embeddings)
        
        entities = [
            embeddings,
            entity_ids,
            [entity_type] * len(embeddings),
            metadata_list
        ]
        
        collection.insert(entities)
        collection.flush()
        print(f"已插入 {len(embeddings)} 个向量到 {collection_name}")
    
    def search_vectors(self, collection_name: str, query_vectors: list, top_k: int = 5):
        """搜索向量"""
        collection = Collection(collection_name)
        collection.load()
        
        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": 10}
        }
        
        results = collection.search(
            data=query_vectors,
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=["entity_id", "entity_type", "metadata"]
        )
        
        return results
    
    def get_collection(self, collection_name: str):
        """获取集合对象"""
        if not utility.has_collection(collection_name):
            return None
        return Collection(collection_name)

    def delete_vectors(self, collection_name: str, entity_ids: list):
        """根据entity_id删除向量"""
        if not utility.has_collection(collection_name):
            return
        collection = Collection(collection_name)
        if not entity_ids:
            return
        expr = f"entity_id in [{', '.join(str(eid) for eid in entity_ids)}]"
        try:
            collection.delete(expr)
            collection.flush()
            print(f"已从 {collection_name} 删除 {len(entity_ids)} 个向量")
        except Exception as e:
            print(f"删除Milvus向量失败: {e}")


# 全局Milvus客户端实例
milvus_client = MilvusClient()

