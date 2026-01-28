from flask import Flask, jsonify, request
from flask_cors import CORS
from openai import OpenAI
import os
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient

# 加载环境变量
load_dotenv()

app = Flask(__name__)
CORS(app)

# --- 1. 数据库连接配置 ---
# 获取 Render 环境变量里的连接字符串
mongo_uri = os.environ.get("MONGO_URI")

# 链接数据库
if mongo_uri:
    try:
        mongo_client = MongoClient(mongo_uri)
        # 'exam_db' 是库名，'tokens' 是集合名，MongoDB会自动创建它们
        tokens_collection = mongo_client['exam_db']['tokens']
        print("✅ MongoDB 连接成功")
    except Exception as e:
        print(f"❌ MongoDB 连接失败: {e}")
        tokens_collection = None
else:
    print("⚠️ 警告: 未设置 MONGO_URI，运行在无数据库模式（卡密功能将不可用）")
    tokens_collection = None

# --- 2. 辅助函数：卡密管理 (已修复判断逻辑) ---
def get_token_quota(token):
    """查询卡密剩余次数，如果是新卡密(特定前缀)则自动创建"""
    # 修复点 1: 必须显式判断 is None
    if tokens_collection is None:
        return 0
    
    # 1. 查库
    record = tokens_collection.find_one({"token": token})
    if record:
        return record['quota']
    
    return 0 # 不符合规则的卡密无效

def decrement_token_quota(token):
    """扣除一次机会"""
    # 修复点 2: 必须显式判断 is not None
    if tokens_collection is not None:
        tokens_collection.update_one(
            {"token": token},
            {"$inc": {"quota": -1}}
        )

# --- 3. 配置限流器逻辑 ---
def get_rate_limit_key():
    try:
        data = request.get_json(silent=True)
        if data and 'token' in data:
            token = data['token'].strip()
            # 只有当卡密真实有效且有余额时，才给予“特权”绕过 IP 限制
            if get_token_quota(token) > 0:
                return None 
    except:
        pass
    return get_remote_address()

limiter = Limiter(
    key_func=get_rate_limit_key,
    app=app,
    storage_uri="memory://" 
)

# --- 4. 配置 OpenAI ---
api_key = os.environ.get("OPENAI_API_KEY") 
client = OpenAI(api_key=api_key)

# --- 5. 定义 Prompts (为了节省篇幅，这里折叠了，请确保你的代码里保留了完整的 Prompts) ---
STAGE1_PROMPT = """
You are a strict exam content creator for Academic English Purposes (EAP).
Generate a JSON object with **8 distinct reading items**.

### 1. SOURCE MATERIAL SIMULATION (Crucial):
Do NOT write like a generic AI assistant. Write like a journalist for **"The Conversation"** or **"New Scientist"**.
- **Tone**: Academic but engaging, objective, analytical.
- **Vocabulary**: Use precise, less common academic collocations (e.g., "precipitate a crisis", "inherent contradiction", "empirical evidence suggests").
- **Avoid AI Clichés**: Do NOT use phrases like "In conclusion", "It is important to note", "In recent years", "delve into".

### 2. STRUCTURAL REQUIREMENTS:
Each paragraph (120-140 words) MUST follow one of these logical flows strictly:
- **Pattern A (The Twist)**: Start with a commonly held belief or a traditional method -> Introduce a "But" or "However" -> Present new evidence that contradicts the start.
- **Pattern B (The Problem-Solution)**: Describe a complex problem -> Dismiss a simple solution -> Propose a nuanced/scientific solution.
- **Pattern C (The Definition)**: Define a concept broadly -> Narrow it down -> Argue why this specific definition matters.

### 3. QUESTION TYPES (Randomized):
- "What point is the writer making?" (Focus on the argument AFTER the 'However').
- "What is the writer doing in this passage?" (e.g., "Challenging a widespread assumption", "Outlining a causal relationship").
- "Which heading best suits this paragraph?"

### 4. RANDOMIZATION:
- **SHUFFLE ANSWERS**: The correct answer index (0-3) MUST be random.
- **TOPICS**: Mix Biology, Linguistics, Urban Design, Cognitive Science, History.

### 5. OUTPUT:
Return ONLY valid JSON.
{
  "exam_set": [
    {
      "passage": "...",
      "question": "...",
      "options": ["...", "...", "...", "..."],
      "correct": 2
    },
    ...
  ]
}
"""

