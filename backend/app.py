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
    mantendo apenas letras, espaços e hífens.
    Remove múltiplos espaços.
    (Para COMPARAÇÃO.)
    """
    if not isinstance(nome, str):
        return ""
    nome_limpo = unicodedata.normalize('NFKD', nome.upper()).encode('ASCII','ignore').decode('utf-8')
    nome_limpo = re.sub(r'[^A-Z\s-]', '', nome_limpo)
    nome_limpo = re.sub(r'\s+', ' ', nome_limpo).strip()
    return nome_limpo

def eh_linha_lixo(linha):
    """
    Retorna True se a linha contiver palavras-chave que indicam
    que não faz parte do nome do cliente (ex.: 'javascript:', etc.),
    ou se for muito curta, só dígitos/hífens, etc.
    Ajuste conforme a necessidade.
    """
    linha_lower = linha.lower()
    junk_keywords = [
        "javascript:", "autoatendimento", "template", "hc03.bb?",
        "tokensessao", "painel de boletos", "banco do brasil", 
        "beneficiário", "agência", "data do movimento", "totais", 
        "registrado", "baixado", "liquidado", "tarifas", "despesas cartorarias", 
        "desc./vendor", "nosso nro."
    ]
    if any(kw in linha_lower for kw in junk_keywords):
        return True

    # Se a linha for muito curta ou só dígitos/hífens, ignoramos
    if len(linha.strip()) < 2:
        return True
    if re.match(r'^[\d-]+$', linha.strip()):
        return True
    return False

def remover_numeros_e_caracteres_extras(texto):
    """
    Remove:
      - Qualquer sequência de dígitos
      - O padrão '* 123456' (ex.: '* 275339')
      - Datas (dd/mm/aaaa)
    E limpa espaços.
    """
    # Remove '* 123456'
    texto = re.sub(r'\*\s*\d+', '', texto)
    # Remove sequências de dígitos
    texto = re.sub(r'\d+', '', texto)
    # Remove datas dd/mm/aaaa
    texto = re.sub(r'\d{2}/\d{2}/\d{4}', '', texto)
    # Converte múltiplos espaços em 1
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def remover_numeros_inicio(linha):
    """
    Remove blocos de dígitos e hífens do início da linha.
    Ex.: "22239710000108249-5" => ""
    """
    return re.sub(r'^[\d-]+\s*', '', linha).strip()

def remover_x_inicial(texto):
    """
    Remove qualquer 'X' (ou sequência de 'X') no início do nome.
    Ex.: "XXXXFRIOS P ARANA LTDA" => "FRIOS P ARANA LTDA"
    """
    return re.sub(r'^[Xx]+\s*', '', texto).strip()

def unir_letra_com_seguinte(raw_name):
    """
    Une tokens de uma só letra com a palavra seguinte.
    Ex.: "P ARANA" => "PARANA"
         "J J L LOPES" => "JJL LOPES"
    Use com cautela pois pode afetar abreviações.
    """
    # Regex que procura um token de 1 letra seguido de espaço + um token maior
    # Ex.: "P ARANA" => "PARANA"
    pattern = re.compile(r'\b([A-Z])\s+([A-Z]+)\b')
    # Substitui repetidamente até não haver mais matches
    while True:
        new_name = pattern.sub(r'\1\2', raw_name)
        if new_name == raw_name:
            break
        raw_name = new_name
    return raw_name

def extrair_dados_pdf(pdf_file):
    """
    1) Lê o PDF inteiro e remove hífens no final de linha.
    2) Percorre linha a linha, ignorando as "linhas lixo".
    3) Acumula em 'current_name_parts' até encontrar a data (dd/mm/aaaa).
    4) Ao encontrar data, junta essas linhas em um 'raw_name',
       remove dígitos/hífens iniciais, remove sequências de dígitos e datas,
       remove 'X' iniciais, e une tokens de 1 letra com a palavra seguinte.
    5) Extrai a operação (2+ letras) após a data.
    6) Monta { nome_pad: { raw_name, op } } para cada registro.
    """
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        texto = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                texto += page_text + "\n"

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
            if eh_linha_lixo(line):
                continue

            date_match = re.search(r'\d{2}/\d{2}/\d{4}', line)
            if date_match:
                # Monta o nome a partir das partes acumuladas
                raw_name_list = []
                for part in current_name_parts:
                    clean_part = remover_numeros_inicio(part)
                    raw_name_list.append(clean_part)
                raw_name = " ".join(raw_name_list).strip()
                current_name_parts.clear()

                # Pega o prefixo antes da data
                prefixo = line[:date_match.start()].strip()
                prefixo = remover_numeros_inicio(prefixo)
                if prefixo:
                    raw_name = (raw_name + " " + prefixo).strip()

                # Remove números/datas/extras do 'raw_name'
                raw_name = remover_numeros_e_caracteres_extras(raw_name)
                # Remove 'X' iniciais
                raw_name = remover_x_inicial(raw_name)
                # Une tokens de 1 letra com a próxima palavra
                raw_name = unir_letra_com_seguinte(raw_name)

                # Captura a operação (2+ letras) após a data
                sufixo = line[date_match.end():]
                op_match = re.search(r'\b([A-Z]{2,})\b', sufixo)
                op = op_match.group(1) if op_match else ""

                if raw_name:
                    nome_pad = padronizar_nome(raw_name)
                    if nome_pad:
                        registros.append((nome_pad, raw_name, op))
            else:
                # Acumula essa linha como parte do nome
                current_name_parts.append(line)

        # Monta dicionário final => {nome_pad: {raw_name, op }}
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
    Extrai nomes do Excel em forma padronizada (para comparação).
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
        # 1) Extrai dados do PDF => { nome_pad: { raw_name, op } }
        pdf_dados = extrair_dados_pdf(pdf_file)
        pdf_nomes_pad = set(pdf_dados.keys())

        # 2) Extrai nomes do Excel (padronizados)
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

        # 3.2) Correspondência parcial => intersecção de tokens
        for nome_pdf in list(apenas_pdf):
            pdf_tokens = set(nome_pdf.split())
            for nome_xl in list(apenas_excel):
                xl_tokens = set(nome_xl.split())
                # Se houver pelo menos um token em comum, consideramos correspondência
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
    # Ajuste host/port conforme necessidade
    app.run(host='0.0.0.0', port=9000, debug=True)
