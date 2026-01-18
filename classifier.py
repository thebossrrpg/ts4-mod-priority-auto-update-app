# Classificação de prioridade e categoria temática
# A LLM entra aqui apenas para ESTIMAR valores, não decidir resultado

import math

def classify_mod(mod_data: dict) -> dict:
    # PLACEHOLDER: valores estimados pela LLM
    remocao = 2.5
    framework = 0
    essencial = 1.5

    score = remocao + framework + essencial
    rounded = math.ceil(score)

    if rounded >= 7:
        priority = 1
    elif rounded >= 5:
        priority = 2
    elif rounded >= 3:
        priority = 3
    elif rounded == 2:
        priority = 4
    else:
        priority = 0

    # Categoria temática FECHADA (placeholder)
    code = "3C"
    label = "Família & Relações Pontuais"

    return {
        "priority": priority,
        "score": score,
        "code": code,
        "label": label
    }
