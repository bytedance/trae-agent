"""
PII 脱敏模块 - 方案 A 核心
组合正则(快、结构化 PII) + 本地小模型(慢、上下文敏感 PII)
原始敏感数据绝不离开本进程,只把脱敏后的明文发到 MiMo API。
"""
from __future__ import annotations
import re
import hashlib
from dataclasses import dataclass
from typing import Callable, Iterable

# ---------- 正则层:结构化 PII,确定性、低开销 ----------
REGEX_PATTERNS: list[tuple[str, str, str]] = [
    # name, pattern, placeholder
    ("EMAIL",     r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b",                                                  "[EMAIL]"),
    ("PHONE_CN",  r"(?<!\d)1[3-9]\d{9}(?!\d)",                                                           "[PHONE]"),
    ("PHONE_INTL",r"\+\d{1,3}[-\s]?\(?\d{1,4}\)?[-\s]?\d{2,4}[-\s]?\d{2,4}([-\s]?\d{0,4})?",              "[PHONE]"),
    ("ID_CN",     r"\b[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b", "[IDCARD]"),
    ("CREDIT",    r"\b(?:\d[ -]?){13,19}\b",                                                             "[CARD]"),       # 简单过滤:正则在下方二次验证
    ("IPV4",      r"\b(?:\d{1,3}\.){3}\d{1,3}\b",                                                        "[IP]"),
    ("URL_TOKEN", r"(?i)(?:api[_-]?key|token|secret|password|access[_-]?key)\s*[:=]\s*[\w\-\.~/+=]{8,}", "[SECRET]"),
    ("JWT",       r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",                  "[JWT]"),
    ("AWS_KEY",   r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",                                                      "[AWSKEY]"),
    ("PRIVKEY",   r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "[PRIVKEY]"),
    ("DNI_ES",    r"\b\d{8}[A-Z]\b",                                                                    "[DNI]"),
]

# Luhn 校验,过滤误判的信用卡号
def _is_credit_card(s: str) -> bool:
    digits = re.sub(r"\D", "", s)
    if not (13 <= len(digits) <= 19):
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0

@dataclass
class SanitizeStats:
    regex_hits: int = 0
    llm_hits: int = 0

# ---------- 上下文敏感 PII:用本地小模型补全 ----------
# 用 chat 格式(小模型对 chat 模板跟得比纯文本 prompt 稳)
SANITIZE_LLM_MESSAGES_FN: Callable[[str], list[dict]] = lambda text: [
    {"role": "system", "content": (
        "你是 PII 脱敏助手。把文本里的真实人名(中/英)、组织名、详细地址、车牌、设备序列号、"
        "订单号(>6 位连续数字)替换为占位符 [NAME] [ORG] [ADDRESS] [PLATE] [DEVICE_ID] [ORDER_ID]。"
        "通用名词、产品名、技术术语(MiMo/Qwen/OpenAI/Python)保持原样。"
        "只输出脱敏后的完整文本,不解释、不加前缀。"
    )},
    {"role": "user", "content": f"请脱敏:\n{text}"},
]

def llm_sanitize(llm_call, text: str, max_chars: int = 1500, max_tokens: int = 256) -> str:
    """调本地小模型做上下文 PII 脱敏。文本过长时按段落处理。"""
    if len(text) <= max_chars:
        return _llm_sanitize_once(llm_call, text, max_tokens)
    parts = re.split(r"(\n{2,}|[。！？!?]\s)", text)
    chunks, cur = [], ""
    for p in parts:
        if len(cur) + len(p) > max_chars and cur:
            chunks.append(cur)
            cur = p
        else:
            cur += p
    if cur:
        chunks.append(cur)
    return "".join(_llm_sanitize_once(llm_call, c, max_tokens) for c in chunks)

def _llm_sanitize_once(llm_call, text: str, max_tokens: int) -> str:
    """llm_call 接受 (messages, max_tokens) 走 chat 格式,或 (prompt) 走文本格式。"""
    # 优先 chat 格式
    if _accepts_chat(llm_call):
        messages = SANITIZE_LLM_MESSAGES_FN(text)
        try:
            out = llm_call(messages, max_tokens)
        except TypeError:
            out = llm_call(messages)
    else:
        prompt = (
            "你是 PII 脱敏助手。把文本里的真实人名(中/英)、组织名、详细地址、车牌、设备序列号、"
            "订单号(>6 位连续数字)替换为占位符 [NAME] [ORG] [ADDRESS] [PLATE] [DEVICE_ID] [ORDER_ID]。"
            "通用名词/产品名/技术术语保留。只输出脱敏后的完整文本,不解释。\n\n"
            f"文本:\n{text}\n\n脱敏后:"
        )
        try:
            out = llm_call(prompt, max_tokens)
        except TypeError:
            out = llm_call(prompt)

    out = (out or "").strip()
    # 兜底:模型可能输出 "脱敏后:" 前缀
    for prefix in ["脱敏后:", "脱敏后：", "结果:", "输出:"]:
        if out.startswith(prefix):
            out = out[len(prefix):].lstrip()
    # 兜底:续写到示例块
    for sentinel in ["文本:", "---", "用户:", "Assistant:", "助手:", "请脱敏:"]:
        if sentinel in out:
            out = out.split(sentinel, 1)[0].strip()
    return out or text  # 失败时保留原样

# 探测 llm_call 接口形态
import inspect
def _accepts_chat(fn) -> bool:
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if len(params) >= 2:
            return True  # 形如 (messages, max_tokens) 或 (text, max_tokens) 都按 chat 走
        return False
    except (ValueError, TypeError):
        return False

# ---------- 顶层 API ----------
class Sanitizer:
    def __init__(self, llm_call: Callable[[str], str] | None, enable_llm: bool = True):
        self.llm_call = llm_call
        self.enable_llm = enable_llm and llm_call is not None
        self.compiled = [(n, re.compile(p), ph) for n, p, ph in REGEX_PATTERNS]
        self.stats = SanitizeStats()

    def sanitize_text(self, text: str) -> str:
        if not text:
            return text
        out = text
        for name, pat, ph in self.compiled:
            def repl(m, _ph=ph, _n=name):
                s = m.group(0)
                if _n == "CREDIT" and not _is_credit_card(s):
                    return s
                self.stats.regex_hits += 1
                return _ph
            out = pat.sub(repl, out)
        if self.enable_llm:
            try:
                new = llm_sanitize(self.llm_call, out)
                if new and new != out:
                    self.stats.llm_hits += 1
                    out = new
            except Exception as e:
                # 脱敏失败不能阻塞,只记到 stats
                print(f"[sanitizer] LLM pass failed: {e}")
        return out

    def sanitize_messages(self, messages: list[dict]) -> list[dict]:
        """对 OpenAI messages 数组逐条脱敏,保留 role/结构。"""
        out = []
        for m in messages:
            mm = dict(m)
            content = mm.get("content")
            if isinstance(content, str):
                mm["content"] = self.sanitize_text(content)
            elif isinstance(content, list):
                # multimodal
                new_parts = []
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "text":
                        np = dict(p)
                        np["text"] = self.sanitize_text(p.get("text", ""))
                        new_parts.append(np)
                    else:
                        new_parts.append(p)
                mm["content"] = new_parts
            out.append(mm)
        return out
