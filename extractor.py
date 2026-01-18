# Leitura e extração básica de dados do mod

import requests
from bs4 import BeautifulSoup

def extract_mod_data(url: str) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    response = requests.get(url, headers=headers, timeout=20)

    soup = BeautifulSoup(response.text, "html.parser")

    title = soup.find("h1")
    title = title.get_text(strip=True) if title else None

    author = None
    meta_author = soup.find("meta", attrs={"name": "author"})
    if meta_author:
        author = meta_author.get("content")

    return {
        "url": url,
        "title": title,
        "author": author,
        "html": response.text
    }