STAGE2_PROMPT = """
You are a strict exam content creator for Academic English Purposes (EAP) 
Generate a "Matching Headings" task based on a single cohesive academic article.

### 1. ARTICLE STRUCTURE:
- Topic: Academic (e.g., Architecture, Environmental Science, History, Linguistics).
- Length: Total 600-700 words.
- Structure: Split the article into **7 Sections** (labeled A, B, C, D, E, F, G).
- Each section must have a distinct "Main Idea".

### 2. HEADINGS GENERATION (The Puzzle):
- Generate **9 Headings** (labeled i to ix).
- **7 Headings** must be the correct titles for sections A-G.
- **2 Headings** must be **Distractors** (plausible but incorrect, or minor details).
- The headings should be short, distinct summaries (e.g., "The financial impact of...", "Early failures in design").

### 3. OUTPUT FORMAT (Strict JSON):
{
  "title": "Article Title",
  "headings": {
    "i": "Heading text...",
    "ii": "Heading text...",
    ... (up to ix)
  },
  "sections": [
    {
      "id": "A",
      "text": "Full text of section A...",
      "correct_heading": "iii" // The roman numeral of the correct answer
    },
    ... (Repeat for B, C, D, E, F, G)
  ]
}
"""

STAGE3_PROMPT = """
You are a strict exam content creator for Academic English Purposes (EAP)
Generate a "Locating Information" task based on a single cohesive academic article.

### 1. ARTICLE STRUCTURE:
- Topic: Academic (e.g., Psychology, Biology, Economics, History).
- Length: Total 650-750 words.
- Structure: Split the article into **7 Sections** (labeled A, B, C, D, E, F, G).

### 2. QUESTIONS GENERATION (The Task):
- Generate **7 Statements** describing specific information found in the text.
- Format examples: "a reason why...", "a list of...", "a mention of...", "evidence that...".
- **CRITICAL**: 
    - Some sections might contain answers to multiple questions.
    - Some sections might not be used at all.
    - But ensure all 7 questions have a valid answer in the text.

### 3. OUTPUT FORMAT (Strict JSON):
{
  "title": "Article Title",
  "questions": [
    {
      "id": 1,
      "text": "a mention of the initial failure...",
      "correct_section": "B" 
    },
    ... (repeat for 7 questions)
  ],
  "sections": [
    {
      "id": "A",
      "text": "Full text of section A..."
    },
    ... (Repeat for B, C, D, E, F, G)
  ]
}
"""

STAGE4_PROMPT = """
You are a strict exam content creator for Academic English Purposes (EAP)
Generate a "Gapped Text" task.

### 1. ARTICLE STRUCTURE:
- Topic: Academic/General Interest (e.g., Psychology, Sociology, Biology).
- Length: Long (800-900 words).
- The text must have logical flow.

### 2. TASK GENERATION:
- Remove **6 whole paragraphs** (or significant logical chunks) from the text.
- Replace them in the text with markers: [[1]], [[2]], [[3]], [[4]], [[5]], [[6]].
- Provide a list of **7 Paragraphs** (Options A-G).
    - 6 are the correct removed paragraphs.
    - 1 is a **Distractor** (does not fit anywhere).

### 3. OUTPUT FORMAT (Strict JSON):
{
  "title": "Article Title",
  "base_text": "Full text with markers [[1]], [[2]]... inside.",
  "options": [
    { "id": "A", "text": "Content of paragraph A..." },
    { "id": "B", "text": "Content of paragraph B..." },
    ... (Up to G)
  ],
  "answers": {
    "1": "C",
    "2": "A",
    "3": "F",
    "4": "B",
    "5": "G",
    "6": "D"
  }
}
"""

# --- 6. 核心路由定义 ---
@app.route('/generate-exam', methods=['POST']) 
@limiter.limit("2 per minute")
@limiter.limit("50 per day")
def generate_exam():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        stage_type = data.get('stage', 'stage1') 
        token = data.get('token', '').strip()
        
        quota_remaining = "IP Limit"

        # === 核心逻辑：卡密验证与扣费 ===
        if token:
            # 修复点 3: 必须显式判断 is None
            if tokens_collection is None:
                return jsonify({"error": "Server Database Error (Contact Admin)"}), 500
            
            # 2. 获取当前剩余次数 (如果新卡密则自动创建)
            current_quota = get_token_quota(token)
            
            # 3. 如果次数不足
            if current_quota <= 0:
                return jsonify({"error": "无效卡密或次数已用完 (Invalid or Exhausted Token)"}), 403
            
            # 4. 扣除一次次数
            decrement_token_quota(token)
            quota_remaining = current_quota - 1
            print(f"Token [{token}] used. Remaining in DB: {quota_remaining}")
        
        # === 生成逻辑 ===
        current_prompt = STAGE1_PROMPT
        if stage_type == 'stage2':
            current_prompt = STAGE2_PROMPT
        elif stage_type == 'stage3': 
            current_prompt = STAGE3_PROMPT
        elif stage_type == 'stage4': 
            current_prompt = STAGE4_PROMPT

        response = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "user", "content": current_prompt}],
            response_format={ "type": "json_object" },
            temperature=0.7 
        )
        content = response.choices[0].message.content
        
        return content, 200, {'X-Remaining-Quota': str(quota_remaining)}

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

# --- 7. 错误处理 ---
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "error": "免费额度请求过于频繁，请稍后再试，或输入卡密使用。",
        "detail": str(e.description)
    }), 429

if __name__ == '__main__':
    app.run(port=5000, debug=True)