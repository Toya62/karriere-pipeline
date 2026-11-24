"""router.py — OmniRoute: multi-provider AI router with fallback.

Routes each AI evaluation through the first healthy provider, in order:
Gemini → Groq → OpenAI-compatible (9Router) → OpenRouter. Gemini keys
rotate across ``GEMINI_API_KEY``, ``GEMINI_API_KEY_2``, ``GEMINI_API_KEY_3``
(and ``GOOGLE_API_KEY*``); after 3 consecutive Gemini failures the provider
is paused for 30s (circuit breaker) and traffic goes straight to the
fallbacks. A provider that returns a non-retryable HTTP error (401/402/403/
404) is disabled for the rest of the run.

Use :func:`route_ai_evaluation` for a single evaluation and
:func:`get_router_status` to inspect provider health.
"""

import os
import json
import logging
import re
import time
import urllib.request
import urllib.error
import ssl

def _get_ssl_context() -> ssl.SSLContext:
    """Create strict SSL context with certificate verification (prevent MITM)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

import urllib.parse
import threading
from typing import Dict, Any, List, Optional

logger = logging.getLogger("ai_router")

# HTTP statuses that will not fix themselves during a run (bad key, no credit, no access, bad model).
NON_RETRYABLE_STATUSES = frozenset({401, 402, 403, 404})

# Canonical prioritized Gemini models
PREFERRED_GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
]

_router_thread_local = threading.local()


def user_has_active_byok(user_id: Optional[int], provider: str = "gemini") -> bool:
    """Check if user has an active, valid BYOK key for provider AND their routing preference allows it."""
    if not user_id or user_id <= 0:
        return False
    try:
        from src.db.database import get_db_connection, get_user_ai_routing_preference
        pref = get_user_ai_routing_preference(user_id)
        if pref == "platform":
            return False

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM user_ai_keys WHERE user_id = ? AND provider = ? AND status = 'active'",
            (user_id, provider.lower()),
        )
        row = cur.fetchone()
        conn.close()
        return row is not None
    except Exception:
        return False


def resolve_gemini_key(user_id: Optional[int]) -> tuple[Optional[str], str]:
    """Resolve Gemini key for an evaluation request:
    1. If user_id provided: check user AI routing preference.
       If preference is 'platform' (default for Pro): route to server key.
       If preference is 'byok' or 'auto': check user_ai_keys for active key.
       Decrypt; on decryption failure -> mark row invalid, fall through to server key and log.
       Return (user_key, 'byok')
    2. Else: return (None, 'server')
    """
    if not user_id or user_id <= 0:
        return None, "server"
    try:
        from src.db.database import get_db_connection, get_user_ai_routing_preference
        from src.core.key_vault import decrypt_key, fingerprint

        pref = get_user_ai_routing_preference(user_id)
        if pref == "platform":
            return None, "server"

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, key_ciphertext, key_fingerprint
            FROM user_ai_keys
            WHERE user_id = ? AND provider = 'gemini' AND status = 'active'
            """,
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return None, "server"

        key_id, ciphertext, fp = row[0], row[1], row[2]
        try:
            key = decrypt_key(ciphertext)
            conn.close()
            return key, "byok"
        except Exception as e:
            logger.error(f"Failed to decrypt user {user_id} Gemini BYOK key (fp {fp}): {e}. Marking key invalid.")
            cur.execute(
                "UPDATE user_ai_keys SET status = 'invalid', last_error = 'Decryption failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (key_id,),
            )
            conn.commit()
            conn.close()
            return None, "server"
    except Exception as exc:
        logger.error(f"Error checking BYOK key for user {user_id}: {exc}")
        return None, "server"

