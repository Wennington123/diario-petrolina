import json
import os
import re
import smtplib
import ssl
import urllib.request
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

CIDADE_URL = "pe/petrolina"
DESTINO = "wenningtondiasx25@gmail.com"
UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "application/pdf,text/html,*/*",
}
STATE = Path(__file__).resolve().parent / "state.json"


def get(url, binario=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        dados = resp.read()
    return dados if binario else dados.decode("utf-8", "replace")


def _mes_url(ano, mes):
    return f"https://doem.org.br/{CIDADE_URL}/diarios/{ano}/{mes:02d}"


MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11,
    "dezembro": 12,
}


def edicoes_do_mes(ano, mes):
    html = get(_mes_url(ano, mes))
    edicoes = []
    for bloco in html.split('class="box-diario"')[1:]:
        link = re.search(r'<a href="([^"]*previsualizar[^"]*)"', bloco)
        data = re.search(r"data-diario[^>]*>\s*(\d{1,2}) de (\w+) de (\d{4})", bloco)
        edicao = re.search(r"Edi\w+\s+([\d.]+)", bloco)
        if not (link and data):
            continue
        mes_num = MESES.get(data.group(2).lower())
        if not mes_num:
            continue
        pdf_url = link.group(1).replace("previsualizar", "baixar")
        edicoes.append(
            {
                "data": f"{data.group(3)}-{mes_num:02d}-{int(data.group(1)):02d}",
                "edicao": edicao.group(1) if edicao else "?",
                "pdf": pdf_url,
            }
        )
    return edicoes


def novas_edicoes():
    hoje = date.today()
    edicoes = edicoes_do_mes(hoje.year, hoje.month)
    if hoje.day <= 3:
        anterior = hoje.replace(day=1) - timedelta(days=1)
        edicoes += edicoes_do_mes(anterior.year, anterior.month)
    ultimo = state()["ultimo"]
    return sorted({e["data"]: e for e in edicoes if e["data"] > ultimo}.values(), key=lambda e: e["data"])


def state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"ultimo": "2026-11-10"}


def salvar_state(ultimo):
    STATE.write_text(json.dumps({"ultimo": ultimo}))


def enviar(pdfs):
    msg = EmailMessage()
    msg["From"] = DESTINO
    msg["To"] = DESTINO
    if len(pdfs) == 1:
        msg["Subject"] = f"Diário Oficial Petrolina — Edição {pdfs[0][1]['edicao']} ({pdfs[0][1]['data']})"
    else:
        msg["Subject"] = f"Diário Oficial Petrolina — {len(pdfs)} edições novas"
    msg.set_content(
        "Diário(s) Oficial(is) de Petrolina anexado(s).\n"
        "Fonte: https://doem.org.br/" + CIDADE_URL + "\n"
    )
    for nome, ed in pdfs:
        msg.add_attachment(
            ed["bytes"],
            maintype="application",
            subtype="pdf",
            filename=f"diario-petrolina-{ed['data']}.pdf",
        )
    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls(context=ctx)
        smtp.login(DESTINO, os.environ["GMAIL_APP_PASSWORD"])
        smtp.send_message(msg)


def main():
    pendentes = novas_edicoes()
    print(f"edições novas: {len(pendentes)}")
    if not pendentes:
        return
    for ed in pendentes:
        ed["bytes"] = get(ed["pdf"], binario=True)
        print(f"  baixada: edição {ed['edicao']} de {ed['data']} ({len(ed['bytes'])} bytes)")
    if not os.environ.get("GMAIL_APP_PASSWORD"):
        print("dry-run: GMAIL_APP_PASSWORD ausente, e-mail não enviado")
        return
    enviar([(ed["data"], ed) for ed in pendentes])
    salvar_state(pendentes[-1]["data"])
    print("e-mail enviado")


if __name__ == "__main__":
    main()
