from flask import Flask, jsonify
from flask_cors import CORS
from openai import OpenAI
import json
import os
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)

# --- 配置区 ---
# 请替换为你的实际 API Key
api_key = os.environ.get("OPENAI_API_KEY") 
client = OpenAI(api_key=api_key)
# 修改 Prompt，要求生成8道题的列表
PROMPT_TEMPLATE = """
You are an expert exam writer for the University of Queensland (UQ) Bridging English Program (BEP). 
Generate a JSON object containing **8 distinct reading questions** simulating "Stage 1 Reading".

### 1. Passage Guidelines (Strict):
- **Length**: 110-140 words per paragraph.
- **Style**: Academic but accessible (IELTS 6.0-6.5 level). 
- **Structure**: almost all paragraphs should employ a **"Contrast" or "Misconception vs. Reality" structure**. 
    - *Example structure*: "People often think X... However, recent research suggests Y..." OR "While X is popular, it has negative effects..."
    - This is crucial because the questions ask about the "Main Point" or "Writer's Purpose".
- **Topics**: Varied academic topics (Biology, Urban Planning, Psychology, Environmental Science, History of Tech). Do NOT use fictional topics.

### 2. Question Guidelines (Rotate strictly between these 3 types):
Type A: **"What point is the writer making in the reading passage?"**
- Correct answer: Summarizes the *argument* (usually found after the "However").
- Distractors: True details mentioned in the text but NOT the main point.

Type B: **"What is the writer doing in this passage?"**
- Options MUST start with -ing verbs (e.g., "Correcting a misunderstanding...", "Outlining a process...", "Doubting a theory...", "Introducing a new concept...").

Type C: **"What would make a good heading for this paragraph?"**
- Options: Short, punchy titles or questions (e.g., "Why do birds sing?", "A new approach to waste").

### 3. Output Format:
Return ONLY valid JSON.
{
  "exam_set": [
    {
      "passage": "Text...",
      "question": "One of the questions types above...",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correct": 0 
    },
    ... (repeat 8 times total)
  ]
}
"""
@app.route('/generate-exam', methods=['GET'])
def generate_exam():
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[{"role": "user", "content": PROMPT_TEMPLATE}],
            response_format={ "type": "json_object" },
            temperature=0.7 # 增加一点随机性以获得多样化的话题
        )
        content = response.choices[0].message.content
        return content # 直接返回 JSON 字符串
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)