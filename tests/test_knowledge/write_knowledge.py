import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"  # 国内镜像
os.environ["HF_TOKEN"] = ""  # 如需登录可填，一般不需要

import chromadb
import json
import os
from sentence_transformers import SentenceTransformer

# ================= 配置区 =================
MODEL_NAME = "BAAI/bge-m3"  # 首次运行会自动下载约2.2GB，网络慢可换成 "all-MiniLM-L6-v2"
DB_PATH = "../../data/mock_test_kb"
JSONL_PATH = "mock_test_data.jsonl"


# ==========================================

def create_mock_data():
    """生成 Mock JSONL 文件"""
    mock_lines = [
        '{"doc_id": "TC_PAY_001", "source_type": "test_case", "module": "订单支付", "content": "前置：用户已登录，购物车商品库存充足且金额>0。步骤：1. 进入购物车点击结算 2. 选择微信支付 3. 调用支付接口 4. 模拟支付成功回调。预期：订单状态变更为已支付，生成支付流水号，库存扣减1，发送支付成功短信。", "tags": ["支付", "库存扣减", "回调"], "metadata": {"priority": "P0", "version": "v2.4.0", "author": "li_si", "create_date": "2025-11-15"}}',
        '{"doc_id": "BUG_PAY_042", "source_type": "bug_report", "module": "订单支付", "content": "标题：并发支付导致库存超卖。复现：同一商品库存为1，两个用户同时点击支付并提交订单。根因：扣减库存操作未加分布式锁，存在竞态条件。修复：引入Redis分布式锁，扣减前校验库存状态。", "tags": ["并发", "库存超卖", "分布式锁"], "metadata": {"priority": "P1", "version": "v2.3.1", "author": "wang_wu", "create_date": "2025-10-20"}}',
        '{"doc_id": "RULE_REFUND_005", "source_type": "business_rule", "module": "售后退款", "content": "退款金额计算规则：1. 未发货订单全额退款。2. 已发货订单仅退款金额≤实际支付金额-运费。3. 使用优惠券的订单，退款按比例分摊，优惠券不退回。4. 退款原路返回，处理时效T+3工作日。", "tags": ["退款", "优惠券", "分摊计算"], "metadata": {"priority": "P1", "version": "v2.4.0", "author": "zhang_san", "create_date": "2025-09-01"}}',
        '{"doc_id": "TC_LOGIN_012", "source_type": "test_case", "module": "用户登录", "content": "前置：无。步骤：1. 输入正确手机号和错误密码 2. 点击登录 3. 连续错误5次。预期：提示密码错误，第5次后触发图形验证码，账户锁定30分钟，记录安全日志。", "tags": ["登录", "安全", "限流"], "metadata": {"priority": "P2", "version": "v2.2.0", "author": "li_si", "create_date": "2025-08-10"}}',
        '{"doc_id": "BUG_ORDER_088", "source_type": "bug_report", "module": "订单管理", "content": "标题：订单状态机异常，已取消订单仍触发发货逻辑。复现：用户取消订单后，仓库系统因消息队列延迟仍收到发货指令。根因：状态变更与消息发送未在同一事务中，取消操作未拦截下游消息。修复：引入状态机校验拦截器，发货前二次校验订单状态。", "tags": ["状态机", "消息队列", "事务一致性"], "metadata": {"priority": "P1", "version": "v2.3.5", "author": "zhao_liu", "create_date": "2025-11-02"}}',
        '{"doc_id": "TC_REFUND_021", "source_type": "test_case", "module": "售后退款", "content": "前置：订单状态为已发货，实付100元，运费10元，使用20元优惠券。步骤：1. 用户申请部分退款80元 2. 客服审核通过。预期：实际退款金额按比例分摊优惠券，剩余优惠券额度失效，退款原路返回至支付宝。", "tags": ["退款", "分摊计算", "优惠券"], "metadata": {"priority": "P1", "version": "v2.4.0", "author": "wang_wu", "create_date": "2025-11-20"}}'
    ]
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(mock_lines))
    print(f"✅ Mock 数据已生成: {JSONL_PATH}")


def ingest_to_chroma():
    """数据入库"""
    print("📥 正在初始化向量库与Embedding模型...")
    client = chromadb.PersistentClient(path=DB_PATH)
    collection = client.get_or_create_collection(name="test_knowledge", metadata={"hnsw:space": "cosine"})
    embedder = SentenceTransformer(MODEL_NAME, device="cpu")

    ids, docs, metadatas = [], [], []
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line.strip())
            ids.append(item["doc_id"])
            docs.append(item["content"])
            metadatas.append({
                "source_type": item["source_type"],
                "module": item["module"],
                "tags": ",".join(item["tags"]),
                "priority": item["metadata"]["priority"]
            })

    if collection.count() == len(ids):
        print(f"⚠️  数据已存在 ({len(ids)} 条)，跳过入库")
    else:
        print(f"🔄 正在向量化并写入 {len(ids)} 条数据...")
        embeddings = embedder.encode(docs, normalize_embeddings=True)
        collection.upsert(ids=ids, embeddings=embeddings.tolist(), documents=docs, metadatas=metadatas)
        print("✅ 入库完成")

    return collection, embedder


def test_retrieve(collection, embedder):
    """测试检索能力"""
    print("\n🔍 开始测试检索...")

    # 测试1：带模块过滤的语义检索
    query1 = "支付成功后库存没扣减怎么办？"
    emb1 = embedder.encode([query1], normalize_embeddings=True)[0]
    res1 = collection.query(
        query_embeddings=[emb1.tolist()],
        n_results=2,
        where={"module": "订单支付"},
        include=["documents", "metadatas"]
    )
    print(f"\n[查询1] {query1} | 过滤: module=订单支付")
    for doc, meta in zip(res1["documents"][0], res1["metadatas"][0]):
        print(f"  ├─ [{meta['source_type']}] {doc[:60]}...")

    # 测试2：不带过滤，看全局匹配
    query2 = "退款金额怎么算？优惠券退吗？"
    emb2 = embedder.encode([query2], normalize_embeddings=True)[0]
    res2 = collection.query(
        query_embeddings=[emb2.tolist()],
        n_results=2,
        include=["documents", "metadatas"]
    )
    print(f"\n[查询2] {query2}")
    for doc, meta in zip(res2["documents"][0], res2["metadatas"][0]):
        print(f"  ├─ [{meta['module']}|{meta['source_type']}] {doc[:60]}...")


if __name__ == "__main__":
#     os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
#     create_mock_data()
    col, emb = ingest_to_chroma()
    test_retrieve(col, emb)
    print(f"\n💾 数据已持久化至: {DB_PATH}")
    print("🔁 再次运行此脚本，将自动跳过入库并验证数据持久性。")