# app.py

from flask import Flask, request, jsonify
from flask_cors import CORS
import PyPDF2
import pandas as pd
import re
import unicodedata

app = Flask(__name__)
CORS(app)

def padronizar_nome(nome):
    """
    Gera uma versão padronizada (maiúsculas, sem acentos) para COMPARAÇÃO.
    Mantém apenas letras, espaços e hifens. Remove múltiplos espaços.
    """
    if not isinstance(nome, str):
        return ""
    nome_limpo = unicodedata.normalize('NFKD', nome.upper()).encode('ASCII','ignore').decode('utf-8')
    # Mantém letras, espaços e hifens
    nome_limpo = re.sub(r'[^A-Z\s-]', '', nome_limpo)
    # Converte múltiplos espaços em um só
    nome_limpo = re.sub(r'\s+', ' ', nome_limpo).strip()
    return nome_limpo

def extrair_dados_pdf(pdf_file):
    """
    1. Lê o PDF inteiro.
    2. Remove hífens no final de linha (ex.: "MAR-\nQUES" => "MARQUES").
    3. Percorre linha a linha, acumulando texto em 'current_name' até encontrar uma linha que contenha data (dd/mm/aaaa).
    4. Quando encontra a data, considera que tudo que foi acumulado em 'current_name' é o nome completo do cliente.
    5. Extrai a operação (2+ letras) após a data, armazena (nome_pad, raw_name, op) numa lista de registros.
    6. Limpa 'current_name' e continua.
    """
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        texto = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                texto += page_text + "\n"

        # Remove hífens no final de linha
        # Ex.: "IMPORTA-\nCAO" => "IMPORTACAO"
        texto = re.sub(r'-\s*\n\s*', '', texto)

        # Normaliza quebras de linha múltiplas
        texto = re.sub(r'\n+', '\n', texto)

        lines = texto.split('\n')

        registros = []
        current_name_parts = []  # acumula pedaços de nome (linhas) até achar a data

        for line in lines:
            line = line.strip()

            # Ignora linhas vazias ou muito irrelevantes (ajuste se necessário)
            if not line:
                continue
            if line.lower().startswith("nosso nro.") or "javascript:" in line.lower():
                continue

            # Verifica se a linha contém a data no formato dd/mm/aaaa
            date_match = re.search(r'\d{2}/\d{2}/\d{4}', line)
            if date_match:
                # Se encontramos a data, então tudo que acumulamos em current_name_parts é o nome
                raw_name = " ".join(current_name_parts).strip()
                current_name_parts.clear()  # zera para a próxima

                # Pega o pedaço da linha ANTES da data (caso tenha algo)
                # e junta também ao raw_name
                prefixo = line[:date_match.start()].strip()
                if prefixo:
                    raw_name = (raw_name + " " + prefixo).strip()

                # Captura a operação (2+ letras) após a data
                sufixo = line[date_match.end():]  # trecho após a data
                op_match = re.search(r'\b([A-Z]{2,})\b', sufixo)
                op = op_match.group(1) if op_match else ""

                if raw_name:
                    # Gera nome padronizado
                    nome_pad = padronizar_nome(raw_name)
                    if nome_pad:
                        registros.append((nome_pad, raw_name, op))
            else:
                # Linha sem data => deve fazer parte do nome
                current_name_parts.append(line)

        # Caso sobrem linhas sem data no final do arquivo (provavelmente não é nome)
        # a gente ignora. Se quiser tratar, pode ajustar aqui.

        # Converte para dict => {nome_pad: { raw_name, op }}
        dados = {}
        for (nome_pad, raw, op) in registros:
            # Se houver repetição do mesmo nome_pad, substituímos pela última
            # ou poderíamos criar uma lista. Ajuste conforme necessidade.
            dados[nome_pad] = {
                "raw_name": raw,
                "op": op
            }
        return dados

    except Exception as e:
        print("Erro ao extrair dados do PDF:", e)
        return {}

def extrair_nomes_excel(excel_file):
    """Extrai nomes do Excel em forma padronizada."""
    try:
        df = pd.read_excel(excel_file, dtype=str)
        nomes = set()
        for coluna in df.columns:
            for valor in df[coluna].dropna():
                nomes.add(padronizar_nome(str(valor)))
        return nomes
    except Exception as e:
        print("Erro ao extrair nomes do Excel:", e)
        return set()

def extrair_primeira_palavra(nome_padronizado):
    """Retorna a primeira palavra (token) do nome padronizado."""
    tokens = nome_padronizado.split()
    return tokens[0] if tokens else ""

@app.route('/compare', methods=['POST'])
def compare_files():
    if 'pdf' not in request.files or 'excel' not in request.files:
        return jsonify({"error": "Envie um arquivo PDF e um arquivo Excel."}), 400

    pdf_file = request.files['pdf']
    excel_file = request.files['excel']

    try:
        # 1) Extrai dados do PDF => { nome_pad: { raw_name, op } }
        pdf_dados = extrair_dados_pdf(pdf_file)
        pdf_nomes_pad = set(pdf_dados.keys())

        # 2) Extrai nomes do Excel (padronizados)
        excel_nomes_pad = extrair_nomes_excel(excel_file)

        # 3) Monta estruturas para resultados
        apenas_pdf = set(pdf_nomes_pad)
        apenas_excel = set(excel_nomes_pad)
        correspondentes = {}  # {nome_pad: { raw_name, op}}

        # 3.1) Correspondência exata
        for nome_pdf in list(pdf_nomes_pad):
            if nome_pdf in excel_nomes_pad:
                correspondentes[nome_pdf] = pdf_dados[nome_pdf]
                apenas_pdf.discard(nome_pdf)
                apenas_excel.discard(nome_pdf)

        # 3.2) Correspondência parcial (se a primeira palavra do PDF aparecer em algum token do Excel)
        for nome_pdf in list(apenas_pdf):
            pdf_first = extrair_primeira_palavra(nome_pdf)
            if not pdf_first:
                continue
            # Verifica se pdf_first está em algum nome do Excel
            for nome_xl in list(apenas_excel):
                xl_tokens = nome_xl.split()
                if pdf_first in xl_tokens:
                    correspondentes[nome_pdf] = pdf_dados[nome_pdf]
                    apenas_pdf.discard(nome_pdf)
                    apenas_excel.discard(nome_xl)
                    break

        # 4) Monta o JSON de resposta
        nomes_em_ambos = []
        for nome_pad in sorted(correspondentes):
            raw = correspondentes[nome_pad]['raw_name']
            op = correspondentes[nome_pad]['op']
            nomes_em_ambos.append({"nome": raw, "op": op})

        apenas_pdf_list = []
        for nome_pad in sorted(apenas_pdf):
            raw = pdf_dados[nome_pad]['raw_name']
            op = pdf_dados[nome_pad]['op']
            apenas_pdf_list.append({"nome": raw, "op": op})

        apenas_excel_list = sorted(list(apenas_excel))

        return jsonify({
            "nomes_em_ambos": nomes_em_ambos,
            "nomes_apenas_excel": apenas_excel_list,
            "nomes_apenas_pdf": apenas_pdf_list
        })

    except Exception as e:
        print("Erro inesperado:", e)
        return jsonify({"error": "Erro interno no servidor."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000, debug=True)
