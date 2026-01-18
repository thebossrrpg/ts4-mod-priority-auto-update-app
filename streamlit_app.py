# TS4 Mod Auto-Classifier
# Criado por Akin (@UnpaidSimmer), com Lovable.

import streamlit as st
from extractor import extract_mod_data
from classifier import classify_mod
from notion_sync import upsert_mod

st.set_page_config(page_title="TS4 Mod Auto-Classifier")

st.title("TS4 Mod Auto-Classifier")

url = st.text_input("Cole a URL do mod")

if st.button("Analisar") and url:
    mod_data = extract_mod_data(url)
    result = classify_mod(mod_data)

    st.success(f"{result['code']} - {result['label']}")

    if st.button("Salvar / Atualizar no Notion"):
        upsert_mod(mod_data, result)
        st.info("Registro atualizado no Notion.")

st.markdown("""
Criado por Akin (@UnpaidSimmer), com Lovable.
""")
