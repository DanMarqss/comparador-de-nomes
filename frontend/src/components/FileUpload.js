import React, { useState } from 'react';
import axios from 'axios';

const FileUpload = () => {
  const [pdfFile, setPdfFile] = useState(null);
  const [excelFile, setExcelFile] = useState(null);
  const [nomesEmAmbos, setNomesEmAmbos] = useState([]);
  const [nomesApenasExcel, setNomesApenasExcel] = useState([]);
  const [nomesApenasPdf, setNomesApenasPdf] = useState([]);
  const [error, setError] = useState(null);

  const handleFileChange = (event, setFile) => {
    setFile(event.target.files[0]);
  };

  const handleSubmit = async () => {
    if (!pdfFile || !excelFile) {
      setError('Por favor, selecione ambos os arquivos antes de continuar.');
      return;
    }

    const formData = new FormData();
    formData.append('pdf', pdfFile);
    formData.append('excel', excelFile);

    try {
      const response = await axios.post('http://179.191.232.25:7000/compare', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      setNomesEmAmbos(response.data.nomes_em_ambos);
      setNomesApenasExcel(response.data.nomes_apenas_excel);
      setNomesApenasPdf(response.data.nomes_apenas_pdf);
      setError(null);
    } catch (error) {
      setError('Erro ao conectar com o servidor ou processar os arquivos.');
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center">
      <div className="bg-white p-6 rounded shadow-md w-1/2">
        <h1 className="text-2xl font-bold mb-4">Comparação de Nomes</h1>

        <input type="file" accept="application/pdf" onChange={(e) => handleFileChange(e, setPdfFile)} />
        <input type="file" accept=".xlsx, .xls" onChange={(e) => handleFileChange(e, setExcelFile)} />

        <button className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-700" onClick={handleSubmit}>
          Comparar
        </button>

        {error && <div className="mt-4 text-red-500"><p>{error}</p></div>}

        <h2 className="text-xl font-semibold mt-4">Nomes Correspondentes:</h2>
        <ul>{nomesEmAmbos.map((nome, i) => <li key={i}>{nome}</li>)}</ul>

        <h2 className="text-xl font-semibold mt-4">Apenas no Excel:</h2>
        <ul>{nomesApenasExcel.map((nome, i) => <li key={i}>{nome}</li>)}</ul>

        <h2 className="text-xl font-semibold mt-4">Apenas no PDF:</h2>
        <ul>{nomesApenasPdf.map((nome, i) => <li key={i}>{nome}</li>)}</ul>
      </div>
    </div>
  );
};

export default FileUpload;