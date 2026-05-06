"""
Módulo de conversão de PDF para Markdown usando Docling
Projeto SIAGOV
"""

import os
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import logging

try:
    from docling.document_converter import DocumentConverter, FormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    # Importações específicas para satisfazer a validação do Pydantic
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
except ImportError:
    print("Erro: Docling não está instalado. Execute: pip install docling")
    raise


class PDFToMarkdownConverter:
    """Conversor de PDF para Markdown usando Docling"""
    
    def __init__(self, output_dir: str = "output", log_dir: str = "logs"):
        
        self.ocr_model_path = Path("/tmp/rapidocr_models")
        self.ocr_model_path.mkdir(parents=True, exist_ok=True)

        self.output_dir = Path(output_dir)
        self.log_dir = Path(log_dir)
        
        # Criar diretórios se não existirem
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configurar logging
        self._setup_logging()
        
        # 1. Configurar as opções do pipeline
        self.pipeline_options = PdfPipelineOptions()
        self.pipeline_options.do_ocr = True 
        self.pipeline_options.do_table_structure = True 
        
        # 2. Configurar o FormatOption EXPLICITAMENTE
        # Passamos exatamente os campos que o erro diz estarem faltando:
        # 'backend' e 'pipeline_cls'
        pdf_format_option = FormatOption(
            pipeline_cls=StandardPdfPipeline,
            backend=PyPdfiumDocumentBackend,
            pipeline_options=self.pipeline_options
        )
        
        # 3. Inicializar o conversor com o mapeamento
        self.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: pdf_format_option
            }
        )
        
        self.logger.info("Conversor inicializado com sucesso (Configuração Explícita)")
    
    def _setup_logging(self):
        """Configura o sistema de logging"""
        log_file = self.log_dir / f"conversion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        self.logger = logging.getLogger(__name__)
    
    def convert_pdf_to_md(self, pdf_path: str) -> Optional[Dict[str, any]]:
        """
        Converte um arquivo PDF para Markdown
        """
        try:
            pdf_path = Path(pdf_path)
            
            if not pdf_path.exists():
                self.logger.error(f"Arquivo não encontrado: {pdf_path}")
                return None
            
            self.logger.info(f"Iniciando conversão de: {pdf_path.name}")
            
            # Converter usando Docling
            result = self.converter.convert(str(pdf_path))
            
            # Extrair markdown
            markdown_content = result.document.export_to_markdown()
            
            # Gerar nome do arquivo de saída
            output_filename = pdf_path.stem + '.md'
            output_path = self.output_dir / output_filename
            
            # Salvar arquivo markdown
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            self.logger.info(f"Conversão concluída: {output_path}")
            
            # Retornar informações da conversão
            return {
                'pdf_path': str(pdf_path),
                'md_path': str(output_path),
                'md_content': markdown_content,
                'num_pages': len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                'timestamp': datetime.now().isoformat(),
                'success': True
            }
            
        except Exception as e:
            self.logger.error(f"Erro na conversão: {str(e)}", exc_info=True)
            return {
                'pdf_path': str(pdf_path),
                'filename': Path(pdf_path).name,
                'success': False,
                'error': str(e)
            }

    def convert_batch(self, pdf_dir: str) -> list:
        pdf_dir = Path(pdf_dir)
        pdf_files = list(pdf_dir.glob('*.pdf'))
        results = []
        for pdf_file in pdf_files:
            result = self.convert_pdf_to_md(pdf_file)
            if result:
                results.append(result)
        return results