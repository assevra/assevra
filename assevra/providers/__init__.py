"""
Judge providers: one interface, every model vendor.

Assevra's judged dimensions have to work wherever a team's models already live.
Mandating one vendor would make the tool unadoptable in half the organizations
that need it — and would quietly couple the *methodology* to a *supplier*, which
is exactly the coupling the project exists to avoid. So a provider is a thin,
replaceable thing: a function that takes a prompt and returns text.

    complete(prompt: str) -> str

Everything above it — the pinned rubrics, the panel/jury aggregation, the JSON
extraction, calibration — is provider-agnostic and unchanged whichever vendor
answers.

Seven providers ship in the box:

===========  =========================  ==========================================
``anthropic``  ``pip install assevra[anthropic]``  Claude, via the Messages API
``openai``     ``pip install assevra[openai]``     GPT, via chat completions
``azure``      ``pip install assevra[openai]``     Azure OpenAI deployments
``bedrock``    ``pip install assevra[bedrock]``    Amazon Bedrock (boto3)
``gemini``     ``pip install assevra[gemini]``     Google Gemini
``local``      *no dependency*                     any OpenAI-compatible endpoint
``mock``       *no dependency*                     a deterministic offline judge
===========  =========================  ==========================================

Two of those matter more than their line count suggests. ``local`` speaks the
OpenAI chat-completions shape over ``urllib``, so Ollama, vLLM, LM Studio, and
llama.cpp all work with **no third-party package and no data leaving the
machine** — the option a regulated-vertical team needs and rarely gets. ``mock``
is a deterministic heuristic judge with no network at all, which is what lets CI
exercise the full judged pipeline on every pull request, including forks with no
secrets.

``provider: auto`` (the default) picks the first provider whose credentials are
actually present, and returns ``None`` when none are — at which point judged
dimensions are *skipped, never silently failed*.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable, Optional

from .. import registry


class ProviderError(Exception):
    """Raised when a provider is asked for but cannot be built."""


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    env: tuple[str, ...]
    extra: str
    default_model: str
    doc: str

    @property
    def configured(self) -> bool:
        return all(os.environ.get(var) for var in self.env) if self.env else True


PROVIDERS: dict[str, ProviderInfo] = {
    "anthropic": ProviderInfo(
        "anthropic",
        ("ANTHROPIC_API_KEY",),
        "anthropic",
        "claude-opus-4-8",
        "Anthropic Claude via the Messages API.",
    ),
    "openai": ProviderInfo(
        "openai",
        ("OPENAI_API_KEY",),
        "openai",
        "gpt-4o",
        "OpenAI chat completions.",
    ),
    "azure": ProviderInfo(
        "azure",
        ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"),
        "openai",
        "",
        "Azure OpenAI. `model` is your deployment name.",
    ),
    "bedrock": ProviderInfo(
        "bedrock",
        ("AWS_REGION",),
        "bedrock",
        "",
        "Amazon Bedrock via boto3. `model` is the Bedrock model id.",
    ),
    "gemini": ProviderInfo(
        "gemini",
        ("GEMINI_API_KEY",),
        "gemini",
        "gemini-2.0-flash",
        "Google Gemini via the Generative AI SDK.",
    ),
    "local": ProviderInfo(
        "local",
        (),
        "",
        "local-model",
        "Any OpenAI-compatible endpoint (Ollama, vLLM, LM Studio). No dependency.",
    ),
    "mock": ProviderInfo(
        "mock",
        (),
        "",
        "mock-judge",
        "A deterministic offline judge for tests and CI. Never calls the network.",
    ),
}

# The order `auto` tries. Local and mock are deliberately last: they are explicit
# choices, not fallbacks something should slide into by accident.
AUTO_ORDER = ("anthropic", "openai", "gemini", "azure", "bedrock")


def _require(module: str, extra: str, provider: str):
    try:
        return __import__(module)
    except ImportError as exc:
        hint = f'pip install "assevra[{extra}]"' if extra else f"pip install {module}"
        raise ProviderError(
            f"the {provider!r} judge provider needs the {module!r} package. Install it with: {hint}"
        ) from exc


# --------------------------------------------------------------------------- #
# Provider factories: each returns complete(prompt) -> str                     #
# --------------------------------------------------------------------------- #
def _anthropic(model: str, opts: dict) -> Callable[[str], str]:
    _require("anthropic", "anthropic", "anthropic")
    from anthropic import Anthropic

    client = Anthropic(**({"base_url": opts["base_url"]} if opts.get("base_url") else {}))
    max_tokens = int(opts.get("max_tokens", 512))
    temperature = float(opts.get("temperature", 0.0))

    def complete(prompt: str) -> str:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    return complete


def _openai_like(model: str, opts: dict, azure: bool = False) -> Callable[[str], str]:
    _require("openai", "openai", "azure" if azure else "openai")
    max_tokens = int(opts.get("max_tokens", 512))
    temperature = float(opts.get("temperature", 0.0))

    if azure:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )
    else:
        from openai import OpenAI

        client = OpenAI(**({"base_url": opts["base_url"]} if opts.get("base_url") else {}))

    def complete(prompt: str) -> str:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    return complete


def _bedrock(model: str, opts: dict) -> Callable[[str], str]:
    _require("boto3", "bedrock", "bedrock")
    import boto3

    client = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION"))
    max_tokens = int(opts.get("max_tokens", 512))
    temperature = float(opts.get("temperature", 0.0))

    def complete(prompt: str) -> str:
        # The Converse API is model-agnostic across Bedrock, so one code path
        # serves Claude, Llama, Mistral, and Titan alike.
        response = client.converse(
            modelId=model,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
        parts = response["output"]["message"]["content"]
        return "".join(part.get("text", "") for part in parts)

    return complete


def _gemini(model: str, opts: dict) -> Callable[[str], str]:
    max_tokens = int(opts.get("max_tokens", 512))
    temperature = float(opts.get("temperature", 0.0))
    try:
        from google import genai  # type: ignore
    except ImportError as exc:
        raise ProviderError(
            "the 'gemini' judge provider needs the google-genai package. "
            'Install it with: pip install "assevra[gemini]"'
        ) from exc

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    def complete(prompt: str) -> str:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={"max_output_tokens": max_tokens, "temperature": temperature},
        )
        return response.text or ""

    return complete


def _local(model: str, opts: dict) -> Callable[[str], str]:
    """Any OpenAI-compatible /v1/chat/completions endpoint, over urllib.

    Dependency-free by design: a team that cannot send evaluation data to a
    vendor should not also have to add packages to score it.
    """
    import urllib.error
    import urllib.request

    base = (opts.get("base_url") or os.environ.get("ASSEVRA_JUDGE_BASE_URL") or "http://localhost:11434/v1").rstrip("/")
    url = f"{base}/chat/completions"
    api_key = os.environ.get(opts.get("api_key_env") or "ASSEVRA_JUDGE_API_KEY", "")
    max_tokens = int(opts.get("max_tokens", 512))
    temperature = float(opts.get("temperature", 0.0))
    timeout = float(opts.get("timeout", 120))

    def complete(prompt: str) -> str:
        body = json.dumps(
            {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ProviderError(f"local judge endpoint {url} is unreachable: {exc}") from exc
        try:
            return payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"local judge endpoint returned an unexpected shape: {payload!r:.200}"
            ) from exc

    return complete


def _mock(model: str, opts: dict) -> Callable[[str], str]:
    """A deterministic, offline judge.

    Its whole purpose is to make the *judged* half of the pipeline testable —
    panels, rubric parsing, calibration arithmetic, skip semantics — without a
    key, a network, or a bill. It reads the rubric it was handed and answers with
    a cheap lexical heuristic, so the same input always produces the same verdict.

    It is not a judge. It is a stand-in that keeps CI honest about everything
    around the judge. Assevra refuses to use it unless you name it explicitly.
    """
    from .mock import mock_complete

    return lambda prompt: mock_complete(prompt, model=model, opts=opts)


_FACTORIES: dict[str, Callable[[str, dict], Callable[[str], str]]] = {
    "anthropic": _anthropic,
    "openai": lambda m, o: _openai_like(m, o, azure=False),
    "azure": lambda m, o: _openai_like(m, o, azure=True),
    "bedrock": _bedrock,
    "gemini": _gemini,
    "local": _local,
    "mock": _mock,
}

for _name, _factory in _FACTORIES.items():
    registry.register_provider(_name, _factory, replace=True)


# --------------------------------------------------------------------------- #
# Resolution                                                                   #
# --------------------------------------------------------------------------- #
def detect() -> Optional[str]:
    """The first provider whose credentials are present, or None."""
    for name in AUTO_ORDER:
        if PROVIDERS[name].configured:
            return name
    return None


def resolve(provider: str = "auto", model: str = "") -> tuple[Optional[str], str]:
    """Settle on (provider, model), or (None, "") when nothing is configured."""
    name = (provider or "auto").strip().lower()
    if name in ("", "auto"):
        name = detect()
        if name is None:
            return None, ""
    if name in ("none", "off", "disabled"):
        return None, ""
    if name not in PROVIDERS:
        raise ProviderError(
            f"unknown judge provider {name!r}; known: {', '.join(sorted(PROVIDERS))}"
        )
    info = PROVIDERS[name]
    chosen = model or os.environ.get("ASSEVRA_JUDGE_MODEL", "") or info.default_model
    if not chosen:
        raise ProviderError(
            f"the {name!r} provider has no default model — set judge.model in "
            f".assevra.yml or pass --judge-model ({info.doc})"
        )
    return name, chosen


def build(provider: str, model: str, **opts) -> Callable[[str], str]:
    """Build the completion callable for a provider."""
    factory = registry.get_provider(provider)
    return factory(model, opts)


def missing_credentials(provider: str) -> list[str]:
    info = PROVIDERS.get(provider)
    if info is None:
        return []
    return [var for var in info.env if not os.environ.get(var)]
