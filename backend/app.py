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
    Converte o nome para maiúsculas, remove acentos,
    mantém apenas letras, espaços e hífens.
    Remove múltiplos espaços.
    """
    if not isinstance(nome, str):
        return ""
    nome_limpo = unicodedata.normalize('NFKD', nome.upper()).encode('ASCII','ignore').decode('utf-8')
    nome_limpo = re.sub(r'[^A-Z\s-]', '', nome_limpo)
    nome_limpo = re.sub(r'\s+', ' ', nome_limpo).strip()
    return nome_limpo

def remover_numeros_inicio(linha):
    """
    Remove qualquer bloco de dígitos e hífens do início da linha.
    Ex: "22239710000108249-5" ou "333-4" etc.
    """
    return re.sub(r'^[\d-]+\s*', '', linha).strip()

def extrair_dados_pdf(pdf_file):
    """
    1) Lê o PDF inteiro e remove hífens no final de linha.
    2) Percorre linha a linha, acumulando tudo em 'current_name_parts' até encontrar uma data (dd/mm/aaaa).
    3) Quando encontra a data, considera que o 'current_name_parts' + o trecho antes da data é o nome completo.
    4) Remove blocos de números/hífens do início de cada linha que compõe o nome.
    5) Extrai a operação (2+ letras) após a data.
    6) Armazena { nome_pad: { "raw_name": <string>, "op": <string> } }
    """
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        texto = ""
        for page in pdf_reader.pages:
            ptext = page.extract_text()
            if ptext:
                texto += ptext + "\n"

        # Remove hífen no final de linha
        texto = re.sub(r'-\s*\n\s*', '', texto)
        # Normaliza quebras de linha
        texto = re.sub(r'\n+', '\n', texto)

        lines = texto.split('\n')
        registros = []
        current_name_parts = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Ignora linhas que sejam "Nosso nro." ou contenham "javascript:"
            if line.lower().startswith("nosso nro.") or "javascript:" in line.lower():
                continue

            # Se a linha contiver a data, processamos o que estava acumulado como nome
            date_match = re.search(r'\d{2}/\d{2}/\d{4}', line)
            if date_match:
                # Monta o nome a partir de tudo que estava acumulado
                # removendo números/hífens iniciais de cada linha
                raw_name = []
                for part in current_name_parts:
                    clean_part = remover_numeros_inicio(part)
                    raw_name.append(clean_part)
                raw_name = " ".join(raw_name).strip()

                # Zera para a próxima
                current_name_parts.clear()

                # Agora pega o prefixo da linha até a data
                prefixo = line[:date_match.start()].strip()
                prefixo = remover_numeros_inicio(prefixo)
                if prefixo:
                    raw_name = (raw_name + " " + prefixo).strip()

                # Captura a operação (2+ letras) após a data
                sufixo = line[date_match.end():]
                op_match = re.search(r'\b([A-Z]{2,})\b', sufixo)
                op = op_match.group(1) if op_match else ""

                if raw_name:
                    nome_pad = padronizar_nome(raw_name)
                    if nome_pad:
                        registros.append((nome_pad, raw_name, op))
            else:
                # Linha sem data => faz parte do nome
                current_name_parts.append(line)

        # Converte para dict => {nome_pad: {raw_name, op}}
        dados = {}
        for (nome_pad, raw, op) in registros:
            dados[nome_pad] = {
                "raw_name": raw,
                "op": op
            }
        return dados

    except Exception as e:
        print("Erro ao extrair dados do PDF:", e)
        return {}

def extrair_nomes_excel(excel_file):
    """
    Extrai nomes do Excel em forma padronizada.
    """
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

@app.route('/compare', methods=['POST'])
def compare_files():
    if 'pdf' not in request.files or 'excel' not in request.files:
        return jsonify({"error": "Envie um arquivo PDF e um arquivo Excel."}), 400

    pdf_file = request.files['pdf']
    excel_file = request.files['excel']

    try:
        # 1) Extrai dados do PDF => { nome_pad: {raw_name, op} }
        pdf_dados = extrair_dados_pdf(pdf_file)
        pdf_nomes_pad = set(pdf_dados.keys())

        # 2) Extrai nomes do Excel
        excel_nomes_pad = extrair_nomes_excel(excel_file)

        # 3) Prepara estruturas de resultado
        apenas_pdf = set(pdf_nomes_pad)
        apenas_excel = set(excel_nomes_pad)
        correspondentes = {}

        # 3.1) Correspondência exata
        for nome_pdf in list(pdf_nomes_pad):
            if nome_pdf in excel_nomes_pad:
                correspondentes[nome_pdf] = pdf_dados[nome_pdf]
                apenas_pdf.discard(nome_pdf)
                apenas_excel.discard(nome_pdf)

        # 3.2) Correspondência parcial (se houver qualquer token em comum)
        # Ex.: PDF => "REINALDO DA SILVA AMARAL" => tokens ["REINALDO","DA","SILVA","AMARAL"]
        #       Excel => "REINALDO AMARAL" => tokens ["REINALDO","AMARAL"]
        # Se intersecção desses tokens > 0 => consideramos correspondência
        for nome_pdf in list(apenas_pdf):
            pdf_tokens = set(nome_pdf.split())
            for nome_xl in list(apenas_excel):
                xl_tokens = set(nome_xl.split())
                # Se tiver intersecção
                if pdf_tokens & xl_tokens:
                    correspondentes[nome_pdf] = pdf_dados[nome_pdf]
                    apenas_pdf.discard(nome_pdf)
                    apenas_excel.discard(nome_xl)
                    break

        # 4) Monta JSON de resposta
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
