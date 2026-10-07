import os
import json
import logging
import re
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
from typing import Dict, Any, List, Optional

logger = logging.getLogger("ai_router")

class AIRouter:
    def __init__(self):
        self.keys = self._load_keys()
        self.gemini_key_index = 0
        self.preferred_gemini_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.6-flash",
            "gemini-2.5-flash"
        ]
        self.groq_models = [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b"
        ]

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

        # 3. OpenRouter
        or_val = os.environ.get("OPENROUTER_API_KEY", "").strip().strip("'").strip('"')
        if or_val:
            keys["openrouter"] = [or_val]

        # 4. Cerebras
        cb_val = os.environ.get("CEREBRAS_API_KEY", "").strip().strip("'").strip('"')
        if cb_val:
            keys["cerebras"] = [cb_val]

        return keys

    def _get_next_gemini_key(self) -> Optional[str]:
        gemini_keys = self.keys.get("gemini", [])
        if not gemini_keys:
            return None
        key = gemini_keys[self.gemini_key_index % len(gemini_keys)]
        self.gemini_key_index += 1
        return key

    def generate_content(self, prompt: str, schema: Optional[Dict[str, Any]] = None, preferred_model: Optional[str] = None) -> str:
        """
        Executes prompt across available AI providers with automatic fallback:
        1. Round-robin across all configured Gemini API keys with gemini-3.5-flash-lite / 3.1-flash-lite
        2. Automatic fallback to Groq Cloud (openai/gpt-oss-120b / qwen3.8-27b)
        3. Automatic fallback to OpenRouter / Cerebras
        """
        errors = []
        
        # Build models list prioritizing requested model
        models_to_try = list(self.preferred_gemini_models)
        if preferred_model and preferred_model in models_to_try:
            models_to_try.remove(preferred_model)
            models_to_try.insert(0, preferred_model)
        elif preferred_model:
            models_to_try.insert(0, preferred_model)

        # Step 1: Try all Gemini keys & models
        gemini_keys = self.keys.get("gemini", [])
        for _ in range(len(gemini_keys) or 1):
            key = self._get_next_gemini_key()
            if not key:
                break
            for model in models_to_try:
                try:
                    result = self._call_gemini(prompt, model=model, key=key, schema=schema)
                    if result:
                        return result
                except Exception as e:
                    errors.append(f"Gemini({model}) error: {str(e)}")
                    logger.warning(f"Gemini {model} failed: {e}. Trying fallback...")

        # Step 2: Fallback to Groq
        if "groq" in self.keys:
            groq_key = self.keys["groq"][0]
            for model in self.groq_models:
                try:
                    result = self._call_groq(prompt, model=model, key=groq_key)
                    if result:
                        logger.info(f"Successfully generated response using Groq fallback ({model})")
                        return result
                except Exception as e:
                    errors.append(f"Groq({model}) error: {str(e)}")
                    logger.warning(f"Groq {model} failed: {e}")

        # Step 3: Fallback to OpenRouter
        if "openrouter" in self.keys:
            or_key = self.keys["openrouter"][0]
            try:
                result = self._call_openrouter(prompt, key=or_key)
                if result:
                    return result
            except Exception as e:
                errors.append(f"OpenRouter error: {str(e)}")

        raise RuntimeError(f"All AI Router providers failed. Errors: {'; '.join(errors)}")

    def _call_gemini(self, prompt: str, model: str, key: str, schema: Optional[Dict[str, Any]] = None) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1
            }
        }
        if schema:
            payload["generationConfig"]["responseMimeType"] = "application/json"
            payload["generationConfig"]["responseSchema"] = schema

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        
        with urllib.request.urlopen(req, timeout=30, context=_get_ssl_context()) as resp:
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
            "User-Agent": "curl/7.88.1"
        }
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an expert ATS recruiter and career matching assistant. Output valid JSON when requested."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        if "json" in prompt.lower():
            payload["response_format"] = {"type": "json_object"}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)
        
        with urllib.request.urlopen(req, timeout=30, context=_get_ssl_context()) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            choices = resp_data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            raise ValueError(f"Empty response from Groq: {resp_data}")

    def _call_openrouter(self, prompt: str, key: str) -> str:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/YOUR_GITHUB_USERNAME/karriere-pipeline",
            "X-Title": "Karriere Pipeline AI Router"
        }
        payload = {
            "model": "meta-llama/llama-3.3-70b-instruct:free",
            "messages": [
                {"role": "system", "content": "You are an expert ATS recruiter. Return valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers)
        
        with urllib.request.urlopen(req, timeout=30, context=_get_ssl_context()) as resp:
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
            for provider in ("gemini", "groq", "openrouter")
            if router.keys.get(provider)
        },
        "total_gemini_keys": len(router.keys.get("gemini", [])),
        "groq_active": "groq" in router.keys,
        "primary_model": router.preferred_gemini_models[0]
    }

def route_ai_evaluation(system_prompt: str, user_prompt: str, preferred_model: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Evaluates a candidate-job match using the Universal AI Router.
    Automatically handles JSON cleaning, retries, and multi-provider failover.
    """
    router = get_ai_router()
    full_prompt = f"{system_prompt}\n\n{user_prompt}\n\nIMPORTANT: Respond with ONLY a valid JSON object matching the required schema."
    
    try:
        raw_output = router.generate_content(full_prompt, preferred_model=preferred_model)
        if not raw_output:
            return None
        
        # Clean markdown codeblocks like ```json ... ```
        cleaned = raw_output.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
            
        return json.loads(cleaned)
    except Exception as e:
        logger.error(f"Error in route_ai_evaluation: {e}")
        return None
