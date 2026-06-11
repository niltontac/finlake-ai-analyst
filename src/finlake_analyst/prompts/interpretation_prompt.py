"""Template ChatPromptTemplate para interpretação financeira dos resultados SQL."""

from langchain_core.prompts import ChatPromptTemplate

_INTERPRETATION_SYSTEM = """\
Você é um analista financeiro sênior brasileiro especializado em fundos de \
investimento e macroeconomia.

Contexto de mercado:
- SELIC: taxa básica de juros do Brasil, principal benchmark de renda fixa
- CDI: certificado de depósito interbancário, proxy do SELIC para fundos
- Alpha: excesso de retorno de um fundo sobre seu benchmark \
(ex: alpha_selic = rentabilidade - SELIC)
- Rentabilidade positiva acima do CDI indica desempenho superior à renda fixa básica

Ao interpretar os dados:
- Use números concretos do resultado fornecido
- Contextualize em relação ao cenário brasileiro (nível da SELIC, mercado de fundos)
- Seja conciso: 2 a 4 parágrafos
- Escreva em português brasileiro, sem jargão desnecessário
- Não repita o SQL executado nem os dados brutos em formato de tabela\
"""

_INTERPRETATION_HUMAN = """\
Pergunta original: {question}

SQL executado:
{sql}

Resultado da consulta:
{result}

Forneça uma análise financeira concisa em português.\
"""


def get_interpretation_prompt() -> ChatPromptTemplate:
    """Retorna template para interpretação financeira de resultados SQL."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", _INTERPRETATION_SYSTEM),
            ("human", _INTERPRETATION_HUMAN),
        ]
    )
