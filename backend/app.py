from flask import Flask, request, jsonify
from flask_cors import CORS
import PyPDF2
import pandas as pd
import re
import unicodedata

app = Flask(__name__)
CORS(app)

def padronizar_nome(nome):
    """Normaliza o nome removendo acentos, espaços extras, caracteres especiais e 'X' indesejados."""
    if not isinstance(nome, str):
        return ""

    nome = nome.upper().strip()  # Converte para maiúsculas e remove espaços extras
    nome = unicodedata.normalize('NFKD', nome).encode('ASCII', 'ignore').decode('utf-8')  # Remove acentos
    nome = re.sub(r'[^A-Z\s]', '', nome)  # Remove qualquer caractere que não seja letra ou espaço
    nome = re.sub(r'\s+', ' ', nome)  # Substitui múltiplos espaços por um único espaço
    
    # 🔹 Remove um "X" inicial caso exista
    nome = re.sub(r'^X+', '', nome).strip()

    return nome

def extrair_nomes_pdf(pdf_file):
    """Extrai nomes do PDF, padronizando e corrigindo quebras de linha."""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        texto = ""
        for page in pdf_reader.pages:
            texto += page.extract_text() + " "

        # 🔹 Substitui quebras de linha por espaços dentro do nome
        texto = re.sub(r'(?<=\w)-\s', '', texto)  # Remove hífens no final de linha
        texto = re.sub(r'\s+', ' ', texto)  # Garante que múltiplos espaços sejam apenas um

        print("\n📄 Texto extraído do PDF (primeiros 500 caracteres):\n", texto[:500])

        nomes = re.findall(r'([A-ZÀ-Ú][A-ZÀ-Ú\s]+)', texto)
        nomes = {padronizar_nome(nome) for nome in nomes if len(nome) > 2}

        print(f"🔍 {len(nomes)} nomes extraídos do PDF: {list(nomes)[:10]}...")
        return nomes
    except Exception as e:
        print("🚨 Erro ao extrair nomes do PDF:", e)
        return set()

def extrair_nomes_excel(excel_file):
    """Extrai e padroniza nomes do Excel."""
    try:
        df = pd.read_excel(excel_file, dtype=str)
        print("\n📊 Colunas do Excel:", df.columns.tolist())

        possiveis_colunas = df.columns.tolist()
        nomes = set()

        for coluna in possiveis_colunas:
            if coluna in df.columns:
                nomes.update(df[coluna].dropna().astype(str).apply(lambda x: padronizar_nome(x.strip())))

        print(f"🔍 {len(nomes)} nomes extraídos do Excel: {list(nomes)[:10]}...")
        return nomes
    except Exception as e:
        print("🚨 Erro ao extrair nomes do Excel:", e)
        return set()

def verificar_correspondencia_parcial(nome_pdf, nomes_excel):
    """Verifica se ao menos o primeiro nome do PDF está presente em algum nome do Excel."""
    primeiro_nome_pdf = nome_pdf.split()[0]  # Pega apenas o primeiro nome

    for nome_excel in nomes_excel:
        if primeiro_nome_pdf in nome_excel:  # Verifica se o primeiro nome está contido no Excel
            return True

    return False

@app.route('/compare', methods=['POST'])
def compare_files():
    if 'pdf' not in request.files or 'excel' not in request.files:
        return jsonify({"error": "Envie um arquivo PDF e um arquivo Excel."}), 400

    pdf_file = request.files['pdf']
    excel_file = request.files['excel']

    print("\n📂 Recebido PDF:", pdf_file.filename)
    print("📂 Recebido Excel:", excel_file.filename)

    try:
        nomes_pdf = extrair_nomes_pdf(pdf_file)
        nomes_excel = extrair_nomes_excel(excel_file)

        print(f"\n📄 Nomes extraídos do PDF: {len(nomes_pdf)}")
        print(f"📊 Nomes extraídos do Excel: {len(nomes_excel)}")

        nomes_em_ambos = sorted(nomes_pdf & nomes_excel)
        nomes_apenas_excel = sorted(nomes_excel - nomes_pdf)
        nomes_apenas_pdf = sorted(nomes_pdf - nomes_excel)

        # 🔹 Adiciona correspondência por primeiro nome se ainda não for encontrado
        for nome in nomes_apenas_pdf.copy():
            if verificar_correspondencia_parcial(nome, nomes_excel):
                nomes_em_ambos.append(nome)
                nomes_apenas_pdf.remove(nome)

        print(f"✅ Correspondências: {len(nomes_em_ambos)}")
        print(f"❌ Apenas no Excel: {len(nomes_apenas_excel)}")
        print(f"❌ Apenas no PDF: {len(nomes_apenas_pdf)}")

        return jsonify({
            "nomes_em_ambos": sorted(nomes_em_ambos),
            "nomes_apenas_excel": sorted(nomes_apenas_excel),
            "nomes_apenas_pdf": sorted(nomes_apenas_pdf)
        })
    except Exception as e:
        print("🚨 Erro inesperado:", e)
        return jsonify({"error": "Erro interno no servidor."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000, debug=True)
