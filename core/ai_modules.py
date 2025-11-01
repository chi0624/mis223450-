import os
import re
import json
import tempfile
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from openai import OpenAI
from django.conf import settings
from .models import Lecture, Question

# 音訊處理（需 ffmpeg；你的 apt.txt 已含 ffmpeg）
from pydub import AudioSegment

load_dotenv()  # 本地讀 .env；Render 讀 Environment


# =========================
# OpenAI Client
# =========================
def create_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    if not api_key or api_key.strip().upper() == "EMPTY":
        raise ValueError("❌ 請設定 OPENAI_API_KEY（Render → Environment 或本地 .env）")
    return OpenAI(api_key=api_key, base_url=api_base)


# =========================
# 長音檔：轉格式 + 切片（8 分鐘一段）
# =========================
def _prepare_audio_chunks(src_path: str,
                          chunk_ms: int = 8 * 60 * 1000,
                          overlap_ms: int = 2000) -> List[str]:
    """
    將任意長度音檔轉為 16kHz mono wav，切段，回傳臨時檔路徑清單。
    需系統有 ffmpeg（由 apt.txt 安裝）。
    """
    if not os.path.exists(src_path):
        raise FileNotFoundError(f"找不到音檔：{src_path}")

    audio = AudioSegment.from_file(src_path)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

    paths: List[str] = []
    duration = len(audio)
    start = 0
    idx = 0

    while start < duration:
        end = min(start + chunk_ms, duration)
        segment = audio[max(0, start - overlap_ms):end]
        fd, tmp_path = tempfile.mkstemp(suffix=f".chunk{idx}.wav")
        os.close(fd)
        segment.export(tmp_path, format="wav")
        paths.append(tmp_path)
        start = end
        idx += 1

    return paths


def transcribe_with_whisper(audio_path: str) -> Optional[str]:
    """
    針對長音檔：先切片後逐段用 whisper-1 轉錄，最後合併。
    """
    try:
        if not os.path.exists(audio_path):
            print(f"❌ 找不到音訊檔案：{audio_path}")
            return None

        print("✅ Whisper API 轉錄開始（長音檔自動分段）")
        client = create_openai_client()
        chunk_paths = _prepare_audio_chunks(audio_path)

        pieces: List[str] = []
        for i, cpath in enumerate(chunk_paths):
            try:
                with open(cpath, "rb") as f:
                    resp = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f
                    )
                text = getattr(resp, "text", None) or (resp if isinstance(resp, str) else "")
                print(f"  └─ 分段 {i+1}/{len(chunk_paths)} 完成，長度：{len(text)}")
                pieces.append((text or "").strip())
            finally:
                try:
                    os.remove(cpath)
                except Exception:
                    pass

        full_text = "\n".join(t for t in pieces if t)
        return full_text.strip() or None

    except Exception as e:
        print(f"❌ Whisper API 轉錄錯誤: {e}")
        return None


# =========================
# 文本分段（避免 prompt 過長）
# =========================
def dynamic_split(text: str, min_length: int = 300, max_length: int = 1000) -> List[str]:
    text = text.strip()
    if len(text) <= max_length:
        return [text]
    paragraphs = re.split(r'(?<=[。！？])\s*', text)
    chunks, temp = [], ""
    for para in paragraphs:
        if len(temp) + len(para) <= max_length:
            temp += para
        else:
            if len(temp) >= min_length:
                chunks.append(temp.strip())
                temp = para
            else:
                temp += para
    if temp:
        chunks.append(temp.strip())
    return chunks


# =========================
# 摘要（分段 + 總結）
# =========================
def generate_summary_for_chunk(client: OpenAI, chunk: str, chunk_index: int, total_chunks: int) -> str:
    messages = [
        {"role": "system", "content": f"""你是一位專業的繁體中文課程摘要設計師。
請針對第 {chunk_index + 1} 段課程內容進行重點摘要，包含：
- 簡潔內容概述（50–80字）
- 2–4 個學習要點，使用條列式
總字數控制在 150 字內。"""},
        {"role": "user", "content": chunk}
    ]
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",   # 較快、較不易超時
            messages=messages,
            temperature=0.3,
            max_tokens=400
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ 段落摘要錯誤: {e}")
        return f"第 {chunk_index + 1} 段摘要失敗"


