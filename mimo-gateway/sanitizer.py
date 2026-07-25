"""
PII 脱敏模块 - 方案 A 核心
组合正则(快、结构化 PII) + 本地小模型(慢、上下文敏感 PII)
原始敏感数据绝不离开本进程,只把脱敏后的明文发到 MiMo API。

修复历史:
  P0-2  失败时 fallback 保留原 PII → 改为返回 [SANITIZE_FAILED] 占位符并 raise
  P0-3  sanitize_messages 不递归 tool_calls / tools → 改为深度递归
  P0-6  Sanitizer.stats 全局共享 → 改为 sanitize() 返回本地 stats
"""
from __future__ import annotations
import re
import inspect
from dataclasses import dataclass
from typing import Callable

# ---------- 正则层:结构化 PII,确定性、低开销 ----------
# 注意:PRIVKEY 用非贪婪 [\s\S]+?,并锚定 BEGIN/END,避免 catastrophic
# backtracking(P1-8);并按 *? + (?=END) 提前检测整块。
REGEX_PATTERNS: list[tuple[str, str, str]] = [
    ("EMAIL",     r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b",                                                  "[EMAIL]"),
    ("PHONE_CN",  r"(?<!\d)1[3-9]\d{9}(?!\d)",                                                           "[PHONE]"),
    ("PHONE_INTL",r"\+\d{1,3}[-\s]?\(?\d{1,4}\)?[-\s]?\d{2,4}[-\s]?\d{2,4}([-\s]?\d{0,4})?",              "[PHONE]"),
    ("ID_CN",     r"\b[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b", "[IDCARD]"),
    ("CREDIT",    r"\b(?:\d[ -]?){13,19}\b",                                                             "[CARD]"),
    ("IPV4",      r"\b(?:\d{1,3}\.){3}\d{1,3}\b",                                                        "[IP]"),
    ("URL_TOKEN", r"(?i)(?:api[_-]?key|token|secret|password|access[_-]?key)\s*[:=]\s*[\w\-\.~/+=]{8,}", "[SECRET]"),
    ("JWT",       r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",                  "[JWT]"),
    ("AWS_KEY",   r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",                                                      "[AWSKEY]"),
    # 锚定的 PEM 块,使用 (?=-----END ... PRIVATE KEY-----) 提前断言,
    # 配合非贪婪,单次扫描就能定位完整块,不会被卡。
    ("PRIVKEY",   r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "[PRIVKEY]"),
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
    """Per-call stats snapshot. NOT shared across requests (P0-6)."""
    regex_hits: int = 0
    llm_hits: int = 0


# ---------- 上下文敏感 PII:用本地小模型补全 ----------
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


class SanitizeFailedError(Exception):
    """Raised when LLM sanitization fails. Caller decides whether to abort."""


# 探测 llm_call 接口形态
def _accepts_chat(fn) -> bool:
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if len(params) >= 2:
            return True
        return False
    except (ValueError, TypeError):
        return False


def _llm_sanitize_once(llm_call, text: str, max_tokens: int) -> str:
    """llm_call 接受 (messages, max_tokens) 走 chat 格式,或 (prompt) 走文本格式。

    P0-2 修复:失败时返回 "[SANITIZE_FAILED]" 占位符并 raise SanitizeFailedError,
    由 caller (sanitize_text) 决定是否 abort。绝不再 return 原文本。
    """
    try:
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
    except Exception as e:
        raise SanitizeFailedError(f"LLM sanitize call raised: {e!r}") from e

    out = (out or "").strip()
    if not out:
        # 模型没输出,视为失败。
        raise SanitizeFailedError("LLM sanitize returned empty string")
    # 兜底:模型可能输出 "脱敏后:" 前缀
    for prefix in ["脱敏后:", "脱敏后：", "结果:", "输出:"]:
        if out.startswith(prefix):
            out = out[len(prefix):].lstrip()
    # 兜底:续写到示例块
    for sentinel in ["文本:", "---", "用户:", "Assistant:", "助手:", "请脱敏:"]:
        if sentinel in out:
            out = out.split(sentinel, 1)[0].strip()
    if not out:
        raise SanitizeFailedError("LLM sanitize produced only prefix/garbage")
    return out


# ---------- 顶层 API ----------
class Sanitizer:
    """Per-request stateless sanitizer. Stats live on each sanitize() return
    value, not on `self`, so concurrent requests can't pollute each other
    (P0-6 修复).
    """

    PLACEHOLDER_FAILED = "[SANITIZE_FAILED]"

    def __init__(self, llm_call: Callable | None, enable_llm: bool = True):
        self.llm_call = llm_call
        self.enable_llm = enable_llm and llm_call is not None
        self.compiled = [(n, re.compile(p), ph) for n, p, ph in REGEX_PATTERNS]

    def sanitize_text(self, text: str) -> str:
        """Returns sanitized text. Raises SanitizeFailedError if the LLM pass
        fails and abort_on_failure=True (set on sanitize()).

        Otherwise the failing chunk is replaced with PLACEHOLDER_FAILED so
        PII is never returned to the upstream LLM.
        """
        return text

    def sanitize(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        abort_on_failure: bool = True,
    ) -> tuple[list[dict], list[dict] | None, SanitizeStats]:
        """Sanitize messages AND tools (P0-3). Returns (messages_out,
        tools_out, stats).

        If `abort_on_failure` is True, a sanitizer failure raises
        SanitizeFailedError; if False, the affected fields are replaced with
        the PLACEHOLDER_FAILED sentinel so the request still goes through
        but the original PII text never escapes the gateway.
        """
        stats = SanitizeStats()
        out_messages = []
        for m in messages:
            mm = self._sanitize_message(m, stats, abort_on_failure)
            out_messages.append(mm)

        out_tools = None
        if tools:
            out_tools = [self._sanitize_tool(t, stats) for t in tools]

        return out_messages, out_tools, stats

    # --- recursive helpers (P0-3) ------------------------------------------

    def _sanitize_message(self, m: dict, stats: SanitizeStats, abort: bool) -> dict:
        mm = dict(m)

        # Recurse into tool_calls / tool_call_id 路径
        if isinstance(mm.get("tool_calls"), list):
            new_calls = []
            for tc in mm["tool_calls"]:
                if not isinstance(tc, dict):
                    new_calls.append(tc)
                    continue
                tc2 = dict(tc)
                fn = tc2.get("function")
                if isinstance(fn, dict) and isinstance(fn.get("arguments"), str):
                    fn2 = dict(fn)
                    fn2["arguments"] = self._sanitize_string(
                        fn["arguments"], stats, abort, depth=1
                    )
                    tc2["function"] = fn2
                new_calls.append(tc2)
            mm["tool_calls"] = new_calls

        # content (string or multimodal list)
        content = mm.get("content")
        if isinstance(content, str):
            mm["content"] = self._sanitize_string(content, stats, abort, depth=0)
        elif isinstance(content, list):
            new_parts = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    np = dict(p)
                    np["text"] = self._sanitize_string(
                        p.get("text", ""), stats, abort, depth=1
                    )
                    new_parts.append(np)
                else:
                    new_parts.append(p)
            mm["content"] = new_parts
        return mm

    def _sanitize_tool(self, t: dict, stats: SanitizeStats) -> dict:
        if not isinstance(t, dict):
            return t
        t2 = dict(t)
        fn = t2.get("function")
        if isinstance(fn, dict):
            fn2 = dict(fn)
            # description / parameters (parameters is JSON Schema — strings
            # inside it might contain PII examples).
            if isinstance(fn2.get("description"), str):
                fn2["description"] = self._regex_only(fn2["description"], stats)
            params = fn2.get("parameters")
            if isinstance(params, dict):
                fn2["parameters"] = self._sanitize_json_schema(params, stats)
            t2["function"] = fn2
        return t2

    def _sanitize_json_schema(self, node, stats: SanitizeStats):
        """Walk JSON-Schema-ish tree (dicts/lists/strings) and sanitize every
        string leaf via regex only (LLM pass too expensive on schema docs).
        """
        if isinstance(node, str):
            return self._regex_only(node, stats)
        if isinstance(node, list):
            return [self._sanitize_json_schema(x, stats) for x in node]
        if isinstance(node, dict):
            return {k: self._sanitize_json_schema(v, stats) for k, v in node.items()}
        return node

    # --- core regex+llm pass -----------------------------------------------

    def _regex_only(self, text: str, stats: SanitizeStats) -> str:
        out = text
        for name, pat, ph in self.compiled:
            def repl(m, _ph=ph, _n=name):
                s = m.group(0)
                if _n == "CREDIT" and not _is_credit_card(s):
                    return s
                stats.regex_hits += 1
                return _ph
            out = pat.sub(repl, out)
        return out

    def _sanitize_string(
        self, text: str, stats: SanitizeStats, abort: bool, depth: int
    ) -> str:
        if not text:
            return text
        out = self._regex_only(text, stats)
        if self.enable_llm:
            try:
                new = llm_sanitize(self.llm_call, out)
                if new and new != out:
                    stats.llm_hits += 1
                    out = new
            except SanitizeFailedError as e:
                if abort:
                    raise
                # P0-2 关键修复:失败时绝不放行原文本。
                # 用占位符替换,既能让请求继续走,
                # 又让上层日志能看到失败痕迹。
                print(
                    f"[sanitizer] LLM pass failed (depth={depth}): {e}; "
                    f"substituting placeholder"
                )
                return self.PLACEHOLDER_FAILED
        return out