from __future__ import annotations

import logging
from typing import Type

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ..config import AppConfig

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self, config: AppConfig) -> None:
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required in key.env for LLM execution.")
        logger.info("Initializing ChatOpenAI model=%s", config.llm_model)
        self._model = ChatOpenAI(
            model=config.llm_model,
            temperature=0,
            api_key=config.openai_api_key,
        )

    def invoke_structured(self, system_prompt: str, user_prompt: str, schema: Type[BaseModel]) -> BaseModel:
        logger.info("Invoking LLM with structured schema=%s", schema.__name__)
        structured = self._model.with_structured_output(schema)
        return structured.invoke(
            [
                ("system", system_prompt),
                ("human", user_prompt),
            ]
        )