class AIRouter:
    def __init__(self):
        self._lock = threading.Lock()
        self.keys = self._load_keys()
        self.gemini_key_index = 0
        self.gemini_consecutive_failures = 0
        self.gemini_cooldown_until = 0.0
        self.preferred_gemini_models = list(PREFERRED_GEMINI_MODELS)
        self.groq_models = [
            "openai/gpt-oss-120b",
            "qwen/qwen3.8-27b",
        ]
        # Maps a provider ("groq") or provider/model ("groq/openai/gpt-oss-120b") to the reason it was disabled.
        self.disabled: Dict[str, str] = {}
        self._dead_gemini_keys: set = set()
        self._last_provider_used: str = "gemini"
        self._last_key_origin: str = "server"

    @property
    def last_provider_used(self) -> str:
        return getattr(_router_thread_local, "last_provider_used", self._last_provider_used)

    @last_provider_used.setter
    def last_provider_used(self, val: str) -> None:
        _router_thread_local.last_provider_used = val
        self._last_provider_used = val

    @property
    def last_key_origin(self) -> str:
        return getattr(_router_thread_local, "last_key_origin", self._last_key_origin)

    @last_key_origin.setter
    def last_key_origin(self, val: str) -> None:
        _router_thread_local.last_key_origin = val
        self._last_key_origin = val

    def _mark_user_key_invalid(self, user_id: int, error_msg: str) -> None:
        """Mark user's BYOK key invalid without affecting global server keys."""
        try:
            from src.db.database import get_db_connection
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE user_ai_keys
                SET status = 'invalid', last_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND provider = 'gemini'
                """,
                (error_msg[:200], user_id),
            )
            conn.commit()
            conn.close()
            logger.warning(f"Marked user {user_id} Gemini BYOK key as invalid: {error_msg}")
        except Exception as ex:
            logger.error(f"Failed to mark user {user_id} key invalid: {ex}")

    def _is_disabled(self, provider: str, model: Optional[str] = None) -> bool:
        return provider in self.disabled or (model is not None and f"{provider}/{model}" in self.disabled)

    def _disable_on_fatal_error(self, provider: str, model: Optional[str], exc: Exception, key: Optional[str] = None) -> None:
        """Disable a provider/model for the rest of the process on a non-retryable HTTP status (logged once)."""
        if not isinstance(exc, urllib.error.HTTPError) or exc.code not in NON_RETRYABLE_STATUSES:
            return
        if provider == "gemini" and exc.code != 404 and key and len(self.keys.get("gemini", [])) > 1:
            # One bad key must not take down the other Gemini keys.
            if key not in self._dead_gemini_keys:
                self._dead_gemini_keys.add(key)
                logger.warning(f"A Gemini API key was disabled for the rest of this run (HTTP {exc.code}); it will be skipped silently.")
            if all(k in self._dead_gemini_keys for k in self.keys["gemini"]):
                self.disabled.setdefault("gemini", f"HTTP {exc.code}")
            return
        # 404 means the specific model is unknown; other statuses affect the whole provider (key/credit/access).
        target = f"{provider}/{model}" if exc.code == 404 and model else provider
        if target in self.disabled:
            return
        self.disabled[target] = f"HTTP {exc.code}"
        logger.warning(f"AI provider '{target}' disabled for the rest of this run (HTTP {exc.code}); it will be skipped silently.")

    def _active_providers(self) -> List[str]:
        """Configured providers that are routed to and not (fully) disabled."""
        active: List[str] = []
        if "gemini" in self.keys and "gemini" not in self.disabled and any(
            not self._is_disabled("gemini", m) for m in self.preferred_gemini_models
        ):
            active.append("gemini")
        if "groq" in self.keys and "groq" not in self.disabled and any(
            not self._is_disabled("groq", m) for m in self.groq_models
        ):
            active.append("groq")
        if "openai" in self.keys and "openai" not in self.disabled:
            active.append("openai")
        if "openrouter" in self.keys and "openrouter" not in self.disabled:
            active.append("openrouter")
        return active

    def all_providers_disabled(self) -> bool:
        """True if providers are configured but every one has been disabled."""
        return bool(self.keys) and not self._active_providers() and bool(self.disabled)

    def _load_keys(self) -> Dict[str, List[str]]:
        # Auto-load local .env if present
        if os.path.exists(".env"):
            try:
                with open(".env", "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'").strip('"')
                            if k and v and k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass

        keys: Dict[str, List[str]] = {}
        
        # 1. Format B: GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3...
        gemini_keys = []
        for var, val in sorted(os.environ.items()):
            if (var.startswith("GEMINI_API_KEY") or var.startswith("GOOGLE_API_KEY")) and var != "GEMINI_API_KEYS":
                clean_val = val.strip().strip("'").strip('"')
                if clean_val and clean_val not in gemini_keys:
                    gemini_keys.append(clean_val)
        if gemini_keys:
            keys["gemini"] = gemini_keys

        # 2. Groq
        groq_val = os.environ.get("GROQ_API_KEY", "").strip().strip("'").strip('"')
        if groq_val:
            keys["groq"] = [groq_val]

        # 3. OpenAI / 9Router
        openai_val = os.environ.get("OPENAI_API_KEY", "").strip().strip("'").strip('"')
        if openai_val:
            keys["openai"] = [openai_val]

        # 4. OpenRouter
        or_val = os.environ.get("OPENROUTER_API_KEY", "").strip().strip("'").strip('"')
        if or_val:
            keys["openrouter"] = [or_val]

        # 5. Cerebras
        cb_val = os.environ.get("CEREBRAS_API_KEY", "").strip().strip("'").strip('"')
        if cb_val:
            keys["cerebras"] = [cb_val]

        return keys

    def _get_next_gemini_key(self) -> Optional[str]:
        with self._lock:
            gemini_keys = self.keys.get("gemini", [])
            if not gemini_keys:
                return None
            live_keys = [k for k in gemini_keys if k not in self._dead_gemini_keys] or gemini_keys
            key = live_keys[self.gemini_key_index % len(live_keys)]
            self.gemini_key_index += 1
            return key

    def generate_content(
        self,
        prompt: str,
        schema: Optional[Dict[str, Any]] = None,
        preferred_model: Optional[str] = None,
        response_mime_type: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> str:
        """
        Executes prompt across available AI providers with automatic fallback:
        1. If user has active BYOK Gemini key: use user key on gemini models.
           - On user key failure: do NOT fall back to server Gemini key.
           - User 401/403 marks user key invalid.
        2. Else: Round-robin across all configured server Gemini API keys.
        3. Automatic fallback to Groq Cloud (openai/gpt-oss-120b / qwen3.8-27b)
        4. Automatic fallback to OpenRouter / Cerebras
        """
        errors = []
        
        # Build models list prioritizing requested model
        models_to_try = list(self.preferred_gemini_models)
        if preferred_model and preferred_model in models_to_try:
            models_to_try.remove(preferred_model)
            models_to_try.insert(0, preferred_model)
        elif preferred_model:
            models_to_try.insert(0, preferred_model)

        # Step 1: Try Gemini (BYOK user key first if configured, else server round-robin)
        byok_key, key_origin = resolve_gemini_key(user_id)
        if key_origin == "byok" and byok_key:
            # User BYOK key path: isolated, never touches server gemini pool or circuit breaker
            byok_attempts = 0
            for model in [m for m in models_to_try][:2]:
                byok_attempts += 1
                try:
                    try:
                        result = self._call_gemini(
                            prompt,
                            model=model,
                            key=byok_key,
                            schema=schema,
                            response_mime_type=response_mime_type,
                        )
                    except TypeError as te:
                        if "response_mime_type" in str(te):
                            result = self._call_gemini(prompt, model=model, key=byok_key, schema=schema)
                        else:
                            raise
                    if result:
                        self.last_provider_used = f"gemini-byok ({model})"
                        self.last_key_origin = "byok"
                        return result
                except Exception as e:
                    errors.append(f"Gemini-BYOK({model}) error: {str(e)}")
                    if isinstance(e, urllib.error.HTTPError) and e.code in (400, 401, 403):
                        logger.warning(f"User {user_id} BYOK Gemini key rejected (HTTP {e.code}). Marking key invalid.")
                        self._mark_user_key_invalid(user_id, f"HTTP {e.code}: {e.reason}")
                        # Strict: Do not retry with another model, do NOT fall back to server Gemini
                        break
                    elif isinstance(e, urllib.error.HTTPError) and e.code == 429:
                        logger.warning(f"User {user_id} BYOK Gemini key rate limited (HTTP 429).")
                        # Strict: Do not hammer user's quota, do NOT fall back to server Gemini
                        break
                    else:
                        logger.warning(f"Gemini-BYOK {model} failed: {e}. Trying fallback...")
            # Note: BYOK user key failed; per design §6.3, we do not fall back to server Gemini.
            # Fall through to Step 2 (Groq) and Step 3 (OpenAI/OpenRouter) using server keys.
        else:
            # Server Gemini key path
            now = time.time()
            gemini_dead = "gemini" in self.keys and "gemini" not in self._active_providers()
            if gemini_dead:
                pass
            elif now > self.gemini_cooldown_until:
                gemini_keys = self.keys.get("gemini", [])
                gemini_attempts = 0
                for _ in range(min(2, len(gemini_keys) or 1)):
                    key = self._get_next_gemini_key()
                    if not key:
                        break
                    for model in [m for m in models_to_try if not self._is_disabled("gemini", m)][:2]:
                        gemini_attempts += 1
                        try:
                            try:
                                result = self._call_gemini(
                                    prompt,
                                    model=model,
                                    key=key,
                                    schema=schema,
                                    response_mime_type=response_mime_type,
                                )
                            except TypeError as te:
                                if "response_mime_type" in str(te):
                                    result = self._call_gemini(prompt, model=model, key=key, schema=schema)
                                else:
                                    raise
                            if result:
                                self.gemini_consecutive_failures = 0
                                self.last_provider_used = f"gemini ({model})"
                                self.last_key_origin = "server"
                                return result
                        except Exception as e:
                            errors.append(f"Gemini({model}) error: {str(e)}")
                            if isinstance(e, urllib.error.HTTPError) and e.code in NON_RETRYABLE_STATUSES:
                                self._disable_on_fatal_error("gemini", model, e, key=key)
                            else:
                                logger.warning(f"Gemini {model} failed: {e}. Trying fallback...")
                        if gemini_attempts >= 2:
                            break
                    if gemini_attempts >= 2:
                        break
                self.gemini_consecutive_failures += 1
                if self.gemini_consecutive_failures >= 3:
                    self.gemini_cooldown_until = now + 30
                    logger.warning("Gemini consecutive failure threshold reached (3). Pausing Gemini for 30s; routing directly to Groq/OpenRouter.")
            else:
                logger.info("Gemini currently in outage cooldown. Routing directly to Groq/OpenRouter.")

        # Step 2: Fallback to Groq
        if "groq" in self.keys and "groq" not in self.disabled:
            groq_key = self.keys["groq"][0]
            for model in self.groq_models:
                if self._is_disabled("groq", model) or "groq" in self.disabled:
                    continue
                try:
                    result = self._call_groq(prompt, model=model, key=groq_key)
                    if result:
                        self.last_provider_used = f"groq ({model})"
                        logger.info(f"Successfully generated response using Groq fallback ({model})")
                        return result
                except Exception as e:
                    errors.append(f"Groq({model}) error: {str(e)}")
                    if isinstance(e, urllib.error.HTTPError) and e.code in NON_RETRYABLE_STATUSES:
                        self._disable_on_fatal_error("groq", model, e)
                    elif isinstance(e, urllib.error.HTTPError) and e.code == 429:
                        logger.warning(f"Groq {model} rate limited (HTTP 429). Pausing 2s before retry...")
                        time.sleep(2.0)
                    else:
                        logger.warning(f"Groq {model} failed: {e}")

        # Step 3: Fallback to OpenAI / 9Router
        if "openai" in self.keys and "openai" not in self.disabled:
            openai_key = self.keys["openai"][0]
            try:
                result = self._call_openai(prompt, key=openai_key)
                if result:
                    self.last_provider_used = "openai"
                    logger.info("Successfully generated response using OpenAI/9Router fallback")
                    return result
            except Exception as e:
                errors.append(f"OpenAI/9Router error: {str(e)}")
                if isinstance(e, urllib.error.HTTPError) and e.code in NON_RETRYABLE_STATUSES:
                    self._disable_on_fatal_error("openai", None, e)
                else:
                    logger.warning(f"OpenAI/9Router failed: {e}")

        # Step 4: Fallback to OpenRouter
        if "openrouter" in self.keys and "openrouter" not in self.disabled:
            or_key = self.keys["openrouter"][0]
            try:
                result = self._call_openrouter(prompt, key=or_key)
                if result:
                    self.last_provider_used = "openrouter"
                    logger.info("Successfully generated response using OpenRouter fallback")
                    return result
            except Exception as e:
                errors.append(f"OpenRouter error: {str(e)}")
                self._disable_on_fatal_error("openrouter", None, e)

        raise RuntimeError(f"All AI Router providers failed. Errors: {'; '.join(errors)}")

    def _call_gemini(
        self,
        prompt: str,
        model: str,
        key: str,
        schema: Optional[Dict[str, Any]] = None,
        response_mime_type: Optional[str] = None,
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        gen_config: Dict[str, Any] = {
            "temperature": 0.1,
        }
        if response_mime_type:
            gen_config["responseMimeType"] = response_mime_type
        elif schema or "json" in prompt.lower():
            gen_config["responseMimeType"] = "application/json"
        else:
            gen_config["responseMimeType"] = "text/plain"

        if schema:
            gen_config["responseSchema"] = schema

        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_config,
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": key.strip(),
        }
        req = urllib.request.Request(url, data=data, headers=headers)
        
        with urllib.request.urlopen(req, timeout=25, context=_get_ssl_context()) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            candidates = resp_data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            raise ValueError(f"Empty response from Gemini: {resp_data}")

    def _call_groq(self, prompt: str, model: str, key: str) -> str:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        sys_msg = (
            "You are an expert LaTeX and career assistant. Follow the prompt instructions strictly."
            if "latex" in prompt.lower()
            else "You are an expert ATS recruiter and career matching assistant. Output valid JSON when requested."
        )
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        if "json" in prompt.lower():
            payload["response_format"] = {"type": "json_object"}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)
        
        with urllib.request.urlopen(req, timeout=12, context=_get_ssl_context()) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            choices = resp_data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            raise ValueError(f"Empty response from Groq: {resp_data}")

    def _call_openai(self, prompt: str, key: str) -> str:
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/") or "https://api.openai.com/v1"
        url = f"{base_url}/chat/completions"
        model = os.environ.get("OPENAI_MODEL", "").strip()
        if not model:
            if "ai-router" in base_url or "20128" in base_url or "9router" in base_url:
                model = "cf/@cf/meta/llama-3.3-70b-instruct-fp8-fast"
            else:
                model = "gpt-4o-mini"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        sys_msg = (
            "You are an expert LaTeX and career assistant. Follow the prompt instructions strictly."
            if "latex" in prompt.lower()
            else "You are an expert ATS recruiter. Return valid JSON only."
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=20, context=_get_ssl_context()) as resp:
            raw_text = resp.read().decode("utf-8")
            if "data: [DONE]" in raw_text:
                raw_text = raw_text.split("data: [DONE]")[0].strip()
            resp_data = json.loads(raw_text)
            choices = resp_data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            raise ValueError(f"Empty response from OpenAI/9Router endpoint: {resp_data}")

    def _call_openrouter(self, prompt: str, key: str) -> str:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/YOUR_GITHUB_USERNAME/karriere-pipeline",
            "X-Title": "Karriere Pipeline AI Router"
        }
        sys_msg = (
            "You are an expert LaTeX and career assistant. Follow the prompt instructions strictly."
            if "latex" in prompt.lower()
            else "You are an expert ATS recruiter. Return valid JSON only."
        )
        payload = {
            "model": "meta-llama/llama-3.3-70b-instruct",
            "messages": [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)
        
        with urllib.request.urlopen(req, timeout=12, context=_get_ssl_context()) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            choices = resp_data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            raise ValueError(f"Empty response from OpenRouter: {resp_data}")

_router_instance: Optional[AIRouter] = None

def get_ai_router() -> AIRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = AIRouter()
    return _router_instance

def get_router_status() -> Dict[str, Any]:
    router = get_ai_router()
    return {
        "providers": {
            provider: len(router.keys[provider])
            for provider in ("gemini", "groq", "openai", "openrouter")
            if router.keys.get(provider)
        },
        "total_gemini_keys": len(router.keys.get("gemini", [])),
        "groq_active": "groq" in router.keys,
        "primary_model": router.preferred_gemini_models[0],
        "disabled_providers": dict(getattr(router, "disabled", {})),
        "all_disabled": bool(getattr(router, "all_providers_disabled", lambda: False)()),
    }

def route_ai_evaluation(
    system_prompt: str,
    user_prompt: str,
    preferred_model: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Evaluates a candidate-job match using the Universal AI Router.
    Automatically handles JSON cleaning, retries, and multi-provider failover.
    Threads optional user_id for BYOK key resolution and cost attribution.
    """
    router = get_ai_router()
    full_prompt = f"{system_prompt}\n\n{user_prompt}\n\nIMPORTANT: Respond with ONLY a valid JSON object matching the required schema."
    
    try:
        raw_output = router.generate_content(
            full_prompt,
            preferred_model=preferred_model,
            user_id=user_id,
        )
        if not raw_output:
            return None
        
        # Clean markdown codeblocks like ```json ... ```
        cleaned = raw_output.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
        else:
            # Fallback regex to isolate JSON object
            m = re.search(r'(\{[\s\S]*\})', cleaned)
            if m:
                cleaned = m.group(1).strip()
            
        # Strip trailing commas before closing braces/brackets
        cleaned = re.sub(r',\s*([\]}])', r'\1', cleaned)

        # Fix truncated JSON: balance unclosed quotes, brackets, and braces if model got cut off
        if cleaned:
            in_str = False
            escape = False
            stack = []
            for char in cleaned:
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == '"':
                    in_str = not in_str
                    continue
                if not in_str:
                    if char in "{[":
                        stack.append(char)
                    elif char == "}" and stack and stack[-1] == "{":
                        stack.pop()
                    elif char == "]" and stack and stack[-1] == "[":
                        stack.pop()

            if in_str:
                cleaned += '"'
            while stack:
                top = stack.pop()
                if top == "{":
                    cleaned += "}"
                elif top == "[":
                    cleaned += "]"

        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            logger.warning(f"AI router returned non-dict JSON (type={type(parsed).__name__}), discarding.")
            return None
        parsed["_ai_provider"] = getattr(router, "last_provider_used", "gemini")
        return parsed
    except Exception as e:
        logger.error(f"Error in route_ai_evaluation: {e}")
        return None
