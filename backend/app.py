from flask import Flask, request, jsonify
from flask_cors import CORS
import PyPDF2
import pandas as pd
import re
import unicodedata

app = Flask(__name__)
CORS(app)

def padronizar_nome(nome):
    """Normaliza o nome removendo acentos, espaços extras e caracteres especiais."""
    if not isinstance(nome, str):
        return ""

    nome = nome.upper().strip()
    nome = unicodedata.normalize('NFKD', nome).encode('ASCII', 'ignore').decode('utf-8')
    nome = re.sub(r'[^A-Z\s]', '', nome)
    nome = re.sub(r'\s+', ' ', nome).strip()
    return nome

def extrair_dados_pdf(pdf_file):
    """Extrai nomes e colunas do PDF."""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        texto = " ".join(page.extract_text() for page in pdf_reader.pages if page.extract_text())

        # Corrigir palavras quebradas
        texto = re.sub(r'(?<=\w)-\s', '', texto)
        texto = re.sub(r'\s+', ' ', texto).strip()

        # Expressão para capturar nome e a coluna "Op."
        matches = re.findall(r'(\d{14,}[-X]?)\s+([A-ZÀ-Ú\s]+?)\s+\d{2}/\d{2}/\d{4}.*?\s+([A-Z]{2,})\s+', texto)

        dados_pdf = {}
        for _, nome, op in matches:
            nome_padronizado = padronizar_nome(nome)
            if nome_padronizado:
                dados_pdf[nome_padronizado] = op

        return dados_pdf
    except Exception as e:
        print("🚨 Erro ao extrair nomes do PDF:", e)
        return {}

def extrair_nomes_excel(excel_file):
    """Extrai nomes do Excel."""
    try:
        df = pd.read_excel(excel_file, dtype=str)
        nomes = set()
        for coluna in df.columns:
            nomes.update(df[coluna].dropna().astype(str).apply(padronizar_nome))
        return nomes
    except Exception as e:
        print("🚨 Erro ao extrair nomes do Excel:", e)
        return set()

def verificar_correspondencia(nome_pdf, nomes_excel):
    """Verifica se ao menos o primeiro e o segundo nome do PDF estão no Excel."""
    partes_pdf = nome_pdf.split()
    if len(partes_pdf) < 2:
        return False

    for nome_excel in nomes_excel:
        partes_excel = nome_excel.split()
        if len(partes_excel) < 2:
            continue

        if partes_pdf[0] == partes_excel[0] and partes_pdf[1] == partes_excel[1]:
            return True

    return False

@app.route('/compare', methods=['POST'])
def compare_files():
    if 'pdf' not in request.files or 'excel' not in request.files:
        return jsonify({"error": "Envie um arquivo PDF e um arquivo Excel."}), 400

    pdf_file = request.files['pdf']
    excel_file = request.files['excel']

    try:
        dados_pdf = extrair_dados_pdf(pdf_file)
        nomes_excel = extrair_nomes_excel(excel_file)

        nomes_pdf = set(dados_pdf.keys())

        nomes_em_ambos = []
        nomes_apenas_excel = []
        nomes_apenas_pdf = []

        for nome in nomes_pdf:
            if nome in nomes_excel or verificar_correspondencia(nome, nomes_excel):
                nomes_em_ambos.append({"nome": nome, "op": dados_pdf.get(nome, "")})
            else:
                nomes_apenas_pdf.append(nome)

        for nome in nomes_excel:
            if nome not in nomes_pdf and not verificar_correspondencia(nome, nomes_pdf):
                nomes_apenas_excel.append(nome)

        return jsonify({
            "nomes_em_ambos": nomes_em_ambos,
            "nomes_apenas_excel": sorted(nomes_apenas_excel),
            "nomes_apenas_pdf": sorted(nomes_apenas_pdf)
        })
    except Exception as e:
        print("🚨 Erro inesperado:", e)
        return jsonify({"error": "Erro interno no servidor."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000, debug=True)