def combine_summaries(client: OpenAI, summaries: List[str]) -> str:
    combined = "\n\n".join([f"段落 {i+1}：{s}" for i, s in enumerate(summaries)])
    messages = [
        {"role": "system", "content": """你是教育設計專家，請將下列分段摘要統整為完整課程摘要，格式如下：

【課程概述】：說明整體課程內容與重要性（150–200字）
【學習重點】：列出本課程的 4–5 個學習目標（條列）
【完成後收穫】：簡述學生完成課程後能具備的能力（60字內）

請使用繁體中文，避免重複敘述，控制總字數在 400 字內。"""},
        {"role": "user", "content": combined}
    ]
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=512
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ 總結錯誤: {e}")
        return "整合摘要失敗"


# =========================
# 出題（選擇題 + 是非題）
# =========================
def normalize_mcq_payload(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        items = data["items"]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("JSON 結構不符合預期")

    cleaned: List[Dict[str, Any]] = []
    for it in items:
        try:
            concept = str(it["concept"]).strip()
            question = str(it["question"]).strip()
            options = it["options"]
            answer = str(it["answer"]).strip().upper()
            explanation = str(it.get("explanation", "")).strip()
            if not isinstance(options, dict):
                continue
            if not all(k in options for k in ["A", "B", "C", "D"]):
                continue
            if answer not in {"A", "B", "C", "D"}:
                continue
            cleaned.append({
                "concept": concept,
                "question": question,
                "options": {
                    "A": str(options["A"]),
                    "B": str(options["B"]),
                    "C": str(options["C"]),
                    "D": str(options["D"]),
                },
                "answer": answer,
                "explanation": explanation,
            })
        except Exception:
            continue
    return cleaned


def safe_json_parse(raw: str) -> List[Dict[str, Any]]:
    try:
        return normalize_mcq_payload(json.loads(raw))
    except Exception:
        pass
    m = re.search(r'```json\s*([\s\S]*?)```', raw, re.IGNORECASE)
    if not m:
        m = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', raw)
    if m:
        candidate = m.group(1)
        candidate = candidate.replace("“", '"').replace("”", '"').replace("’", "'")
        candidate = re.sub(r",\s*([\]}])", r"\1", candidate)
        try:
            return normalize_mcq_payload(json.loads(candidate))
        except Exception as e:
            print("❌ JSON 區塊解析仍失敗：", e)
    print("⚠️ MCQ 原始回應（截斷 500 字）：", raw[:500])
    raise ValueError("模型未回傳合法 JSON")


def generate_quiz_with_retry(client: OpenAI, summary: str, count: int = 3) -> List[Dict[str, Any]]:
    system = f"""你是一位課程出題 AI，請根據以下課程摘要產生 {count} 題選擇題。
嚴格且只輸出 JSON「陣列」，不要任何說明、不要加 ```json。每一題物件必須包含：
concept, question, options(A/B/C/D), answer(只能是 A/B/C/D), explanation。"""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": summary}
    ]
    # 嘗試 1
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
            max_tokens=1500
        )
        raw = resp.choices[0].message.content or ""
        return safe_json_parse(raw)
    except Exception as e:
        print("🔁 第一次解析失敗，改用更嚴格提示重試：", e)

    # 嘗試 2（更嚴格）
    hard_prompt = summary + f"\n\n請嚴格輸出 {count} 題選擇題，只輸出 JSON 陣列，格式嚴謹。不要有任何說明、```json、前後文字。"
    try:
        messages = [
            {"role": "system", "content": "你只會輸出 JSON。"},
            {"role": "user", "content": hard_prompt}
        ]
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.1,
            max_tokens=1500
        )
        raw = resp.choices[0].message.content or ""
        return safe_json_parse(raw)
    except Exception as e:
        print("❌ 重試仍失敗：", e)
        return []


def generate_tf_questions(client: OpenAI, summary: str, count: int) -> List[Dict[str, Any]]:
    messages = [
        {
            "role": "system",
            "content": f"""請根據以下課程摘要，設計 {count} 題是非題（True/False），格式如下：
[
  {{
    "concept": "學習概念",
    "question": "問題內容",
    "answer": "True",
    "explanation": "正確答案解析"
  }},
  ...
]
請回傳 JSON 格式資料，不要有其他文字說明。"""
        },
        {"role": "user", "content": summary}
    ]
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=1200
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"❌ 是非題產生失敗：{e}")
        return []


# =========================
# 寫入資料庫
# =========================
def parse_and_store_questions(summary: str, quiz_data: List[Dict[str, Any]], lecture: Lecture, question_type: str) -> None:
    if not quiz_data:
        return
    for item in quiz_data:
        try:
            if question_type == 'mcq':
                options = item.get('options', {}) or {}
                Question.objects.create(
                    lecture=lecture,
                    question_text=str(item.get('question', '')).strip(),
                    option_a=str(options.get('A', '')).strip(),
                    option_b=str(options.get('B', '')).strip(),
                    option_c=str(options.get('C', '')).strip(),
                    option_d=str(options.get('D', '')).strip(),
                    correct_answer=str(item.get('answer', '')).strip(),
                    explanation=str(item.get('explanation', '')).strip(),
                    question_type='mcq'
                )
            elif question_type == 'tf':
                Question.objects.create(
                    lecture=lecture,
                    question_text=str(item.get('question', '')).strip(),
                    correct_answer=str(item.get('answer', '')).strip(),
                    explanation=str(item.get('explanation', '')).strip(),
                    question_type='tf'
                )
        except Exception as e:
            print(f"⚠️ 儲存題目失敗：{e}")


# =========================
# Pipeline：音檔 → 摘要 → 題庫
# =========================
def process_audio_and_generate_quiz(lecture_id: int, num_mcq: int = 3, num_tf: int = 0) -> None:
    lecture = Lecture.objects.get(id=lecture_id)
    client = create_openai_client()

    print("🎧 開始語音轉錄")
    transcript = transcribe_with_whisper(lecture.audio_file.path)
    if not transcript:
        print("❌ 轉錄失敗，流程終止")
        return
    lecture.transcript = transcript
    lecture.save()

    print("📝 開始摘要處理")
    chunks = dynamic_split(transcript)
    summaries = [generate_summary_for_chunk(client, c, i, len(chunks)) for i, c in enumerate(chunks)]
    final_summary = combine_summaries(client, summaries)
    lecture.summary = final_summary
    lecture.save()

    print("🧠 開始產生考題")
    if num_mcq > 0:
        mcq_data = generate_quiz_with_retry(client, final_summary, num_mcq)
        if mcq_data:
            parse_and_store_questions(final_summary, mcq_data, lecture, 'mcq')
        else:
            print("⚠️ 沒有回傳 MCQ 題目")

    if num_tf > 0:
        tf_data = generate_tf_questions(client, final_summary, num_tf)
        if tf_data:
            parse_and_store_questions(final_summary, tf_data, lecture, 'tf')
        else:
            print("⚠️ 沒有回傳 TF 題目")


def process_transcript_and_generate_quiz(lecture: Lecture, client: Optional[OpenAI] = None,
                                         num_mcq: int = 3, num_tf: int = 0) -> None:
    client = client or create_openai_client()

    transcript = lecture.transcript
    if not transcript:
        print("❌ 無轉錄內容，無法生成摘要與題目")
        return

    print("📝 開始摘要處理")
    chunks = dynamic_split(transcript)
    summaries = [generate_summary_for_chunk(client, c, i, len(chunks)) for i, c in enumerate(chunks)]
    final_summary = combine_summaries(client, summaries)
    lecture.summary = final_summary
    lecture.save()

    print("🧠 開始產生考題")
    if num_mcq > 0:
        mcq_data = generate_quiz_with_retry(client, final_summary, num_mcq)
        if mcq_data:
            parse_and_store_questions(final_summary, mcq_data, lecture, 'mcq')
        else:
            print("⚠️ 沒有回傳 MCQ 題目")

    if num_tf > 0:
        tf_data = generate_tf_questions(client, final_summary, num_tf)
        if tf_data:
            parse_and_store_questions(final_summary, tf_data, lecture, 'tf')
        else:
            print("⚠️ 沒有回傳 TF 題目")
